"""Voz a texto con Whisper local (faster-whisper).

Se corre en la laptop: los audios de los usuarios no salen de la maquina.
"""
from functools import lru_cache

MODEL_SIZE = "small"  # buen balance velocidad/calidad en CPU; probar large-v3-turbo si hay GPU


@lru_cache(maxsize=1)
def _model():
    from faster_whisper import WhisperModel

    return WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")


def _decodifica(path: str):
    """Audio -> numpy float32 mono a 16 kHz. Se decodifica aqui (y no dentro de faster-whisper) porque PyAV 15+
    quito el argumento metadata_errors que faster-whisper 1.2 le pasa a av.open."""
    import av
    import numpy as np

    partes = []
    with av.open(path) as cont:
        res = av.AudioResampler(format="s16", layout="mono", rate=16000)
        for frame in cont.decode(audio=0):
            for f in res.resample(frame):
                partes.append(f.to_ndarray().reshape(-1))
        for f in res.resample(None):  # vacia el buffer del resampler
            partes.append(f.to_ndarray().reshape(-1))
    if not partes:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(partes).astype(np.float32) / 32768.0


@lru_cache(maxsize=1)
def vocabulario() -> str:
    """Pista para Whisper: nombres en ingles que en espanol suele oir mal ("Mug Knight", "HuffGoblin").
    Se arma con los BAF del catalogo y algunos personajes frecuentes (Whisper usa ~200 tokens de prompt)."""
    from pathlib import Path

    import pandas as pd

    csv = Path(__file__).resolve().parent.parent / "data" / "marvel_legends_baf.csv"
    bafs = sorted(pd.read_csv(csv)["baf"].dropna().unique()) if csv.exists() else []
    base = ("Marvel Legends de Hasbro. BAF (Build-A-Figure). Moon Knight, Iron Man Extremis, Miles Morales, "
            "Spider-Verse, Peni Parker, Spider-Man 2099, Wolverine, Punisher, Captain America, Doctor Doom, "
            "Mister Knight, Scarlet Spider. BAF: ")
    return base + ", ".join(bafs[:70]) + "."


def transcribe(path: str, language: str = "es") -> str:
    segmentos, _ = _model().transcribe(_decodifica(path), language=language, vad_filter=True,
                                       initial_prompt=vocabulario())
    return " ".join(s.text.strip() for s in segmentos).strip()
