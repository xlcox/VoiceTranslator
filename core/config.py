"""Конфигурационный модуль для загрузки и управления настройками приложения."""
import json
import os

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
            "target_lang": "zh-CN",
            "whisper_model": "small"
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
            "playback_timeout": 10
        }
    }

    if not os.path.exists(filename):
        _temp_logger.info(
            f"Конфигурационный файл {filename} не найден, создается файл с настройками по умолчанию.")
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=4, ensure_ascii=False)
        return default_config

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            config = json.load(f)

        merged_config = _merge_configs(default_config, config)

        if config != merged_config:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(merged_config, f, indent=4, ensure_ascii=False)
            _temp_logger.info("Конфигурация обновлена новыми полями")

        return merged_config

    except Exception as e:
        _temp_logger.error(
            f"Ошибка чтения конфигурационного файла: {e}. Используются настройки по умолчанию.")
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
