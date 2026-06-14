# Guia de Transição e Implantação de Infraestrutura: Azure para GCP Compute Engine
## Projeto: AnimeRecap Pipeline (`custodiio/anime-pipeline`)

Este documento serve como guia definitivo para migrar, configurar e implantar o pipeline do **AnimeRecap** da infraestrutura antiga da Azure para a plataforma do **Google Cloud Platform (GCP)** em uma instância VM do **Compute Engine**.

---

## 1. Visão Geral da Arquitetura do Projeto

O ecossistema do AnimeRecap é composto por três partes principais que rodam na VPS:

1. **Bot do Telegram + Webhook Server (Python)**: Um único processo unificado (`main.py`) que gerencia a comunicação via Telegram, escuta os webhooks do Kaggle e gerencia o estado da fila.
2. **VideoRender Frontend (React + TS + Vite)**: A interface visual do editor de marcações e legendas. Ele é compilado em arquivos estáticos (`dist/`) e servido diretamente pelo próprio servidor HTTP do Webhook em Python na porta padrão `8080` (configurada via `WEBHOOK_PORT`).
3. **Banco de Dados (PostgreSQL)**: Armazena o estado granular de execução de cada projeto, presets e overlays persistentes.

---

## 2. Preparativos no Console do GCP

Antes de iniciar a configuração interna no terminal, é necessário provisionar os recursos de rede e computação no painel web do GCP.

### A. Rede VPC e Firewall
1. Acesse o painel **Rede VPC** -> **Firewall**.
2. Crie uma regra de entrada (**Ingress**) para permitir conexões HTTP (porta 80) e HTTPS (porta 443) públicas.
3. Se for necessário acesso direto de desenvolvimento para testes da API, você pode abrir temporariamente a porta `8080`, mas a recomendação de produção é passar todo o tráfego externo pelas portas 80/443 do **Nginx**.
4. Associe essas regras à tag de rede da VM (ex: `anime-pipeline-server`).

### B. Instância de VM (Compute Engine)
1. Vá para **Compute Engine** -> **Instâncias de VM** e clique em **Criar Instância**.
2. **Especificações Recomendadas**:
   - Sistema Operacional: Ubuntu Server (22.04 LTS ou superior).
   - Tipo de Máquina: `e2-medium` (2 vCPUs, 4 GB de memória) ou superior, pois a VPS precisará lidar com concorrência de webhooks, download temporário de vídeos e compilação do frontend React.
3. Na seção de **Firewalls**, certifique-se de marcar:
   - [x] Permitir tráfego HTTP.
   - [x] Permitir tráfego HTTPS.
4. Em **Configurações Avançadas** -> **Rede**, adicione a tag de rede correspondente criada anteriormente (ex: `anime-pipeline-server`).
5. Configure um **IP Externo Estático** (IP reservado) para a sua VM. Isso evita que o IP público mude toda vez que a instância for reiniciada, o que quebraria a comunicação do Bot do Telegram e dos Notebooks do Kaggle.

---

## 3. Provisionamento e Migração do Banco de Dados (PostgreSQL)

O projeto depende do PostgreSQL para rastreamento granular do pipeline. Você tem duas abordagens principais na GCP:

### Opção A: Cloud SQL para PostgreSQL (Recomendado para Produção)
Uma instância gerenciada pelo GCP que cuida de backups, escalabilidade e atualizações de forma nativa.
1. Crie uma instância no **Cloud SQL** -> **PostgreSQL**.
2. Configure o usuário administrador (ex: `pipelineadmin`) e uma senha forte.
3. Libere o IP externo da sua VM do Compute Engine nas conexões autorizadas do Cloud SQL.
4. Obtenha a string de conexão para salvar no `.env`.

### Opção B: Instalar PostgreSQL Localmente na VM (Econômico)
Se desejar reduzir custos rodando o banco diretamente na mesma VM da aplicação:
1. Conectado na VM via SSH, instale o banco:
   ```bash
   sudo apt update
   sudo apt install -y postgresql postgresql-contrib
   ```
2. Acesse o terminal do PostgreSQL e crie o usuário e a base de dados:
   ```bash
   sudo -i -u postgres psql
   ```
   Dentro do shell do PostgreSQL (`psql`):
   ```sql
   CREATE DATABASE anime_pipeline_db;
   CREATE USER pipelineadmin WITH PASSWORD 'UmaSenhaMuitoForteEConfiguradaNoEnv';
   GRANT ALL PRIVILEGES ON DATABASE anime_pipeline_db TO pipelineadmin;
   -- Se for PostgreSQL 15+, dê permissão no schema public também:
   \c anime_pipeline_db
   GRANT ALL ON SCHEMA public TO pipelineadmin;
   \q
   ```

### Migração de Dados (Azure -> GCP)
Caso queira migrar o histórico de projetos, overlays e presets da Azure para o novo banco GCP:
1. Faça o backup dos dados na VPS antiga (Azure):
   ```bash
   pg_dump "postgresql://pipelineadmin:SenhaAntiga@HostAzure:5432/postgres?sslmode=require" -F c -b -v -f backup_pipeline.dump
   ```
2. Transfira o arquivo `backup_pipeline.dump` para a nova VM GCP.
3. Restaure o backup no novo banco GCP:
   ```bash
   # Se for banco local na VM GCP:
   pg_restore -U pipelineadmin -d anime_pipeline_db -v backup_pipeline.dump
   
   # Se for Cloud SQL na GCP:
   pg_restore -h IP_DO_CLOUD_SQL -U pipelineadmin -d postgres -v backup_pipeline.dump
   ```

---

## 4. Preparação do Ambiente no Terminal da VM (GCP)

Conectado via SSH na nova VM, execute os seguintes passos de configuração do sistema:

### A. Instalar Dependências de Sistema
```bash
sudo apt update && sudo apt upgrade -y
# Instala ferramentas essenciais: Git, Python 3, Venv, FFmpeg, Nginx e Certbot
sudo apt install -y git python3-pip python3-venv ffmpeg nginx certbot python3-certbot-nginx
```

### B. Instalar Node.js e NPM (Necessários para compilar o Frontend)
Instale a versão estável mais recente do Node.js (v20+):
```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

---

## 5. Clonagem e Organização do Diretório

Adote o padrão estabelecido de armazenar todos os robôs e projetos dentro do diretório `/home/<seu-usuario-linux>/apps/`.

```bash
# Crie e acesse a pasta de aplicações
mkdir -p ~/apps
cd ~/apps

# Clone o repositório utilizando a grafia exata
git clone https://github.com/custodiio/anime-pipeline.git AnimeRecap
cd AnimeRecap

# Crie a pasta onde serão armazenados temporariamente os vídeos enviados
mkdir -p uploads
```

---

## 6. Configuração das Variáveis de Ambiente (`.env`)

O arquivo `.env` contém credenciais e chaves confidenciais. **Ele nunca deve ser versionado no Git**. 

> [!IMPORTANT]
> **Segurança de Credenciais**: Nunca insira chaves de API, segredos do drive ou senhas de banco diretamente no código. Sempre referencie-as no `.env` e garanta que o arquivo `.gitignore` impeça o envio acidental desse arquivo ao repositório.

Crie o arquivo na raiz do projeto:
```bash
nano .env
```

Preencha com o seguinte template atualizado para a GCP:
```ini
# ─── Telegram ───
TELEGRAM_BOT_TOKEN=Seu_Token_Do_Telegram_Bot
AUTHORIZED_TELEGRAM_USERS=Seu_ID_Do_Telegram
SESSION_SECRET=Sua_Chave_De_Sessao_Aleatoria_E_Forte

# ─── Google Drive OAuth ───
DRIVE_REFRESH_TOKEN=Seu_Refresh_Token_Do_Drive
DRIVE_CLIENT_ID=Seu_Client_Id_Da_API_Do_Drive
DRIVE_CLIENT_SECRET=Seu_Client_Secret_Da_API_Do_Drive

# ─── PostgreSQL GCP (Cloud SQL ou Local VM) ───
# Exemplo Local VM: postgresql://pipelineadmin:SenhaForte@localhost:5432/anime_pipeline_db
# Exemplo Cloud SQL: postgresql://pipelineadmin:SenhaForte@IP_CLOUD_SQL:5432/anime_pipeline_db
DATABASE_URL=Sua_String_De_Conexao_PostgreSQL_GCP

# ─── Webhook (URL pública configurada no Nginx) ───
PIPELINE_WEBHOOK_URL=https://seu-dominio.com
VIDEORENDER_URL=https://seu-dominio.com
FRONTEND_URL=https://seu-dominio.com

# Porta interna do servidor Webhook Python (padrão: 8080)
WEBHOOK_PORT=8080

# ─── Kaggle Contas ───
KAGGLE_USERNAME_1=usuario_1
KAGGLE_KEY_1=chave_1
# (Adicione as demais contas se necessário: KAGGLE_USERNAME_2, KAGGLE_KEY_2...)

# ─── GitHub Actions ───
GITHUB_TOKEN=Seu_Github_Personal_Access_Token
GITHUB_REPO=custodiio/anime-pipeline

# ─── APIs de Inteligência Artificial ───
GEMINI_API_KEY=Sua_Chave_Gemini
OPENAI_API_KEY=Sua_Chave_OpenAI
HF_TOKEN=Seu_Token_HuggingFace

# Outros
SEO_SERVER_URL=http://localhost:3333
```

---

## 7. Compilação e Configuração da Aplicação

### A. Criar Ambiente Virtual Python
Crie o venv e instale as dependências da aplicação para isolar o ambiente de execução Python:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### B. Compilar o Frontend React + Vite
Navegue até a subpasta do frontend, instale as dependências do Node e compile o bundle estático que será servido:
```bash
cd videorender-frontend
npm install
npm run build
cd ..
```
> [!NOTE]
> A compilação criará a pasta `videorender-frontend/dist/`. É fundamental rodar o comando `npm run build` sempre que houver modificações na interface gráfica do VideoRender.

---

## 8. Configuração do Systemd para Manter o Bot Online 24/7

Para que o bot e o servidor HTTP do webhook iniciem automaticamente no boot da máquina e se recuperem sozinhos em caso de falhas, configure a aplicação como um serviço do sistema.

1. Crie o arquivo de definição do serviço:
   ```bash
   sudo nano /etc/systemd/system/anime-recap.service
   ```

2. Adicione o seguinte conteúdo, substituindo `<seu-usuario-linux>` pelo nome do seu usuário na VM do GCP:
   ```ini
   [Unit]
   Description=Servico AnimeRecap Pipeline Bot e Webhook
   After=network.target

   [Service]
   Type=simple
   User=<seu-usuario-linux>
   WorkingDirectory=/home/<seu-usuario-linux>/apps/AnimeRecap
   ExecStart=/home/<seu-usuario-linux>/apps/AnimeRecap/.venv/bin/python main.py
   Restart=always
   RestartSec=10
   Environment=PYTHONUNBUFFERED=1

   [Install]
   WantedBy=multi-user.target
   ```

3. Carregue, habilite e inicialize o serviço:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable anime-recap.service
   sudo systemctl start anime-recap.service
   ```

4. Verifique se o serviço está rodando perfeitamente:
   ```bash
   sudo systemctl status anime-recap.service
   ```

---

## 9. Configuração do Proxy Reverso no Nginx

O Nginx receberá as conexões públicas (portas 80 e 443) e as direcionará para o webhook Python que roda localmente na porta `8080`.

1. Edite o arquivo de configuração padrão do Nginx:
   ```bash
   sudo nano /etc/nginx/sites-available/default
   ```

2. Substitua o conteúdo do bloco de servidor pelo modelo abaixo, ajustando o domínio para o seu endereço registrado:
   ```nginx
   server {
       listen 80 default_server;
       listen [::]:80 default_server;

       server_name seu-dominio.com www.seu-dominio.com;

       # Configuração para suportar uploads grandes de arquivos locais
       client_max_body_size 500M;

       location / {
           proxy_pass http://127.0.0.1:8080;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection 'upgrade';
           proxy_set_header Host $host;
           proxy_cache_bypass $http_upgrade;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

3. Teste a sintaxe do Nginx para verificar possíveis erros:
   ```bash
   sudo nginx -t
   ```

4. Reinicie o serviço do Nginx para aplicar as alterações:
   ```bash
   sudo systemctl restart nginx
   ```

---

## 10. Configuração de Segurança SSL (HTTPS) com o Certbot

O Certbot configura automaticamente a criptografia SSL e redireciona todo o tráfego HTTP para HTTPS.

1. Execute o Certbot apontando para os seus domínios configurados:
   ```bash
   sudo certbot --nginx -d seu-dominio.com -d www.seu-dominio.com
   ```
2. Siga as instruções no prompt (insira um e-mail de contato e aceite os termos de serviço).
3. O Certbot modificará o arquivo do Nginx em `/etc/nginx/sites-available/default` aplicando as chaves criptográficas SSL geradas pelo Let's Encrypt de forma automática.

---

## 11. Resumo de Comandos de Operação Diária

Aqui estão os principais comandos necessários para operar a aplicação após a migração estar concluída:

* **Verificar Status do Bot/Webhook**:
  ```bash
  sudo systemctl status anime-recap.service
  ```
* **Acompanhar os Logs da Aplicação em Tempo Real**:
  ```bash
  sudo journalctl -u anime-recap.service -f
  ```
* **Reiniciar a Aplicação**:
  ```bash
  sudo systemctl restart anime-recap.service
  ```
* **Atualizar a Aplicação com Código Novo (Git Update)**:
  ```bash
  cd ~/apps/AnimeRecap
  git pull
  
  # Se houver mudanças no Frontend React:
  cd videorender-frontend
  npm install
  npm run build
  cd ..
  
  # Reiniciar serviço para aplicar modificações Python
  sudo systemctl restart anime-recap.service
  ```
* **Reiniciar Nginx**:
  ```bash
  sudo systemctl restart nginx
  ```
