"""Основной файл приложения для голосового перевода с воспроизведением через SoundPad."""
import asyncio
import logging
import os
import signal
import sys

from core.config import load_config
from core.logger_config import setup_logger
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


def setup_windows_console():
    """Настройка консоли Windows для корректного отображения Unicode."""
    if sys.platform == 'win32':
        # Устанавливаем кодовую страницу UTF-8
        os.system('chcp 65001 >nul')

        # Альтернативный способ через ctypes
        try:
            import ctypes
            # Устанавливаем кодовую страницу консоли
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleCP(65001)
            kernel32.SetConsoleOutputCP(65001)

            # Пытаемся установить шрифт, поддерживающий Unicode
            LF_FACESIZE = 32
            STD_OUTPUT_HANDLE = -11

            class COORD(ctypes.Structure):
                _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

            class CONSOLE_FONT_INFOEX(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_ulong),
                            ("nFont", ctypes.c_ulong),
                            ("dwFontSize", COORD),
                            ("FontFamily", ctypes.c_uint),
                            ("FontWeight", ctypes.c_uint),
                            ("FaceName", ctypes.c_wchar * LF_FACESIZE)]

            font = CONSOLE_FONT_INFOEX()
            font.cbSize = ctypes.sizeof(CONSOLE_FONT_INFOEX)
            font.nFont = 12
            font.dwFontSize.X = 8
            font.dwFontSize.Y = 16
            font.FontFamily = 54
            font.FontWeight = 400
            font.FaceName = "Lucida Console"

            handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
            kernel32.SetCurrentConsoleFontEx(handle, ctypes.c_long(False),
                                             ctypes.pointer(font))
        except Exception as e:
            print(f"Console setup warning: {e}")


async def async_main():
    """Асинхронная основная функция."""
    setup_windows_console()

    config = load_config()
    log_level = config["app"]["log_level"]

    config_logger = setup_logger("Config", log_level)
    main_logger = setup_logger("Main", log_level)
    soundpad_logger = setup_logger("SoundPad", log_level)
    translator_logger = setup_logger("Translator", log_level)

    # Принудительно устанавливаем UTF-8 для всех выводов
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

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
