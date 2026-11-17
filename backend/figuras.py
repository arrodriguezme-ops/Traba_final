"""Busqueda por figura (con o sin BAF): retail, valor en EE. UU., precio en tiendas de Peru y reventa en Lima."""
from __future__ import annotations

import re

import pandas as pd
from rapidfuzz import fuzz, process, utils

from backend.matching import DATA, _con_catalogo, load_catalog, load_reales
from backend.pricing import TIPO_CAMBIO


def _norm(s) -> str:
    s = str(s).lower().replace("spider-man", "spiderman").replace("x-men", "xmen")
    return re.sub(r"[^a-z0-9]", "", s)


def load_figuras() -> pd.DataFrame:
    """Un renglon por empaque (1.692): figura, anio, retail_usd, valor_mercado_usd, imagen, etiqueta."""
    f = pd.read_csv(DATA / "marvel_legends_retail_historico.csv")
    f = f[f["figura"].notna()].copy()
    f["anio"] = f["anio"].astype("Int64")
    f["etiqueta"] = f["figura"] + " (" + f["anio"].astype(str) + ")"
    f["_n"] = f["figura"].map(_norm)
    return f.sort_values(["anio", "figura"], ascending=[False, True]).reset_index(drop=True)


def load_tiendas() -> pd.DataFrame:
    t = pd.read_csv(DATA / "tiendas_pe_cruzado.csv", dtype={"ean": str})
    t["_n"] = t["figura"].map(lambda x: _norm(x) if isinstance(x, str) else "")
    return t


def reales_con_anio(figs: pd.DataFrame) -> pd.DataFrame:
    """Avisos reales con un anio estimado: por la pieza de BAF si la traen, o si el nombre es unico en el catalogo."""
    r = load_reales()
    r["_n"] = r["figura"].map(_norm)
    por_baf = _con_catalogo(r, load_catalog()).set_index("id")["anio"]
    unicos = figs.groupby("_n").filter(lambda g: len(g) == 1).set_index("_n")["anio"]
    r["anio"] = r["id"].map(por_baf)
    if "anio_estimado" in r:  # anio anotado a mano cuando la caja o el aviso lo dejan claro
        r["anio"] = r["anio"].fillna(pd.to_numeric(r["anio_estimado"], errors="coerce"))
    r["anio"] = r["anio"].fillna(r["_n"].map(unicos))
    ret = figs.groupby(["_n", "anio"])["retail_usd"].first()
    r["retail_usd"] = pd.to_numeric(pd.Series(
        [ret.get((n, int(a))) if pd.notna(a) else None for n, a in zip(r["_n"], r["anio"])], index=r.index))
    if "retail_usd_ref" in r:  # retail anotado a mano cuando el nombre del aviso no coincide con el catalogo
        r["retail_usd"] = r["retail_usd"].fillna(pd.to_numeric(r["retail_usd_ref"], errors="coerce"))
    r["efecto_dm"] = (r["precio_pen"] - r["retail_usd"] * TIPO_CAMBIO) / (r["retail_usd"] * TIPO_CAMBIO)
    r["canal"] = r["fuente"].map(lambda s: "Facebook Marketplace" if "Facebook" in s else
                                 "eBay (sin envio ni aranceles)" if s == "eBay" else
                                 "Tai Loy (historico Wayback)" if "Wayback" in s else
                                 "Tai Loy" if "Tai Loy" in s else
                                 "Compra propia (historica)" if s.startswith("Compra propia") else
                                 "Lista de vendedor (historia)" if s.startswith("Lista de vendedor") else
                                 "Otra tienda online")
    return r


# Lo que Whisper (o el usuario) dice en espanol y el catalogo tiene en ingles
_COLORES = {"marron": "brown", "marrón": "brown", "negro": "black", "negra": "black", "blanco": "white",
            "blanca": "white", "azul": "blue", "rojo": "red", "roja": "red", "verde": "green", "dorado": "gold",
            "clasico": "classic", "clásico": "classic", "traje": "suit"}
_RELLENO = (r"quiero|quisiera|busco|buscando|estoy|est[aá]s|armar|completar|figura|figuras|marvel|legends?|precio|"
            r"cu[aá]nto|cuesta|vale|d[oó]nde|puedo|encontrar(?:lo|la|las|los)?|encuentro|buscar(?:lo|la)?|comprar|"
            r"tiendas?|que|vendan|venden|de|del|la|el|los|las|una?|en|vivo|a|y|l[ií]nea|hasta|soles|por|favor|si")


def normaliza_pedido(texto: str) -> str:
    """Corrige lo que Whisper suele oir mal y unifica 'buff/baf/waf/base de' como BAF."""
    t = f" {texto} "
    t = re.sub(r"(?i)\b(la |el )?(buff?s?|waf|baf|bath|base)\b(?= de| del|\s)", " BAF ", t)
    t = re.sub(r"(?i)\bspider ?man\b|\bspiderman\b", "Spider-Man", t)
    t = re.sub(r"(?i)\bspider(-man)? de pen+[iy] ?[bp]arker\b", "SP//dr", t)
    t = re.sub(r"(?i)\bmug knight\b|\bmoon nite\b|\bmo[gn]+ ?nite\b|\bmu[gn] ?knight\b", "Moon Knight", t)
    t = re.sub(r"(?i)\baer[o]? ?man\b|\bairman\b", "Iron Man", t)
    t = re.sub(r"(?i)\brenew your (boats|bows|vous|vows)\b", "Renew Your Vows", t)
    t = re.sub(r"(?i)\bh[ua]ff? ?goblin\b|\bhob goblin\b", "Hobgoblin", t)
    t = re.sub(r"(?i)\b(a)?b?omination\b|\babaminaci[oó]n\b|\babominaci[oó]n\b", "Abomination", t)
    t = re.sub(r"(?i)\bm[aá]s morales\b|\bmiles morales\b", "Miles Morales", t)
    t = re.sub(r"(?i)\binto the spider[- ]?(wars|verse|vers)\b", "Into the Spider-Verse", t)
    t = re.sub(r"(?i)\bpenny? ?barker\b|\bpeni ?parker\b", "Peni Parker", t)
    return re.sub(r"\s+", " ", t).strip()


def buscar(texto: str, figs: pd.DataFrame, n: int = 8) -> list[int]:
    """Indices de los empaques que mejor coinciden con el texto (nombre de figura; un anio en el texto ayuda)."""
    texto = normaliza_pedido((texto or "").strip())
    if not texto:
        return []
    anio_re = r"\b(?:199\d|20[0-2]\d)\b"  # 1990-2029; asi "Spider-Man 2099" no se lee como anio
    anio = re.search(anio_re, texto)
    q = re.sub(anio_re, " ", texto)
    q = re.sub(r"[¿?¡!.,;:]", " ", q)
    q = re.sub(rf"(?i)\b({_RELLENO})\b", " ", q)
    q = " ".join(_COLORES.get(w.lower(), w) for w in q.split())
    q = re.sub(r"(?i)\bBAF\b", " ", q).strip()
    if not q:
        return []
    nombres = figs["figura"].tolist()
    # limit alto: hay decenas de "Wolverine" o "Spider-Man" y la version buscada no debe quedar fuera del corte
    res = process.extract(q, nombres, scorer=fuzz.WRatio, limit=400, score_cutoff=70,
                          processor=utils.default_process)
    # WRatio premia nombres cortos contenidos ("Wolverine" en "wolverine brown suit"); se promedia con token_sort
    # para que gane el nombre completo ("Wolverine (Brown Suit)").
    # Bonus por cobertura: cuantas palabras del nombre estan (casi) en el pedido. Asi "Punisher traje negro" no
    # termina en "Black Tom Cassidy" solo por compartir "black".
    qt = utils.default_process(q).split()

    def cobertura(nombre: str) -> float:
        nt = utils.default_process(nombre).split()
        return sum(any(fuzz.ratio(w, x) >= 80 for x in qt) for w in nt) / len(nt) if nt else 0

    pts = {i: (s + fuzz.token_sort_ratio(q, nombres[i], processor=utils.default_process)) / 2
           + 20 * cobertura(nombres[i]) for _, s, i in res}
    idx = sorted(pts, key=lambda i: (-round(pts[i]), -int(figs.at[i, "anio"] or 0)))
    if anio:
        a = int(anio.group())
        idx = [i for i in idx if figs.at[i, "anio"] == a] + [i for i in idx if figs.at[i, "anio"] != a]
    return idx[:n]


def ficha(fila: pd.Series, tiendas: pd.DataFrame, reales: pd.DataFrame, cat: pd.DataFrame) -> dict:
    """Todo lo que sabemos de un empaque. Las tiendas y avisos se buscan por nombre del personaje."""
    n = fila["_n"]
    t = tiendas[tiendas["_n"] == n].sort_values("precio_pen")
    r = reales[reales["_n"] == n].sort_values("precio_pen")
    # Legendsverse fecha algunos waves con un anio de diferencia entre la guia de precios y la de BAF
    baf = cat[(cat["figura"].map(_norm) == n) & ((cat["anio"] - int(fila["anio"])).abs() <= 1)]
    baf = baf[["baf", "pieza", "anio"]].drop_duplicates(["baf", "pieza"])
    otros_anios = int((tiendas["_n"] == n).sum() and (t["anio"] != fila["anio"]).sum())
    return {"tiendas": t, "reventa": r, "baf": baf, "otros_anios_tienda": otros_anios}


def sobreprecio_por_canal(tiendas: pd.DataFrame, reales: pd.DataFrame) -> pd.DataFrame:
    """Sobreprecio (Precio_rev - P_retail)/P_retail por canal. Solo avisos con figura y anio identificados."""
    t = tiendas[(tiendas["confianza"] == "alta") & (tiendas["n_figuras_pack"] == 1) & tiendas["efecto_dm"].notna()]
    t = t.sort_values("tienda").drop_duplicates(["titulo", "precio_pen", "vendedor"])
    a = pd.DataFrame({"canal": t["tienda"].replace({"Oechsle": "Plaza Vea / Oechsle", "Plaza Vea": "Plaza Vea / Oechsle"}),
                      "efecto": t["efecto_dm"], "precio": t["precio_pen"]})
    # Fuera del promedio: compras historicas del founder (otro anio y otro tipo de cambio), lotes, packs, customs,
    # preventas y avisos dudosos. Siguen visibles en la ficha de cada figura.
    dudoso = reales["marca_calidad"].fillna("").str.contains(
        "custom|lote|pack|linea_ambigua|no_legends|posible_replica|foto_de_catalogo|precio_muy_alto|pieza_suelta|incompleto|subasta")
    fuera = reales["tipo_aviso"].fillna("").isin(["lote", "lote_ebay", "preventa", "compra_historica"])
    b = reales[reales["efecto_dm"].notna() & ~dudoso & ~fuera].copy()
    # Un vendedor que repite el mismo producto en varias publicaciones cuenta una vez (la mas reciente)
    b = b.sort_values("fecha_publicacion", na_position="first").drop_duplicates(["vendedor", "_n", "anio"], keep="last")
    b = pd.DataFrame({"canal": b["canal"], "efecto": b["efecto_dm"], "precio": b["precio_pen"]})
    x = pd.concat([a, b], ignore_index=True)
    g = x.groupby("canal").agg(avisos=("efecto", "size"), sobreprecio_mediano=("efecto", "median"),
                               sobreprecio_promedio=("efecto", "mean"), precio_mediano_pen=("precio", "median"))
    return g.sort_values("sobreprecio_mediano").reset_index()
