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
from PySide6.QtCore import Qt, QTimer
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
# Fila para mensagens de texto (resultado parcial/final) -> consumida só na thread principal
ui_updates = queue.Queue()


def audio_callback(indata, frames, time, status):
  if status:
    print(status)
  q.put(bytes(indata))

# ===========================
# PROCESSAMENTO DE ÁUDIO
# ===========================


def process_audio():
  """Thread: consome áudio da fila e produz resultados parciais e finais.

  Estratégia de baixa latência:
  - Alimenta o recognizer com blocos menores.
  - Se não houver resultado final (AcceptWaveform False), mostra parcial.
  - Usa root.after para garantir thread-safety no Tkinter.
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
        ui_updates.put(final_text)
        last_partial = ""
    else:
      try:
        pres = json.loads(rec.PartialResult())
      except json.JSONDecodeError:
        continue
      partial = pres.get("partial", "").strip()
      now = time.time()
      if partial and partial != last_partial and (now - last_update_ts) >= PARTIAL_MIN_INTERVAL:
        ui_updates.put(partial + " …")
        last_partial = partial
        last_update_ts = now


def _drain_ui_updates(label: QLabel):
  """Consome mensagens pendentes e atualiza o rótulo (thread-safe via QTimer)."""
  try:
    processed = 0
    last_text = None
    while True:
      last_text = ui_updates.get_nowait()
      processed += 1
      if processed >= 10:
        break
  except queue.Empty:
    pass

  if last_text is not None:
    label.setText(last_text)


class MainWindow(QWidget):
  def __init__(self):
    super().__init__()
    self.setWindowTitle("Live Meeting Transcription")
    self.setMinimumSize(640, 160)
    self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

    layout = QVBoxLayout(self)
    self.label = QLabel("Ready…", self)
    self.label.setWordWrap(True)

    self.label.setStyleSheet("font-size: 16px;")
    layout.addWidget(self.label)

    # Timer para puxar atualizações com baixa latência (~25 fps)
    self.timer = QTimer(self)
    self.timer.setInterval(40)
    self.timer.timeout.connect(lambda: _drain_ui_updates(self.label))
    self.timer.start()


def main():
  app = QApplication(sys.argv)
  window = MainWindow()
  window.show()

  # Thread para processamento
  threading.Thread(target=process_audio, daemon=True).start()

  # Inicia captura de áudio e loop da aplicação Qt
  with sounddevice.RawInputStream(samplerate=SAMPLE_RATE, blocksize=BLOCKSIZE, dtype="int16",
                                  channels=1, callback=audio_callback):
    ret = app.exec()

  # Fecha stream antes de encerrar o processo
  sys.exit(ret)


if __name__ == "__main__":
  main()
