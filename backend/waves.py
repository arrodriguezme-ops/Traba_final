"""Vista por wave/linea: figuras de cada wave (con BAF o sin BAF), retail, valor de mercado y avisos reales."""
from __future__ import annotations

import re

import pandas as pd

from backend.matching import DATA, load_catalog, load_reales
from backend.pricing import TIPO_CAMBIO, efecto_doble_marginalizacion, retail_usd


def _norm(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def load_waves() -> pd.DataFrame:
    w = pd.read_csv(DATA / "marvel_legends_waves.csv")
    return w.sort_values(["anio", "wave"], ascending=[False, True]).reset_index(drop=True)


def _figuras_wave_df() -> pd.DataFrame:
    return pd.read_csv(DATA / "marvel_legends_waves_figuras.csv")


def _figuras_df() -> pd.DataFrame:
    return pd.read_csv(DATA / "marvel_legends_figuras.csv")


def figuras_de_wave(wave: str, cat: pd.DataFrame | None = None) -> pd.DataFrame:
    """Figuras del wave: figura, valor_mercado_usd, imagen, baf (si el wave es de un BAF)."""
    cat = load_catalog() if cat is None else cat
    if wave in set(cat["wave"].dropna()):
        d = cat[cat["wave"] == wave].drop_duplicates("figura")
        return pd.DataFrame({"figura": d["figura"], "valor_mercado_usd": d["precio_figura_usd"],
                             "imagen": d["imagen_pieza"], "baf": d["baf"]})
    wf = _figuras_wave_df()
    d = wf[wf["wave"] == wave][["figura", "url_figura"]].drop_duplicates("url_figura")
    d = d.merge(_figuras_df()[["url_figura", "valor_mercado_usd", "imagen"]].drop_duplicates("url_figura"),
                on="url_figura", how="left")
    d["baf"] = None
    return d[["figura", "valor_mercado_usd", "imagen", "baf"]]


def tabla_wave(wave: str, anio: int, retail_prom_usd, cat: pd.DataFrame | None = None, tc: float = TIPO_CAMBIO):
    """Por figura del wave: retail, valor de mercado y mejores avisos reales (Lima y eBay)."""
    figs = figuras_de_wave(wave, cat)
    retail = retail_usd(anio) or (retail_prom_usd if retail_prom_usd == retail_prom_usd and retail_prom_usd > 0 else None)
    retail = retail if retail and retail > 0 else None
    reales = load_reales()
    reales = reales.assign(_n=reales["figura"].map(_norm), _l=reales["linea_interpretada"].map(_norm))
    nw = _norm(wave)
    filas = []
    for f in figs.itertuples():
        # Un nombre como "Thor" o "Spider-Man" aparece en decenas de waves: solo cuenta como aviso de ESTE wave
        # si el aviso trae una linea que coincide con el wave (o el BAF del wave). Si no, queda como "wave sin confirmar".
        mismo = reales[reales["_n"] == _norm(f.figura)]
        ok = [(len(l) >= 6 and (l in nw or nw in l)) or (isinstance(b, str) and b == f.baf)
              for l, b in zip(mismo["_l"], mismo["baf"])]
        av = mismo[pd.Series(ok, index=mismo.index, dtype=bool)].sort_values("precio_pen")
        mejor = av.iloc[0] if len(av) else None
        filas.append({
            "figura": f.figura, "imagen": f.imagen, "baf": f.baf,
            "retail_usd": retail, "mercado_usd": f.valor_mercado_usd,
            "avisos": len(av),
            "mejor_pen": mejor["precio_pen"] if mejor is not None else None,
            "donde": (mejor["distrito"] if mejor is not None else None),
            "fuente": (mejor["fuente"] if mejor is not None else None),
            "efecto_dm": (efecto_doble_marginalizacion(mejor["precio_pen"], retail, tc)
                          if mejor is not None and retail else None),
        })
    return pd.DataFrame(filas), retail


def avisos_sin_wave(waves_con_aviso: set) -> pd.DataFrame:
    """Avisos reales con precio cuya figura no se pudo atar a un wave concreto (se muestran aparte)."""
    r = load_reales()
    r = r[~r["id"].isin(waves_con_aviso)]
    return r[["figura", "linea_interpretada", "estado", "precio_pen", "distrito", "fuente"]].sort_values("figura")
