import os
import sys
import logging
from instagrapi import Client
from instagrapi.mixins.challenge import ChallengeChoice
from dotenv import load_dotenv

# Configura logs
logging.basicConfig(level=logging.INFO)

load_dotenv()

SESSION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instagram_session.json')

def challenge_code_handler(username, choice):
    print(f'\n[DESAFIO INSTAGRAM] O Instagram enviou um código de verificação via {choice.name} para o usuário {username}.')
    code = input('Digite o código de verificação recebido: ').strip()
    return code

cl = Client()
cl.challenge_code_handler = challenge_code_handler
cl.delay_range = [1, 3]

username = os.getenv('INSTAGRAM_USERNAME') or os.getenv('INSTAGRAM_USER')
password = os.getenv('INSTAGRAM_PASSWORD') or os.getenv('INSTAGRAM_PASS')

if not username or not password:
    print('[ERRO] Usuário ou senha do Instagram não encontrados no arquivo .env')
    sys.exit(1)

session_loaded = False

if os.path.exists(SESSION_FILE):
    try:
        print(f'Tentando carregar sessão existente de: {SESSION_FILE}...')
        cl.load_settings(SESSION_FILE)
        cl.get_timeline_feed()
        print('\n[SUCESSO] Sessão existente do Instagram carregada e autenticada!')
        session_loaded = True
    except Exception as e:
        print(f'[AVISO] Sessão salva expirada ou inválida ({e}). Realizando novo login...')
        if os.path.exists(SESSION_FILE):
            try:
                os.remove(SESSION_FILE)
            except Exception:
                pass

if not session_loaded:
    print(f'Tentando novo login para o usuário: {username}...')
    try:
        cl.login(username, password)
        cl.dump_settings(SESSION_FILE)
        print('\n[SUCESSO] Login efetuado com sucesso!')
        print(f'Sessão salva em: {SESSION_FILE}')
    except Exception as e:
        print(f'\n[ERRO] Falha ao efetuar login: {e}')
        sys.exit(1)

