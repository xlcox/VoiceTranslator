# Voice Translator

Голосовой переводчик с воспроизведением через SoundPad. Приложение записывает голос, распознает речь с помощью Whisper, переводит текст через Argos Translate и воспроизводит перевод через SoundPad с использованием синтеза речи Edge TTS.

### Текущие проблемы
1. При первом запуске с отсутствием файла конфига не выбирается голос tts.
2. Большое потребление ресурсов
3. Ненормальное завершение программы при нажатии на крестик

Установка

1. Создайте директорию `models/`
2. Скачайте модели перевода с https://www.argosopentech.com/argospm/index/
3. Поместите файлы `.argosmodel` в директорию `models/`
Пример для перевода с русского на китайский: `translate-ru_zh-1_7.argosmodel`

Конфигурация

Приложение использует файл `config.json`:

Секция `app`
- `log_level`: Уровень логирования (DEBUG, INFO, WARNING, ERROR)
- `hotkey`: Горячая клавиша для активации записи (по умолчанию "page up")

Секция `translation`
- `source_lang`: Исходный язык для распознавания речи (коды: ru, zh, en, ja, ko, es, fr, de, it, pt, ar)
- `target_lang`: Целевой язык для перевода
- `whisper_model`: Модель Whisper для распознавания ("tiny", "base", "small", "medium", "large")

Секция `tts`
- `voice`: Голос для синтеза речи (пусто для автоматического выбора)
- `rate`: Скорость речи (например, "-20%")
- `volume`: Громкость (например, "+30%")

Секция `soundpad`
- `play_in_speakers`: Воспроизводить звук в динамики (true/false)
- `play_in_microphone`: Воспроизводить звук в микрофон (true/false)

Сборка исполняемого файла Windows

```
.\build.bat
```

После сборки:
1. Скопируйте модели перевода в `dist/VoiceTranslator/models/`
2. Скопируйте папку SoundPad в `dist/VoiceTranslator/SoundPad/`
3. Запустите `dist/VoiceTranslator/VoiceTranslator.exe`

Структура проекта

```
voice-translator/
├── core/                    # Основные модули
│   ├── config.py           # Управление конфигурацией
│   ├── constants.py        # Константы приложения
│   ├── logger_config.py    # Настройка логирования
│   ├── soundpad_manager.py # Управление SoundPad
│   └── voice_translator.py # Основная логика перевода
├── models/                  # Модели перевода Argos
├── logs/                   # Логи приложения
├── SoundPad/              # SoundPad (дополнительно)
├── build.bat              # Скрипт сборки для Windows
├── config.json            # Конфигурация приложения
├── main.py                # Точка входа
├── requirements.txt       # Зависимости Python
├── VoiceTranslator.spec  # Конфигурация PyInstaller
└── README.md             # Документация
```
