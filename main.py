import json
import os
import queue
import shutil
import threading
import time
import tkinter as tk
import urllib.request
import wave
import zipfile

import numpy as np
import sounddevice as sd  # Audio
import vosk

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

  print("[INFO] Modelo Vosk não encontrado. Baixando modelo pequeno PT-BR...")
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
model = vosk.Model(LANG_MODEL_PATH)
rec = vosk.KaldiRecognizer(model, SAMPLE_RATE)

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


def _drain_ui_updates():
  """Consome mensagens pendentes da fila de UI mantendo thread principal segura."""
  try:
    processed = 0
    while True:
      text = ui_updates.get_nowait()
      label_var.set(text)
      processed += 1
      if processed >= 10:  # evita monopolizar loop se houver enxurrada
        break
  except queue.Empty:
    pass
  # agenda próxima checagem (intervalo curto para baixa latência visual)
  root.after(40, _drain_ui_updates)  # ~25fps


# ===========================
# GUI
# ===========================
root = tk.Tk()
root.title("Reunião Ao Vivo - Open Source")
root.geometry("640x160")
root.attributes("-topmost", True)  # Always on top
label_var = tk.StringVar(value="Iniciando microfone e modelo…")
label = tk.Label(root, textvariable=label_var, font=("Arial", 16), wraplength=620, justify="left")
label.pack(pady=20, padx=10)

# Inicia polling de atualizações de UI
root.after(50, _drain_ui_updates)

# Thread para processamento
threading.Thread(target=process_audio, daemon=True).start()

# Inicia captura
with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=BLOCKSIZE, dtype="int16",
                       channels=1, callback=audio_callback):
  root.mainloop()
