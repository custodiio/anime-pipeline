import os

filepath = r'd:\Applications\AnimeRecap\bot\telegram_bot.py'
with open(filepath, 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Update /start command
old_start = """@authorized
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    \"\"\"Mensagem de boas-vindas com menu visual.\"\"\"
    await update.message.reply_text(
        "🎬 *Agente de Postagem — AnimeRecap*\\n\\n"
        "Pipeline automatizado de pós-produção.\\n\\n"
        "📝 *Comandos:*\\n"
        "  /novo `<nome>` — Inicia novo projeto\\n"
        "  /status — Status do projeto ativo\\n"
        "  /cells `[notebook]` — Tracking por célula\\n"
        "  /sessao — Gera link do VideoRender\\n"
        "  /config — Confirma config (dispara render)\\n"
        "  /upload — Obter link para upload local de arquivos\\n"
        "  /cancel — Cancela projeto ativo\\n"
        "  /myid — Mostra seu User ID\\n\\n"
        "📦 *Envio de arquivos:*\\n"
        "  1. Envie o *vídeo* (com marca d'água)\\n"
        "  2. Envie o *áudio* (original do vídeo)\\n"
        "  3. Use `/novo Nome do Anime`\\n\\n"
        "💻 *Para vídeos gigantes (>20MB):*\\n"
        "  Use o comando `/upload` para receber o link do painel web,\\n"
        "  faça o upload dos arquivos e depois use:\\n"
        "  `/usar_local Nome do Anime`",
        parse_mode="Markdown"
    )"""

new_start = """@authorized
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    \"\"\"Mensagem de boas-vindas com menu visual.\"\"\"
    buttons = [
        [InlineKeyboardButton("🚀 Novo Projeto Automático", callback_data="new_auto")],
        [InlineKeyboardButton("🛠️ Novo Projeto Manual", callback_data="new_manual")]
    ]
    await update.message.reply_text(
        "🎬 *Agente de Postagem — AnimeRecap*\\n\\n"
        "Bem-vindo! Escolha uma opção abaixo após enviar os arquivos, ou use os comandos normais.\\n\\n"
        "📦 *Envio de arquivos:*\\n"
        "  1. Envie o *vídeo* (com marca d'água)\\n"
        "  2. Envie o *áudio* (original do vídeo)\\n"
        "  3. Clique em um dos botões ou use `/novo Nome`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )"""
code = code.replace(old_start, new_start)

# 2. Update cmd_status to show Disparar Função
old_status_buttons = """    buttons = []
    if project.get("status") == "waiting_config":
        buttons.append([InlineKeyboardButton("⚙️ Abrir VideoRender", callback_data="open_session")])
        buttons.append([InlineKeyboardButton("✅ Config Pronta", callback_data="confirm_config")])
    buttons.append([InlineKeyboardButton("🔄 Atualizar", callback_data="refresh_status")])

    reply_markup = InlineKeyboardMarkup(buttons) if buttons else None"""

new_status_buttons = """    buttons = []
    if project.get("status") == "waiting_config":
        buttons.append([InlineKeyboardButton("⚙️ Abrir VideoRender", callback_data="open_session")])
        buttons.append([InlineKeyboardButton("✅ Config Pronta", callback_data="confirm_config")])
    buttons.append([InlineKeyboardButton("🎯 Disparar Função", callback_data="trigger_menu")])
    buttons.append([InlineKeyboardButton("🔄 Atualizar", callback_data="refresh_status")])

    reply_markup = InlineKeyboardMarkup(buttons) if buttons else None"""
code = code.replace(old_status_buttons, new_status_buttons)

# 3. Handle callbacks for new_auto and new_manual
old_handle_callback = """    if data == "toggle_wm":"""
new_handle_callback = """    if data == "new_auto" or data == "new_manual":
        if chat_id not in user_uploads or not user_uploads[chat_id].get("video") or not user_uploads[chat_id].get("audio"):
            await query.edit_message_text("❌ Envie vídeo e áudio primeiro!")
            return
        from bot.database import get_active_project
        active = get_active_project(chat_id)
        if active:
            await query.edit_message_text("⚠️ Já existe um projeto ativo. Use /cancel primeiro.")
            return
            
        user_uploads[chat_id]["name"] = f"Projeto_{chat_id[:6]}"
        user_uploads[chat_id]["local"] = False
        user_uploads[chat_id]["watermark"] = True
        user_uploads[chat_id]["enhancer"] = False
        user_uploads[chat_id]["manual_mode"] = (data == "new_manual")
        await send_config_menu(None, chat_id, query)
        
    elif data == "toggle_wm":"""
code = code.replace(old_handle_callback, new_handle_callback)

# 4. Handle start_project manual mode
old_start_project = """        try:
            # Informar ao controller as opções selecionadas (rodando em background para não bloquear o loop)
            project = await asyncio.to_thread(
                controller.iniciar_projeto,
                project_name=opts["name"],
                chat_id=chat_id,
                video_path=opts["video"],
                audio_path=opts["audio"],
                mask_path=opts.get("mask"),
                opts=opts  # Passar as configs para o controller registrar
            )
            pid = str(project["id"])

            token = gerar_session_token(pid)
            active_sessions[token] = {"project_id": pid, "chat_id": chat_id, "created_at": time.time()}
            session_link = get_session_link(token)

            # Dispara o Omni ANTES de enviar a mensagem (pra não bloquear se a msg falhar)
            controller.disparar_omni_imediatamente(pid)

            await query.message.reply_text(
                f"✅ Upload e Divisão Concluídos!\\n\\n"
                f"🔄 Disparando a Dublagem (Omni)...\\n\\n"
                f"⚙️ Sessão de Configuração de Legenda:\\n"
                f"Configure o estilo da legenda (com um texto placeholder).\\n"
                f"Se quiser remover marca d'água, adicione a máscara na tela de config.\\n\\n"
                f"🎬 Abrir VideoRender:\\n{session_link}\\n\\n"
                f"📊 Use /status para acompanhar."
            )"""

new_start_project = """        try:
            manual_mode = opts.get("manual_mode", False)
            if manual_mode:
                project = await asyncio.to_thread(
                    controller.iniciar_projeto_manual,
                    project_name=opts["name"],
                    chat_id=chat_id,
                    video_path=opts["video"],
                    audio_path=opts["audio"],
                    mask_path=opts.get("mask"),
                    opts=opts
                )
            else:
                project = await asyncio.to_thread(
                    controller.iniciar_projeto,
                    project_name=opts["name"],
                    chat_id=chat_id,
                    video_path=opts["video"],
                    audio_path=opts["audio"],
                    mask_path=opts.get("mask"),
                    opts=opts
                )
            pid = str(project["id"])

            token = gerar_session_token(pid)
            active_sessions[token] = {"project_id": pid, "chat_id": chat_id, "created_at": time.time()}
            session_link = get_session_link(token)

            if not manual_mode:
                controller.disparar_omni_imediatamente(pid)
                msg_text = (
                    f"✅ Upload e Divisão Concluídos!\\n\\n"
                    f"🔄 Disparando a Dublagem (Omni)...\\n\\n"
                    f"⚙️ Sessão de Configuração de Legenda:\\n"
                    f"Configure o estilo da legenda.\\n"
                    f"🎬 Abrir VideoRender:\\n{session_link}\\n\\n"
                    f"📊 Use /status para acompanhar."
                )
            else:
                msg_text = (
                    f"🛠️ Projeto Manual Inicializado!\\n\\n"
                    f"✅ Upload e Divisão Concluídos.\\n"
                    f"Nenhuma função foi disparada automaticamente.\\n"
                    f"🎬 Sessão VideoRender:\\n{session_link}\\n\\n"
                    f"Use /status e clique em '🎯 Disparar Função' para rodar os blocos."
                )

            await query.message.reply_text(msg_text)"""
code = code.replace(old_start_project, new_start_project)

# 5. Handle refresh_status buttons update
old_refresh_status = """    elif data == "refresh_status":
        project = get_active_project(chat_id)
        if project:
            status_text = format_status(project)
            buttons = [[InlineKeyboardButton("🔄 Atualizar", callback_data="refresh_status")]]
            if project.get("status") == "waiting_config":
                buttons.insert(0, [InlineKeyboardButton("⚙️ Abrir VideoRender", callback_data="open_session")])
                buttons.insert(1, [InlineKeyboardButton("✅ Config Pronta", callback_data="confirm_config")])
            await query.edit_message_text(status_text, parse_mode="Markdown",
                                          reply_markup=InlineKeyboardMarkup(buttons))"""

new_refresh_status = """    elif data == "refresh_status":
        project = get_active_project(chat_id)
        if project:
            status_text = format_status(project)
            buttons = []
            if project.get("status") == "waiting_config":
                buttons.append([InlineKeyboardButton("⚙️ Abrir VideoRender", callback_data="open_session")])
                buttons.append([InlineKeyboardButton("✅ Config Pronta", callback_data="confirm_config")])
            buttons.append([InlineKeyboardButton("🎯 Disparar Função", callback_data="trigger_menu")])
            buttons.append([InlineKeyboardButton("🔄 Atualizar", callback_data="refresh_status")])
            await query.edit_message_text(status_text, parse_mode="Markdown",
                                          reply_markup=InlineKeyboardMarkup(buttons))"""
code = code.replace(old_refresh_status, new_refresh_status)

# 6. Add trigger handling at the end of handle_callback
trigger_handlers = """
    # -------- DISPARO MANUAL --------
    elif data == "trigger_menu":
        project = get_active_project(chat_id)
        if not project:
            await query.edit_message_text("❌ Sem projeto ativo.")
            return
        buttons = [
            [InlineKeyboardButton("🧠 Omni", callback_data="trigger_omni"),
             InlineKeyboardButton("🧹 Watermark", callback_data="trigger_wm_menu")],
            [InlineKeyboardButton("⚡ Enhancer", callback_data="trigger_enhancer_menu"),
             InlineKeyboardButton("🎬 Render", callback_data="trigger_render_menu")],
            [InlineKeyboardButton("📦 Merge", callback_data="trigger_merge")],
            [InlineKeyboardButton("🔙 Voltar", callback_data="refresh_status")]
        ]
        await query.edit_message_text("🎯 *Menu de Disparo*\\nQual função deseja iniciar?", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

    elif data == "trigger_omni":
        project = get_active_project(chat_id)
        if project:
            pid = str(project["id"])
            ok, err = controller.check_omni_ready()
            if not ok:
                await query.answer(err, show_alert=True)
                return
            controller.disparar_omni_imediatamente(pid)
            await query.edit_message_text("🚀 Omni disparado!")

    elif data == "trigger_merge":
        project = get_active_project(chat_id)
        if project:
            pid = str(project["id"])
            ok, err = controller.check_merge_ready()
            if not ok:
                await query.answer(err, show_alert=True)
                return
            controller.disparar_merge(pid)
            await query.edit_message_text("🚀 Merge disparado!")

    elif data in ["trigger_wm_menu", "trigger_enhancer_menu", "trigger_render_menu"]:
        prefix = data.replace("_menu", "")
        buttons = []
        for i in range(1, 6):
            buttons.append([InlineKeyboardButton(f"Parte {i}", callback_data=f"{prefix}_{i}")])
        buttons.append([InlineKeyboardButton("Todas as Partes", callback_data=f"{prefix}_all")])
        buttons.append([InlineKeyboardButton("🔙 Voltar", callback_data="trigger_menu")])
        names = {"trigger_wm": "Watermark", "trigger_enhancer": "Enhancer", "trigger_render": "Render"}
        await query.edit_message_text(f"🎯 *{names[prefix]}*\\nEscolha a parte:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("trigger_wm_"):
        project = get_active_project(chat_id)
        if not project: return
        pid = str(project["id"])
        ok, err = controller.check_watermark_ready()
        if not ok:
            await query.answer(err, show_alert=True)
            return
        from bot.github_actions import dispatch_parallel
        part = data.split("_")[-1]
        if part == "all":
            controller.disparar_watermark(pid)
            await query.edit_message_text("🚀 Watermark disparado para todas as partes!")
        else:
            from bot.database import update_step
            update_step(pid, f"step_watermark_pt{part}", "running")
            dispatch_parallel([f"wm-pt{part}"], pid)
            await query.edit_message_text(f"🚀 Watermark PT {part} disparado!")

    elif data.startswith("trigger_enhancer_"):
        project = get_active_project(chat_id)
        if not project: return
        pid = str(project["id"])
        part = data.split("_")[-1]
        p_val = int(part) if part != "all" else None
        ok, err = controller.check_enhancer_ready(p_val)
        if not ok:
            await query.answer(err, show_alert=True)
            return
        from bot.github_actions import dispatch_parallel
        if part == "all":
            controller.disparar_enhancer(pid)
            await query.edit_message_text("🚀 Enhancer disparado para todas as partes!")
        else:
            from bot.database import update_step
            update_step(pid, f"step_enhancer_pt{part}", "running")
            dispatch_parallel([f"enhancer-pt{part}"], pid)
            await query.edit_message_text(f"🚀 Enhancer PT {part} disparado!")

    elif data.startswith("trigger_render_"):
        project = get_active_project(chat_id)
        if not project: return
        pid = str(project["id"])
        part = data.split("_")[-1]
        p_val = int(part) if part != "all" else None
        ok, err = controller.check_render_ready(p_val)
        if not ok:
            await query.answer(err, show_alert=True)
            return
        from bot.github_actions import dispatch_parallel
        if part == "all":
            controller.disparar_render(pid)
            await query.edit_message_text("🚀 Render disparado para todas as partes!")
        else:
            from bot.database import update_step
            update_step(pid, f"step_render_pt{part}", "running")
            dispatch_parallel([f"render-pt{part}"], pid)
            await query.edit_message_text(f"🚀 Render PT {part} disparado!")
"""

# Insert trigger_handlers into handle_callback
if "elif data == \"confirm_config\":" in code:
    code = code.replace("                await query.message.reply_text(\"🎬 Renderização disparada!\")", "                await query.message.reply_text(\"🎬 Renderização disparada!\")\n" + trigger_handlers)


# 7. Add polling completion check
old_poll_loop = """                projects = get_running_projects()
                for proj in projects:
                    pid = str(proj["id"])
                    controller.verificar_e_avancar(pid)"""

new_poll_loop = """                projects = get_running_projects()
                for proj in projects:
                    pid = str(proj["id"])
                    # Se antes era running e agora o controller.verificar_e_avancar marcar como completed, podemos checar
                    status_antes = proj.get("status")
                    controller.verificar_e_avancar(pid)
                    
                    from bot.database import get_project
                    proj_depois = get_project(pid)
                    if status_antes != "completed" and proj_depois and proj_depois.get("status") == "completed":
                        # Projeto acabou de finalizar!
                        chat_id = proj_depois["chat_id"]
                        link = controller.drive.get_file_link("KAGGLE/PIPELINE/FINAL/anime_final.mp4")
                        if link:
                            msg = f"✅ *Processo Finalizado!*\\nO vídeo final está pronto:\\n🔗 [Acessar no Drive]({link})"
                        else:
                            msg = f"✅ *Processo Finalizado!*\\nO vídeo final está na pasta KAGGLE/PIPELINE/FINAL no Drive."
                        
                        import requests
                        api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                        requests.post(api_url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})"""
code = code.replace(old_poll_loop, new_poll_loop)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(code)

print("telegram_bot.py updated!")
