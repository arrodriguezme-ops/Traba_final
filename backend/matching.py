"""Catalogo de BAF/piezas, avisos de Lima y el plan para completar un BAF."""
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
}


def load_catalog() -> pd.DataFrame:
    return pd.read_csv(DATA / "marvel_legends_baf.csv").dropna(subset=["figura"])


def load_listings() -> pd.DataFrame:
    return pd.read_csv(DATA / "listings.csv")


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


def plan_baf(cat: pd.DataFrame, lst: pd.DataFrame, baf: str, tengo: set, distrito=None, max_precio=None):
    """Por cada pieza que te falta, la mejor oferta (con pieza incluida). Devuelve (plan, resumen)."""
    piezas = cat[cat["baf"] == baf].drop_duplicates("pieza")
    filas = []
    for p in piezas.itertuples():
        if p.pieza in tengo:
            continue
        o = ofertas_figura(lst[lst["incluye_pieza"]], p.figura, distrito, max_precio, baf)
        o = o[o["pieza"] == p.pieza]
        mejor = o.iloc[0] if len(o) else None
        filas.append({
            "pieza": p.pieza, "figura": p.figura, "imagen": p.imagen_pieza,
            "referencia_usd": p.precio_figura_usd,
            "vendedor": mejor["vendedor"] if mejor is not None else None,
            "distrito": mejor["distrito"] if mejor is not None else None,
            "precio_pen": mejor["precio_pen"] if mejor is not None else None,
            "envio_pen": mejor["envio_pen"] if mejor is not None else None,
            "total_pen": mejor["total_pen"] if mejor is not None else None,
            "eta_min": mejor["eta_min"] if mejor is not None else None,
            "efecto_dm": (efecto_doble_marginalizacion(mejor["precio_pen"], retail_usd(p.anio))
                          if mejor is not None else None),
            "lat": mejor["lat"] if mejor is not None else None,
            "lon": mejor["lon"] if mejor is not None else None,
        })
    plan = pd.DataFrame(filas)
    resumen = {
        "total_piezas": len(piezas), "faltan": len(plan),
        "sin_oferta": int(plan["total_pen"].isna().sum()) if len(plan) else 0,
        "costo_pen": float(plan["total_pen"].sum()) if len(plan) else 0.0,
    }
    return plan, resumen
