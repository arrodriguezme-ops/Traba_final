"""Catalogo de BAF/piezas, avisos de Lima y el plan para completar un BAF."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from backend.delivery import delivery_quote, haversine_km
from backend.pricing import efecto_doble_marginalizacion, retail_usd

DATA = Path(__file__).resolve().parent.parent / "data"

DISTRITOS = {
    "Miraflores": (-12.1211, -77.0297), "San Isidro": (-12.0977, -77.0365), "Surco": (-12.1450, -76.9930),
    "La Molina": (-12.0867, -76.9100), "San Miguel": (-12.0770, -77.0870), "Jesus Maria": (-12.0700, -77.0510),
    "Lima Centro": (-12.0464, -77.0428), "Los Olivos": (-11.9700, -77.0700),
    "San Juan de Lurigancho": (-11.9770, -77.0080), "Callao": (-12.0560, -77.1180),
    "Barranco": (-12.1400, -77.0210), "Magdalena": (-12.0900, -77.0720),
    # Distritos que aparecieron en avisos reales de Facebook Marketplace (centroides aproximados)
    "La Victoria": (-12.0650, -77.0150), "San Martin de Porres": (-12.0000, -77.0800),
    "Puente Piedra": (-11.8670, -77.0760), "Chorrillos": (-12.1700, -77.0100),
    "Rimac": (-12.0290, -77.0300), "Pueblo Libre": (-12.0720, -77.0630),
}


def load_catalog() -> pd.DataFrame:
    return pd.read_csv(DATA / "marvel_legends_baf.csv").dropna(subset=["figura"])


ONLINE = {"Lima (online)": "Lima Centro"}  # tienda online con entrega en Lima: se ubica en el centro


def load_reales() -> pd.DataFrame:
    """Avisos reales transcritos de capturas (Facebook, eBay, Tai Loy). Sin las busquedas ni los sin precio."""
    r = pd.read_csv(DATA / "listings_reales.csv")
    r = r[r["precio_pen"].notna() & (r["tipo_aviso"] != "busqueda")].copy()
    base = r["distrito"].map(lambda z: ONLINE.get(z, z))
    r["lat"] = base.map(lambda z: DISTRITOS.get(z, (None, None))[0])
    r["lon"] = base.map(lambda z: DISTRITOS.get(z, (None, None))[1])
    r["local"] = r["lat"].notna()
    r["importacion"] = ~r["local"] & r["fuente"].eq("eBay")
    r["bafpieza_ok"] = r["incluye_pieza_baf"].astype(str).eq("True")
    return r


def _con_catalogo(r: pd.DataFrame, cat: pd.DataFrame) -> pd.DataFrame:
    """Une avisos reales con el catalogo por (baf, pieza, figura) para heredar nombres, anio y wave."""
    k = lambda d: d["baf"].str.lower() + "|" + d["pieza"].str.lower().str.strip() + "|" + d["figura"].str.lower()
    c = cat.assign(_k=k(cat)).drop_duplicates("_k")[["_k", "baf", "pieza", "figura", "anio", "wave"]]
    x = r[r["baf"].notna() & r["pieza_baf"].notna() & r["bafpieza_ok"]].copy()
    x["_k"] = x["baf"].str.lower() + "|" + x["pieza_baf"].str.lower().str.strip() + "|" + x["figura"].str.lower()
    return x.drop(columns=["baf", "figura", "anio", "wave"], errors="ignore").merge(c, on="_k", how="inner")


def load_listings() -> pd.DataFrame:
    """Avisos sinteticos + avisos reales de Lima que traen pieza de BAF (los reales llevan fuente='real')."""
    s = pd.read_csv(DATA / "listings.csv")
    s["fuente"] = "sintetico"
    x = _con_catalogo(load_reales(), load_catalog())
    x = x[x["local"]]
    real = pd.DataFrame({
        "id": 100000 + x["id"], "baf": x["baf"], "wave": x["wave"], "anio": x["anio"], "pieza": x["pieza"],
        "figura": x["figura"], "condicion": x["estado"], "incluye_pieza": True, "precio_pen": x["precio_pen"],
        "vendedor": x["vendedor"], "distrito": x["distrito"], "lat": x["lat"], "lon": x["lon"], "fuente": "real"})
    return pd.concat([s, real], ignore_index=True)


def ofertas_importacion(cat: pd.DataFrame | None = None) -> pd.DataFrame:
    """Avisos de eBay con pieza BAF: precio + envio a Peru si se conoce (sin aranceles ni IGV)."""
    cat = load_catalog() if cat is None else cat
    x = _con_catalogo(load_reales(), cat)
    x = x[x["importacion"]].copy()
    x["total_pen"] = x["precio_pen"] + x["envio_pen"].fillna(0)
    x["envio_conocido"] = x["envio_pen"].notna()
    return x[["baf", "pieza", "figura", "precio_pen", "envio_pen", "total_pen", "envio_conocido", "fuente", "notas"]]


def catalogo(cat: pd.DataFrame) -> dict:
    return {"bafs": sorted(cat["baf"].unique()), "figuras": sorted(cat["figura"].unique()),
            "distritos": sorted(DISTRITOS)}


def _con_envio(d: pd.DataFrame, distrito) -> pd.DataFrame:
    d = d.copy()
    destino = DISTRITOS.get(distrito or "")
    if d.empty or not destino:
        d["envio_pen"], d["eta_min"] = None, None
        d["total_pen"] = d["precio_pen"]
        return d
    q = pd.DataFrame([delivery_quote(haversine_km(la, lo, *destino)) for la, lo in zip(d["lat"], d["lon"])],
                     index=d.index)
    d = pd.concat([d, q[["envio_pen", "eta_min"]]], axis=1)
    d["total_pen"] = d["precio_pen"] + d["envio_pen"]
    return d


def ofertas_figura(lst: pd.DataFrame, figura: str, distrito=None, max_precio=None, baf=None) -> pd.DataFrame:
    d = lst[lst["figura"] == figura]
    if baf:
        d = d[d["baf"] == baf]
    if max_precio:
        d = d[d["precio_pen"] <= max_precio]
    return _con_envio(d, distrito).sort_values("total_pen")


def plan_baf(cat: pd.DataFrame, lst: pd.DataFrame, baf: str, tengo: set, distrito=None, max_precio=None, imp=None):
    """Por cada pieza que te falta, la mejor oferta (con pieza incluida). Devuelve (plan, resumen)."""
    piezas = cat[cat["baf"] == baf].drop_duplicates("pieza")
    filas = []
    for p in piezas.itertuples():
        if p.pieza in tengo:
            continue
        o = ofertas_figura(lst[lst["incluye_pieza"]], p.figura, distrito, max_precio, baf)
        o = o[o["pieza"] == p.pieza]
        io = imp[(imp["baf"] == baf) & (imp["pieza"] == p.pieza)].sort_values("total_pen") if imp is not None else None
        mejor_imp = io.iloc[0] if io is not None and len(io) else None
        mejor = o.iloc[0] if len(o) else None
        filas.append({
            "pieza": p.pieza, "figura": p.figura, "imagen": p.imagen_pieza,
            "referencia_usd": p.precio_figura_usd,
            "fuente": mejor["fuente"] if mejor is not None else None,
            "vendedor": mejor["vendedor"] if mejor is not None else None,
            "distrito": mejor["distrito"] if mejor is not None else None,
            "precio_pen": mejor["precio_pen"] if mejor is not None else None,
            "envio_pen": mejor["envio_pen"] if mejor is not None else None,
            "total_pen": mejor["total_pen"] if mejor is not None else None,
            "eta_min": mejor["eta_min"] if mejor is not None else None,
            "efecto_dm": (efecto_doble_marginalizacion(mejor["precio_pen"], retail_usd(p.anio))
                          if mejor is not None else None),
            "ebay_pen": mejor_imp["total_pen"] if mejor_imp is not None else None,
            "ebay_envio_conocido": bool(mejor_imp["envio_conocido"]) if mejor_imp is not None else None,
            "lat": mejor["lat"] if mejor is not None else None,
            "lon": mejor["lon"] if mejor is not None else None,
        })
    plan = pd.DataFrame(filas)
    resumen = {
        "total_piezas": len(piezas), "faltan": len(plan),
        "sin_oferta": int(plan["total_pen"].isna().sum()) if len(plan) else 0,
        "reales": int((plan["fuente"] == "real").sum()) if len(plan) else 0,
        "costo_pen": float(plan["total_pen"].sum()) if len(plan) else 0.0,
    }
    return plan, resumen
