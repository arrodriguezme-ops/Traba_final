"""Lista de figuras de cada wave SIN BAF -> data/marvel_legends_waves_figuras.csv.

Lee data/marvel_legends_waves.csv (ya generado) y baja la pagina de cada wave que no es un BAF.
Misma cortesia que scrape_legendsverse_figuras.py (3 s, User-Agent generico, cache, parada en 403/429).
Uso: python data/scrape_legendsverse_waves.py
"""
import sys
from pathlib import Path

import httpx
import pandas as pd
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
from scrape_legendsverse_figuras import CACHE, ROOT, UA, Bloqueado, get  # noqa: E402


def figuras_de_wave(html: str, wave: str, anio, url_wave: str) -> list[dict]:
    s = BeautifulSoup(html, "html.parser")
    vistos, out = set(), []
    for a in s.find_all("a", href=True):
        if "/figures/" in a["href"] and a["href"] not in vistos and a.get_text(strip=True):
            vistos.add(a["href"])
            out.append({"wave": wave, "anio_wave": anio, "figura": a.get_text(strip=True),
                        "url_figura": a["href"], "url_wave": url_wave})
    return out


def main() -> None:
    waves = pd.read_csv(ROOT / "marvel_legends_waves.csv")
    baf = pd.read_csv(ROOT / "marvel_legends_baf.csv")
    es_baf = set(baf["wave"].dropna()) | set(baf["baf"])
    sin_baf = waves[~waves["wave"].isin(es_baf)]
    CACHE.mkdir(exist_ok=True)
    filas = []
    with httpx.Client(headers={"User-Agent": UA}, timeout=30, follow_redirects=True) as c:
        try:
            print(f"{len(sin_baf)} waves sin BAF", flush=True)
            for i, w in enumerate(sin_baf.itertuples(), 1):
                filas += figuras_de_wave(get(c, w.url_wave), w.wave, w.anio, w.url_wave)
                print(f"[{i}/{len(sin_baf)}] {w.wave} -> {len(filas)} figuras", flush=True)
        except Bloqueado as e:
            print(f"PARADO: {e}. Guardo lo obtenido.", file=sys.stderr)
    pd.DataFrame(filas).to_csv(ROOT / "marvel_legends_waves_figuras.csv", index=False)
    print(f"{len(filas)} filas -> marvel_legends_waves_figuras.csv")


if __name__ == "__main__":
    main()
