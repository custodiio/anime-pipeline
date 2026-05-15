import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()
from bot.drive_manager import DriveManager, DRIVE_ARQUIVO

print('Esvaziando KAGGLE/ARQUIVO no Drive...')
try:
    drive = DriveManager()
    arquivo_id = drive._buscar_id(DRIVE_ARQUIVO)
    if arquivo_id:
        arquivos = drive.service.files().list(
            q=f"'{arquivo_id}' in parents and trashed=false",
            fields='files(id, name)'
        ).execute().get('files', [])
        
        if not arquivos:
            print("  A pasta ARQUIVO ja esta vazia no Drive!")
            
        for arq in arquivos:
            try:
                drive.service.files().delete(fileId=arq['id']).execute()
                print(f"  Lixo deletado do Drive: {arq['name']}")
            except Exception as e:
                print(f"  Erro ao deletar {arq['name']}: {e}")
        print('Pasta ARQUIVO no Drive limpa!')
except Exception as e:
    print(f'Erro no Drive: {e}')
