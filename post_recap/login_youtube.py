import os
from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv

load_dotenv()

# Escopos necessários para fazer upload de vídeos e definir miniaturas no YouTube
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube"
]

def main():
    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
    
    if not client_id:
        print("[ERRO] Configure o YOUTUBE_CLIENT_ID no seu arquivo .env antes de executar.")
        return
        
    if not client_secret:
        print("[ERRO] Configure o YOUTUBE_CLIENT_SECRET no seu arquivo .env antes de executar.")
        print("Obtenha o Client Secret no painel da sua conta do Google Cloud Console para o app ID especificado.")
        return

    # Monta a configuração do cliente dinamicamente a partir do .env
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost:8080/", "urn:ietf:wg:oauth:2.0:oob"]
        }
    }
    
    print("Iniciando fluxo de autenticação do YouTube...")
    print("Uma janela de navegador se abrirá para você fazer login no perfil do canal do YouTube.")
    
    try:
        flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
        # Executa o servidor local na porta 8080 para receber o callback
        creds = flow.run_local_server(port=8080, prompt="select_account")
        
        print("\n[OK] Autenticação realizada com sucesso!")
        print("\n--- COPIE E COLE ESTA LINHA NO SEU ARQUIVO .env ---")
        print(f"YOUTUBE_REFRESH_TOKEN={creds.refresh_token}")
        print("----------------------------------------------------\n")
        print("Após atualizar o seu arquivo .env, o bot poderá fazer os envios de rascunhos para o YouTube.")
    except Exception as e:
        print(f"[ERRO] Ocorreu uma falha na autenticação: {e}")

if __name__ == "__main__":
    main()
