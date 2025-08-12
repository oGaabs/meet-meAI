import json
import os
import queue
import shutil
import sys
import threading
import time
import urllib.request
import zipfile

import sounddevice  # Áudio: sounddevice + numpy
import vosk  # STT (Speech-to-Text)
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

# ===========================
# CONFIGURAÇÕES
# ===========================
LANG_MODEL_PATH = "model_en"  # Pasta onde o modelo será baixado automaticamente
SAMPLE_RATE = 16000
# Tamanho do bloco menor => menor latência (cada bloco ~0.25s se 4000 amostras)
BLOCKSIZE = 3200  # Ajuste (opções comuns: 1600, 3200, 4000, 8000). Menor = mais CPU, mais rapidez.


def ensure_vosk_model(path: str):
  """Baixa e extrai automaticamente um modelo pequeno de EN-US do Vosk se não existir.

  Usa um modelo (cerca de ~50MB). Se quiser outro, substitua a URL.
  """
  if os.path.isdir(path) and any(os.scandir(path)):
    return

  print("[INFO] Modelo Vosk não encontrado. Baixando modelo...")
  url = "https://alphacephei.com/vosk/models/vosk-model-en-us-0.22-lgraph.zip"
  zip_name = "vosk-model-en-us-0.22-lgraph.zip"
  try:
    urllib.request.urlretrieve(url, zip_name)
    print("[INFO] Download concluído. Extraindo...")
    with zipfile.ZipFile(zip_name, 'r') as zf:
      zf.extractall('.')
    # Renomeia pasta extraída para LANG_MODEL_PATH
    extracted_dir = "vosk-model-en-us-0.22-lgraph"
    if os.path.exists(path):
      shutil.rmtree(path)
    os.rename(extracted_dir, path)
    print("[INFO] Modelo preparado em", path)
  finally:
    if os.path.exists(zip_name):
      os.remove(zip_name)


ensure_vosk_model(LANG_MODEL_PATH)

# Carrega Vosk STT depois de garantir modelo
print("Loading Vosk model... (this may take a few seconds)")
model = vosk.Model(LANG_MODEL_PATH)
rec = vosk.KaldiRecognizer(model, SAMPLE_RATE)
rec.SetWords(True)
print("Modelo Vosk carregado com sucesso!")


# ===========================
# AUDIO STREAM
# ===========================
q = queue.Queue()


class UiBus(QObject):
  """Barramento de sinais para atualizar a UI de forma thread-safe (Qt-idiomático).

  textChanged(str) é emitido pelo worker (thread de áudio) e entregue
  na thread principal via conexão enfileirada automática do Qt.
  """
  textChanged = Signal(str)


def audio_callback(indata, frames, time, status):
  if status:
    print(status)
  q.put(bytes(indata))

# ===========================
# PROCESSAMENTO DE ÁUDIO
# ===========================


def process_audio(bus: UiBus):
  """Thread: consome áudio da fila e produz resultados parciais e finais.

  Estratégia de baixa latência:
  - Alimenta o recognizer com blocos menores.
  - Se não houver resultado final (AcceptWaveform False), mostra parcial.
  - Emite sinais Qt (queued) para atualizar a UI na thread principal.
  """
  last_partial = ""
  last_update_ts = 0.0
  PARTIAL_MIN_INTERVAL = 0.08  # segundos (limite para não piscar demais)

  while True:
    data = q.get()

    if rec.AcceptWaveform(data):
      try:
        result = json.loads(rec.Result())
      except json.JSONDecodeError:
        continue
      final_text = result.get("text", "").strip()
      if final_text:
        bus.textChanged.emit(final_text)
        last_partial = ""
    else:
      try:
        pres = json.loads(rec.PartialResult())
      except json.JSONDecodeError:
        continue
      partial = pres.get("partial", "").strip()
      now = time.time()
      if partial and partial != last_partial and (now - last_update_ts) >= PARTIAL_MIN_INTERVAL:
        bus.textChanged.emit(partial + " …")
        last_partial = partial
        last_update_ts = now


class MainWindow(QWidget):
  def __init__(self, bus: UiBus):
    super().__init__()
    self.setWindowTitle("Live Meeting Transcription")
    self.setMinimumSize(640, 160)
    self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

    layout = QVBoxLayout(self)
    self.label = QLabel("Ready…", self)
    self.label.setWordWrap(True)

    self.label.setStyleSheet("font-size: 16px;")
    layout.addWidget(self.label)
    # Conecta diretamente o sinal ao slot, Qt fará queued connection entre threads
    bus.textChanged.connect(self.label.setText)


def main():
  app = QApplication(sys.argv)
  # Cria o barramento de sinais após o QApplication
  bus = UiBus()
  window = MainWindow(bus)
  window.show()

  # Thread para processamento
  threading.Thread(target=process_audio, args=(bus,), daemon=True).start()

  # Inicia captura de áudio e loop da aplicação Qt
  with sounddevice.RawInputStream(samplerate=SAMPLE_RATE, blocksize=BLOCKSIZE, dtype="int16",
                                  channels=1, callback=audio_callback):
    ret = app.exec()

  # Fecha stream antes de encerrar o processo
  sys.exit(ret)


if __name__ == "__main__":
  main()
