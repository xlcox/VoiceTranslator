"""Модуль управления воспроизведением аудио через SoundPad."""
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import soundfile as sf

SOUNDPAD_AVAILABLE = False
try:
    from soundpad_control import SoundpadRemoteControl

    SOUNDPAD_AVAILABLE = True
except ImportError:
    pass


class SoundpadManager:
    """Управляет подключением и воспроизведением аудио через SoundPad."""

    def __init__(self, config, logger):
        """Инициализирует менеджер SoundPad с конфигурацией и логгером."""
        self.cfg = config.get("soundpad", {})
        self.logger = logger
        self.soundpad = None
        self.is_connected = False
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._current_playing = False

        if not SOUNDPAD_AVAILABLE:
            self.logger.warning(
                "Библиотека soundpad_control недоступна. Функционал SoundPad отключен.")
            return

        if not self.cfg.get("enabled", True):
            self.logger.info("SoundPad отключен в конфигурации.")
            return

        self._initialize_soundpad()

    def _initialize_soundpad(self):
        """Инициализирует подключение к SoundPad."""
        try:
            with self._lock:
                self.soundpad = SoundpadRemoteControl()
                self.logger.info("Инициализировано подключение к SoundPad.")
                self._check_connection()
        except Exception as e:
            self.logger.error(f"Ошибка инициализации SoundPad: {e}")
            self.soundpad = None

    def _check_connection(self):
        """Проверяет доступность подключения к SoundPad."""
        if not self.soundpad:
            return False

        try:
            count = self.soundpad.get_sound_file_count()
            self.is_connected = True
            self.logger.debug(
                f"SoundPad подключен. В библиотеке {count} звуков.")
            return True
        except Exception as e:
            self.logger.warning(f"SoundPad не отвечает: {e}")
            self.is_connected = False
            return False

    def ensure_running(self):
        """Запускает SoundPad если он не запущен и включена опция auto_start."""
        if not self.cfg.get("auto_start", True):
            return self._check_connection()

        if self.is_connected:
            return True

        soundpad_path = self.cfg.get("soundpad_path", "SoundPad/Soundpad.exe")

        if not os.path.exists(soundpad_path):
            self.logger.warning(f"SoundPad не найден по пути: {soundpad_path}")
            return False

        try:
            subprocess.Popen([soundpad_path],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)

            self.logger.info("Запуск SoundPad...")
            time.sleep(3)

            self._initialize_soundpad()
            return self.is_connected

        except Exception as e:
            self.logger.error(f"Ошибка запуска SoundPad: {e}")
            return False

    def play_audio_file(self, audio_file_path, async_mode=True):
        """Воспроизводит аудиофайл через SoundPad."""
        if async_mode:
            future = self._executor.submit(self._play_audio_file_sync,
                                           audio_file_path)
            return future
        else:
            return self._play_audio_file_sync(audio_file_path)

    def _play_audio_file_sync(self, audio_file_path):
        """Синхронное воспроизведение аудиофайла через SoundPad."""
        if not self.ensure_running():
            self.logger.error(
                "Невозможно воспроизвести аудио: SoundPad недоступен.")
            return False

        if not os.path.exists(audio_file_path):
            self.logger.error(f"Аудиофайл не найден: {audio_file_path}")
            return False

        try:
            with self._lock:
                self._current_playing = True

                self.logger.info(
                    f"Добавление аудиофайла в SoundPad: {audio_file_path}")
                self.soundpad.add_sound(audio_file_path)

                count = self.soundpad.get_sound_file_count()
                index = count

                self.logger.debug(f"Воспроизведение звука с индексом {index}")

                speakers = self.cfg.get("play_in_speakers", True)
                microphone = self.cfg.get("play_in_microphone", True)

                self.logger.info(
                    f"Воспроизведение: динамики={speakers}, микрофон={microphone}")
                success = self.soundpad.play_sound(index, speakers=speakers,
                                                   mic=microphone)

                if success:
                    try:
                        data, sr = sf.read(audio_file_path)
                        duration = len(data) / sr
                        wait_time = min(duration + 0.5,
                                        self.cfg.get("playback_timeout", 10))
                        self.logger.debug(
                            f"Ожидание завершения воспроизведения: {wait_time:.2f} сек.")
                        time.sleep(wait_time)
                    except Exception as e:
                        self.logger.warning(
                            f"Не удалось определить длительность аудио: {e}")
                        time.sleep(1)

                    if self.cfg.get("cleanup_after_play", True):
                        self._cleanup_sound(index)

                    self._current_playing = False
                    return True
                else:
                    self.logger.error("Ошибка воспроизведения через SoundPad.")
                    self._current_playing = False
                    return False

        except Exception as e:
            self.logger.error(f"Ошибка воспроизведения через SoundPad: {e}")
            self._current_playing = False
            return False

    def _cleanup_sound(self, index):
        """Удаляет звук из SoundPad после воспроизведения."""
        try:
            self.soundpad.select_row(index)
            self.soundpad.remove_selected_entries(remove_from_disk=False)
            self.logger.debug(f"Звук с индексом {index} удален из SoundPad.")
        except Exception as e:
            self.logger.warning(f"Не удалось удалить звук из SoundPad: {e}")

    def is_playing(self):
        """Проверяет, идет ли в данный момент воспроизведение."""
        return self._current_playing

    def cleanup(self):
        """Освобождает ресурсы менеджера SoundPad."""
        self._executor.shutdown(wait=False)
