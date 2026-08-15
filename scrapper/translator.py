"""
Módulo de Tradução Automática (Chinês zh-CN -> Português pt-BR).
"""

import re
import httpx
import logging

logger = logging.getLogger(__name__)

def translate_zh_to_pt(text: str) -> str:
    """
    Traduz títulos e textos em Chinês para Português PT-BR usando Google Translate API.
    """
    if not text or not text.strip():
        return text or ""
        
    text_clean = text.strip()
    
    # Se o texto não possui caracteres chineses (\u4e00-\u9fff), não precisa traduzir
    if not re.search(r'[\u4e00-\u9fff]', text_clean):
        return text_clean

    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "zh-CN",
            "tl": "pt",
            "dt": "t",
            "q": text_clean
        }
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data and isinstance(data, list) and len(data) > 0 and data[0]:
                    translated_parts = [item[0] for item in data[0] if item and isinstance(item, list) and item[0]]
                    translated = "".join(translated_parts).strip()
                    if translated:
                        return translated
    except Exception as e:
        logger.warning(f"Erro na tradução automática de '{text_clean[:20]}...': {e}")

    # Fallback de emergência para número de episódios
    ep_match = re.search(r'(?:第|\s)?(\d{1,4})(?:集|话|話)', text_clean)
    if ep_match:
        return f"Episódio {ep_match.group(1)}"
        
    return text_clean
