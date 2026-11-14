"""Voz a texto con Whisper local (faster-whisper).

Se corre en la laptop: los audios de los usuarios no salen de la maquina.
"""
from functools import lru_cache

MODEL_SIZE = "small"  # buen balance velocidad/calidad en CPU; probar large-v3-turbo si hay GPU


@lru_cache(maxsize=1)
def _model():
    from faster_whisper import WhisperModel

    return WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")


def transcribe(path: str, language: str = "es") -> str:
    segmentos, _ = _model().transcribe(path, language=language, vad_filter=True)
    return " ".join(s.text.strip() for s in segmentos).strip()
