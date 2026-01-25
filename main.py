"""Основной файл приложения для голосового перевода с воспроизведением через SoundPad."""
import asyncio
import signal
import sys

from core.config import load_config
from core.logger_config import setup_logger
from core.soundpad_manager import SoundpadManager
from core.voice_translator import VoiceTranslator


def signal_handler(signum, frame):
    """Обработчик сигналов для корректного завершения."""
    print("\nПолучен сигнал завершения. Остановка приложения...")
    sys.exit(0)


async def async_main():
    """Асинхронная основная функция."""
    config = load_config()
    logger = setup_logger("VoiceTranslator", config["app"]["log_level"])

    soundpad_mgr = None
    app = None

    try:
        soundpad_mgr = SoundpadManager(config, logger)
        app = VoiceTranslator(config, soundpad_mgr, logger)
        await app.run()
    except KeyboardInterrupt:
        logger.info("Получен сигнал прерывания (Ctrl+C).")
    except Exception as e:
        logger.error(f"Критическая ошибка в основном потоке: {e}",
                     exc_info=True)
    finally:
        if app:
            app.shutdown()
        if soundpad_mgr:
            soundpad_mgr.cleanup()
        logger.info("Приложение завершено.")


def main():
    """Основная функция запуска приложения."""
    # Регистрация обработчиков сигналов
    signal.signal(signal.SIGINT, signal_handler)
    if sys.platform != 'win32':
        signal.signal(signal.SIGTERM, signal_handler)

    # Для Windows: настройка политики event loop
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # Запуск асинхронного приложения
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass  # Уже обработано в async_main
    except Exception as e:
        print(f"Критическая ошибка при запуске: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
