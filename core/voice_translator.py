"""Основной модуль для записи, распознавания, перевода и синтеза речи."""
import asyncio
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from pathlib import Path

import edge_tts
import keyboard
import numpy as np
import sounddevice as sd
import whisper
import argostranslate.package
import argostranslate.translate

from core.constants import (
    AUDIO_SAMPLE_RATE, AUDIO_MIN_DURATION,
    AUDIO_TEMP_FILE, AUDIO_TRIM_TAIL_DURATION,
    AUDIO_MAX_RECORDING_DURATION, AUDIO_BLOCKSIZE,
    HOTKEY_MIN_PRESS_DURATION, HOTKEY_DEBOUNCE_DELAY,
    PLAYBACK_WAIT_BUFFER, PLAYBACK_MAX_TIMEOUT,
    MODELS_DIR,
    DEFAULT_TTS_VOICES, DEFAULT_TTS_RATE, DEFAULT_TTS_VOLUME
)


class AppState(Enum):
    """Состояния приложения."""
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    PLAYING = "playing"


class VoiceTranslator:
    """Основной класс приложения для перевода голоса в реальном времени."""

    def __init__(self, config, soundpad_manager, logger):
        """Инициализирует переводчик голоса с указанной конфигурацией.

        Args:
            config: Конфигурация приложения
            soundpad_manager: Менеджер SoundPad для воспроизведения
            logger: Логгер для записи событий
        """
        self.cfg = config
        self.soundpad = soundpad_manager
        self.logger = logger

        self._state = AppState.IDLE
        self._state_lock = threading.Lock()
        self.audio_buffer = []
        self._buffer_lock = threading.Lock()

        self._hotkey_pressed_time = 0
        self._last_release_time = 0

        self._executor = ThreadPoolExecutor(
            max_workers=3,
            thread_name_prefix="VT-Worker"
        )

        self.model = None
        self._model_loading = True
        self._model_load_failed = False
        self.logger.info(
            f"Loading Whisper model: {self.cfg['translation']['whisper_model']}")
        self._executor.submit(self._load_whisper_model)

        self.translator = None
        self._init_translator()

        self._temp_file = str(Path(AUDIO_TEMP_FILE).resolve())

        self._max_buffer_blocks = int(
            (
                        AUDIO_MAX_RECORDING_DURATION * AUDIO_SAMPLE_RATE) / AUDIO_BLOCKSIZE
        )

        if not self.cfg['tts'].get('voice') or self.cfg['tts'][
            'voice'].strip() == "":
            target_lang = self.cfg['translation']['target_lang']
            voice = DEFAULT_TTS_VOICES.get(target_lang)
            if voice:
                self.cfg['tts']['voice'] = voice
                self.logger.info(
                    f"Auto-selected TTS voice for {target_lang}: {voice}")
            else:
                self.logger.warning(
                    f"No default TTS voice for language: {target_lang}")

        self.logger.debug(f"Temp file: {self._temp_file}")
        self.logger.debug(
            f"Source language: {self.cfg['translation']['source_lang']}")
        self.logger.debug(
            f"Target language: {self.cfg['translation']['target_lang']}")
        self.logger.debug(f"TTS voice: {self.cfg['tts']['voice']}")

    def _init_translator(self):
        """Инициализирует Argos Translate с локальными моделями."""
        source = self.cfg['translation']['source_lang']
        target = self.cfg['translation']['target_lang']

        try:
            models_dir = Path(MODELS_DIR)
            model_file = f"translate-{source}_{target}-1_7.argosmodel"
            model_path = models_dir / model_file

            if not model_path.exists():
                self.logger.error(
                    f"Translation model not found: {model_file}\n"
                    f"Please download the model and place it in {MODELS_DIR}/ directory.\n"
                    f"You can find models at: https://www.argosopentech.com/argospm/index/"
                )
                return

            self.logger.info(f"Installing model: {model_file}")
            argostranslate.package.install_from_path(str(model_path))

            installed_languages = argostranslate.translate.get_installed_languages()
            from_lang = None
            to_lang = None

            for lang in installed_languages:
                if lang.code == source:
                    from_lang = lang
                if lang.code == target:
                    to_lang = lang

            if not from_lang or not to_lang:
                self.logger.error(
                    f"Languages {source} or {target} not found after installation")
                return

            translation = from_lang.get_translation(to_lang)
            if not translation:
                self.logger.error(
                    f"Translation {source}→{target} not available")
                return

            self.translator = (from_lang, to_lang)
            self.logger.info(f"Translator ready: {source} → {target}")

        except Exception as e:
            self.logger.error(f"Translator init failed: {e}")
            self.translator = None

    def _load_whisper_model(self):
        """Загружает модель Whisper в фоновом режиме."""
        try:
            self.model = whisper.load_model(
                self.cfg['translation']['whisper_model'])
            self._model_loading = False
            self.logger.info("Whisper model loaded")
        except Exception as e:
            self.logger.error(f"Whisper load error: {e}")
            self._model_loading = False
            self._model_load_failed = True

    def _get_state(self):
        """Потокобезопасное получение состояния.

        Returns:
            AppState: Текущее состояние приложения
        """
        with self._state_lock:
            return self._state

    def _set_state(self, new_state):
        """Потокобезопасное изменение состояния.

        Args:
            new_state: Новое состояние приложения
        """
        with self._state_lock:
            old_state = self._state
            self._state = new_state
            if old_state != new_state:
                self.logger.debug(
                    f"State: {old_state.value} → {new_state.value}")

    def _change_state(self, expected_state, new_state):
        """Атомарно меняет состояние, если текущее состояние равно expected_state.

        Args:
            expected_state: Ожидаемое текущее состояние
            new_state: Новое состояние

        Returns:
            bool: True если изменение успешно
        """
        with self._state_lock:
            if self._state == expected_state:
                self._state = new_state
                self.logger.debug(
                    f"State change: {expected_state.value} → {new_state.value}")
                return True
        return False

    def _trim_silence_from_end(self, audio, sample_rate):
        """Обрезает тишину в конце аудиозаписи.

        Args:
            audio: Аудиоданные
            sample_rate: Частота дискретизации

        Returns:
            np.ndarray: Обрезанные аудиоданные
        """
        if len(audio) == 0:
            return audio

        energy = np.abs(audio)
        threshold = np.max(energy) * 0.05

        for i in range(len(energy) - 1, -1, -1):
            if energy[i] > threshold:
                end_point = min(i + int(0.2 * sample_rate), len(audio))
                return audio[:end_point]

        return audio[:int(sample_rate * 0.1)]

    def audio_callback(self, indata, frames, time_info, status):
        """Callback функция для захвата аудио с микрофона.

        Args:
            indata: Входные аудиоданные
            frames: Количество кадров
            time_info: Временная информация
            status: Статус устройства
        """
        if status:
            self.logger.debug(f"Audio status: {status}")

        if self._get_state() == AppState.RECORDING:
            with self._buffer_lock:
                if len(self.audio_buffer) < self._max_buffer_blocks:
                    self.audio_buffer.append(indata.copy())
                elif len(self.audio_buffer) == self._max_buffer_blocks:
                    self.logger.warning(
                        f"Recording limit reached ({AUDIO_MAX_RECORDING_DURATION}s)")

    def _transcribe(self, audio):
        """Распознает речь в аудиоданных с помощью Whisper.

        Args:
            audio: Аудиоданные для распознавания

        Returns:
            str or None: Распознанный текст или None при ошибке
        """
        if self.model is None:
            self.logger.error("Whisper model not loaded")
            return None

        if np.max(np.abs(audio)) < 0.01:
            return None

        try:
            result = self.model.transcribe(
                audio,
                language=self.cfg['translation']['source_lang'],
                fp16=False,
                task="transcribe"
            )
            return result["text"].strip()
        except Exception as e:
            self.logger.error(f"Transcription error: {e}")
            return None

    def _translate_sync(self, text):
        """Синхронная обертка для перевода через Argos.

        Args:
            text: Текст для перевода

        Returns:
            str: Переведенный текст или оригинал при ошибке
        """
        if not text or not self.translator:
            return text

        try:
            from_lang, to_lang = self.translator
            translation = from_lang.get_translation(to_lang)

            if translation:
                translated_text = translation.translate(text)
                self.logger.debug(
                    f"Translation: {text[:50]}... → {translated_text[:50]}...")
                return translated_text
            else:
                self.logger.warning(
                    f"Translation {from_lang.code}→{to_lang.code} unavailable")
                return text

        except Exception as e:
            self.logger.error(f"Translation error: {e}")
            return text

    async def _generate_tts(self, text):
        """Синтезирует речь из текста с помощью Edge TTS.

        Args:
            text: Текст для синтеза

        Returns:
            str or None: Путь к созданному аудиофайлу или None при ошибке
        """
        if not text:
            return None

        tts_cfg = self.cfg['tts']

        if not tts_cfg.get('voice') or tts_cfg['voice'].strip() == "":
            target_lang = self.cfg['translation']['target_lang']
            voice = DEFAULT_TTS_VOICES.get(target_lang)
            if not voice:
                self.logger.error(f"No TTS voice for language: {target_lang}")
                return None
            tts_cfg['voice'] = voice
            self.logger.info(f"Using auto-selected voice: {voice}")

        try:
            communicate = edge_tts.Communicate(
                text,
                voice=tts_cfg['voice'],
                volume=tts_cfg.get('volume', DEFAULT_TTS_VOLUME),
                rate=tts_cfg.get('rate', DEFAULT_TTS_RATE)
            )
            await communicate.save(self._temp_file)
            return self._temp_file if os.path.exists(self._temp_file) else None
        except Exception as e:
            self.logger.error(f"TTS error: {e}")
            return None

    async def process_audio(self):
        """Обрабатывает записанный аудиосигнал.

        Выполняет транскрипцию, перевод и синтез речи.
        """
        if self._get_state() != AppState.PROCESSING:
            self.logger.warning(
                "Called process_audio when not in PROCESSING state")
            self._change_state(self._get_state(), AppState.IDLE)
            return

        self._set_state(AppState.PROCESSING)

        try:
            with self._buffer_lock:
                if not self.audio_buffer:
                    self.logger.warning("Empty audio buffer")
                    return
                audio = np.concatenate(self.audio_buffer, axis=0).flatten()
                self.audio_buffer.clear()

            audio = self._trim_silence_from_end(audio, AUDIO_SAMPLE_RATE)
            duration = len(audio) / AUDIO_SAMPLE_RATE

            if duration < AUDIO_MIN_DURATION:
                self.logger.info(f"Recording too short: {duration:.1f}s")
                return

            self.logger.info(f"Processing ({duration:.1f}s)...")

            loop = asyncio.get_running_loop()
            text = await loop.run_in_executor(self._executor, self._transcribe,
                                              audio)

            if not text:
                self.logger.info("No speech detected")
                return

            self.logger.info(
                f"Recognized ({self.cfg['translation']['source_lang']}): {text}")

            try:
                translated = await loop.run_in_executor(self._executor,
                                                        self._translate_sync,
                                                        text)
                self.logger.info(
                    f"Translated ({self.cfg['translation']['target_lang']}): {translated}")
            except Exception as e:
                self.logger.error(f"Translation failed: {e}")
                return

            audio_file = await self._generate_tts(translated)
            if not audio_file:
                self.logger.error("TTS failed")
                return

            self._set_state(AppState.PLAYING)

            future = self.soundpad.play_audio_file(audio_file, async_mode=True)

            try:
                success = await asyncio.wait_for(
                    asyncio.wrap_future(future),
                    timeout=PLAYBACK_MAX_TIMEOUT
                )
                if not success:
                    self.logger.error("Playback failed")
            except asyncio.TimeoutError:
                self.logger.error("Playback timeout")
            except Exception as e:
                self.logger.error(f"Playback error: {e}")
            finally:
                await asyncio.sleep(PLAYBACK_WAIT_BUFFER)
                if os.path.exists(audio_file):
                    try:
                        os.remove(audio_file)
                        self.logger.debug("Temp file cleaned")
                    except OSError as e:
                        self.logger.debug(f"Cleanup error: {e}")

        except Exception as e:
            self.logger.error(f"Processing error: {e}", exc_info=True)
        finally:
            self._set_state(AppState.IDLE)

    def _on_keyboard_event(self, event):
        """Единый обработчик событий клавиатуры (нажатие и отпускание).

        Args:
            event: Событие клавиатуры
        """
        if event.event_type == keyboard.KEY_DOWN:
            if (
                    time.time() - self._last_release_time > HOTKEY_DEBOUNCE_DELAY and
                    not self._model_loading and not self._model_load_failed):

                if self._change_state(AppState.IDLE, AppState.RECORDING):
                    self._hotkey_pressed_time = time.time()
                    with self._buffer_lock:
                        self.audio_buffer.clear()
                    self.logger.debug("Recording started")

        elif event.event_type == keyboard.KEY_UP:
            current_time = time.time()
            press_duration = current_time - self._hotkey_pressed_time
            self._last_release_time = current_time

            if self._get_state() == AppState.RECORDING:
                if press_duration >= HOTKEY_MIN_PRESS_DURATION:
                    if self._change_state(AppState.RECORDING,
                                          AppState.PROCESSING):
                        self.logger.info(
                            f"Recording finished ({press_duration:.1f}s)")

                        if hasattr(self, 'loop') and self.loop.is_running():
                            asyncio.run_coroutine_threadsafe(
                                self.process_audio(), self.loop)
                        else:
                            self.logger.error("Event loop unavailable")
                            self._change_state(AppState.PROCESSING,
                                               AppState.IDLE)
                else:
                    if self._change_state(AppState.RECORDING, AppState.IDLE):
                        with self._buffer_lock:
                            self.audio_buffer.clear()
                        self.logger.debug("Short key press ignored")

    async def run(self):
        """Основной цикл работы приложения."""
        if self._model_load_failed:
            self.logger.error("Whisper model failed to load")
            return

        if not self.translator:
            self.logger.error("Translator not initialized. Cannot start.")
            return

        while self._model_loading:
            await asyncio.sleep(0.5)

        if self.model is None:
            self.logger.error("Whisper model not available")
            return

        hotkey = self.cfg['app']['hotkey']
        voice = self.cfg['tts']['voice']

        self.logger.info(f"Ready. Hold '{hotkey}' to record")
        self.logger.info(f"TTS Voice: {voice}")

        self.loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()

        try:
            keyboard.unhook_all()
            keyboard.hook_key(hotkey, self._on_keyboard_event, suppress=False)
        except Exception as e:
            self.logger.error(f"Keyboard hook error: {e}")
            return

        try:
            with sd.InputStream(
                    samplerate=AUDIO_SAMPLE_RATE,
                    channels=1,
                    dtype='float32',
                    callback=self.audio_callback,
                    blocksize=AUDIO_BLOCKSIZE
            ):
                await self._stop_event.wait()
        except Exception as e:
            self.logger.error(f"Audio stream error: {e}", exc_info=True)
        finally:
            try:
                keyboard.unhook_all()
            except Exception:
                pass

    def shutdown(self):
        """Освобождает ресурсы при завершении работы."""
        self.logger.info("Shutting down...")

        if hasattr(self, '_stop_event'):
            self._stop_event.set()

        try:
            keyboard.unhook_all()
        except Exception:
            pass

        self._executor.shutdown(wait=True, cancel_futures=True)
        if os.path.exists(self._temp_file):
            try:
                os.remove(self._temp_file)
            except OSError:
                pass
