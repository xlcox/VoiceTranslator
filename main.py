"""Основной файл приложения для голосового перевода с воспроизведением через SoundPad."""
import asyncio
import logging
import signal
import sys

from core.logger_config import setup_logger
from core.config import load_config
from core.soundpad_manager import SoundpadManager
from core.voice_translator import VoiceTranslator


def signal_handler(signum, frame):
    """Обработчик сигналов для корректного завершения.

    Args:
        signum: Номер сигнала
        frame: Текущий стек вызовов
    """
    print("\nTermination signal received. Stopping...")
    sys.exit(0)


async def async_main():
    """Асинхронная основная функция."""
    config = load_config()

    log_level = config["app"]["log_level"]

    config_logger = setup_logger("Config", log_level)
    main_logger = setup_logger("Main", log_level)
    soundpad_logger = setup_logger("SoundPad", log_level)
    translator_logger = setup_logger("Translator", log_level)

    main_logger.info("=" * 50)
    main_logger.info("Voice Translator with SoundPad")
    main_logger.info(f"Log level: {log_level}")
    main_logger.info("=" * 50)

    soundpad_mgr = None
    app = None

    try:
        soundpad_mgr = SoundpadManager(config, soundpad_logger)
        app = VoiceTranslator(config, soundpad_mgr, translator_logger)
        await app.run()
    except KeyboardInterrupt:
        main_logger.info("Interrupted by user")
    except Exception as e:
        main_logger.error(f"Critical error: {e}")
        if main_logger.level <= logging.DEBUG:
            main_logger.error("Full traceback:", exc_info=True)
    finally:
        main_logger.info("-" * 50)
        if app:
            app.shutdown()
        if soundpad_mgr:
            soundpad_mgr.cleanup()
        main_logger.info("Application stopped")
        main_logger.info("=" * 50)


def main():
    """Основная функция запуска приложения."""
    signal.signal(signal.SIGINT, signal_handler)
    if sys.platform != 'win32':
        signal.signal(signal.SIGTERM, signal_handler)

    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Critical startup error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
