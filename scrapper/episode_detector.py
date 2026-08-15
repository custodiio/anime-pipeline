"""
Douyin Anime Scraper — Detector de episódios em títulos chineses.
Extrai o número do episódio de padrões como 第12集, EP12, [12], etc.
"""

import re
from typing import Optional


# Padrões de episódio em títulos chineses (ordem de prioridade)
EP_PATTERNS = [
    r"第\s*(\d+)\s*[集话話]",   # 第12集 / 第12话 / 第12話
    r"[Ee][Pp]?\s*(\d+)",       # EP12 / ep12 / E12
    r"\[(\d+)\]",               # [12]
    r"#(\d+)",                  # #12
    r"(\d+)\s*话",              # 12话
    r"(\d+)\s*集",              # 12集
]


def extract_episode(title: str) -> Optional[int]:
    """
    Extrai o número do episódio de um título de vídeo.

    Exemplos:
        "动漫解说 第12集 完结" → 12
        "海贼王 EP1089 精彩片段" → 1089
        "咒术回战 [23] recap" → 23
        "没有episodio aqui" → None
    """
    if not title:
        return None

    for pattern in EP_PATTERNS:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            return int(match.group(1))

    return None


def is_continuation(episode: Optional[int], last_posted: Optional[int]) -> bool:
    """
    Verifica se um episódio é a continuação do último postado.

    Args:
        episode: Número do episódio do vídeo atual
        last_posted: Número do último episódio postado

    Returns:
        True se episode == last_posted + 1
    """
    if episode is None or last_posted is None:
        return False
    return episode == last_posted + 1
