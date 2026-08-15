"""
Agendador de Episódios & Fila Circular Round-Robin.
Gerencia horários fixos 100% personalizáveis na UI, pasta de isolamento 'data/next_staging'
com retenção de 6 horas, e tratamento de vídeos avulsos.
"""

import os
import time
import shutil
import logging
import threading
from datetime import datetime, timedelta, time as dtime
from scrapper import database, pipeline_integrator, post_recap_integrator

logger = logging.getLogger(__name__)

# Diretório de Staging Isolado para o próximo vídeo pronto
STAGING_DIR = os.path.join("data", "next_staging")
os.makedirs(STAGING_DIR, exist_ok=True)

# Horários padrões iniciais (apenas como sugestão caso o usuário não altere)
DEFAULT_TIME_SLOTS = {
    1: ["18:00"],
    2: ["12:00", "18:00"],
    3: ["10:00", "15:00", "20:00"]
}

def get_daily_post_rate() -> int:
    """Retorna o ritmo diário de postagens configurado (1, 2 ou 3). Default = 2."""
    rate_str = database.get_user_setting("daily_post_rate", "2")
    try:
        return max(1, min(3, int(rate_str)))
    except Exception:
        return 2

def set_daily_post_rate(rate: int) -> bool:
    """Atualiza o ritmo diário de postagens (1, 2 ou 3)."""
    rate = max(1, min(3, int(rate)))
    return database.set_user_setting("daily_post_rate", str(rate))

def get_autopost_times() -> list[str]:
    """Retorna a lista de horários fixos definidos pelo usuário para o ritmo atual."""
    rate = get_daily_post_rate()
    default_str = ",".join(DEFAULT_TIME_SLOTS.get(rate, DEFAULT_TIME_SLOTS[2]))
    saved_str = database.get_user_setting(f"autopost_times_rate_{rate}", default_str)
    times = [t.strip() for t in saved_str.split(",") if t.strip()]
    
    # Ajusta o tamanho da lista conforme o ritmo escolhido
    if len(times) < rate:
        defaults = DEFAULT_TIME_SLOTS.get(rate, DEFAULT_TIME_SLOTS[2])
        while len(times) < rate:
            times.append(defaults[len(times) if len(times) < len(defaults) else -1])
    return times[:rate]

def set_autopost_times(times_list: list[str]) -> bool:
    """Salva os horários fixos personalizados fornecidos pelo usuário."""
    rate = get_daily_post_rate()
    valid_times = []
    for t in times_list:
        t_clean = t.strip()
        try:
            datetime.strptime(t_clean, "%H:%M")
            valid_times.append(t_clean)
        except ValueError:
            pass
            
    if not valid_times:
        valid_times = DEFAULT_TIME_SLOTS.get(rate, DEFAULT_TIME_SLOTS[2])
        
    return database.set_user_setting(f"autopost_times_rate_{rate}", ",".join(valid_times[:rate]))

def get_next_scheduled_target_time() -> datetime:
    """
    Calcula o próximo horário exato de publicação com base nos horários definidos pelo usuário.
    """
    now = datetime.now()
    slots = get_autopost_times()
    
    today_slots = []
    for s in slots:
        try:
            t_obj = datetime.strptime(s, "%H:%M").time()
            dt_slot = datetime.combine(now.date(), t_obj)
            today_slots.append(dt_slot)
        except Exception:
            pass
            
    today_slots.sort()
    
    # Procura o próximo slot de hoje
    for slot in today_slots:
        if slot > now:
            return slot

    # Se todos de hoje passaram, pega o primeiro de amanhã
    tomorrow = now.date() + timedelta(days=1)
    if today_slots:
        first_time = today_slots[0].time()
        return datetime.combine(tomorrow, first_time)

    return datetime.combine(tomorrow, dtime(18, 0))

def cleanup_old_next_staging(max_age_hours: int = 6):
    """
    Limpa arquivos da pasta data/next_staging mantidos por mais de 6 horas pós-postagem.
    """
    if not os.path.exists(STAGING_DIR):
        return
    now_ts = time.time()
    cutoff_ts = now_ts - (max_age_hours * 3600)

    for item in os.listdir(STAGING_DIR):
        item_path = os.path.join(STAGING_DIR, item)
        try:
            if os.path.isfile(item_path):
                if os.path.getmtime(item_path) < cutoff_ts:
                    os.remove(item_path)
                    logger.info(f"🧹 Removido arquivo de staging antigo (>6h): {item_path}")
        except Exception as e:
            logger.warning(f"Erro ao limpar arquivo de staging {item_path}: {e}")

def get_next_episodes_to_post(count: int = None) -> list[dict]:
    """
    Seleciona os próximos episódios a serem postados hoje respeitando a Fila Round-Robin.
    Prioridades:
      1. Episódios marcados com 'post_now' (Furar Fila Imediato - Avulsos ou Manuais)
      2. Episódios marcados com 'next_in_queue' (Prioridade Alta)
      3. Rotação Round-Robin entre coleções ativas com autoposting = 1
    """
    if count is None:
        count = get_daily_post_rate()

    conn = database.get_connection()
    cursor = conn.cursor()
    selected_episodes = []

    try:
        # 1. Busca episódios marcados com 'post_now'
        cursor.execute("""
            SELECT e.*, c.title_pt as collection_title_pt, c.title_zh as collection_title_zh
            FROM collection_episodes e
            JOIN douyin_collections c ON e.mix_id = c.mix_id
            WHERE e.status = 'post_now'
            ORDER BY e.id ASC
            LIMIT ?
        """, (count,))
        post_now_eps = [dict(row) for row in cursor.fetchall()]
        selected_episodes.extend(post_now_eps)

        if len(selected_episodes) >= count:
            return selected_episodes[:count]

        remaining_count = count - len(selected_episodes)

        # 2. Busca episódios marcados com 'next_in_queue'
        cursor.execute("""
            SELECT e.*, c.title_pt as collection_title_pt, c.title_zh as collection_title_zh
            FROM collection_episodes e
            JOIN douyin_collections c ON e.mix_id = c.mix_id
            WHERE e.status = 'next_in_queue'
            ORDER BY e.id ASC
            LIMIT ?
        """, (remaining_count,))
        next_queue_eps = [dict(row) for row in cursor.fetchall()]
        selected_episodes.extend(next_queue_eps)

        if len(selected_episodes) >= count:
            return selected_episodes[:count]

        remaining_count = count - len(selected_episodes)

        # 3. Lógica Round-Robin Intercalada por Sequência:
        # Busca a próxima coleção ativa onde o menor episódio pendente ('pending') tem o menor número de sequência.
        # Isso garante que a fila rode 1 episódio por coleção no nível EP N antes de avançar para EP N+1.
        cursor.execute("""
            SELECT 
                c.mix_id,
                c.title_pt as collection_title_pt,
                c.title_zh as collection_title_zh,
                MIN(CASE WHEN e.episode_num IS NOT NULL THEN e.episode_num ELSE 999999 END) as next_ep_num,
                COUNT(CASE WHEN e.status IN ('posted', 'published', 'completed') THEN 1 END) as posted_count,
                MAX(e.posted_at) as last_posted_at
            FROM douyin_collections c
            JOIN collection_episodes e ON c.mix_id = e.mix_id
            WHERE c.autoposting = 1 AND c.status = 'active' AND e.status = 'pending'
            GROUP BY c.mix_id
            ORDER BY next_ep_num ASC, last_posted_at ASC, c.created_at ASC
        """)
        active_collections = [dict(row) for row in cursor.fetchall()]

        for col in active_collections:
            if remaining_count <= 0:
                break
            mix_id = col["mix_id"]
            cursor.execute("""
                SELECT e.*, ? as collection_title_pt, ? as collection_title_zh
                FROM collection_episodes e
                WHERE e.mix_id = ? AND e.status = 'pending'
                ORDER BY CASE WHEN e.episode_num IS NULL THEN 999999 ELSE e.episode_num END ASC, e.id ASC
                LIMIT 1
            """, (col["collection_title_pt"], col["collection_title_zh"], mix_id))
            row = cursor.fetchone()
            if row:
                ep_dict = dict(row)
                if not any(se["id"] == ep_dict["id"] for se in selected_episodes):
                    selected_episodes.append(ep_dict)
                    remaining_count -= 1

    except Exception as e:
        logger.error(f"Erro ao selecionar próximos episódios no agendador: {e}")
    finally:
        conn.close()

    return selected_episodes

def trigger_pre_render_for_next_episode():
    """
    Aciona o pipeline completo (AnimeRecap) antecipadamente para o PRÓXIMO episódio da fila.
    O vídeo dublado e renderizado é mantido na pasta isolada 'data/next_staging/' por 6 horas.
    """
    # Realiza a limpeza de arquivos antigos mantidos há mais de 6 horas
    cleanup_old_next_staging()

    # 🛑 Trava de Segurança: Não produz se já houver 3 ou mais vídeos agendados/pendentes no Post_recap
    try:
        import sqlite3 as _sqlite_posts
        _posts_db_path = "/home/ubuntu/apps/Post_recap/posts.db"
        if os.path.exists(_posts_db_path):
            _conn_p = _sqlite_posts.connect(_posts_db_path)
            _cur_p = _conn_p.cursor()
            _cur_p.execute("SELECT COUNT(*) FROM scheduled_posts WHERE status = 'pending'")
            _pending_count = _cur_p.fetchone()[0]
            _conn_p.close()
            
            if _pending_count >= 3:
                logger.info(f"🛑 Fila de postagem já possui {_pending_count} vídeos pendentes (limite: 3). Ignorando pré-renderização automática.")
                return {"ok": False, "message": f"Fila de postagem cheia ({_pending_count} pendentes). Produção adiada."}
    except Exception as e_check:
        logger.warning(f"Aviso ao verificar fila do Post_recap: {e_check}")

    next_eps = get_next_episodes_to_post(count=1)
    if not next_eps:
        logger.info("ℹ️ Nenhum episódio pendente na fila para pré-renderização.")
        return None

    target_ep = next_eps[0]
    ep_id = target_ep["id"]

    logger.info(f"⚡ Acionando pré-processamento do AnimeRecap para o EP #{ep_id} ({target_ep['title'][:30]})...")
    
    # 1. Aciona o AnimeRecap (Download + Corte 2:45 + Presets no Omni + Configs)
    res_pipeline = pipeline_integrator.dispatch_episode_to_pipeline(ep_id)
    
    # 2. Calcula o próximo horário personalizado pelo usuário para agendamento futuro no Post_recap (pós-render)
    target_time = get_next_scheduled_target_time()

    return {
        "episode_id": ep_id,
        "pipeline_result": res_pipeline,
        "scheduled_target_time": target_time.strftime("%Y-%m-%d %H:%M:%S")
    }

def apply_episode_action(ep_id: int, action: str) -> dict:
    """
    Aplica ações em episódios (ex: acelerar, dividir, postar agora, descartar).
    Para episódios avulsos ou acionamentos 'post_now', roda de forma isolada no pipeline.
    """
    ep = database.get_episode_by_id(ep_id)
    if not ep:
        return {"ok": False, "message": f"Episódio #{ep_id} não encontrado."}

    valid_actions = ["post_now", "force_post_now", "next_in_queue", "keep_original", "accelerate", "ignore"]
    if action not in valid_actions:
        return {"ok": False, "message": f"Ação '{action}' inválida."}

    new_status = "pending"
    if action in ["post_now", "force_post_now"]:
        new_status = "post_now"
    elif action == "next_in_queue":
        new_status = "next_in_queue"
    elif action == "ignore":
        new_status = "ignored"

    success = database.update_episode_status(ep_id, new_status)
    
    # Se for acionamento 'post_now' ou 'force_post_now', dispara o pipeline em segundo plano
    if action in ["post_now", "force_post_now"]:
        force_flag = (action == "force_post_now")
        logger.info(f"⚡ Disparando pipeline em segundo plano para o episódio #{ep_id} (force={force_flag})...")
        
        # Dispara em background thread para a API responder instantaneamente
        t = threading.Thread(
            target=pipeline_integrator.dispatch_episode_to_pipeline,
            args=(ep_id, force_flag),
            daemon=True
        )
        t.start()

        return {
            "ok": True,
            "episode_id": ep_id,
            "action": action,
            "manual_execution": True,
            "message": f"⚡ Disparo do episódio #{ep_id} iniciado em segundo plano! Acompanhe as etapas pelo Telegram."
        }

    if success:
        return {"ok": True, "episode_id": ep_id, "action": action, "new_status": new_status, "message": f"Ação '{action}' aplicada ao episódio #{ep_id} com sucesso."}
    return {"ok": False, "message": "Falha ao atualizar banco de dados."}
