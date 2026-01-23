from soundpad_control import SoundpadRemoteControl
import subprocess
import time
import sys
import os

# Конфигурация
SOUNDPAD_PATH = os.path.join("SoundPad", "Soundpad.exe")
TEST_SOUND_FILE = "test.wav"


def is_soundpad_running():
    """Проверяет, запущен ли Soundpad"""
    try:
        import psutil
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] and 'soundpad' in proc.info['name'].lower():
                return True
        return False
    except ImportError:
        # Если psutil не установлен, используем альтернативный метод
        import subprocess
        result = subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq Soundpad.exe'],
            capture_output=True, text=True)
        return 'Soundpad.exe' in result.stdout


def ensure_soundpad_running():
    """Запускает Soundpad, если он не запущен"""
    if not is_soundpad_running():
        print("Soundpad не запущен. Запускаю из папки SoundPad...")

        if not os.path.exists(SOUNDPAD_PATH):
            print(f"Ошибка: Soundpad не найден по пути {SOUNDPAD_PATH}")
            print("Убедитесь, что:")
            print(f"1. Папка 'SoundPad' находится рядом с {__file__}")
            print(f"2. В папке есть файл Soundpad.exe")
            return False

        try:
            # Запускаем Soundpad в фоновом режиме
            subprocess.Popen([SOUNDPAD_PATH],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)

            # Даём время на запуск
            print("Ожидание запуска Soundpad (3 секунды)...")
            time.sleep(3)

            # Проверяем, запустился ли
            if is_soundpad_running():
                print("✓ Soundpad успешно запущен")
                return True
            else:
                print("✗ Не удалось запустить Soundpad")
                return False

        except Exception as e:
            print(f"Ошибка при запуске Soundpad: {e}")
            return False
    else:
        print("✓ Soundpad уже запущен")
        return True


def main():
    """Основная функция тестирования"""
    print("=" * 50)
    print("Тест Soundpad API")
    print("=" * 50)

    # 1. Убеждаемся, что Soundpad запущен
    if not ensure_soundpad_running():
        print("Прерывание: Soundpad не доступен")
        return

    # 2. Проверяем наличие тестового файла
    if not os.path.exists(TEST_SOUND_FILE):
        print(f"Ошибка: Тестовый файл '{TEST_SOUND_FILE}' не найден")
        print("Создайте WAV файл или скопируйте его в текущую папку")
        return

    print(f"✓ Тестовый файл найден: {TEST_SOUND_FILE}")

    # 3. Подключаемся к Soundpad
    print("\nПодключение к Soundpad...")
    try:
        soundpad = SoundpadRemoteControl()
        print("✓ Подключение установлено")
    except Exception as e:
        print(f"✗ Ошибка подключения: {e}")
        print("\nВозможные причины:")
        print("1. Soundpad запущен без прав администратора")
        print("2. Проблемы с named pipe")
        print("3. Soundpad не поддерживает Remote Control")
        return

    # 4. Проверяем текущее количество звуков
    try:
        initial_count = soundpad.get_sound_file_count()
        print(f"Текущее количество звуков в библиотеке: {initial_count}")
    except Exception as e:
        print(f"✗ Не удалось получить количество звуков: {e}")
        return

    # 5. Добавляем тестовый файл в Soundpad
    print(f"\nДобавление файла '{TEST_SOUND_FILE}' в Soundpad...")
    try:
        soundpad.add_sound(TEST_SOUND_FILE)
        print("✓ Файл добавлен")
    except Exception as e:
        print(f"✗ Ошибка при добавлении файла: {e}")
        print("\nВозможные причины:")
        print("1. Soundpad Trial версия (ограничена)")
        print("2. Неправильный путь к файлу")
        print("3. Формат файла не поддерживается")
        return

    # 6. Получаем индекс добавленного файла
    try:
        new_count = soundpad.get_sound_file_count()
        if new_count > initial_count:
            index = new_count  # Индекс нового файла
            print(f"Индекс добавленного файла: {index}")
        else:
            print(
                "⚠ Количество файлов не изменилось. Используем последний индекс.")
            index = new_count
    except Exception as e:
        print(f"✗ Ошибка при получении индекса: {e}")
        return

    # 7. Воспроизводим звук в микрофон
    print("\nВоспроизведение звука в микрофон...")
    try:
        # Параметры: index, speakers=False, mic=True
        success = soundpad.play_sound(index, speakers=False, mic=True)

        if success:
            print("✓ Звук отправлен в микрофон")
            print("Проверьте, слышен ли звук в приложении (игре/дискорде)")
        else:
            print("✗ Ошибка воспроизведения")
            print("Проверьте настройки микрофона в Soundpad")

    except Exception as e:
        print(f"✗ Ошибка при воспроизведении: {e}")

    # 8. Очистка - удаляем добавленный звук
    print("\nОчистка...")
    try:
        soundpad.select_row(index)
        soundpad.remove_selected_entries(remove_from_disk=False)
        print("✓ Добавленный звук удалён из библиотеки")
    except Exception as e:
        print(f"⚠ Не удалось удалить звук: {e}")

    # 9. Закрытие соединения
    print("\n" + "=" * 50)
    print("Тест завершён!")

    # Подсказки для пользователя
    print("\n⚠ Если звук не слышно в микрофоне:")
    print("1. Откройте Soundpad")
    print("2. Перейдите в Settings → Microphone")
    print("3. Убедитесь, что выбрано устройство 'Soundpad'")
    print("4. Проверьте уровень микрофона (не на 0%)")


if __name__ == "__main__":
    main()
