import os
from dotenv import load_dotenv
load_dotenv()
from bot.drive_manager import DriveManager

drive = DriveManager()
print('Procurando ATIVO:')
folder_id = drive._buscar_id('KAGGLE/PIPELINE/ATIVO')
print('ID ATIVO:', folder_id)

if folder_id:
    results = drive.service.files().list(
        q=f"'{folder_id}' in parents and trashed=false", 
        fields="files(id, name)"
    ).execute()
    for f in results.get('files', []):
        print(' ', f['name'], f['id'])
else:
    print('Pasta ATIVO não encontrada!')
