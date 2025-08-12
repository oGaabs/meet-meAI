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
from PySide6.QtCore import QObject, Qt, QTime, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                               QScrollArea, QSplitter, QVBoxLayout, QWidget)

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
  # Novo: sinal para segmentos finais (usar apenas para log cronológico/por palestrante)
  finalSegment = Signal(str)


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
        # Emite também evento de segmento final para o log por palestrante
        bus.finalSegment.emit(final_text)
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


class SpeakerLog(QWidget):
  """Lista rolável de segmentos com timestamp e cor por palestrante.

  Por ora, sem diarização, usamos um único palestrante (Speaker 1).
  """

  def __init__(self, parent=None):
    super().__init__(parent)

    self._speaker_name = "Speaker 1"
    # Paleta simples e determinística; com 1 palestrante escolhemos uma cor agradável
    self._speaker_color = QColor("#4FC3F7")  # azul claro

    outer = QVBoxLayout(self)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    # Área de rolagem com container vertical
    self.scroll = QScrollArea(self)
    self.scroll.setWidgetResizable(True)
    self.scroll.setFrameShape(QFrame.NoFrame)

    self.container = QWidget()
    self.vbox = QVBoxLayout(self.container)
    self.vbox.setContentsMargins(8, 8, 8, 8)
    self.vbox.setSpacing(8)
    self.vbox.addStretch(1)

    self.scroll.setWidget(self.container)
    outer.addWidget(self.scroll)

    # Estilo escuro
    self.setStyleSheet(
        """
      QWidget#SpeakerRow { background: transparent; }
      QLabel#Timestamp { color: #9aa0a6; font-size: 12px; }
      QLabel#Speaker { font-weight: 600; font-size: 13px; }
      QLabel#Utterance { color: #ffffff; font-size: 13px; }
      QScrollArea { background: #000000; border: none; }
      QScrollBar:vertical { background: #111; width: 10px; }
      QScrollBar::handle:vertical { background: #333; min-height: 24px; border-radius: 5px; }
      QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
      """
    )

  def _format_time(self) -> str:
    # HH:MM:SS local
    return QTime.currentTime().toString("HH:mm:ss")

  def add_segment(self, text: str):
    if not text:
      return

    row = QWidget(self.container)
    row.setObjectName("SpeakerRow")
    h = QHBoxLayout(row)
    h.setContentsMargins(8, 8, 8, 0)
    h.setSpacing(10)

    ts = QLabel(self._format_time(), row)
    ts.setObjectName("Timestamp")

    spk = QLabel(self._speaker_name + ":", row)
    spk.setObjectName("Speaker")
    # nome do palestrante colorido
    spk.setStyleSheet(f"color: {self._speaker_color.name()};")

    utt = QLabel(text, row)
    utt.setObjectName("Utterance")
    utt.setWordWrap(True)

    h.addWidget(ts)
    h.addWidget(spk)
    h.addWidget(utt, 1)

    # Insere antes do stretch final
    self.vbox.insertWidget(self.vbox.count() - 1, row)

    # Auto-scroll para o fim
    vsb = self.scroll.verticalScrollBar()
    vsb.setValue(vsb.maximum())


class MainWindow(QWidget):
  def __init__(self, bus: UiBus):
    super().__init__()
    self.setWindowTitle("Live Meeting Transcription")
    self.setMinimumSize(720, 360)
    self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

    # Estilo escuro moderno (janela inteira)
    self.setStyleSheet(
        """
      QWidget { background-color: #000000; color: #ffffff; }
      QLabel#Current { font-size: 16px; }
      QFrame#TopPane { background: #0b0b0b; border-bottom: 1px solid #202124; }
      """
    )

    root = QVBoxLayout(self)

    splitter = QSplitter(Qt.Vertical, self)
    root.addWidget(splitter)

    # Topo: painel atual (mantém self.label intacto)
    top = QFrame(self)
    top.setObjectName("TopPane")
    top_layout = QVBoxLayout(top)
    top_layout.setContentsMargins(12, 12, 12, 12)
    top_layout.setSpacing(8)

    self.label = QLabel("Ready…", top)
    self.label.setObjectName("Current")
    self.label.setWordWrap(True)
    top_layout.addWidget(self.label)

    # Base: log por palestrante com rolagem automática
    self.speakerLog = SpeakerLog(self)

    splitter.addWidget(top)
    splitter.addWidget(self.speakerLog)
    splitter.setSizes([2, 3])  # proporção inicial

    # Conexões de sinais (não altera o comportamento da label atual)
    bus.textChanged.connect(self.label.setText)
    bus.finalSegment.connect(self.speakerLog.add_segment)


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
