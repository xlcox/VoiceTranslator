import logging
import sys


def setup_logger(name, log_level_str="INFO"):
    # Преобразуем строку уровня (напр. "DEBUG") в константу logging
    level = getattr(logging, log_level_str.upper(), logging.INFO)

    # Формат логов
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(module)s | %(message)s",
        datefmt="%H:%M:%S"
    )

    # Создаем логгер
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Очищаем старые хендлеры, чтобы не дублировать логи при перезагрузке
    if logger.hasHandlers():
        logger.handlers.clear()

    # Вывод в файл
    file_handler = logging.FileHandler("app.log", encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Вывод в консоль
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger
