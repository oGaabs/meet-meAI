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

# Theme import
try:
  from theme import build_qss
except Exception:
  def build_qss() -> str:
    return ""

# ===========================
# CONFIGURAÇÕES
# ===========================
SAMPLE_RATE = 16000
# Tamanho do bloco menor => menor latência (cada bloco ~0.25s se 4000 amostras)
BLOCKSIZE = 3200  # Ajuste (opções comuns: 1600, 3200, 4000, 8000). Menor = mais CPU, mais rapidez.


def download_and_extract_model(url: str, target_dir: str, extracted_dir_name: str):
  """Baixa um zip de modelo, extrai e renomeia para target_dir."""
  if os.path.isdir(target_dir) and any(os.scandir(target_dir)):
    return

  print(f"[INFO] Modelo não encontrado. Baixando de {url} ...")
  zip_name = extracted_dir_name + ".zip"
  try:
    urllib.request.urlretrieve(url, zip_name)
    print("[INFO] Download concluído. Extraindo...")
    with zipfile.ZipFile(zip_name, 'r') as zf:
      zf.extractall('.')
    if os.path.exists(target_dir):
      shutil.rmtree(target_dir)
    os.rename(extracted_dir_name, target_dir)
    print(f"[INFO] Modelo preparado em {target_dir}")
  finally:
    if os.path.exists(zip_name):
      os.remove(zip_name)


def ensure_vosk_model(path: str):
  url = "https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip"
  extracted_dir = "vosk-model-en-us-0.22"
  download_and_extract_model(url, path, extracted_dir)


def ensure_vosk_speaker_model(path: str):
  url = "https://alphacephei.com/vosk/models/vosk-model-spk-0.4.zip"
  extracted_dir = "vosk-model-spk-0.4"
  download_and_extract_model(url, path, extracted_dir)


ensure_vosk_model("model_en")
ensure_vosk_speaker_model("model_spk")

# Carrega Vosk STT depois de garantir modelo
print("Loading Vosk model... (this may take a few seconds)")
model = vosk.Model("model_en")
rec = vosk.KaldiRecognizer(model, SAMPLE_RATE)
rec.SetWords(True)

print("Loading Vosk speaker model... (this may take a few seconds)")
speaker_model = vosk.SpkModel("model_spk")
rec.SetSpkModel(speaker_model)


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

    self._speaker_name = "S1"
    # Paleta simples e determinística; com 1 palestrante escolhemos uma cor agradável
    self._speaker_color = QColor("#4FC3F7")  # azul claro
    self._row_count = 0  # para controlar separadores entre falas

    outer = QVBoxLayout(self)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    # Área de rolagem com container vertical
    self.scroll = QScrollArea(self)
    self.scroll.setWidgetResizable(True)
    self.scroll.setFrameShape(QFrame.NoFrame)

    self.container = QWidget()
    self.vbox = QVBoxLayout(self.container)
    self.vbox.setContentsMargins(12, 12, 12, 12)
    # Menor espaçamento vertical entre falas
    self.vbox.setSpacing(0)
    self.vbox.addStretch(1)

    self.scroll.setWidget(self.container)
    outer.addWidget(self.scroll)

    # Remove old inline stylesheet; rely on global QSS

  def _format_time(self) -> str:
    # HH:MM:SS local
    return QTime.currentTime().toString("HH:mm:ss")

  def add_segment(self, text: str):
    if not text:
      return

    # Adiciona separador apenas se já houver pelo menos uma fala
    if self._row_count > 0:
      sep = QWidget(self.container)
      sep.setObjectName("Separator")
      sep.setFixedHeight(1)
      self.vbox.insertWidget(self.vbox.count() - 1, sep)

    row = QWidget(self.container)
    row.setObjectName("SpeakerRow")
    h = QHBoxLayout(row)
    # Margens internas mais compactas
    h.setContentsMargins(6, 6, 6, 6)
    h.setSpacing(6)

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

    # Insere a fala antes do stretch final
    self.vbox.insertWidget(self.vbox.count() - 1, row)
    self._row_count += 1

    # Auto-scroll para o fim
    vsb = self.scroll.verticalScrollBar()
    vsb.setValue(vsb.maximum())


class MainWindow(QWidget):
  def __init__(self, bus: UiBus):
    super().__init__()
    self.setWindowTitle("Live Meeting Transcription")
    self.setMinimumSize(800, 420)
    self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

    root = QVBoxLayout(self)
    root.setContentsMargins(12, 12, 12, 12)
    root.setSpacing(12)

    # Header bar (brand + status)
    header = QFrame(self)
    header.setObjectName("HeaderBar")
    hbox = QHBoxLayout(header)
    hbox.setContentsMargins(12, 10, 12, 10)
    hbox.setSpacing(8)

    brand = QLabel("meet-meAI", header)
    brand.setObjectName("Brand")
    pill = QLabel("BETA", header)
    pill.setObjectName("BrandPill")

    hbox.addWidget(brand)
    hbox.addWidget(pill)
    hbox.addStretch(1)

    root.addWidget(header)

    splitter = QSplitter(Qt.Vertical, self)
    root.addWidget(splitter, 1)

    # Top: current transcript card
    top = QFrame(self)
    top.setObjectName("Card")
    top_layout = QVBoxLayout(top)
    top_layout.setContentsMargins(16, 16, 16, 16)
    top_layout.setSpacing(8)

    self.label = QLabel("Ready…", top)
    self.label.setObjectName("Current")
    self.label.setWordWrap(True)

    top_layout.addWidget(self.label)

    # Bottom: speaker log card
    bottom = QFrame(self)
    bottom.setObjectName("Card")
    bottom_layout = QVBoxLayout(bottom)
    bottom_layout.setContentsMargins(8, 8, 8, 8)
    bottom_layout.setSpacing(8)

    self.speakerLog = SpeakerLog(self)
    bottom_layout.addWidget(self.speakerLog)

    splitter.addWidget(top)
    splitter.addWidget(bottom)
    splitter.setSizes([2, 3])

    bus.textChanged.connect(self.label.setText)
    bus.finalSegment.connect(self.speakerLog.add_segment)


def main():
  app = QApplication(sys.argv)
  bus = UiBus()

  # Apply theme
  try:
    app.setStyleSheet(build_qss())
  except Exception:
    pass

  window = MainWindow(bus)
  window.show()

  threading.Thread(target=process_audio, args=(bus,), daemon=True).start()

  with sounddevice.RawInputStream(samplerate=SAMPLE_RATE, blocksize=BLOCKSIZE, dtype="int16",
                                  channels=1, callback=audio_callback):
    ret = app.exec()

  sys.exit(ret)


if __name__ == "__main__":
  main()
