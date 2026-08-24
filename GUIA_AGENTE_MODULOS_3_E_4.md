# 🤖 Guia Técnico para o Agente IA: Implementação e Deploy dos Módulos 3 e 4

> **Destinatário:** Agente IA responsável por ativar, finalizar e realizar o deploy do **Módulo 3 (Post Recap & Scheduler)** e **Módulo 4 (TikTok Approval & OAuth)** no repositório `custodiio/anime-pipeline` / Hugging Face Space `alehcrim/anime-pipeline`.

---

## 🧭 1. Contexto do Ecossistema e Estado Atual

Este repositório é um **Monorepo** que hospeda todo o pipeline de automação de Anime Recaps em uma única instância no **Hugging Face Space**.

### 🔄 Como o Módulo 3 e o Módulo 4 se encaixam:
1. **Módulo 2 (Kuma Pipeline)** finaliza o vídeo 4K dublado e com legendas e salva no Google Drive em `KAGGLE/FINAL/video_final.mp4` e atualiza a tabela `pipeline_projects` no Neon PostgreSQL.
2. **Módulo 4 (`tiktok_approval/`)**:
   - Fornece as rotas OAuth2 para conectar contas do TikTok (`/api/tiktok/login`, `/api/tiktok/callback`) e do YouTube (`/api/youtube/login`, `/api/youtube/callback`).
   - **Regra Global de Segurança**: Valida se o usuário está aprovado em `tiktok_approved_users` (`approved = 1`) antes de liberar as conexões.
   - Armazena tokens renováveis nas tabelas `tiktok_connections` e `tiktok_youtube_connections`.
3. **Módulo 3 (`post_recap/`)**:
   - Executa um Bot no Telegram (`POSTRECAP_TELEGRAM_BOT_TOKEN`) e um Worker de publicação agendada.
   - Lê os vídeos finalizados do Drive, consome os tokens das tabelas do Módulo 4 (`tiktok_connections`, `tiktok_youtube_connections`), e faz o upload automático para TikTok, YouTube Shorts e Instagram Reels.
   - Registra logs de envio na tabela `postrecap_post_logs`.

---

## ⚡ 2. Execução Simultânea no Hugging Face Space (`app.py`)

Todos os módulos rodam **simultaneamente** sob o orquestrador [`app.py`](file:///d:/Applications/AnimeRecap/app.py) na raiz do repositório.

### Como o `app.py` gerencia o Módulo 3 e 4:
- **Módulo 3 (`post_recap`)**:
  - Função `start_postrecap_service()` em `app.py`:
    - Verifica se a variável `POSTRECAP_TELEGRAM_BOT_TOKEN` está presente.
    - Executa o bot em loop resiliente dentro de uma thread `daemon=True` (`Thread-Post Recap`).
- **Módulo 4 (`tiktok_approval`)**:
  - Função `start_tiktok_approval_service()` em `app.py`:
    - Inicia a API FastAPI do TikTok Approval via `uvicorn.run(tiktok_app, host="0.0.0.0", port=8000)`.
    - As rotas são adicionalmente injetadas na aplicação raiz do Gradio (`demo.app`) através de `inject_api_routes()` para responderem diretamente na URL pública do Space (`https://alehcrim-anime-pipeline.hf.space/api/...`).

> [!TIP]
> **Nunca utilize `time.sleep` bloqueante ou loops síncronos na thread principal do `app.py`**. Cada serviço deve rodar em sua própria thread ou subprocesso com captura de exceções `try/except` para não derrubar os demais módulos caso ocorra algum erro.

---

## 🗺️ 3. Mapa de Variáveis de Ambiente (Prevenção de Conflitos)

Para evitar colisões de variáveis entre bots e serviços que rodam no mesmo ambiente:

| Módulo | Variável | Descrição / Uso | Obrigatório? |
| :--- | :--- | :--- | :--- |
| **Global** | `DATABASE_URL` | String de conexão com o PostgreSQL Neon | ✅ Sim |
| **Global** | `AUTHORIZED_TELEGRAM_USERS` | IDs de Telegram autorizados (ex: `123456,789101`) | ✅ Sim |
| **Global** | `DRIVE_CLIENT_ID` / `DRIVE_CLIENT_SECRET` / `DRIVE_REFRESH_TOKEN` | Credenciais OAuth do Google Drive | ✅ Sim |
| **Módulo 1** | `SCRAPPER_TELEGRAM_TOKEN` | Token do Bot Telegram do Scrapper Douyin | ✅ Módulo 1 |
| **Módulo 2** | `TELEGRAM_BOT_TOKEN` | Token do Bot Telegram do Kuma Pipeline | ✅ Módulo 2 |
| **Módulo 3** | `POSTRECAP_TELEGRAM_BOT_TOKEN` | **Token EXCLUSIVO** do Bot Telegram do Post Recap | ✅ Módulo 3 |
| **Módulo 3** | `INSTAGRAM_USERNAME` / `INSTAGRAM_PASSWORD` | Credenciais de postagem no Instagram | ⚠️ Opcional |
| **Módulo 4** | `TIKTOK_CLIENT_KEY` / `TIKTOK_CLIENT_SECRET` | Credenciais da API do TikTok Developers | ✅ Módulo 4 |
| **Módulo 4** | `TIKTOK_REDIRECT_URI` | Callback OAuth TikTok (`https://alehcrim-anime-pipeline.hf.space/api/tiktok/callback`) | ✅ Módulo 4 |
| **Módulo 4** | `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET` | Credenciais OAuth do Google Console (YouTube Data API v3) | ✅ Módulo 4 |
| **Módulo 4** | `YOUTUBE_REDIRECT_URI` | Callback OAuth YouTube (`https://alehcrim-anime-pipeline.hf.space/api/youtube/callback`) | ✅ Módulo 4 |
| **Módulo 4** | `FRONTEND_URL` | URL do frontend do painel de aprovação (se aplicável) | ⚠️ Opcional |

> [!CAUTION]
> **NUNCA compartilhe o mesmo token do Telegram entre dois módulos.** Se o `POSTRECAP_TELEGRAM_BOT_TOKEN` for igual ao `TELEGRAM_BOT_TOKEN`, o Telegram rejeitará com erro `409 Conflict: terminated by other getUpdates request`.

---

## 🗄️ 4. Banco de Dados Compartilhado (Neon PostgreSQL)

Todas as tabelas são gerenciadas de forma centralizada em [`shared/schema_init.py`](file:///d:/Applications/AnimeRecap/shared/schema_init.py).

### Tabelas do Módulo 3 (`post_recap`):
* `postrecap_scheduled_posts`: Fila de posts agendados contendo caminho do vídeo no Drive, títulos, tags, horários e flags (`post_youtube`, `post_tiktok`, `post_instagram`, `status`).
* `postrecap_post_logs`: Histórico e logs de execução de cada postagem realizada nas redes.
* `postrecap_instagram_queue`: Fila auxiliar para uploads no Instagram.

### Tabelas do Módulo 4 (`tiktok_approval`):
* `tiktok_approved_users`: Lista de e-mails de administradores autorizados (`approved = 1`).
* `tiktok_connections`: Tokens OAuth2, `open_id`, `refresh_token` e perfil conectado do TikTok.
* `tiktok_youtube_connections`: Tokens OAuth2, `channel_id`, `refresh_token` do canal do YouTube.
* `tiktok_audit_logs`: Log de ações e auditoria de segurança.

---

## 🛡️ 5. Regras Globais do Usuário

1. **Idioma**: Todas as comunicações e logs explicativos devem ser em `pt-br`.
2. **Sem Credenciais no Código**: Nunca insira senhas, chaves de API ou tokens diretamente no código. Referencie sempre via `.env` ou Hugging Face Secrets (`os.getenv(...)`).
3. **Aprovação de Login Manual**:
   - No Módulo 4 (`tiktok_approval/main.py`), ao realizar login/OAuth, consulte a tabela `tiktok_approved_users`.
   - Se o e-mail não existir ou `approved != 1`, bloqueie o acesso e nunca renderize informações ou ações administrativas.
   - Para aprovar um usuário localmente, execute o script:
     ```bash
     python tiktok_approval/approve_user.py <email_do_usuario>
     ```

---

## 🚀 6. Checklist de Implementação e Deploy

Quando finalizar ou ajustar os Módulos 3 e 4:

1. **Testar Dependências**:
   - Garanta que qualquer nova biblioteca esteja incluída no [`requirements.txt`](file:///d:/Applications/AnimeRecap/requirements.txt).
2. **Validar Inicialização no `app.py`**:
   - Verifique se as funções `start_postrecap_service()` e `start_tiktok_approval_service()` em `app.py` estão chamando as funções principais corretas de `post_recap/bot.py` e `tiktok_approval/main.py`.
3. **Commit no Repositório Git**:
   ```bash
   git add .
   git commit -m "Implementa e ativa Módulos 3 (Post Recap) e 4 (TikTok Approval)"
   git push origin main
   ```
4. **Deploy no Hugging Face Space**:
   - Execute o script mestre de sincronização:
     ```bash
     python scratch/deploy_module2_and_space.py
     ```
   - O script atualizará todos os arquivos e pastas (`shared/`, `bot/`, `scrapper/`, `douyin_api/`, `post_recap/`, `tiktok_approval/`, `app.py`) no Space `alehcrim/anime-pipeline`.
5. **Verificar no Dashboard (Porta 7860)**:
   - Abra a URL do Hugging Face Space para confirmar que os status de `Post Recap Bot & Scheduler` e `TikTok Approval API (8000)` aparecem com status `✅ Online`.
