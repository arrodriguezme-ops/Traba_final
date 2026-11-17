"""Consolida todas las observaciones de precios (reventa, tiendas actuales y series de Wayback Machine) en una sola tabla.

Uso:  PYTHONPATH=. python -m backend.consolidar     ->  data/observaciones_precios.csv
"""
from __future__ import annotations

import html
import re

import numpy as np
import pandas as pd
from rapidfuzz import fuzz

from backend.figuras import _norm, load_figuras, load_tiendas, reales_con_anio
from backend.matching import DATA
from backend.pricing import TIPO_CAMBIO

# Tipo de cambio PEN/USD promedio aproximado por ano (para comparar con el retail de la epoca)
TC_ANIO = {2010: 2.83, 2011: 2.75, 2012: 2.64, 2013: 2.70, 2014: 2.84, 2015: 3.19, 2016: 3.38, 2017: 3.26, 2018: 3.29,
           2019: 3.34, 2020: 3.50, 2021: 3.88, 2022: 3.84, 2023: 3.74, 2024: 3.75, 2025: 3.65, 2026: 3.45}
CACHE = DATA / "cache"
RUIDO = (r"marvel|legends?|series|serie|figura|figuras|de acci[oó]n|acci[oó]n|hasbro|pulgadas|\d+ ?cm|tailoy\.com\.pe|tailoy|envios?|a todo el per[uú]|"
         r"todo el peru|seven figuarts|exclusive|wave|collection|nuevo|sellad[oa]|completo|completa|toy ?biz|classics?|variante|oferta|"
         r"con|de|el|la|los|las|y|vs|the|and|del|en")
TRAD = {"antorcha humana": "human torch", "tormenta": "storm", "hombre de hierro": "iron man", "gambito": "gambit", "bestia": "beast",
        "ciclope": "cyclops", "cíclope": "cyclops", "lobezno": "wolverine", "duende verde": "green goblin", "capitan america": "captain america",
        "capitán américa": "captain america", "capitana marvel": "captain marvel", "viuda negra": "black widow", "spiderman": "spider-man",
        "spider man": "spider-man", "ironman": "iron man", "dr.doom": "doctor doom", "dr. doom": "doctor doom", "dr strange": "doctor strange",
        "phanter": "panther", "black phanter": "black panther"}


def _limpia(t: str) -> str:
    s = html.unescape(str(t)).lower()
    for a, b in TRAD.items():
        s = s.replace(a, b)
    s = re.sub(r"\b[a-z]\d{4}\b", " ", s)  # codigos Hasbro (F7086)
    s = re.sub(r"\b(" + RUIDO + r")\b", " ", s)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\- ]", " ", s)).strip()


class Matcher:
    def __init__(self):
        f = load_figuras()
        self.f = f[f["n_figuras_pack"] == 1]
        self.nombres = self.f.groupby("figura").size().index.tolist()
        self.low = [n.lower() for n in self.nombres]

    GENERICOS = {"spider-man", "iron man", "thor", "hulk", "wolverine", "captain america", "black panther", "deadpool", "venom",
                 "x-men", "avengers", "storm", "cyclops", "loki", "daredevil", "punisher"}

    def __call__(self, titulo: str, anio_max: int, umbral: int = 90):
        # "Black Widow Legends Series - Yelena Belova": el nombre de la figura es el ultimo tramo
        tramos = [t for t in re.split(r"\s[-–—]\s|:\s", html.unescape(str(titulo))) if len(t.strip()) >= 3]
        for t in ([tramos[-1]] if tramos else []) + [titulo]:
            r = self._una(t, anio_max)
            if r:
                return r
        return None

    def _una(self, titulo: str, anio_max: int):
        q = _limpia(titulo)
        if len(q) < 3 or q in self.GENERICOS:
            return None
        qt = set(q.split())
        cands = [n for n in self.nombres if len(n) >= 4 and set(_limpia(n).split()) and set(_limpia(n).split()) <= qt]
        if not cands:
            return None
        largo = max(len(_limpia(n)) for n in cands)
        fin = []
        for n in cands:
            if len(_limpia(n)) < 0.6 * largo or (_limpia(n) in self.GENERICOS and len(qt) > 1):
                continue
            ok = self.f[(self.f["figura"] == n) & (self.f["anio"] <= anio_max)]
            if len(ok):
                fin.append((int(ok["anio"].max()), len(n), n))
        if not fin:
            return None
        anio, _, nombre = max(fin)
        ok = self.f[(self.f["figura"] == nombre) & (self.f["anio"] <= anio_max)]
        sel = ok.sort_values("anio").iloc[-1]
        return dict(figura=nombre, anio=int(sel["anio"]), fabricante=sel["fabricante"], retail_usd=sel["retail_usd"],
                    confianza="alta" if len(ok) == 1 else "media")


def _fila(fecha, fuente, canal, vendedor, titulo, m, precio, regular=None, estado="", url="", tipo="tienda", marca=""):
    return dict(fecha=fecha, fuente_dato=fuente, canal=canal, vendedor=vendedor, titulo_original=titulo,
                figura=m["figura"] if m else None, anio=m["anio"] if m else None, fabricante=m["fabricante"] if m else None,
                retail_usd=m["retail_usd"] if m else None, confianza=m["confianza"] if m else None, precio_pen=precio,
                precio_regular_pen=regular, estado=estado, url=url, tipo=tipo, marca_calidad=marca)


def construir() -> pd.DataFrame:
    match = Matcher()
    filas: list[dict] = []
    figs = load_figuras()

    # 1) Reventa y avisos transcritos (sin las filas de Wayback, que se vuelven a leer abajo)
    r = reales_con_anio(figs)
    r = r[~r["fuente"].str.contains("Wayback")]
    for _, x in r.iterrows():
        m = None
        if pd.notna(x["anio"]):
            cat = figs[(figs["_n"] == x["_n"]) & (figs["anio"] == int(x["anio"]))]
            if len(cat):
                c = cat.iloc[0]
                m = dict(figura=c["figura"], anio=int(c["anio"]), fabricante=c["fabricante"], retail_usd=c["retail_usd"], confianza="alta")
        if m is None and pd.notna(x["anio"]):
            m = dict(figura=x["figura"], anio=int(x["anio"]), fabricante=None, retail_usd=x.get("retail_usd"), confianza="media")
        fecha = x.get("fecha_publicacion") if pd.notna(x.get("fecha_publicacion")) else x.get("fecha_observada")
        filas.append(_fila(fecha, "listings_reales", x["canal"], x["vendedor"], x["titulo_original"] if pd.notna(x["titulo_original"]) else x["figura"],
                           m, x["precio_pen"], estado=x.get("estado", ""), tipo="reventa" if x["canal"] in ("Facebook Marketplace", "eBay (sin envio ni aranceles)") else "tienda",
                           marca=x.get("marca_calidad") if pd.notna(x.get("marca_calidad")) else ""))

    # 2) Tiendas peruanas observadas el 14-11-2026
    t = load_tiendas()
    for _, x in t.iterrows():
        if not x.get("es_legends"):
            continue
        m = None
        if pd.notna(x["figura"]) and pd.notna(x["anio"]):
            m = dict(figura=x["figura"], anio=int(x["anio"]), fabricante="Hasbro", retail_usd=x["retail_usd"], confianza=x["confianza"])
        filas.append(_fila(x["fecha_observada"], "tiendas_pe_2026", x["tienda"], x["tienda"], x["titulo"], m, x["precio_pen"],
                           regular=x["precio_lista_pen"], url=x["url"], marca="pack" if x.get("n_figuras_pack", 1) > 1 else ""))

    # 3) Tai Loy, serie de Wayback Machine
    tl = pd.read_csv(CACHE / "tl_todo_wayback.csv")
    tl = tl[tl["precio"].notna()]
    for _, x in tl.iterrows():
        txt = f"{x['titulo']} {x['url']}"
        if not re.search(r"legends|mvl", txt, re.I) or re.search(r"combate|mech|titan|olympus|lanzador|role play|squish|mochila|cuaderno|libro|album", txt, re.I):
            continue
        titulo = x["titulo"] if re.search(r"[a-z]{3}", str(x["titulo"]), re.I) and "tailoy.com.pe |" not in str(x["titulo"]).lower() else re.sub(r"-\d+\.html?$", "", x["url"].rsplit("/", 1)[-1]).replace("-", " ")
        m = match(titulo, int(x["captura"][:4]))
        filas.append(_fila(x["captura"], "tailoy_wayback", "Tai Loy (historico Wayback)", "Tai Loy", titulo, m, float(x["precio"]), url=x["url"]))
    # precios de liquidacion o lecturas raras: mucho mas bajos que el resto de capturas del mismo producto
    ult = pd.DataFrame([f for f in filas if f["fuente_dato"] == "tailoy_wayback"])
    med = ult.groupby("url")["precio_pen"].median()
    for f in filas:
        if f["fuente_dato"] == "tailoy_wayback" and f["precio_pen"] < 0.5 * med[f["url"]]:
            f["marca_calidad"] = "precio_dudoso"

    # 4) Seven Figuarts, categorias Marvel Legends de Wayback
    s = pd.read_csv(CACHE / "seven_parsed.csv")
    s = s[s["titulo"].str.contains("legends", case=False, na=False) & ~s["titulo"].str.contains("funko", case=False, na=False) & s["precio"].notna()]
    for _, x in s.iterrows():
        m = match(x["titulo"], int(x["captura"][:4]))
        reg = x["precio_regular"] if pd.notna(x["precio_regular"]) and float(x["precio_regular"]) > float(x["precio"]) else None
        filas.append(_fila(x["captura"], "seven_wayback", "Seven Figuarts (historico Wayback)", "Seven Figuarts", x["titulo"], m, float(x["precio"]), regular=reg))

    # 5) Toys Master 2025 (Wayback)
    tm = pd.read_csv(CACHE / "toysmaster_parsed.csv")
    tm = tm[tm["precio"].notna() & tm["titulo"].str.contains("legends", case=False, na=False)].drop_duplicates(["captura", "titulo"])
    for _, x in tm.iterrows():
        m = match(x["titulo"], int(x["captura"][:4]))
        filas.append(_fila(x["captura"], "toysmaster_wayback", "Toys Master (historico Wayback)", "Toys Master", x["titulo"], m, float(x["precio"])))

    # 6) MercadoLibre Peru 2010-2011 (ya cruzado con el catalogo)
    ml = pd.read_csv(DATA / "ml_peru_cruzado.csv")
    for _, x in ml.iterrows():
        m = None
        if pd.notna(x["figura_cat"]):
            m = dict(figura=x["figura_cat"], anio=int(x["anio_cat"]), fabricante=x["fabricante"], retail_usd=x["retail_usd"], confianza="media")
        filas.append(_fila(x["captura"], "mercadolibre_wayback", "MercadoLibre Peru (2010-2011)", "MercadoLibre", x["titulo"], m, float(x["precio"]),
                           estado=x.get("estado") if pd.notna(x.get("estado")) else "", url=x["url"], tipo="reventa"))

    d = pd.DataFrame(filas)
    t = d["titulo_original"].fillna("").str.lower()
    d.loc[t.str.contains(r"two.?pack|2.?pack|3.?pack|vs|\s&\s| y .* pack|lote|set completo") & d["marca_calidad"].fillna("").eq(""), "marca_calidad"] = "pack"
    d.loc[t.str.contains(r"shield|helmet|casco|role play|gauntlet|escudo|accesorio|mask"), "marca_calidad"] = "accesorio"
    d["fecha"] = pd.to_datetime(d["fecha"], errors="coerce")
    d["anio_obs"] = d["fecha"].dt.year
    d["tc_epoca"] = d["anio_obs"].map(TC_ANIO).fillna(TIPO_CAMBIO)
    for col, tc in (("sobreprecio_tc345", TIPO_CAMBIO), ("sobreprecio_tc_epoca", d["tc_epoca"])):
        d[col] = (d["precio_pen"] - d["retail_usd"] * tc) / (d["retail_usd"] * tc)
    d["figura_clave"] = d["figura"].map(lambda s: _norm(s) if isinstance(s, str) else None)
    return d.sort_values(["figura", "fecha"]).reset_index(drop=True)


def universo(d: pd.DataFrame) -> dict:
    """Figuras unicas: del catalogo y cuantas tienen al menos una observacion."""
    f = load_figuras()
    f1 = f[f["n_figuras_pack"] == 1]
    unicas = f1.drop_duplicates(["_n", "anio"])
    obs = d[d["figura"].notna()].assign(_n=lambda x: x["figura"].map(_norm)).drop_duplicates(["_n", "anio"])
    llave = set(zip(obs["_n"], obs["anio"].astype(int)))
    cubiertas = unicas[[(n, int(a)) in llave for n, a in zip(unicas["_n"], unicas["anio"])]]
    por_fuente = {k: g.assign(_n=g["figura"].map(_norm)).drop_duplicates(["_n", "anio"]).shape[0]
                  for k, g in d[d["figura"].notna()].groupby("fuente_dato")}
    return dict(catalogo_empaques=len(f), catalogo_figuras_unicas=len(unicas), nombres_unicos=f1["_n"].nunique(),
                con_observaciones=len(cubiertas), por_fuente=por_fuente,
                sin_cruzar=int(d["figura"].isna().sum()), filas=len(d))


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    d = construir()
    d.to_csv(DATA / "observaciones_precios.csv", index=False)
    print(universo(d))
