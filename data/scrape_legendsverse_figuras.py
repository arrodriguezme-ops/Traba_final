"""Construye data/marvel_legends_waves.csv y data/marvel_legends_figuras.csv desde Legendsverse.

Fuentes (paginas publicas permitidas por su robots.txt):
  - https://legendsverse.com/checklist/marvel-legends/waves        (172 waves: figuras, retail y valor de mercado)
  - https://legendsverse.com/checklist/marvel-legends/price-guide  (1.573 figuras con valor de mercado y foto)
Cortesia: DELAY s entre peticiones, User-Agent generico, cache local (data/cache/, ignorado por git) y parada
al primer 403/429. Solo se guardan datos derivados. Valores en USD de EE. UU. (ventas completadas en eBay).

Uso: python data/scrape_legendsverse_figuras.py [--max-pages N]
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

BASE = "https://legendsverse.com/checklist/marvel-legends"
UA = "Mozilla/5.0 (compatible; CourseProjectBot/0.1; educational low-volume)"
DELAY = 3.0
ROOT = Path(__file__).parent
CACHE = ROOT / "cache"


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


def parse_waves(html: str) -> pd.DataFrame:
    s = BeautifulSoup(html, "html.parser")
    filas, anio = [], None
    for h in s.find_all(["h2", "h3"]):
        t = h.get_text(" ", strip=True)
        m = re.match(r"All (\d{4}) Marvel Legends waves", t)
        if m:
            anio = int(m.group(1))
            continue
        a = h.find("a", href=True)
        if h.name != "h3" or not a or "/waves/" not in a["href"]:
            continue
        card = h
        for _ in range(6):  # sube hasta el contenedor que trae retail/valor
            card = card.parent
            if card is None or "Retail" in card.get_text(" ", strip=True):
                break
        txt = re.sub(r"\s+", " ", card.get_text(" ", strip=True)) if card else ""
        n = re.search(r"(\d+)\s+Retail", txt)
        ret = re.search(r"Retail\s+\$([\d,\.]+)", txt)
        mkt = re.search(r"Market value\s+\$([\d,\.]+)", txt)
        url = a["href"]
        filas.append({
            "wave": a.get_text(strip=True), "anio": anio, "url_wave": url,
            "slug": re.sub(r"-\d+$", "", url.rstrip("/").split("/")[-1]),
            "n_figuras": int(n.group(1)) if n else None,
            "retail_total_usd": float(ret.group(1).replace(",", "")) if ret else None,
            "mercado_total_usd": float(mkt.group(1).replace(",", "")) if mkt else None,
        })
    df = pd.DataFrame(filas).drop_duplicates("url_wave")
    df["retail_prom_usd"] = (df["retail_total_usd"] / df["n_figuras"]).round(2)
    return df


def parse_price_page(html: str) -> list[dict]:
    s = BeautifulSoup(html, "html.parser")
    out = []
    for h in s.find_all("h2"):
        a = h.find("a", href=True)
        if not a or "/figures/" not in a["href"]:
            continue
        card = h.parent.parent  # contenedor de la tarjeta
        img = card.find("img")
        val = card.find(string=re.compile(r"Worth"))
        txt = re.sub(r"\s+", " ", card.get_text(" ", strip=True))
        yr = re.search(r"\b(19|20)\d{2}\b", txt)
        w = re.search(r"Worth\s+\$([\d,\.]+)", txt)
        out.append({
            "figura": a.get_text(strip=True), "anio": int(yr.group()) if yr else None,
            "valor_mercado_usd": float(w.group(1).replace(",", "")) if w else None,
            "imagen": img["src"] if img and str(img.get("src", "")).startswith("http") else None,
            "url_figura": a["href"],
            "slug_figura": a["href"].rstrip("/").split("/")[-1],
        })
    return out


def asignar_wave(slug_fig: str, waves: pd.DataFrame):
    """Wave cuyo slug es el prefijo mas largo del slug de la figura (aprox.)."""
    mejor, largo = None, 0
    for w in waves.itertuples():
        if slug_fig.startswith(w.slug + "-") and len(w.slug) > largo:
            mejor, largo = w, len(w.slug)
    return (mejor.wave, mejor.url_wave) if mejor else (None, None)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=0)
    n = ap.parse_args().max_pages
    CACHE.mkdir(exist_ok=True)
    figs = []
    with httpx.Client(headers={"User-Agent": UA}, timeout=30, follow_redirects=True) as c:
        try:
            waves = parse_waves(get(c, f"{BASE}/waves"))
            waves.to_csv(ROOT / "marvel_legends_waves.csv", index=False)
            print(f"{len(waves)} waves -> marvel_legends_waves.csv", flush=True)
            p, total = 1, 36
            while p <= (n or total):
                html = get(c, f"{BASE}/price-guide" + (f"?page={p}" if p > 1 else ""))
                if p == 1:
                    total = max([int(x) for x in re.findall(r"price-guide\?page=(\d+)", html)] or [1])
                pagina = parse_price_page(html)
                figs += pagina
                print(f"[pagina {p}/{n or total}] +{len(pagina)} = {len(figs)} figuras", flush=True)
                if not pagina:
                    break
                p += 1
        except Bloqueado as e:
            print(f"PARADO: {e}. Guardo lo obtenido.", file=sys.stderr)
    df = pd.DataFrame(figs).drop_duplicates("url_figura")
    if len(df) and "waves" in locals():
        asign = df["slug_figura"].map(lambda s: asignar_wave(s, waves))
        df["wave"] = [a[0] for a in asign]
        df["url_wave"] = [a[1] for a in asign]
    df.to_csv(ROOT / "marvel_legends_figuras.csv", index=False)
    print(f"{len(df)} figuras -> marvel_legends_figuras.csv ({df['wave'].notna().mean():.0%} con wave)")


if __name__ == "__main__":
    main()
