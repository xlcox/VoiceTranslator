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


class AppState(Enum):
    """Состояния приложения."""
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    PLAYING = "playing"


class VoiceTranslator:
    """Основной класс приложения для перевода голоса в реальном времени."""

    def __init__(self, config, soundpad_manager, logger):
        """Инициализирует переводчик голоса с указанной конфигурацией."""
        self.cfg = config
        self.soundpad = soundpad_manager
        self.logger = logger

        self._state = AppState.IDLE
        self._state_lock = threading.Lock()
        self.audio_buffer = []
        self._buffer_lock = threading.Lock()

        self._hotkey_pressed_time = 0
        self._min_hotkey_press = 0.1
        self._last_release_time = 0
        self._debounce_delay = 0.05

        self._executor = ThreadPoolExecutor(max_workers=3,
                                            thread_name_prefix="VT-Worker")

        self.model = None
        self._model_loading = True
        self._model_load_failed = False
        self.logger.info(
            f"Загрузка модели Whisper: {self.cfg['translation']['whisper_model']}")
        self._executor.submit(self._load_whisper_model)

        self.translator = None
        self._init_translator()

        self._fs = self.cfg['audio']['fs']
        self._min_duration = self.cfg['audio']['min_duration']

        # Используем абсолютный путь для временного файла
        self._temp_file = str(Path(self.cfg['audio']['temp_file']).resolve())

        self._silence_threshold = 0.01
        self._trim_tail_duration = 0.5

        # Вычисляем максимальный размер буфера для записи
        # Позволяем записывать до 60 секунд (настраиваемо)
        self._max_recording_duration = 60  # секунд
        self._blocksize = 1024  # будет использоваться в run()
        # Максимум блоков = (макс_длительность * частота) / размер_блока
        self._max_buffer_blocks = int(
            (self._max_recording_duration * self._fs) / self._blocksize
        )

        self.logger.info("Система инициализирована.")
        self.logger.debug(f"Путь к временному файлу TTS: {self._temp_file}")
        self.logger.debug(
            f"Максимальная длительность записи: {self._max_recording_duration} сек "
            f"({self._max_buffer_blocks} блоков)")

    def _init_translator(self):
        """Инициализирует Argos Translate с локальными моделями согласно документации."""
        self.logger.info("Использование Argos Translate (офлайн)")
        source = self.cfg['translation']['source_lang']
        target = self.cfg['translation']['target_lang']

        try:
            # 1. Пытаемся найти уже установленную пару языков
            installed_languages = argostranslate.translate.get_installed_languages()
            from_lang = next(
                (l for l in installed_languages if l.code == source), None)
            to_lang = next(
                (l for l in installed_languages if l.code == target), None)

            if from_lang and to_lang:
                self.translator = (from_lang, to_lang)
                self.logger.info(f"Переводчик готов: {source} -> {target}")
                return

            # 2. Если языки не установлены, ищем и устанавливаем модель
            self.logger.info(
                f"Модель для перевода {source}->{target} не найдена, выполняем установку...")

            # Получаем список доступных пакетов
            available_packages = argostranslate.package.get_available_packages()
            needed_package = next(
                (p for p in available_packages
                 if p.from_code == source and p.to_code == target),
                None
            )

            if needed_package:
                self.logger.info(
                    f"Найдена модель: {needed_package}. Начало загрузки...")
                # Библиотека сама скачает и установит модель
                needed_package.install()
                self.logger.info("Модель успешно установлена.")
            else:
                # Резервный вариант: проверяем локальную папку models
                models_dir = Path("models")
                model_file = f"translate-{source}_{target}-1_7.argosmodel"
                model_path = models_dir / model_file

                if model_path.exists():
                    self.logger.info(
                        f"Устанавливаем локальную модель: {model_file}")
                    argostranslate.package.install_from_path(str(model_path))
                else:
                    raise RuntimeError(
                        f"Не удалось найти модель перевода {source}->{target}. "
                        f"Проверьте наличие файла {model_file} в папке models или "
                        f"установите модель через argostranslate.package.update_package_index()"
                    )

            # 3. Повторная инициализация после установки
            installed_languages = argostranslate.translate.get_installed_languages()
            from_lang = next(
                (l for l in installed_languages if l.code == source), None)
            to_lang = next(
                (l for l in installed_languages if l.code == target), None)

            if not from_lang or not to_lang:
                raise RuntimeError(
                    f"Не удалось найти языки после установки модели: {source} -> {target}"
                )

            self.translator = (from_lang, to_lang)
            self.logger.info(
                f"Переводчик инициализирован: {source} -> {target}")

        except Exception as e:
            self.logger.error(
                f"Критическая ошибка инициализации Argos Translate: {e}")
            raise RuntimeError(f"Не удалось инициализировать переводчик: {e}")

    def _load_whisper_model(self):
        """Загружает модель Whisper в фоновом режиме."""
        try:
            self.model = whisper.load_model(
                self.cfg['translation']['whisper_model'])
            self._model_loading = False
            self.logger.info("Модель Whisper успешно загружена.")
        except Exception as e:
            self.logger.error(f"Ошибка загрузки модели Whisper: {e}")
            self._model_loading = False
            self._model_load_failed = True

    def _get_state(self):
        """Потокобезопасное получение состояния."""
        with self._state_lock:
            return self._state

    def _set_state(self, new_state):
        """Потокобезопасное изменение состояния."""
        with self._state_lock:
            old_state = self._state
            self._state = new_state
            if old_state != new_state:
                self.logger.debug(
                    f"Изменение состояния: {old_state.value} -> {new_state.value}")

    def _can_start_recording(self):
        """Проверяет возможность начала записи."""
        return (self._get_state() == AppState.IDLE and
                not self._model_loading and
                not self._model_load_failed)

    def _trim_silence_from_end(self, audio, sample_rate):
        """Обрезает тишину в конце аудиозаписи."""
        if len(audio) == 0:
            return audio

        # Уменьшаем порог тишины для лучшего обнаружения
        energy = np.abs(audio)
        threshold = np.max(energy) * 0.05  # 5% от максимальной энергии

        # Ищем последнюю точку с энергией выше порога
        for i in range(len(energy) - 1, -1, -1):
            if energy[i] > threshold:
                # Оставляем небольшую паузу после последнего звука
                end_point = min(i + int(0.2 * sample_rate), len(audio))
                return audio[:end_point]

        return audio[:int(
            sample_rate * 0.1)]  # Возвращаем короткий сегмент если все тихо

    def audio_callback(self, indata, frames, time_info, status):
        """Callback функция для захвата аудио с микрофона."""
        if status:
            self.logger.warning(f"Статус аудиоустройства: {status}")

        if self._get_state() == AppState.RECORDING:
            with self._buffer_lock:
                # Ограничиваем размер буфера для предотвращения утечек памяти
                # Теперь лимит основан на максимальной длительности записи
                if len(self.audio_buffer) < self._max_buffer_blocks:
                    self.audio_buffer.append(indata.copy())
                else:
                    # Если достигли лимита, логируем предупреждение
                    if len(self.audio_buffer) == self._max_buffer_blocks:
                        self.logger.warning(
                            f"Достигнут максимальный лимит записи "
                            f"({self._max_recording_duration} сек). "
                            f"Запись продолжается, но новые данные не сохраняются."
                        )

    def _transcribe(self, audio):
        """Распознает речь в аудиоданных с помощью Whisper."""
        if self.model is None:
            self.logger.error("Модель Whisper не загружена")
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
            self.logger.error(f"Ошибка транскрипции: {e}")
            return None

    def _translate_sync(self, text):
        """Синхронная обертка для перевода через Argos."""
        if not text or not self.translator:
            return text

        try:
            from_lang, to_lang = self.translator
            translation = from_lang.get_translation(to_lang)

            if translation:
                return translation.translate(text)
            else:
                # Пробуем найти альтернативный путь перевода
                self.logger.warning(
                    f"Прямой перевод {from_lang.code} -> {to_lang.code} недоступен")
                return text
        except Exception as e:
            self.logger.error(f"Ошибка перевода: {e}")
            return text

    async def _generate_tts(self, text):
        """Синтезирует речь из текста с помощью Edge TTS."""
        if not text:
            return None

        tts_cfg = self.cfg['tts']
        try:
            communicate = edge_tts.Communicate(
                text,
                voice=tts_cfg['voice'],
                volume=tts_cfg['volume'],
                rate=tts_cfg['rate']
            )
            await communicate.save(self._temp_file)
            return self._temp_file if os.path.exists(self._temp_file) else None
        except Exception as e:
            self.logger.error(f"Ошибка синтеза речи: {e}")
            return None

    async def process_audio(self):
        """Обрабатывает записанный аудиосигнал."""
        self._set_state(AppState.PROCESSING)

        try:
            with self._buffer_lock:
                if not self.audio_buffer:
                    self.logger.warning("Аудиобуфер пуст")
                    return
                audio = np.concatenate(self.audio_buffer, axis=0).flatten()
                self.audio_buffer.clear()

            audio = self._trim_silence_from_end(audio, self._fs)
            duration = len(audio) / self._fs

            if duration < self._min_duration:
                self.logger.debug(
                    f"Запись слишком короткая: {duration:.2f} сек.")
                return

            self.logger.info(f"Обработка аудио ({duration:.2f} сек)...")

            loop = asyncio.get_running_loop()
            text = await loop.run_in_executor(self._executor, self._transcribe,
                                              audio)

            if not text:
                self.logger.info("Речь не распознана.")
                return

            self.logger.info(f"Распознанный текст: {text}")

            try:
                translated = await loop.run_in_executor(self._executor,
                                                        self._translate_sync,
                                                        text)
                self.logger.info(f"Переведенный текст: {translated}")
            except Exception as e:
                self.logger.error(f"Ошибка перевода: {e}")
                return

            audio_file = await self._generate_tts(translated)
            if not audio_file:
                self.logger.error("Ошибка синтеза речи")
                return

            self._set_state(AppState.PLAYING)
            self.logger.info("Запуск воспроизведения через SoundPad...")

            future = self.soundpad.play_audio_file(audio_file, async_mode=True)

            try:
                success = await asyncio.wait_for(asyncio.wrap_future(future),
                                                 timeout=30)
                if success:
                    self.logger.info("Аудио успешно воспроизведено.")
                else:
                    self.logger.error("Ошибка воспроизведения.")
            except asyncio.TimeoutError:
                self.logger.error("Превышен таймаут воспроизведения")
            except Exception as e:
                self.logger.error(f"Ошибка при воспроизведении: {e}")
            finally:
                # Удаляем временный файл после небольшой задержки
                await asyncio.sleep(1.0)
                if os.path.exists(audio_file):
                    try:
                        os.remove(audio_file)
                        self.logger.debug("Временный аудиофайл удален.")
                    except OSError as e:
                        self.logger.warning(
                            f"Не удалось удалить временный файл: {e}")

        except Exception as e:
            self.logger.error(f"Ошибка обработки аудио: {e}", exc_info=True)
        finally:
            self._set_state(AppState.IDLE)

    def _on_key_press_callback(self, event):
        """Обработчик нажатия клавиши (вызывается в отдельном потоке)."""
        # Если мы уже пишем (IDLE -> RECORDING), игнорируем повторные события (авто-повтор клавиш)
        if self._get_state() == AppState.IDLE:
            # Проверка дебаунса (защита от дребезга)
            if time.time() - self._last_release_time > self._debounce_delay:
                # Проверяем готовность моделей перед началом
                if not self._model_loading and not self._model_load_failed:
                    self._set_state(AppState.RECORDING)
                    self._hotkey_pressed_time = time.time()
                    with self._buffer_lock:
                        self.audio_buffer.clear()
                    self.logger.debug("Начало записи аудио (Hook).")

    def _on_key_release_callback(self, event):
        """Обработчик отпускания клавиши (вызывается в отдельном потоке)."""
        if self._get_state() == AppState.RECORDING:
            current_time = time.time()
            press_duration = current_time - self._hotkey_pressed_time
            self._last_release_time = current_time

            if press_duration >= self._min_hotkey_press:
                self.logger.debug(
                    f"Окончание записи аудио (длительность: {press_duration:.2f}с).")
                # Важно: запускаем асинхронную обработку в основном event loop
                if hasattr(self, 'loop') and self.loop.is_running():
                    asyncio.run_coroutine_threadsafe(self.process_audio(),
                                                     self.loop)
                else:
                    self.logger.warning("Event loop недоступен.")
                    self._set_state(AppState.IDLE)
            else:
                # Сброс, если нажатие слишком короткое
                with self._buffer_lock:
                    self.audio_buffer.clear()
                self._set_state(AppState.IDLE)
                self.logger.debug("Слишком короткое нажатие клавиши.")

    async def run(self):
        """Основной цикл работы приложения."""
        if self._model_load_failed:
            self.logger.error(
                "Модель Whisper не загрузилась. Завершение работы.")
            return

        while self._model_loading:
            self.logger.info("Ожидание загрузки модели Whisper...")
            await asyncio.sleep(0.5)

        if self.model is None:
            self.logger.error(
                "Не удалось загрузить модель Whisper. Завершение работы.")
            return

        hotkey = self.cfg['app']['hotkey']
        self.logger.info(
            f"Система готова к работе. Удерживайте клавишу '{hotkey}' для записи.")

        # Сохраняем ссылку на текущий loop для колбэков
        self.loop = asyncio.get_running_loop()
        # Событие для удержания приложения запущенным
        self._stop_event = asyncio.Event()

        # Регистрация хуков клавиатуры
        try:
            # Очищаем старые хуки
            keyboard.unhook_all()

            # Используем правильный API keyboard
            keyboard.hook_key(hotkey, self._on_keyboard_event, suppress=False)

        except Exception as e:
            self.logger.error(f"Ошибка установки хуков клавиатуры: {e}")
            return

        try:
            # Запускаем стрим микрофона и ждем события остановки
            with sd.InputStream(
                    samplerate=self._fs,
                    channels=1,
                    dtype='float32',
                    callback=self.audio_callback,
                    blocksize=self._blocksize
                    # Используем сохраненное значение
            ):
                # Ждем сигнала завершения
                await self._stop_event.wait()
        except Exception as e:
            self.logger.error(f"Ошибка в аудиопотоке: {e}", exc_info=True)
        finally:
            try:
                keyboard.unhook_all()
            except:
                pass

    def _on_keyboard_event(self, event):
        """Единый обработчик событий клавиатуры (нажатие и отпускание)."""
        if event.event_type == keyboard.KEY_DOWN:
            # Обработка нажатия
            if self._get_state() == AppState.IDLE:
                # Проверка дебаунса
                if time.time() - self._last_release_time > self._debounce_delay:
                    # Проверяем готовность моделей перед началом
                    if not self._model_loading and not self._model_load_failed:
                        self._set_state(AppState.RECORDING)
                        self._hotkey_pressed_time = time.time()
                        with self._buffer_lock:
                            self.audio_buffer.clear()
                        self.logger.debug("Начало записи аудио.")

        elif event.event_type == keyboard.KEY_UP:
            # Обработка отпускания
            if self._get_state() == AppState.RECORDING:
                current_time = time.time()
                press_duration = current_time - self._hotkey_pressed_time
                self._last_release_time = current_time

                if press_duration >= self._min_hotkey_press:
                    self.logger.debug(
                        f"Окончание записи аудио (длительность: {press_duration:.2f}с).")
                    # Запускаем асинхронную обработку в основном event loop
                    if hasattr(self, 'loop') and self.loop.is_running():
                        asyncio.run_coroutine_threadsafe(self.process_audio(),
                                                         self.loop)
                    else:
                        self.logger.warning("Event loop недоступен.")
                        self._set_state(AppState.IDLE)
                else:
                    # Сброс, если нажатие слишком короткое
                    with self._buffer_lock:
                        self.audio_buffer.clear()
                    self._set_state(AppState.IDLE)
                    self.logger.debug("Слишком короткое нажатие клавиши.")

    def shutdown(self):
        """Освобождает ресурсы при завершении работы."""
        self.logger.info("Завершение работы...")

        if hasattr(self, '_stop_event'):
            self._stop_event.set()

        try:
            keyboard.unhook_all()  # Изменено с unhook_all_hotkeys()
        except:
            pass

        self._executor.shutdown(wait=True, cancel_futures=True)
        if os.path.exists(self._temp_file):
            try:
                os.remove(self._temp_file)
            except OSError:
                pass
