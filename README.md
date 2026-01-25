## Конфигурация

Приложение использует JSON-конфигурацию (`config.json`) с секциями:

### app
- `log_level`: Уровень логирования (DEBUG, INFO, WARNING, ERROR)
- `hotkey`: Горячая клавиша для активации записи (по умолчанию "page up")

### translation
- `source_lang`: Исходный язык для распознавания речи (например, "ru", "zh", "en")
- `target_lang`: Целевой язык для перевода (например, "ru", "zh", "en")
- `whisper_model`: Модель Whisper для распознавания речи ("tiny", "base", "small", "medium", "large")

### tts
- `voice`: Голос для синтеза речи. Если оставить пустым, будет выбран автоматически по целевому языку.
- `rate`: Скорость речи (например, "-20%")
- `volume`: Громкость (например, "+30%")

### soundpad
- `play_in_speakers`: Воспроизводить звук в динамики (true/false)
- `play_in_microphone`: Воспроизводить звук в микрофон (true/false)

### Примеры конфигурации

**Перевод с русского на китайский:**
```json
{
  "app": { "log_level": "INFO", "hotkey": "page up" },
  "translation": {
    "source_lang": "ru",
    "target_lang": "zh",
    "whisper_model": "small"
  },
  "tts": {
    "voice": "",  // Автоматически выберет китайский голос
    "rate": "-20%",
    "volume": "+30%"
  }
}