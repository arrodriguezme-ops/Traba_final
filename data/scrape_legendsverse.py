"""Construye data/marvel_legends_baf.csv desde Legendsverse (BAF -> piezas -> figura que la trae).

Fuente: https://legendsverse.com/guides/marvel-legends-build-a-figure-list
Cortesia: bajo volumen, DELAY segundos entre peticiones, User-Agent generico, cache local
(data/cache/, ignorado por git) y parada al primer 403/429. Solo se guardan datos derivados
(nombres, anio, precio de mercado, URLs de origen e imagen), no el HTML. Precios en USD de EE. UU.

Uso: python data/scrape_legendsverse.py [--max N]
"""
import argparse
import hashlib
import re
import sys
import time
from pathlib import Path

import httpx
import pandas as pd
from bs4 import BeautifulSoup

LIST_URL = "https://legendsverse.com/guides/marvel-legends-build-a-figure-list"
UA = "Mozilla/5.0 (compatible; CourseProjectBot/0.1; educational low-volume)"
DELAY = 3.0
ROOT = Path(__file__).parent
CACHE = ROOT / "cache"
OUT = ROOT / "marvel_legends_baf.csv"


class Bloqueado(Exception):
    pass


def get(client: httpx.Client, url: str) -> str:
    f = CACHE / (hashlib.md5(url.encode()).hexdigest() + ".html")
    if f.exists():
        return f.read_text(encoding="utf-8")
    time.sleep(DELAY)
    r = client.get(url)
    if r.status_code in (403, 429):
        raise Bloqueado(f"{r.status_code} en {url}")
    r.raise_for_status()
    f.write_text(r.text, encoding="utf-8")
    return r.text


def usd(txt: str):
    m = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", txt or "")
    return float(m.group(1).replace(",", "")) if m else None


def lista_baf(html: str) -> list[dict]:
    s = BeautifulSoup(html, "html.parser")
    out = []
    for tr in s.find("table").find_all("tr")[1:]:
        tds = tr.find_all("td")
        a = tr.find("a", href=True)
        if len(tds) < 4 or not a:
            continue
        t = [x.get_text(" ", strip=True) for x in tds]
        out.append({"baf": t[0], "anio": int(t[1]) if t[1].isdigit() else None, "wave": t[2], "url_baf": a["href"]})
    return out


def piezas(html: str, meta: dict) -> list[dict]:
    s = BeautifulSoup(html, "html.parser")
    wave_val = None
    m = re.search(r"\$([\d,]+\.\d{2})\s*Wave value", s.get_text(" ", strip=True))
    if m:
        wave_val = float(m.group(1).replace(",", ""))
    filas = []
    for src in s.find_all(attrs={"data-testid": "baf-piece-source"}):
        card = src.find_parent("div", class_=lambda c: c and "border-b" in c)
        if not card:
            continue
        a = src.find("a", href=True)
        img = card.find("img")
        val = card.find(attrs={"data-testid": "baf-piece-value"})
        filas.append({
            **meta,
            "pieza": card.find("h3").get_text(strip=True),
            "figura": a.get_text(strip=True) if a else None,
            "precio_figura_usd": usd(val.get_text()) if val else None,
            "imagen_pieza": img["src"] if img and str(img.get("src", "")).startswith("http") else None,
            "url_figura": a["href"] if a else None,
            "valor_wave_usd": wave_val,
        })
    return filas


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=0)
    n = ap.parse_args().max
    CACHE.mkdir(exist_ok=True)
    filas = []
    with httpx.Client(headers={"User-Agent": UA}, timeout=30, follow_redirects=True) as c:
        try:
            bafs = lista_baf(get(c, LIST_URL))
            if n:
                bafs = bafs[:n]
            print(f"{len(bafs)} BAF", flush=True)
            for i, b in enumerate(bafs, 1):
                filas += piezas(get(c, b["url_baf"]), b)
                print(f"[{i}/{len(bafs)}] {b['baf']} ({b['anio']}) -> {len(filas)} filas", flush=True)
        except Bloqueado as e:
            print(f"PARADO: {e}. Guardo lo obtenido.", file=sys.stderr)
    pd.DataFrame(filas).to_csv(OUT, index=False)
    print(f"{len(filas)} filas -> {OUT}")


if __name__ == "__main__":
    main()
