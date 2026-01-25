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
        # Убираем постоянное хранение объекта self.soundpad, так как он не потокобезопасен
        self.soundpad = None
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=2,
                                            thread_name_prefix="SP-Worker")
        self._current_playing = threading.Event()
        self._shutdown = False

        # Кеширование настроек для производительности
        self._enabled = self.cfg.get("enabled", True)
        self._auto_start = self.cfg.get("auto_start", True)
        self._soundpad_path = self.cfg.get("soundpad_path",
                                           "SoundPad/Soundpad.exe")
        self._play_in_speakers = self.cfg.get("play_in_speakers", True)
        self._play_in_microphone = self.cfg.get("play_in_microphone", True)
        self._cleanup_after_play = self.cfg.get("cleanup_after_play", True)
        self._playback_timeout = self.cfg.get("playback_timeout", 10)

        if not SOUNDPAD_AVAILABLE:
            self.logger.warning(
                "Библиотека soundpad_control недоступна. Функционал SoundPad отключен.")
            return

        if not self._enabled:
            self.logger.info("SoundPad отключен в конфигурации.")
            return

        # Проверяем запуск, но не храним соединение
        self.ensure_running()

    def _get_connection(self):
        """Создает НОВОЕ подключение к SoundPad. Безопасно для вызова из любого потока."""
        try:
            return SoundpadRemoteControl()
        except Exception as e:
            self.logger.error(
                f"Не удалось создать подключение к SoundPad: {e}")
            return None

    def _is_soundpad_running(self):
        """Проверяет, запущен ли процесс SoundPad."""
        if os.name != 'nt':
            return False

        try:
            import psutil
            for proc in psutil.process_iter(['name']):
                if proc.info['name'] and 'soundpad' in proc.info[
                    'name'].lower():
                    return True
        except ImportError:
            try:
                result = subprocess.run(
                    ['tasklist', '/FI', 'IMAGENAME eq Soundpad.exe'],
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                return 'Soundpad.exe' in result.stdout
            except Exception:
                pass
        except Exception:
            pass

        return False

    def ensure_running(self):
        """Запускает SoundPad если он не запущен и включена опция auto_start."""
        if self._shutdown:
            return False

        # Проверяем процесс
        if self._is_soundpad_running():
            return True

        if not self._auto_start:
            return False

        if not os.path.exists(self._soundpad_path):
            self.logger.warning(
                f"SoundPad не найден по пути: {self._soundpad_path}")
            return False

        try:
            subprocess.Popen(
                [self._soundpad_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            self.logger.info("Запуск SoundPad...")
            time.sleep(2)  # Даем время на запуск
            return True

        except Exception as e:
            self.logger.error(f"Ошибка запуска SoundPad: {e}")
            return False

    def stop_playback(self):
        """Принудительно останавливает текущее воспроизведение в SoundPad."""
        try:
            # Создаем временное соединение для отправки команды стоп
            sp = self._get_connection()
            if sp:
                success = True
                if hasattr(sp, 'stop_sound'):
                    success = sp.stop_sound()
                elif hasattr(sp, 'stop_playing'):
                    success = sp.stop_playing()

                if success:
                    self._current_playing.clear()
                    self.logger.debug("Воспроизведение остановлено")
                return success
        except Exception as e:
            self.logger.warning(f"Ошибка при остановке воспроизведения: {e}")
        return False

    def _get_audio_duration(self, audio_file_path):
        """Получает длительность аудиофайла."""
        try:
            data, sr = sf.read(audio_file_path)
            return len(data) / sr
        except Exception as e:
            self.logger.warning(
                f"Не удалось определить длительность аудио: {e}")
            return 1.0

    def _add_sound_to_soundpad(self, sp_client, audio_file_path):
        """Добавляет звук используя переданный клиент SoundPad."""
        try:
            initial_count = sp_client.get_sound_file_count()
            self.logger.debug(f"Добавление файла: {audio_file_path}")

            sp_client.add_sound(audio_file_path)
            time.sleep(0.1)

            new_count = sp_client.get_sound_file_count()
            index = new_count
            return index
        except Exception as e:
            self.logger.error(f"Не удалось добавить звук в SoundPad: {e}")
            return None

    def play_audio_file(self, audio_file_path, async_mode=True):
        """Воспроизводит аудиофайл через SoundPad с повторными попытками."""
        max_retries = self.cfg.get("max_retry_attempts", 3)

        for attempt in range(max_retries):
            try:
                if async_mode:
                    return self._executor.submit(
                        self._play_audio_file_with_retry,
                        audio_file_path, attempt + 1, max_retries)
                else:
                    return self._play_audio_file_with_retry(audio_file_path,
                                                            attempt + 1,
                                                            max_retries)
            except Exception as e:
                self.logger.error(
                    f"Ошибка запуска задачи воспроизведения: {e}")
                return False

    def _play_audio_file_with_retry(self, audio_file_path, attempt,
                                    max_attempts):
        """Воспроизведение с обработкой ошибок и повторными попытками."""
        # Принудительная остановка предыдущего воспроизведения
        if self.cfg.get("force_stop_before_play", True):
            self.stop_playback()

        delay = self.cfg.get("playback_delay", 0.2)
        if delay > 0:
            time.sleep(delay)

        return self._play_audio_file_sync(audio_file_path)

    def _play_audio_file_sync(self, audio_file_path):
        """Синхронное воспроизведение аудиофайла внутри рабочего потока."""
        if self._shutdown:
            return False

        if not self.ensure_running():
            self.logger.error("SoundPad недоступен.")
            return False

        if not os.path.exists(audio_file_path):
            self.logger.error(f"Файл не найден: {audio_file_path}")
            return False

        duration = self._get_audio_duration(audio_file_path)

        # !!! ГЛАВНОЕ ИЗМЕНЕНИЕ: Создаем подключение внутри потока !!!
        local_sp = self._get_connection()
        if not local_sp:
            self.logger.error(
                "Не удалось подключиться к SoundPad в рабочем потоке.")
            return False

        try:
            with self._lock:
                self._current_playing.set()

                # Передаем локальный клиент local_sp в методы
                index = self._add_sound_to_soundpad(local_sp, audio_file_path)
                if index is None:
                    self._current_playing.clear()
                    return False

                self.logger.info(f"Воспроизведение индекса {index}")
                success = local_sp.play_sound(
                    index,
                    speakers=self._play_in_speakers,
                    mic=self._play_in_microphone
                )

                if success:
                    wait_time = min(duration + 0.5, self._playback_timeout)
                    time.sleep(wait_time)

                    if self._cleanup_after_play:
                        self._cleanup_sound(local_sp, index)
                        time.sleep(0.1)

                    self._current_playing.clear()
                    return True
                else:
                    self.logger.error("Ошибка команды play_sound.")
                    if self._cleanup_after_play:
                        self._cleanup_sound(local_sp, index)
                    self._current_playing.clear()
                    return False

        except Exception as e:
            self.logger.error(f"Ошибка воспроизведения: {e}", exc_info=True)
            self._current_playing.clear()
            return False

    def _cleanup_sound(self, sp_client, index):
        """Удаляет звук, используя переданный клиент."""
        try:
            sp_client.select_row(index)
            time.sleep(0.05)
            sp_client.remove_selected_entries(remove_from_disk=False)
            self.logger.debug(f"Звук {index} удален.")
        except Exception as e:
            self.logger.warning(f"Не удалось удалить звук: {e}")

    def is_playing(self):
        return self._current_playing.is_set()

    def cleanup(self):
        self.logger.info("Очистка ресурсов SoundPad...")
        self._shutdown = True
        self._current_playing.clear()
        self._executor.shutdown(wait=True, cancel_futures=True)
