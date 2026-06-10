"""
居家監控 - 麥克風錄音模組
偵測到入侵時錄下一段聲音,存成 WAV 檔。
"""

import wave

import sounddevice as sd


def record_audio(path: str, duration: float, samplerate: int = 44100,
                 channels: int = 1) -> str:
    """錄音指定秒數並存成 WAV 檔,回傳檔案路徑。"""
    frames = int(duration * samplerate)
    # 直接用 int16 錄音,方便寫入 WAV
    recording = sd.rec(frames, samplerate=samplerate, channels=channels,
                       dtype="int16")
    sd.wait()

    with wave.open(path, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # int16 = 2 bytes
        wf.setframerate(samplerate)
        wf.writeframes(recording.tobytes())
    return path
