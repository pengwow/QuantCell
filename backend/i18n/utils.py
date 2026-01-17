import json
from pathlib import Path
from functools import lru_cache
from loguru import logger

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent

@lru_cache(maxsize=4)
def load_translations(locale: str) -> dict:
    """
    Load translations for a specific locale from the i18n directory.
    
    Args:
        locale: The locale code (e.g., 'zh-CN', 'en-US')
        
    Returns:
        dict: A dictionary of translations
    """
    try:
        i18n_dir = PROJECT_ROOT / "i18n"
        file_path = i18n_dir / f"{locale}.json"
        
        if not file_path.exists():
            logger.warning(f"Translation file not found: {file_path}")
            return {}
            
        with open(file_path, "r", encoding="utf-8") as f:
            translations = json.load(f)
            
        return translations
    except Exception as e:
        logger.error(f"Failed to load translations for {locale}: {e}")
        return {}
