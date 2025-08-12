# meet-meAI

Aplicativo simples de transcrição em tempo real usando Vosk + PySide6.

## Requisitos
- Python 3.8 - 3.12
- Microfone
- Windows / Linux / macOS

## Instalação
```cmd
python -m venv .venv
\.venv\Scripts\activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

## Execução
```cmd
python main.py
```
Na primeira execução o script baixa automaticamente um modelo pequeno EN-US do Vosk
(~50MB) e coloca na pasta `model_en`.

## Estrutura
- `main.py` – captura áudio, faz reconhecimento e mostra texto na GUI (PySide6).
- `requirements.txt` – dependências mínimas.

## Trocar modelo
Se quiser usar outro modelo (maior e mais preciso):
1. Baixe em https://alphacephei.com/vosk/models
2. Extraia e renomeie a pasta para `model_en` (substituindo a existente) ou ajuste a
	constante `LANG_MODEL_PATH` em `main.py`.

## Observações
- Interface migrada para PySide6 e ajustada para ser responsiva (texto com quebra automática
	e janela redimensionável).

## Licença
Uso educacional/demonstração. Verifique licenças dos modelos Vosk.