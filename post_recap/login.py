import os
import json
import requests
import urllib.parse
from dotenv import load_dotenv

# Carrega as variáveis do .env
load_dotenv()

CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY")
CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET")

if not CLIENT_KEY or not CLIENT_SECRET:
    raise ValueError("[ERRO] TIKTOK_CLIENT_KEY ou TIKTOK_CLIENT_SECRET ausentes no .env")

# O código exato que você pescou da URL
codigo_bruto = "DBQaJR7pYXDYux9ao23VZwxWGh4_zfhpeHmYLuGmQ2Genluxi3UmD877YeGJFNaYR-ihb2Q4x6HGwy8bkhIDIjKRaK-MWjESrH_Pd7pQfE5j0p4XM3xUBHUslikAAz7gpQcVttIzHUI8IOiq58HvcR07-6BoJEN6vQEdjT-LyWpEjnNJbwNiu7TYoKpPPn2UWIxoZTUxW4eDkBYz%2Av%214494.s1"
codigo_limpo = urllib.parse.unquote(codigo_bruto)

url = "https://open.tiktokapis.com/v2/oauth/token/"

headers = {
    "Content-Type": "application/x-www-form-urlencoded",
    "Cache-Control": "no-cache"
}

data = {
    "client_key": CLIENT_KEY,
    "client_secret": CLIENT_SECRET,
    "code": codigo_limpo,
    "grant_type": "authorization_code",
    "redirect_uri": os.getenv("TIKTOK_REDIRECT_URI", "https://api.postrecap.tech/api/tiktok/callback")
}

response = requests.post(url, headers=headers, data=data)

print("Status:", response.status_code)
res_json = response.json()
print("\nResposta da API:")
print(res_json)

if response.status_code == 200 and "access_token" in res_json:
    token_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "token.json")
    with open(token_file_path, "w", encoding="utf-8") as f:
        json.dump(res_json, f, indent=4, ensure_ascii=False)
    print(f"\n[OK] Token salvo com sucesso em: {token_file_path}")
else:
    print("\n[ERRO] Não foi possível obter o token de acesso. Verifique se o código é válido ou se já foi consumido.")