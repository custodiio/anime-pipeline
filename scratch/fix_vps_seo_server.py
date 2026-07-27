with open('/home/ubuntu/apps/SeoAnimeRecap/server.js', 'r', encoding='utf-8') as f:
    content = f.read()

bad_str = "// driveManager.uploadFileToPath(specFile, 'kaggle/pipeline/final', 'guia_postagem.json', 'application/json')"
good_str = "driveManager.uploadFileToPath(specFile, 'kaggle/pipeline/final', 'guia_postagem.json', 'application/json')"

if bad_str in content:
    content = content.replace(bad_str, good_str)
    with open('/home/ubuntu/apps/SeoAnimeRecap/server.js', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Corrigido server.js no VPS!")
else:
    print("String antiga não encontrada ou já corrigida.")
