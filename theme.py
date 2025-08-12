"""
Theme for the PySide6 app.

Notes:
- Dark UI with subtle borders and rounded surfaces.
- Cyan→purple accent gradient reminiscent of marketing sites.
- System-safe font stack (Inter if present, falls back gracefully).
"""

from __future__ import annotations


# Color tokens (feel free to tweak)
BG_0 = "#0b0c10"       # page background (near-black)
BG_1 = "#0f1115"       # surface background
BORDER = "#1f242b"     # subtle hairline border
TEXT = "#e6e7ea"       # primary text
TEXT_MUTED = "#98a2b3" # secondary text
ACCENT_1 = "#7c3aed"   # purple
ACCENT_2 = "#06b6d4"   # cyan


def build_qss() -> str:
  """Return the global QSS stylesheet string."""
  return f"""
  /* Base */
  * {{
    font-family: Inter, 'Segoe UI', Roboto, Arial, sans-serif;
  }}

  QWidget {{
    background-color: {BG_0};
    color: {TEXT};
    selection-background-color: {ACCENT_1};
  }}

  /* Headings and subtle text */
  QLabel#Current {{
    font-size: 17px;
    font-weight: 600;
  }}

  QLabel#Muted, QLabel#Timestamp {{
    color: {TEXT_MUTED};
    font-size: 12px;
  }}

  QLabel#Speaker {{
    font-weight: 700;
    font-size: 13px;
  }}

  /* Header bar */
  QFrame#HeaderBar {{
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid {BORDER};
    border-radius: 12px;
  }}

  QLabel#Brand {{
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.3px;
  }}

  QLabel#BrandPill {{
    padding: 2px 8px;
    border-radius: 999px;
    color: #ffffff;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
      stop:0 {ACCENT_2}, stop:1 {ACCENT_1});
    font-size: 11px;
    font-weight: 700;
  }}

  /* Card surfaces */
  QFrame#Card {{
    border: 1px solid {BORDER};
    border-radius: 16px;
  }}

  /* Speaker log */
  QScrollArea {{
    background: transparent;
    border: none;
  }}

  QWidget#SpeakerRow {{
  }}

  /* Separator line between speakers */
  QWidget#Separator {{
    background: {BORDER};
    margin: 2px 6px; /* pequeno respiro vertical e alinhamento com conteúdo */
  }}

  /* Tighter layout hints for rows */
  QWidget#SpeakerRow QLabel#Speaker {{
    margin-right: 4px;
  }}

  QLabel#Utterance {{
    color: {TEXT};
    font-size: 13px;
  }}

  /* Splitter */
  QSplitter::handle {{
    margin: 4px 0;
    height: 4px;
  }}
  QSplitter::handle:vertical:hover {{
    background: #1a1f27;
  }}

  /* Scrollbars */
  QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px 0 4px 0;
  }}
  QScrollBar::handle:vertical {{
    background: #2a2f36;
    min-height: 24px;
    border-radius: 5px;
  }}
  QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
  QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

  /* Links / accents */
  QLabel#LinkLike {{
    color: {ACCENT_2};
  }}
  """
