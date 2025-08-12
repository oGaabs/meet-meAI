import datetime as dt
import json
import os
import queue
import shutil
import threading
import time
import tkinter as tk
import urllib.request
import zipfile
from tkinter import scrolledtext, ttk

import sounddevice  # Áudio: sounddevice + numpy
import vosk  # STT (Speech-to-Text):

from utils_tools import argo_translate, date_to_text, number_to_text

# ===========================
# CONFIGURAÇÕES
# ===========================
LANG_MODEL_PATH = "model_en"  # Pasta onde o modelo será baixado automaticamente3
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
  url = "https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip"
  zip_name = "vosk-model-en-us-0.22.zip"
  try:
    urllib.request.urlretrieve(url, zip_name)
    print("[INFO] Download concluído. Extraindo...")
    with zipfile.ZipFile(zip_name, 'r') as zf:
      zf.extractall('.')
    # Renomeia pasta extraída para LANG_MODEL_PATH
    extracted_dir = "vosk-model-en-us-0.22"
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
# Fila para blocos finais (histórico com timestamp)
history_updates = queue.Queue()


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
        # Timestamp: pega início da primeira palavra (se disponível)
        words = result.get("result", [])
        if words:
          start_sec = words[0].get("start", 0.0)
        else:
          start_sec = time.time()
        ts_struct = time.gmtime(start_sec)
        timestamp = time.strftime("%H:%M:%S", ts_struct)
        # Speaker placeholder (pode evoluir p/ diarização real)
        speaker = "S1"
        history_updates.put({
            "timestamp": timestamp,
            "speaker": speaker,
            "text": final_text
        })
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
  """Consome mensagens pendentes: parcial/final em tempo real e histórico."""
  # Atualizações em tempo real
  try:
    processed = 0
    while True:
      text = ui_updates.get_nowait()
      realtime_var.set(text)
      processed += 1
      if processed >= 10:
        break
  except queue.Empty:
    pass

  # Histórico final
  try:
    while True:
      item = history_updates.get_nowait()
      _append_history(item)
  except queue.Empty:
    pass

  root.after(60, _drain_ui_updates)


def _append_history(item: dict):
  """Insere linha de histórico com timestamp e cor de speaker, auto-scroll se no fim."""
  if not history_text:
    return
  at_end = False
  try:
    first, last = history_text.yview()
    # Considera 'no fim' se a barra já está perto do final
    at_end = (last > 0.97)
  except Exception:
    pass

  timestamp = item.get("timestamp", "--:--:--")
  speaker = item.get("speaker", "S1")
  text = item.get("text", "")
  line = f"[{timestamp}] {speaker}: {text}\n"
  tag = f"speaker_{speaker}"
  if tag not in history_text.tag_names():
    # Define cor automática (simples: hash do nome)
    base_colors = ["#4FC3F7", "#CE93D8", "#81C784", "#FFB74D", "#F06292", "#9575CD"]
    color = base_colors[hash(speaker) % len(base_colors)]
    history_text.tag_configure(tag, foreground=color, font=("Segoe UI", 11, "bold"))

  # Timestamp estilo neutro
  if "timestamp" not in history_text.tag_names():
    history_text.tag_configure("timestamp", foreground="#888", font=("Consolas", 10))

  # Inserção com tags: timestamp separado
  history_text.insert(tk.END, f"[{timestamp}] ", ("timestamp",))
  history_text.insert(tk.END, f"{speaker}", (tag,))
  history_text.insert(tk.END, f": {text}\n")
  if at_end:
    history_text.see(tk.END)


# ===========================
# GUI
# ===========================

# --- Import utility tools ---

root = tk.Tk()
root.title("Live Meeting Transcription")
root.geometry("1100x520")
root.configure(bg="#000000")
try:
  root.iconbitmap(default="")
except Exception:
  pass

# Estilo moderno
style = ttk.Style()
try:
  style.theme_use("clam")
except Exception:
  pass
style.configure("TFrame", background="#000000")
style.configure("TLabel", background="#000000", foreground="#FFFFFF")

main_pane = ttk.Frame(root)
main_pane.pack(fill="both", expand=True, padx=10, pady=10)

# --- Main content (left) ---
content_frame = ttk.Frame(main_pane)
content_frame.pack(side="left", fill="both", expand=True)

# HISTÓRICO (topo)
history_label = ttk.Label(content_frame, text="Histórico (final)", font=("Segoe UI", 11, "bold"))
history_label.pack(anchor="w")

history_text = scrolledtext.ScrolledText(content_frame, height=16, wrap="word", font=("Segoe UI", 11),
                                         background="#111111", foreground="#FFFFFF", insertbackground="#FFFFFF",
                                         borderwidth=0, padx=8, pady=6)
history_text.pack(fill="both", expand=True)
history_text.configure(state="normal")

# TEMPO REAL (abaixo)
realtime_frame = ttk.Frame(content_frame)
realtime_frame.pack(fill="x", pady=(12, 0))
realtime_label_title = ttk.Label(realtime_frame, text="Transcrição em tempo real", font=("Segoe UI", 11, "bold"))
realtime_label_title.pack(anchor="w")
realtime_var = tk.StringVar(value="Pronto…")
realtime_label = ttk.Label(realtime_frame, textvariable=realtime_var, font=("Segoe UI", 15), wraplength=860, justify="left")
realtime_label.pack(fill="x", pady=(4, 0))

# Dica inferior
footer = ttk.Label(content_frame, text="Ctrl+C para sair", font=("Segoe UI", 9))
footer.pack(anchor="e", pady=(6, 0))

# --- Utility tools panel (right) ---
utils_frame = ttk.Frame(main_pane)
utils_frame.pack(side="right", fill="y", padx=(16, 0))
ttk.Label(utils_frame, text="Utilitários", font=("Segoe UI", 12, "bold")).pack(pady=(0, 8))

# Number to text
ttk.Label(utils_frame, text="Número para texto:").pack(anchor="w")
num_entry = ttk.Entry(utils_frame, width=18)
num_entry.pack(anchor="w")
num_result = tk.StringVar()
ttk.Label(utils_frame, textvariable=num_result, foreground="#4FC3F7").pack(anchor="w", pady=(0, 6))


# Atualiza automaticamente o resultado ao digitar
def update_num_result(*args):
  val = num_entry.get()
  try:
    n = int(val)
    num_result.set(number_to_text(n))
  except Exception:
    num_result.set("(inválido)")


num_entry.bind('<KeyRelease>', lambda e: update_num_result())


# Date to text with dropdowns
ttk.Label(utils_frame, text="Data para texto:").pack(anchor="w")
date_frame = ttk.Frame(utils_frame)
date_frame.pack(anchor="w")
# Day dropdown
day_var = tk.StringVar(value="1")
day_menu = ttk.Combobox(date_frame, textvariable=day_var, width=3, values=[str(i) for i in range(1, 32)])
day_menu.pack(side="left")
ttk.Label(date_frame, text="/").pack(side="left")
# Month dropdown
month_var = tk.StringVar(value="1")
month_menu = ttk.Combobox(date_frame, textvariable=month_var, width=3, values=[str(i) for i in range(1, 13)])
month_menu.pack(side="left")
ttk.Label(date_frame, text="/").pack(side="left")
# Year dropdown
current_year = dt.datetime.now().year
year_var = tk.StringVar(value=str(current_year))
year_menu = ttk.Combobox(date_frame, textvariable=year_var, width=5, values=[str(y) for y in range(current_year - 50, current_year + 11)])
year_menu.pack(side="left")
date_result = tk.StringVar()
ttk.Label(utils_frame, textvariable=date_result, foreground="#81C784").pack(anchor="w", pady=(0, 6))


# Atualiza automaticamente o resultado ao mudar qualquer campo
def update_date_result(*args):
  y = year_var.get()
  m = month_var.get().zfill(2)
  d = day_var.get().zfill(2)
  date_str = f"{y}-{m}-{d}"
  date_result.set(date_to_text(date_str))


day_var.trace_add('write', update_date_result)
month_var.trace_add('write', update_date_result)
year_var.trace_add('write', update_date_result)

# Argo translator
ttk.Label(utils_frame, text="Tradutor Argo (demo):").pack(anchor="w")
argo_entry = ttk.Entry(utils_frame, width=18)
argo_entry.pack(anchor="w")
argo_result = tk.StringVar()
ttk.Label(utils_frame, textvariable=argo_result, foreground="#FFB74D").pack(anchor="w", pady=(0, 6))


def on_argo_translate():
  argo_result.set(argo_translate(argo_entry.get()))


ttk.Button(utils_frame, text="Traduzir", command=on_argo_translate).pack(anchor="w", pady=(0, 8))

# Inicia polling de atualizações de UI
root.after(80, _drain_ui_updates)

# Thread para processamento
threading.Thread(target=process_audio, daemon=True).start()

# Inicia captura
with sounddevice.RawInputStream(samplerate=SAMPLE_RATE, blocksize=BLOCKSIZE, dtype="int16",
                                channels=1, callback=audio_callback):
  root.mainloop()
