import os
import sys
import subprocess
import logging

logger = logging.getLogger(__name__)

FFMPEG = os.getenv("FFMPEG_PATH", "/usr/bin/ffmpeg")
FFPROBE = os.getenv("FFPROBE_PATH", "/usr/bin/ffprobe")


def get_video_duration(video_path: str) -> float:
    """Retorna a duração do vídeo em segundos usando ffprobe."""
    if not os.path.exists(video_path):
        return 0.0
    cmd = [
        FFPROBE, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10)
        return float(res.stdout.strip())
    except Exception as e:
        logger.error(f"Erro ao obter duração do vídeo {video_path}: {e}")
        return 0.0


def adjust_video_duration_for_pipeline(input_path: str, output_path: str, target_max_seconds: float = 165.0) -> tuple[str, str]:
    """
    Ajusta a duração do vídeo conforme a regra:
    - Se a duração for <= 165s (2:45 min): mantém como está.
    - Se a duração for > 165s e <= 240s (4 min): acelera proporcionalmente para durar exatamente 165s.
    - Se a duração for > 240s (> 4 min): CORTA nos primeiros 4 minutos (240s) e ACELERA esses 4 min inteiros para durar exatamente 165s (2:45 min).
    """
    if not os.path.exists(input_path):
        logger.error(f"Arquivo não encontrado: {input_path}")
        return input_path, "error"

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    duration = get_video_duration(input_path)
    logger.info(f"Analisando duração do vídeo {os.path.basename(input_path)}: {duration:.2f}s")

    if duration > 240.0:
        logger.info(f"✂️ Vídeo de {duration:.2f}s excede 4 minutos (>240s). Aplicando pipeline: cortar 4 min → acelerar para 2:45 min...")
        tmp_cut_path = output_path.replace(".mp4", "_cut4min.mp4")
        os.makedirs(os.path.dirname(tmp_cut_path), exist_ok=True)
        
        cut_ok = truncate_video(input_path, tmp_cut_path, seconds=240.0)
        if not cut_ok or not os.path.exists(tmp_cut_path):
            logger.error("Falha ao cortar os primeiros 4 min. Tentando aceleração direta...")
            speed_factor = duration / target_max_seconds
            speed_ok = speedup_video(input_path, output_path, speed_factor)
            if speed_ok and os.path.exists(output_path):
                return output_path, "adjusted"
            return input_path, "error"

        speed_factor = 240.0 / target_max_seconds
        logger.info(f"Acelerando 4 min cortado em {speed_factor:.4f}x para encaixar em {target_max_seconds}s (2:45 min)...")
        speed_ok = speedup_video(tmp_cut_path, output_path, speed_factor)
        try: os.remove(tmp_cut_path)
        except Exception: pass

        if speed_ok and os.path.exists(output_path):
            return output_path, "truncated"
        logger.error("Falha ao acelerar o corte. Usando original como fallback.")
        return input_path, "error"

    if duration > target_max_seconds:
        speed_factor = duration / target_max_seconds
        logger.info(f"Vídeo de {duration:.2f}s está acima de {target_max_seconds}s. Acelerando por fator {speed_factor:.3f}x para 165s...")
        success = speedup_video(input_path, output_path, speed_factor)
        if success and os.path.exists(output_path):
            return output_path, "adjusted"

    return input_path, "ready"


def speedup_video(input_path: str, output_path: str, speed_factor: float) -> bool:
    """Acelera vídeo e áudio via ffmpeg (setpts + atempo)."""
    if not os.path.exists(input_path):
        return False

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pts_factor = 1.0 / speed_factor
    if speed_factor <= 2.0:
        af_filter = f"atempo={speed_factor:.4f}"
    else:
        af_filter = f"atempo=2.0,atempo={speed_factor/2.0:.4f}"

    cmd = [
        FFMPEG, "-y", "-i", input_path,
        "-filter_complex", f"[0:v]setpts={pts_factor:.4f}*PTS[v];[0:a]{af_filter}[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
        output_path
    ]
    try:
        logger.info(f"Acelerando vídeo {input_path} em {speed_factor:.3f}x para {output_path}...")
        res = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        logger.error(f"Erro ao acelerar vídeo com ffmpeg: {e}")
        return False


def truncate_video(input_path: str, output_path: str, seconds: float = 165.0) -> bool:
    """Corta o vídeo nos primeiros N segundos."""
    if not os.path.exists(input_path):
        logger.error(f"Arquivo de entrada não encontrado para corte: {input_path}")
        return False
        
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cmd = [
        FFMPEG, "-y", "-ss", "0", "-i", input_path, "-t", str(seconds),
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", output_path
    ]
    try:
        logger.info(f"Cortando vídeo {input_path} para {seconds}s...")
        res = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        logger.error(f"Erro ao cortar vídeo com ffmpeg: {e}")
        return False


def extract_audio(video_path: str, audio_path: str) -> bool:
    """Extrai a faixa de áudio de um vídeo e a converte para MP3 usando ffmpeg."""
    if not os.path.exists(video_path):
        return False
    os.makedirs(os.path.dirname(audio_path), exist_ok=True)
    cmd = [FFMPEG, "-y", "-i", video_path, "-vn", "-acodec", "libmp3lame", "-q:a", "2", audio_path]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)
        return os.path.exists(audio_path) and os.path.getsize(audio_path) > 0
    except Exception as e:
        logger.error(f"Erro ao extrair áudio: {e}")
        return False


def process_media_for_pipeline(
    video_path: str,
    output_dir: str,
    category: str,
    action: str = "keep_original",
    custom_speed: float = 1.0
) -> tuple[str, str, bool]:
    """
    Processa a mídia baixada baseando-se na ação escolhida pelo usuário.
    Extrai o áudio em MP3.
    Retorna (caminho_video_final, caminho_audio_final, sucesso)
    """
    os.makedirs(output_dir, exist_ok=True)
    video_basename = os.path.basename(video_path)
    name_without_ext, _ = os.path.splitext(video_basename)
    
    final_video_path = os.path.join(output_dir, f"{name_without_ext}_processed.mp4")
    final_audio_path = os.path.join(output_dir, f"{name_without_ext}_audio.mp3")
    
    try:
        duration = get_video_duration(video_path)
        logger.info(f"Vídeo {video_basename} tem duração de {duration:.2f}s (Ação: {action}, Fator: {custom_speed})")
        
        if action == "accelerate":
            # Acelerar padrão: se for > 240s, corta nos 4 min e acelera para 2:45 min.
            # Se for menor, apenas acelera proporcionalmente para 2:45 min.
            target_max_seconds = 165.0
            if duration > 240.0:
                logger.info("Ação 'acelerar': Cortando para 4 min e acelerando para 2m45s...")
                tmp_cut = os.path.join(output_dir, f"{name_without_ext}_tmp_cut.mp4")
                if truncate_video(video_path, tmp_cut, seconds=240.0):
                    speed_factor = 240.0 / target_max_seconds
                    success = speedup_video(tmp_cut, final_video_path, speed_factor)
                    try: os.remove(tmp_cut)
                    except: pass
                    if not success:
                        return video_path, "", False
                else:
                    return video_path, "", False
            elif duration > target_max_seconds:
                logger.info("Ação 'acelerar': Acelerando para 2m45s...")
                speed_factor = duration / target_max_seconds
                if not speedup_video(video_path, final_video_path, speed_factor):
                    return video_path, "", False
            else:
                final_video_path = video_path

        elif action == "speedup_custom":
            # Aceleração ou desaceleração customizada (ex: 0.9x)
            if abs(custom_speed - 1.0) > 0.001:
                logger.info(f"Ação 'speedup_custom': Aplicando velocidade de {custom_speed}x...")
                if not speedup_video(video_path, final_video_path, custom_speed):
                    return video_path, "", False
            else:
                final_video_path = video_path
        
        else:
            # Manter original
            logger.info("Ação 'keep_original': Mantendo vídeo original.")
            final_video_path = video_path
            
        # Extrai o áudio do vídeo final (processado ou original)
        audio_success = extract_audio(final_video_path, final_audio_path)
        if not audio_success:
            logger.error("Falha ao extrair áudio.")
            return final_video_path, "", False
            
        return final_video_path, final_audio_path, True
        
    except Exception as e:
        logger.error(f"Erro geral no processamento de mídia: {e}")
        return video_path, "", False

