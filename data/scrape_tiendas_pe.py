"""Precios de Marvel Legends en tiendas peruanas -> data/tiendas_pe.csv.

Fuentes (revisado robots.txt el 2026-11-14; ninguna regla impide estas rutas):
  - Tai Loy (Magento):        /catalogsearch/result/?q=marvel+legends (su robots no tiene reglas para '*')
  - Falabella Peru:           /falabella-pe/search?Ntt=marvel+legends (JSON __NEXT_DATA__ de la pagina)
  - Oechsle y Plaza Vea (VTEX): API publica de catalogo /api/catalog_system/pub/products/search
No incluidas: Mercado Libre (redirige a verificacion de cuenta; su API pide token), Ripley (robots prohibe /search/),
Facebook Marketplace (requiere sesion y sus terminos prohiben la recoleccion automatizada).
Cortesia: 3 s entre peticiones, User-Agent generico, cache en data/cache/ y parada en 403/429.

Uso: python data/scrape_tiendas_pe.py
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

import httpx
import pandas as pd
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
from scrape_legendsverse_figuras import CACHE, ROOT, UA, Bloqueado, get  # noqa: E402

Q = "marvel legends"
HOY = date.today().isoformat()


def _num(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def tailoy(c) -> list[dict]:
    out, p, paginas = [], 1, 1
    while p <= paginas:
        html = get(c, f"https://www.tailoy.com.pe/catalogsearch/result/?q=marvel+legends&p={p}")
        s = BeautifulSoup(html, "html.parser")
        if p == 1:
            tot = re.findall(r'toolbar-number">(\d+)', html)
            n = max(int(x) for x in tot) if tot else 0
            paginas = max(1, -(-n // 25))
        vistos = set()
        for it in s.select(".product-item-info"):
            a = it.select_one(".product-item-link")
            if not a or not a.get("href") or a["href"] in vistos:
                continue
            vistos.add(a["href"])
            fin = it.select_one("[data-price-type='finalPrice']")
            old = it.select_one("[data-price-type='oldPrice']")
            out.append({"tienda": "Tai Loy", "titulo": a.get_text(" ", strip=True), "marca": None,
                        "precio_pen": _num(fin.get("data-price-amount")) if fin else None,
                        "precio_lista_pen": _num(old.get("data-price-amount")) if old else None,
                        "disponible": None, "vendedor": "Tai Loy", "url": a["href"]})
        print(f"Tai Loy p{p}/{paginas}: {len(out)}", flush=True)
        p += 1
    return out


def _buscar(o, k):
    if isinstance(o, dict):
        if k in o:
            return o[k]
        for v in o.values():
            r = _buscar(v, k)
            if r is not None:
                return r
    elif isinstance(o, list):
        for v in o:
            r = _buscar(v, k)
            if r is not None:
                return r
    return None


def falabella(c) -> list[dict]:
    out, p, paginas = [], 1, 1
    while p <= paginas:
        html = get(c, f"https://www.falabella.com.pe/falabella-pe/search?Ntt=marvel+legends&page={p}")
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
        if not m:
            break
        j = json.loads(m.group(1))
        if p == 1:
            pag = _buscar(j, "pagination") or {}
            paginas = max(1, -(-int(pag.get("count", 0)) // int(pag.get("perPage", 48) or 48)))
        for r in _buscar(j, "results") or []:
            precios = {x.get("type"): _num((x.get("price") or [None])[0]) for x in r.get("prices", [])}
            actual = precios.get("eventPrice") or precios.get("internetPrice") or precios.get("normalPrice")
            out.append({"tienda": "Falabella", "titulo": r.get("displayName"), "marca": r.get("brand"),
                        "precio_pen": actual, "precio_lista_pen": precios.get("normalPrice"),
                        "precio_cmr_pen": precios.get("cmrPrice"), "disponible": None,
                        "vendedor": r.get("sellerName"), "url": r.get("url")})
        print(f"Falabella p{p}/{paginas}: {len(out)}", flush=True)
        p += 1
    return out


def vtex(c, tienda: str, base: str) -> list[dict]:
    out, desde = [], 0
    while True:
        url = f"{base}/api/catalog_system/pub/products/search?ft=marvel%20legends&_from={desde}&_to={desde + 49}"
        data = json.loads(get(c, url))
        for p in data:
            it = p["items"][0]
            o = it["sellers"][0]["commertialOffer"]
            ref = [r.get("Value") for r in it.get("referenceId") or []]
            hay = (o.get("AvailableQuantity") or 0) > 0
            out.append({"tienda": tienda, "titulo": p.get("productName"), "marca": p.get("brand"),
                        # VTEX pone Price=0 cuando no hay stock: no es un precio real
                        "precio_pen": _num(o.get("Price")) if hay else None,
                        "precio_lista_pen": _num(o.get("ListPrice")) if hay else None,
                        "disponible": hay, "ean": it.get("ean") or None,
                        # Son marketplaces: el prefijo del referenceId es la tienda que vende (p. ej. TOYSMASTER)
                        "vendedor": (ref[0].split("-")[0] if ref and "-" in ref[0] else it["sellers"][0].get("sellerName")),
                        "url": p.get("link")})
        print(f"{tienda} desde {desde}: {len(out)}", flush=True)
        if len(data) < 50 or desde >= 450:
            break
        desde += 50
    return out


def main() -> None:
    CACHE.mkdir(exist_ok=True)
    filas = []
    with httpx.Client(headers={"User-Agent": UA}, timeout=40, follow_redirects=True) as c:
        for nombre, f in [("Tai Loy", lambda: tailoy(c)), ("Falabella", lambda: falabella(c)),
                          ("Oechsle", lambda: vtex(c, "Oechsle", "https://www.oechsle.pe")),
                          ("Plaza Vea", lambda: vtex(c, "Plaza Vea", "https://www.plazavea.com.pe"))]:
            try:
                filas += f()
            except Bloqueado as e:
                print(f"PARADO en {nombre}: {e}", file=sys.stderr)
            except Exception as e:  # una tienda que cambia su HTML no debe tumbar las demas
                print(f"ERROR en {nombre}: {e!r}", file=sys.stderr)
    df = pd.DataFrame(filas).drop_duplicates(["tienda", "url"])
    df["fecha_observada"] = HOY
    df["es_legends"] = df["titulo"].str.contains(r"legends?", case=False, na=False) & ~df["titulo"].str.contains(
        r"mafex|figuarts|marvel select|funko|hot toys|lego|mcfarlane|minimates", case=False, na=False)
    df.to_csv(ROOT / "tiendas_pe.csv", index=False)
    print(df.groupby("tienda").agg(n=("titulo", "size"), legends=("es_legends", "sum")))


if __name__ == "__main__":
    main()
