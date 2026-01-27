"""Константы приложения."""

# Настройки аудио
AUDIO_SAMPLE_RATE = 16000  # Частота дискретизации для Whisper (Гц)
AUDIO_MIN_DURATION = 0.8  # Минимальная длительность записи для обработки (сек)
AUDIO_PLAYBACK_GAIN = 1.5  # Коэффициент усиления воспроизведения
AUDIO_TEMP_FILE = "tts_temp.wav"  # Временный файл для TTS

# Настройки SoundPad
SOUNDPAD_AUTO_START = True  # Автозапуск SoundPad при необходимости
SOUNDPAD_PATH = "SoundPad/Soundpad.exe"  # Путь к исполняемому файлу SoundPad
SOUNDPAD_PLAYBACK_TIMEOUT = 10  # Таймаут ожидания воспроизведения (сек)
SOUNDPAD_FORCE_STOP_BEFORE_PLAY = True  # Останавливать текущее воспроизведение перед новым
SOUNDPAD_PLAYBACK_DELAY = 0.2  # Задержка перед воспроизведением (сек)
SOUNDPAD_MAX_RETRY_ATTEMPTS = 3  # Максимальное количество попыток воспроизведения

# Настройки перевода
TRANSLATION_ENGINE = "argos"  # Используемый движок перевода

# Параметры обработки аудио
AUDIO_SILENCE_THRESHOLD = 0.01  # Порог определения тишины (от 0 до 1)
AUDIO_TRIM_TAIL_DURATION = 0.5  # Длительность обрезки тишины в конце (сек)
AUDIO_MAX_RECORDING_DURATION = 60  # Максимальная длительность записи (сек)
AUDIO_BLOCKSIZE = 1024  # Размер блока для захвата аудио (семплы)

# Параметры горячей клавиши
HOTKEY_MIN_PRESS_DURATION = 0.1  # Минимальная длительность нажатия для активации (сек)
HOTKEY_DEBOUNCE_DELAY = 0.05  # Задержка для подавления дребезга (сек)

# Параметры воспроизведения
PLAYBACK_WAIT_BUFFER = 0.5  # Дополнительное время ожидания после воспроизведения (сек)
PLAYBACK_MAX_TIMEOUT = 30  # Максимальный таймаут ожидания воспроизведения (сек)

# Пути и директории
LOGS_DIR = "logs"  # Директория для логов
MODELS_DIR = "models"  # Директория для моделей перевода
CONFIG_FILE = "config.json"  # Файл конфигурации

# Настройки TTS (голоса по умолчанию для языков)
DEFAULT_TTS_VOICES = {
    "ru": "ru-RU-SvetlanaNeural",  # Русский мужской голос
    "zh": "zh-CN-YunxiNeural",  # Китайский мужской голос
    "en": "en-US-ChristopherNeural",  # Английский мужской голос
    "ja": "ja-JP-KeitaNeural",  # Японский мужской голос
    "ko": "ko-KR-InJoonNeural",  # Корейский мужской голос
    "es": "es-ES-AlvaroNeural",  # Испанский мужской голос
    "fr": "fr-FR-HenriNeural",  # Французский мужской голос
    "de": "de-DE-ConradNeural",  # Немецкий мужской голос
    "it": "it-IT-DiegoNeural",  # Итальянский мужской голос
    "pt": "pt-BR-AntonioNeural",  # Португальский мужской голос
    "ar": "ar-SA-HamedNeural",  # Арабский мужской голос
}

# Настройки TTS по умолчанию (если не заданы в конфиге)
DEFAULT_TTS_RATE = "-20%"  # Скорость воспроизведения по умолчанию
DEFAULT_TTS_VOLUME = "+30%"  # Громкость по умолчанию
