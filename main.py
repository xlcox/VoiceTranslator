import sounddevice as sd
import numpy as np
import edge_tts
import whisper
from deep_translator import GoogleTranslator
import keyboard
import asyncio
import soundfile as sf
import os

# ---------------- Настройки ----------------
FS = 16000
HOTKEY = 'page up'
MIN_AUDIO_SEC = 0.8
TTS_FILE = "tts.wav"

# ---------------- Инициализация ----------------
model = whisper.load_model("small")
translator = GoogleTranslator(source='ru', target='zh-CN')

audio_buffer = []
recording = False


# ---------------- Аудио callback ----------------
def audio_callback(indata, frames, time_info, status):
    if recording:
        audio_buffer.append(indata.copy())


# ---------------- Whisper ----------------
def speech_to_text(audio):
    if np.max(np.abs(audio)) < 0.01:
        print("⚠️ Слишком тихий звук")
        return ""
    result = model.transcribe(audio, language='ru')
    return result["text"].strip()


# ---------------- TTS ----------------
async def speak(text, filename=TTS_FILE):
    communicate = edge_tts.Communicate(
        text,
        voice="zh-CN-YunxiNeural",  # мужской голос
        volume="+30%",               # громкость
        rate="-20%"                  # уменьшение скорости на 20%
    )
    await communicate.save(filename)
    return os.path.exists(filename) and os.path.getsize(filename) > 0


def play_audio(filename, gain=1.5):
    data, sr = sf.read(filename, dtype='float32')

    # дополнительное усиление
    data *= gain
    data = np.clip(data, -1.0, 1.0)

    sd.play(data, sr)
    sd.wait()


# ---------------- Основной цикл ----------------
async def main():
    global recording, audio_buffer

    print(f"🎤 Удерживайте '{HOTKEY}' для записи")

    with sd.InputStream(
            samplerate=FS,
            channels=1,
            dtype='float32',
            callback=audio_callback
    ):
        while True:
            if keyboard.is_pressed(HOTKEY):
                if not recording:
                    audio_buffer = []
                    recording = True
                    print("▶️ Запись...")
            else:
                if recording:
                    recording = False
                    print("⏹️ Остановка")

                    if not audio_buffer:
                        continue

                    audio = np.concatenate(audio_buffer, axis=0).flatten()
                    duration = len(audio) / FS
                    print(f"⏱ Длина: {duration:.2f} сек")

                    if duration < MIN_AUDIO_SEC:
                        print("⚠️ Слишком коротко")
                        continue

                    text = speech_to_text(audio)
                    print("📝 RU:", text)

                    if not text:
                        continue

                    translated = translator.translate(text)
                    print("🌏 ZH:", translated)

                    if await speak(translated):
                        play_audio(TTS_FILE, gain=1.5)

            await asyncio.sleep(0.05)


# ---------------- Запуск ----------------
asyncio.run(main())
