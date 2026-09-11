import requests
import os
from dotenv import load_dotenv

# Carrega as variáveis do .env
load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    print("❌ Erro: GEMINI_API_KEY não encontrada no .env")
    exit(1)

URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={API_KEY}"

pergunta = """
Você é um professor de matemática do 6º ano.
Corrija esta resposta de aluno sobre frações equivalentes:

RESPOSTA DO ALUNO:
"1/2 é igual a 2/4 porque se eu dobrar o de cima e o de baixo dá a mesma coisa"

Dê uma nota de 0 a 10 e explique brevemente o que o aluno acertou e errou.
"""

payload = {
    "contents": [{"parts": [{"text": pergunta}]}]
}

print("🤖 Enviando pergunta pro Gemini...")
response = requests.post(URL, json=payload)

if response.status_code == 200:
    data = response.json()
    resposta = data["candidates"][0]["content"]["parts"][0]["text"]
    print("\n✅ RESPOSTA DO GEMINI:")
    print("-" * 50)
    print(resposta)
    print("-" * 50)
else:
    print(f"❌ Erro: {response.status_code}")
    print(response.text)