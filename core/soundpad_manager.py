"""Модуль управления воспроизведением аудио через SoundPad."""
import os
from soundpad_control import SoundpadRemoteControl
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import soundfile as sf

from core.constants import (
    SOUNDPAD_AUTO_START, SOUNDPAD_PATH,
    SOUNDPAD_PLAYBACK_TIMEOUT,
    SOUNDPAD_FORCE_STOP_BEFORE_PLAY, SOUNDPAD_PLAYBACK_DELAY,
    SOUNDPAD_MAX_RETRY_ATTEMPTS
)


class SoundpadManager:
    """Управляет подключением и воспроизведением аудио через SoundPad."""

    def __init__(self, config, logger):
        """Инициализирует менеджер SoundPad с конфигурацией и логгером.

        Args:
            config: Конфигурация приложения
            logger: Логгер для записи событий
        """
        self.cfg = config.get("soundpad", {})
        self.logger = logger
        self.soundpad = None
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="SP-Worker"
        )
        self._current_playing = threading.Event()
        self._shutdown = False

        self._auto_start = SOUNDPAD_AUTO_START
        self._soundpad_path = SOUNDPAD_PATH
        self._play_in_speakers = self.cfg.get("play_in_speakers", True)
        self._play_in_microphone = self.cfg.get("play_in_microphone", True)
        self._playback_timeout = SOUNDPAD_PLAYBACK_TIMEOUT

        if self.ensure_running():
            self.logger.info("SoundPad ready")
        else:
            self.logger.warning("SoundPad not available - playback may fail")

    def _get_connection(self):
        """Создает новое подключение к SoundPad.

        Returns:
            SoundpadRemoteControl or None: Подключение к SoundPad или None при ошибке
        """
        try:
            return SoundpadRemoteControl()
        except Exception as e:
            self.logger.debug(f"Connection failed: {e}")
            return None

    def _verify_connection(self, max_attempts=3, retry_delay=1.0):
        """Проверяет возможность подключения к SoundPad с повторными попытками.

        Args:
            max_attempts: Максимальное количество попыток
            retry_delay: Задержка между попытками в секундах

        Returns:
            bool: True если подключение успешно
        """
        for attempt in range(max_attempts):
            try:
                test_sp = self._get_connection()
                if test_sp:
                    test_sp.get_sound_file_count()
                    self.logger.debug(f"Connected (attempt {attempt + 1})")
                    return True
            except Exception as e:
                self.logger.debug(
                    f"Connection attempt {attempt + 1}/{max_attempts} failed: {e}")
                if attempt < max_attempts - 1:
                    time.sleep(retry_delay)

        return False

    def _is_soundpad_running(self):
        """Проверяет, запущен ли процесс SoundPad и отвечает ли он на команды.

        Метод проверяет не только наличие процесса, но и его способность отвечать
        на API запросы. Это предотвращает ложные срабатывания когда процесс существует,
        но не работает корректно (зомби-процесс, завершается, не отвечает).

        Returns:
            bool: True если процесс запущен И отвечает на команды
        """
        if os.name != 'nt':
            return False

        process_exists = False

        try:
            import psutil
            for proc in psutil.process_iter(['name', 'status']):
                if proc.info['name'] and 'soundpad' in proc.info[
                    'name'].lower():
                    if proc.info.get('status') != psutil.STATUS_ZOMBIE:
                        process_exists = True
                        break
        except ImportError:
            try:
                result = subprocess.run(
                    ['tasklist', '/FI', 'IMAGENAME eq Soundpad.exe'],
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=2
                )
                process_exists = 'Soundpad.exe' in result.stdout
            except Exception:
                pass
        except Exception:
            pass

        if not process_exists:
            return False

        return self._verify_connection(max_attempts=1, retry_delay=0.1)

    def ensure_running(self):
        """Запускает SoundPad если он не запущен и проверяет готовность к работе.

        Выполняет следующую логику:
        1. Проверяет возможность подключения к API
        2. Если подключение не работает, проверяет процесс и его API
        3. Если процесса нет и включен auto_start - запускает SoundPad

        Returns:
            bool: True если SoundPad запущен и готов к работе
        """
        if self._shutdown:
            self.logger.debug("Shutdown in progress")
            return False

        if self._verify_connection(max_attempts=1, retry_delay=0.5):
            self.logger.debug("Already connected to SoundPad")
            return True

        if self._is_soundpad_running():
            self.logger.debug("SoundPad running and responding")
            return True

        if not self._auto_start:
            self.logger.warning("SoundPad not running and auto_start disabled")
            return False

        if not os.path.exists(self._soundpad_path):
            self.logger.error(f"SoundPad not found: {self._soundpad_path}")
            return False

        try:
            self.logger.info("Starting SoundPad...")
            subprocess.Popen(
                [self._soundpad_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            if self._verify_connection(max_attempts=10, retry_delay=1.0):
                self.logger.debug("SoundPad started successfully")
                return True
            else:
                self.logger.error("SoundPad started but not responding")
                return False

        except Exception as e:
            self.logger.error(f"SoundPad start failed: {e}")
            return False

    def stop_playback(self):
        """Принудительно останавливает текущее воспроизведение в SoundPad.

        Returns:
            bool: True если остановка успешна
        """
        try:
            sp = self._get_connection()
            if sp:
                success = True
                if hasattr(sp, 'stop_sound'):
                    success = sp.stop_sound()
                elif hasattr(sp, 'stop_playing'):
                    success = sp.stop_playing()

                if success:
                    self._current_playing.clear()
                    self.logger.debug("Playback stopped")
                return success
        except Exception as e:
            self.logger.debug(f"Stop error: {e}")
        return False

    def _get_audio_duration(self, audio_file_path):
        """Получает длительность аудиофайла.

        Args:
            audio_file_path: Путь к аудиофайлу

        Returns:
            float: Длительность в секундах или 1.0 при ошибке
        """
        try:
            data, sr = sf.read(audio_file_path)
            return len(data) / sr
        except Exception as e:
            self.logger.debug(f"Duration check failed: {e}")
            return 1.0

    def _add_sound_to_soundpad(self, sp_client, audio_file_path):
        """Добавляет звук используя переданный клиент SoundPad.

        Args:
            sp_client: Подключение к SoundPad
            audio_file_path: Путь к аудиофайлу

        Returns:
            int or None: Индекс добавленного звука или None при ошибке
        """
        try:
            abs_path = str(Path(audio_file_path).resolve())

            if not os.path.exists(abs_path):
                self.logger.error(f"File not found: {abs_path}")
                return None

            initial_count = sp_client.get_sound_file_count()
            self.logger.debug(f"Adding file: {abs_path}")

            sp_client.add_sound(abs_path)
            time.sleep(0.15)

            new_count = sp_client.get_sound_file_count()
            index = new_count

            self.logger.debug(
                f"Added index {index} ({initial_count}→{new_count})")
            return index
        except Exception as e:
            self.logger.error(f"Add sound failed: {e}")
            return None

    def play_audio_file(self, audio_file_path, async_mode=True):
        """Воспроизводит аудиофайл через SoundPad.

        Args:
            audio_file_path: Путь к аудиофайлу
            async_mode: Режим асинхронного выполнения

        Returns:
            concurrent.futures.Future or bool: Результат воспроизведения
        """
        try:
            if async_mode:
                return self._executor.submit(
                    self._play_audio_file_sync,
                    audio_file_path
                )
            else:
                return self._play_audio_file_sync(audio_file_path)
        except Exception as e:
            self.logger.error(f"Playback task error: {e}")
            return False

    def _play_audio_file_sync(self, audio_file_path):
        """Синхронное воспроизведение аудиофайла.

        Args:
            audio_file_path: Путь к аудиофайлу

        Returns:
            bool: Результат воспроизведения
        """
        if self._shutdown:
            self.logger.warning("Shutdown in progress")
            return False

        if SOUNDPAD_FORCE_STOP_BEFORE_PLAY:
            self.stop_playback()

        if SOUNDPAD_PLAYBACK_DELAY > 0:
            time.sleep(SOUNDPAD_PLAYBACK_DELAY)

        abs_path = str(Path(audio_file_path).resolve())

        if not os.path.exists(abs_path):
            self.logger.error(f"File not found: {abs_path}")
            return False

        self.logger.debug("Checking SoundPad availability...")
        if not self.ensure_running():
            self.logger.error("SoundPad unavailable")
            return False

        duration = self._get_audio_duration(abs_path)

        local_sp = self._get_connection()
        if not local_sp:
            self.logger.error("Connection failed")
            return False

        try:
            with self._lock:
                self._current_playing.set()

                index = self._add_sound_to_soundpad(local_sp, abs_path)
                if index is None:
                    self._current_playing.clear()
                    return False

                self.logger.debug(f"Playing sound [{index}] ({duration:.1f}s)")
                success = local_sp.play_sound(
                    index,
                    speakers=self._play_in_speakers,
                    mic=self._play_in_microphone
                )

                if success:
                    wait_time = min(duration + 0.5, self._playback_timeout)
                    time.sleep(wait_time)

                    self._cleanup_sound(local_sp, index)
                    time.sleep(0.1)

                    self._current_playing.clear()
                    return True
                else:
                    self.logger.error("Play command failed")
                    self._cleanup_sound(local_sp, index)
                    self._current_playing.clear()
                    return False

        except Exception as e:
            self.logger.error(f"Playback error: {e}", exc_info=True)
            self._current_playing.clear()
            return False

    def _cleanup_sound(self, sp_client, index):
        """Удаляет звук из SoundPad.

        Args:
            sp_client: Подключение к SoundPad
            index: Индекс звука для удаления
        """
        try:
            sp_client.select_row(index)
            time.sleep(0.05)
            sp_client.remove_selected_entries(remove_from_disk=False)
            self.logger.debug(f"Removed sound [{index}]")
        except Exception as e:
            self.logger.debug(f"Cleanup error: {e}")

    def is_playing(self):
        """Проверяет, идет ли воспроизведение.

        Returns:
            bool: True если воспроизведение идет
        """
        return self._current_playing.is_set()

    def cleanup(self):
        """Освобождает ресурсы при завершении работы."""
        self.logger.info("Cleaning up resources...")
        self._shutdown = True
        self._current_playing.clear()
        self._executor.shutdown(wait=True, cancel_futures=True)
        self.logger.info("SoundPad resources released")
