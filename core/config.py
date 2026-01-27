"""Конфигурационный модуль для загрузки и управления настройками приложения."""
import json
import logging
from pathlib import Path

from core.constants import (CONFIG_FILE, DEFAULT_TTS_VOICES, DEFAULT_TTS_RATE,
                            DEFAULT_TTS_VOLUME)

logger = logging.getLogger(__name__)


def load_config(filename=CONFIG_FILE):
    """Загружает конфигурацию из JSON файла или создает файл с настройками по умолчанию.

    Args:
        filename: Имя конфигурационного файла

    Returns:
        dict: Загруженная конфигурация
    """
    default_config = {
        "app": {
            "log_level": "INFO",
            "hotkey": "page up"
        },
        "translation": {
            "source_lang": "ru",
            "target_lang": "zh",
            "whisper_model": "small"
        },
        "tts": {
            "voice": "",
            "rate": DEFAULT_TTS_RATE,
            "volume": DEFAULT_TTS_VOLUME
        },
        "soundpad": {
            "play_in_speakers": True,
            "play_in_microphone": True
        }
    }

    config_path = Path(filename)

    if not config_path.exists():
        logger.info(f"Creating default config: {filename}")
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2, ensure_ascii=False)
            logger.info(f"Config created: {config_path.absolute()}")
            return default_config
        except Exception as e:
            logger.error(f"Config creation error: {e}, using defaults")
            return default_config

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            user_config = json.load(f)

        merged_config = _merge_configs(default_config, user_config)

        target_lang = merged_config["translation"]["target_lang"]
        tts_config = merged_config["tts"]

        if not tts_config.get("voice") or tts_config["voice"].strip() == "":
            voice = DEFAULT_TTS_VOICES.get(target_lang, "")
            if voice:
                tts_config["voice"] = voice
                logger.info(
                    f"Auto-selected TTS voice for {target_lang}: {voice}")
            else:
                logger.warning(
                    f"No default TTS voice for language: {target_lang}")

        logger.debug(f"Loaded config from: {config_path.absolute()}")
        return merged_config
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}, using defaults")
        return default_config
    except Exception as e:
        logger.error(f"Config load error: {e}, using defaults")
        return default_config


def _merge_configs(default, user):
    """Рекурсивно объединяет две конфигурации.

    Args:
        default: Конфигурация по умолчанию
        user: Пользовательская конфигурация

    Returns:
        dict: Объединенная конфигурация
    """
    result = default.copy()

    for key, value in user.items():
        if (key in result and isinstance(result[key], dict)
                and isinstance(value, dict)):
            result[key] = _merge_configs(result[key], value)
        else:
            result[key] = value

    return result
