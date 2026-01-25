"""Конфигурационный модуль для загрузки и управления настройками приложения."""
import json
import os
from pathlib import Path
from .logger_config import setup_logger

_temp_logger = setup_logger("ConfigLoader", "INFO")


def load_config(filename="config.json"):
    """Загружает конфигурацию из файла JSON или создает файл с настройками по умолчанию."""
    default_config = {
        "app": {
            "log_level": "INFO",
            "hotkey": "page up"
        },
        "audio": {
            "fs": 16000,
            "min_duration": 0.8,
            "playback_gain": 1.5,
            "temp_file": "tts_temp.wav"
        },
        "translation": {
            "source_lang": "ru",
            "target_lang": "zh",
            "whisper_model": "small",
            "engine": "argos"
        },
        "tts": {
            "voice": "zh-CN-YunxiNeural",
            "rate": "-20%",
            "volume": "+30%"
        },
        "soundpad": {
            "enabled": True,
            "auto_start": True,
            "soundpad_path": "SoundPad/Soundpad.exe",
            "play_in_speakers": True,
            "play_in_microphone": True,
            "cleanup_after_play": True,
            "playback_timeout": 10,
            "force_stop_before_play": True,
            "playback_delay": 0.2,
            "max_retry_attempts": 3,
        }
    }

    config_path = Path(filename)

    if not config_path.exists():
        _temp_logger.info(
            f"Конфиг {filename} не найден, создаем с настройками по умолчанию")
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2, ensure_ascii=False)
            _temp_logger.info(f"Конфиг создан: {config_path.absolute()}")
            return default_config
        except Exception as e:
            _temp_logger.error(
                f"Ошибка создания конфига: {e}, используем настройки по умолчанию")
            return default_config

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            user_config = json.load(f)

        merged_config = _merge_configs(default_config, user_config)
        _temp_logger.info(f"Конфиг загружен из {config_path.absolute()}")
        return merged_config
    except json.JSONDecodeError as e:
        _temp_logger.error(
            f"Ошибка парсинга JSON: {e}, используем настройки по умолчанию")
        return default_config
    except Exception as e:
        _temp_logger.error(
            f"Ошибка загрузки конфига: {e}, используем настройки по умолчанию")
        return default_config


def _merge_configs(default, user):
    """Рекурсивно объединяет две конфигурации, сохраняя значения по умолчанию для отсутствующих ключей."""
    result = default.copy()

    for key, value in user.items():
        if key in result and isinstance(result[key], dict) and isinstance(
                value, dict):
            result[key] = _merge_configs(result[key], value)
        else:
            result[key] = value

    return result
