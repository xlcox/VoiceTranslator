"""Основной файл приложения для голосового перевода с воспроизведением через SoundPad."""
import asyncio

from core.config import load_config
from core.logger_config import setup_logger
from core.soundpad_manager import SoundpadManager
from core.voice_translator import VoiceTranslator


def main():
    """Основная функция запуска приложения."""
    config = load_config()
    logger = setup_logger("VoiceTranslator", config["app"]["log_level"])

    soundpad_mgr = SoundpadManager(config, logger)
    app = VoiceTranslator(config, soundpad_mgr, logger)

    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        logger.info("Принудительное завершение работы.")
    except Exception as e:
        logger.error(f"Критическая ошибка в основном потоке: {e}")
    finally:
        soundpad_mgr.cleanup()


if __name__ == "__main__":
    main()
