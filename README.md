# meet-meAI

Aplicativo simples de transcrição em tempo real (Português) usando Vosk + Tkinter.

## Requisitos
- Python 3.8 - 3.11
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
Na primeira execução o script baixa automaticamente o modelo pequeno PT-BR do Vosk
(~50MB) e coloca na pasta `model_pt`.

## Estrutura
- `main.py` – captura áudio, faz reconhecimento e mostra texto na GUI.
- `requirements.txt` – dependências mínimas.

## Trocar modelo
Se quiser usar outro modelo (maior e mais preciso):
1. Baixe em https://alphacephei.com/vosk/models
2. Extraia e renomeie a pasta para `model_pt` (substituindo a existente).

## Observações
- Este fork remove diarização de falantes para evitar necessidade de autenticação.
- Para adicionar diarização depois, pode integrar pyannote.audio com um token Hugging Face.

## Licença
Uso educacional/demonstração. Verifique licenças dos modelos Vosk.