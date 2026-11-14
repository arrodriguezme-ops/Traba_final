"""Genera data/listings.csv: avisos SINTETICOS de vendedores de Lima sobre figuras REALES del catalogo.

Las figuras, BAF, piezas y precios de referencia vienen de data/marvel_legends_baf.csv (Legendsverse).
Los vendedores, distritos y precios en soles son inventados para el demo (sin personas reales):
precio_pen = precio_usd_referencia * TIPO_CAMBIO * RECARGO_IMPORTACION * ruido.
Uso: python data/make_listings.py
"""
import random
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.pricing import TIPO_CAMBIO  # noqa: E402

random.seed(2026)
RECARGO_IMPORTACION = 1.35  # supuesto: flete, aduana y margen del vendedor local

DISTRITOS = {
    "Miraflores": (-12.1211, -77.0297), "San Isidro": (-12.0977, -77.0365), "Surco": (-12.1450, -76.9930),
    "La Molina": (-12.0867, -76.9100), "San Miguel": (-12.0770, -77.0870), "Jesus Maria": (-12.0700, -77.0510),
    "Lima Centro": (-12.0464, -77.0428), "Los Olivos": (-11.9700, -77.0700),
    "San Juan de Lurigancho": (-11.9770, -77.0080), "Callao": (-12.0560, -77.1180),
    "Barranco": (-12.1400, -77.0210), "Magdalena": (-12.0900, -77.0720),
}
VENDEDORES = [f"Tienda_{n}" for n in ["Kaiju", "Mecha", "Hobby", "Vault", "Akiba", "Titan", "Retro", "Nexus",
                                     "Legend", "Shelf"]]


def main() -> None:
    root = Path(__file__).parent
    cat = pd.read_csv(root / "marvel_legends_baf.csv").dropna(subset=["figura", "precio_figura_usd"])
    filas = []
    for r in cat.itertuples():
        for _ in range(random.choice([0, 1, 1, 2])):
            distrito = random.choice(list(DISTRITOS))
            lat, lon = DISTRITOS[distrito]
            incluye = random.random() < 0.8  # 20% vienen sin la pieza del BAF
            precio = r.precio_figura_usd * TIPO_CAMBIO * RECARGO_IMPORTACION * random.uniform(0.85, 1.25)
            if not incluye:
                precio *= 0.7
            filas.append({
                "baf": r.baf, "wave": r.wave, "anio": r.anio, "pieza": r.pieza, "figura": r.figura,
                "condicion": random.choice(["nueva", "nueva", "abierta"]),
                "incluye_pieza": incluye, "precio_pen": round(precio / 5) * 5,
                "vendedor": random.choice(VENDEDORES), "distrito": distrito,
                "lat": round(lat + random.uniform(-0.004, 0.004), 5),
                "lon": round(lon + random.uniform(-0.004, 0.004), 5),
            })
    df = pd.DataFrame(filas).sort_values(["baf", "pieza"]).reset_index(drop=True)
    df.insert(0, "id", df.index + 1)
    df.to_csv(root / "listings.csv", index=False)
    print(f"{len(df)} avisos sinteticos sobre {cat['figura'].nunique()} figuras reales")


if __name__ == "__main__":
    main()
