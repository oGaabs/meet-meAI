

import inflect
import datetime

import requests
from num2words import num2words


def number_to_text(n, lang='en'):
  try:
    return num2words(n, lang=lang)
  except Exception:
    return str(n)

# Date to text (English, e.g., 2025-08-12 -> August twelfth, twenty twenty-five)


p = inflect.engine()


def date_to_text(date_str):
  try:
    dt = datetime.datetime.strptime(date_str, '%Y-%m-%d')
  except Exception:
    return date_str
  months = [
      'January', 'February', 'March', 'April', 'May', 'June',
      'July', 'August', 'September', 'October', 'November', 'December'
  ]
  day = dt.day
  day_ordinals = {
      1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth",
      6: "sixth", 7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth",
      11: "eleventh", 12: "twelfth", 13: "thirteenth", 14: "fourteenth",
      15: "fifteenth", 16: "sixteenth", 17: "seventeenth", 18: "eighteenth", 19: "nineteenth",
      20: "twentieth", 21: "twenty-first", 22: "twenty-second", 23: "twenty-third",
      24: "twenty-fourth", 25: "twenty-fifth", 26: "twenty-sixth", 27: "twenty-seventh",
      28: "twenty-eighth", 29: "twenty-ninth", 30: "thirtieth", 31: "thirty-first"
  }
  day_text = day_ordinals.get(day, str(day))
  year_text = ' '.join([number_to_text(int(x)) for x in str(dt.year)])
  return f"{months[dt.month - 1]} {day_text}, {year_text}"


def argo_translate(text, source_lang='pt', target_lang='en'):
  """
  Translate text using the Argos Translate public API (https://translate.argosopentech.com/translate).
  """
  url = "https://translate.argosopentech.com/translate"
  payload = {
      "q": text,
      "source": source_lang,
      "target": target_lang
  }
  headers = {
      "Content-Type": "application/json"
  }
  try:
    res = requests.post(url, json=payload, headers=headers, timeout=10)
    res.raise_for_status()
    data = res.json()
    return data.get("translatedText", str(data))
  except Exception as e:
    return f"[Argo API error] {e}"
