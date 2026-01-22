import sounddevice as sd
import numpy as np
import edge_tts
import whisper
from deep_translator import GoogleTranslator
import keyboard
import asyncio
import soundfile as sf
import os
import json
from dataclasses import dataclass

# Импортируем наш новый модуль логирования
from logger_config import setup_logger


# ---------------- Загрузка Конфигурации ----------------
def load_config(filename="config.json"):
    # Если файла нет, создадим базовый, чтобы программа не упала
    default_config = {
        "app": {"log_level": "INFO", "hotkey": "page up"},
        "audio": {"fs": 16000, "min_duration": 0.8, "playback_gain": 1.5,
                  "temp_file": "tts_temp.wav"},
        "translation": {"source_lang": "ru", "target_lang": "zh-CN",
                        "whisper_model": "small"},
        "tts": {"voice": "zh-CN-YunxiNeural", "rate": "-20%", "volume": "+30%"}
    }

    if not os.path.exists(filename):
        print(f"⚠️ Файл {filename} не найден. Создан файл по умолчанию.")
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=4, ensure_ascii=False)
        return default_config

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(
            f"❌ Ошибка чтения конфига: {e}. Используются настройки по умолчанию.")
        return default_config


# Загружаем настройки
CFG = load_config()

# Настраиваем логгер, используя уровень из конфига
logger = setup_logger("VoiceTranslator", CFG["app"]["log_level"])


# ---------------- Класс Переводчика ----------------
class VoiceTranslator:
    def __init__(self, config):
        self.cfg = config
        self.audio_buffer = []
        self.recording = False

        logger.info(
            f"Загрузка модели Whisper ({self.cfg['translation']['whisper_model']})...")
        self.model = whisper.load_model(
            self.cfg['translation']['whisper_model'])

        self.translator = GoogleTranslator(
            source=self.cfg['translation']['source_lang'],
            target=self.cfg['translation']['target_lang']
        )
        logger.info("Система инициализирована.")

    def audio_callback(self, indata, frames, time_info, status):
        if status:
            logger.warning(f"Audio status: {status}")
        if self.recording:
            self.audio_buffer.append(indata.copy())

    def _transcribe(self, audio):
        if np.max(np.abs(audio)) < 0.01:
            return None
        # Используем язык из конфига
        result = self.model.transcribe(audio, language=self.cfg['translation'][
            'source_lang'])
        return result["text"].strip()

    async def _generate_tts(self, text):
        tts_cfg = self.cfg['tts']
        communicate = edge_tts.Communicate(
            text,
            voice=tts_cfg['voice'],
            volume=tts_cfg['volume'],
            rate=tts_cfg['rate']
        )
        filename = self.cfg['audio']['temp_file']
        await communicate.save(filename)
        return os.path.exists(filename)

    def _play_audio(self):
        filename = self.cfg['audio']['temp_file']
        if not os.path.exists(filename):
            return

        try:
            data, sr = sf.read(filename, dtype='float32')
            data *= self.cfg['audio']['playback_gain']
            data = np.clip(data, -1.0, 1.0)
            sd.play(data, sr)
            sd.wait()
        except Exception as e:
            logger.error(f"Ошибка воспроизведения: {e}")
        finally:
            try:
                os.remove(filename)
            except OSError:
                pass

    async def process_audio(self):
        try:
            if not self.audio_buffer:
                return

            audio = np.concatenate(self.audio_buffer, axis=0).flatten()
            self.audio_buffer = []

            fs = self.cfg['audio']['fs']
            duration = len(audio) / fs

            if duration < self.cfg['audio']['min_duration']:
                logger.debug(
                    f"Запись слишком короткая: {duration:.2f}с")  # DEBUG уровень
                return

            logger.info("Начало обработки...")

            # 1. Распознавание
            text = self._transcribe(audio)
            if not text:
                logger.info("Тишина или неразборчиво")
                return
            logger.info(f"🎤 Исходный текст: {text}")

            # 2. Перевод
            translated = self.translator.translate(text)
            logger.info(f"🌏 Перевод: {translated}")

            # 3. Озвучка
            if await self._generate_tts(translated):
                self._play_audio()

        except Exception as e:
            logger.error(f"Ошибка процессинга: {e}", exc_info=True)

    async def run(self):
        hotkey = self.cfg['app']['hotkey']
        fs = self.cfg['audio']['fs']

        logger.info(f"Готов к работе. Удерживайте клавишу '{hotkey}'")

        with sd.InputStream(samplerate=fs, channels=1, dtype='float32',
                            callback=self.audio_callback):
            while True:
                is_pressed = keyboard.is_pressed(hotkey)

                if is_pressed and not self.recording:
                    self.recording = True
                    self.audio_buffer = []
                    logger.debug("▶️ Старт записи")  # DEBUG уровень

                elif not is_pressed and self.recording:
                    self.recording = False
                    logger.debug("⏹️ Стоп записи")
                    await self.process_audio()

                await asyncio.sleep(0.05)


if __name__ == "__main__":
    app = VoiceTranslator(CFG)
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        logger.info("Принудительное завершение.")
