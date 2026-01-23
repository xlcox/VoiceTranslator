"""Основной модуль для записи, распознавания, перевода и синтеза речи."""
import asyncio
import os
import threading
import time

import edge_tts
import keyboard
import numpy as np
import sounddevice as sd
import soundfile as sf
from deep_translator import GoogleTranslator
import whisper


class VoiceTranslator:
    """Основной класс приложения для перевода голоса в реальном времени."""

    def __init__(self, config, soundpad_manager, logger):
        """Инициализирует переводчик голоса с указанной конфигурацией."""
        self.cfg = config
        self.soundpad = soundpad_manager
        self.logger = logger
        self.audio_buffer = []
        self.recording = False
        self.processing = False
        self._hotkey_pressed_time = 0
        self._min_hotkey_press = 0.1

        self.logger.info(
            f"Загрузка модели Whisper: {self.cfg['translation']['whisper_model']}")
        self.model = whisper.load_model(
            self.cfg['translation']['whisper_model'])

        self.translator = GoogleTranslator(
            source=self.cfg['translation']['source_lang'],
            target=self.cfg['translation']['target_lang']
        )
        self.logger.info("Система инициализирована.")

    def audio_callback(self, indata, frames, time_info, status):
        """Callback функция для захвата аудио с микрофона."""
        if status:
            self.logger.warning(f"Статус аудиоустройства: {status}")
        if self.recording and not self.processing:
            self.audio_buffer.append(indata.copy())

    def _transcribe(self, audio):
        """Распознает речь в аудиоданных с помощью Whisper."""
        if np.max(np.abs(audio)) < 0.01:
            return None
        result = self.model.transcribe(audio, language=self.cfg['translation'][
            'source_lang'])
        return result["text"].strip()

    async def _generate_tts(self, text):
        """Синтезирует речь из текста с помощью Edge TTS."""
        tts_cfg = self.cfg['tts']
        communicate = edge_tts.Communicate(
            text,
            voice=tts_cfg['voice'],
            volume=tts_cfg['volume'],
            rate=tts_cfg['rate']
        )
        filename = self.cfg['audio']['temp_file']
        await communicate.save(filename)
        return filename if os.path.exists(filename) else None

    async def process_audio(self):
        """Обрабатывает записанный аудиосигнал: распознает, переводит и воспроизводит."""
        self.processing = True
        try:
            if not self.audio_buffer:
                self.processing = False
                return

            audio = np.concatenate(self.audio_buffer, axis=0).flatten()
            self.audio_buffer = []

            fs = self.cfg['audio']['fs']
            duration = len(audio) / fs

            if duration < self.cfg['audio']['min_duration']:
                self.logger.debug(
                    f"Запись слишком короткая: {duration:.2f} сек.")
                self.processing = False
                return

            self.logger.info("Начало обработки аудио...")

            text = self._transcribe(audio)
            if not text:
                self.logger.info(
                    "Речь не распознана (тишина или неразборчиво).")
                self.processing = False
                return

            self.logger.info(f"Распознанный текст: {text}")

            try:
                translated = self.translator.translate(text)
                self.logger.info(f"Переведенный текст: {translated}")
            except Exception as e:
                self.logger.error(f"Ошибка перевода: {e}")
                self.processing = False
                return

            audio_file = await self._generate_tts(translated)
            if audio_file:
                future = self.soundpad.play_audio_file(audio_file,
                                                       async_mode=True)

                def cleanup_after_play(f):
                    """Очистка временных файлов после воспроизведения."""
                    try:
                        success = f.result(timeout=self.cfg['soundpad'].get(
                            'playback_timeout', 10))
                        if success:
                            self.logger.info(
                                "Аудио успешно воспроизведено через SoundPad.")
                    except Exception as e:
                        self.logger.error(f"Ошибка при воспроизведении: {e}")

                    if os.path.exists(audio_file) and self.cfg.get("soundpad",
                                                                   {}).get(
                        "cleanup_after_play", True):
                        try:
                            os.remove(audio_file)
                            self.logger.debug("Временный аудиофайл удален.")
                        except OSError:
                            pass

                t = threading.Thread(target=cleanup_after_play, args=(future,))
                t.daemon = True
                t.start()

        except Exception as e:
            self.logger.error(f"Ошибка обработки аудио: {e}", exc_info=True)
        finally:
            self.processing = False

    async def run(self):
        """Основной цикл работы приложения с захватом аудио по горячей клавише."""
        hotkey = self.cfg['app']['hotkey']
        fs = self.cfg['audio']['fs']

        self.logger.info(
            f"Система готова к работе. Удерживайте клавишу '{hotkey}' для записи.")
        self.logger.info(
            f"SoundPad включен: {self.cfg.get('soundpad', {}).get('enabled', True)}")

        play_speakers = self.cfg.get('soundpad', {}).get('play_in_speakers',
                                                         True)
        play_mic = self.cfg.get('soundpad', {}).get('play_in_microphone', True)
        self.logger.info(
            f"Воспроизведение: динамики={play_speakers}, микрофон={play_mic}")

        with sd.InputStream(samplerate=fs, channels=1, dtype='float32',
                            callback=self.audio_callback):
            while True:
                try:
                    is_pressed = keyboard.is_pressed(hotkey)
                    current_time = time.time()

                    if is_pressed and not self.recording and not self.processing:
                        self.recording = True
                        self.audio_buffer = []
                        self._hotkey_pressed_time = current_time
                        self.logger.debug("Начало записи аудио.")

                    elif not is_pressed and self.recording:
                        press_duration = current_time - self._hotkey_pressed_time
                        if press_duration >= self._min_hotkey_press:
                            self.recording = False
                            self.logger.debug("Окончание записи аудио.")
                            await self.process_audio()
                        else:
                            self.recording = False
                            self.audio_buffer = []
                            self.logger.debug(
                                "Слишком короткое нажатие клавиши, запись отменена.")

                except Exception as e:
                    self.logger.error(f"Ошибка в основном цикле: {e}")

                await asyncio.sleep(0.05)
