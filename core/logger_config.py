"""Модуль настройки логирования для приложения."""
import logging
import os
import sys


def setup_logger(name, log_level_str="INFO"):
    """Создает и настраивает логгер с указанным именем и уровнем логирования."""
    level = getattr(logging, log_level_str.upper(), logging.INFO)

    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(module)-15s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.hasHandlers():
        logger.handlers.clear()

    file_handler = logging.FileHandler(os.path.join(log_dir, "app.log"),
                                       encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger
