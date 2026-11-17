"""Estimacion del precio 'justo' de reventa en Lima a partir de los avisos reales.

Regresion ridge sobre el logaritmo del precio en soles. Covariables: retail, estado, antiguedad, canal y
caracteristicas de la figura (BAF, Retro, exclusiva, Toy Biz, valor de mercado en EE. UU., cuantas versiones tiene el personaje).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backend.matching import load_catalog
from backend.pricing import TIPO_CAMBIO

EXCLUSIVAS = "walmart|target|amazon|walgreens|gamestop|sdcc|exclusive|toys-r-us|fan-channel|gamestop"
NOMBRES = {"lr": "Retail (log)", "nuevo": "Nuevo / en caja", "edad": "Antigüedad (años)", "ebay": "Canal eBay",
           "tailoy": "Canal Tai Loy", "baf": "Trae pieza de BAF", "retro": "Línea Retro", "excl": "Exclusiva de tienda",
           "toybiz": "Fabricante Toy Biz", "mercado": "Valor de mercado EE. UU. vs retail (log)",
           "tiene_mercado": "Tiene valor de mercado", "popular": "Versiones del personaje (log)"}
COLS = list(NOMBRES)
_FILTRO_DUDOSO = ("custom|lote|pack|linea_ambigua|no_legends|posible_replica|foto_de_catalogo|precio_muy_alto|"
                  "pieza_suelta|incompleto|subasta|precio_dudoso|sin_identificar")


def _caracteristicas(figs: pd.DataFrame) -> pd.DataFrame:
    """Covariables por empaque del catalogo (indexadas como figs)."""
    cat = load_catalog()
    baf = {(str(n).lower(), int(a)) for n, a in zip(cat["figura"], cat["anio"]) if pd.notna(a)}
    n_vers = figs.groupby("_n")["id"].transform("count")
    slug = figs["slug_figura"].fillna("").str.lower() + " " + figs["figura"].fillna("").str.lower()
    ratio = (figs["valor_mercado_usd"] / figs["retail_usd"]).where(figs["valor_mercado_usd"].notna() & (figs["retail_usd"] > 0))
    return pd.DataFrame({
        "lr": np.log(figs["retail_usd"] * TIPO_CAMBIO),
        "edad": 2026 - figs["anio"].astype(float),
        "baf": [float((str(n).lower(), int(a)) in baf) for n, a in zip(figs["figura"], figs["anio"])],
        "retro": slug.str.contains("retro").astype(float),
        "excl": slug.str.contains(EXCLUSIVAS).astype(float),
        "toybiz": figs["fabricante"].fillna("").str.contains("Toy", case=False).astype(float),
        "mercado": np.log(ratio.clip(0.2, 5)).fillna(0.0),
        "tiene_mercado": ratio.notna().astype(float),
        "popular": np.log(n_vers.astype(float)),
    }, index=figs.index)


def _matriz(caract: pd.DataFrame, nuevo, ebay, tailoy) -> pd.DataFrame:
    x = caract.copy()
    x["nuevo"], x["ebay"], x["tailoy"] = nuevo, ebay, tailoy
    return x[COLS]


def ajustar(figs: pd.DataFrame, reales: pd.DataFrame, lam: float = 3.0) -> dict | None:
    caract = _caracteristicas(figs)
    clave = figs.assign(_i=figs.index).drop_duplicates(["_n", "anio"]).set_index(["_n", "anio"])["_i"]
    b = reales[reales["efecto_dm"].notna()].copy()
    b = b[~b["marca_calidad"].fillna("").str.contains(_FILTRO_DUDOSO)
          & ~b["tipo_aviso"].fillna("").isin(["lote", "lote_ebay", "preventa", "compra_historica"])]
    b = b[b["canal"].isin(["Facebook Marketplace", "eBay (sin envio ni aranceles)", "Tai Loy", "Tai Loy (historico Wayback)"])]
    b = b.sort_values("fecha_publicacion", na_position="first").drop_duplicates(["vendedor", "_n", "anio"], keep="last")
    pos = [clave.get((n, int(a))) for n, a in zip(b["_n"], b["anio"])]
    b = b[[p is not None for p in pos]]
    pos = [p for p in pos if p is not None]
    if len(b) < 30:
        return None
    X = _matriz(caract.loc[pos].reset_index(drop=True),
                b["estado"].fillna("").str.contains("sellad|nuevo|caja").astype(float).values,
                b["canal"].str.startswith("eBay").astype(float).values,
                b["canal"].str.startswith("Tai Loy").astype(float).values)
    y = np.log(b["precio_pen"].astype(float).values)
    mu, sd = X.mean(), X.std().replace(0, 1)
    Z = np.column_stack([np.ones(len(X)), ((X - mu) / sd).values])
    pen = lam * np.eye(Z.shape[1]); pen[0, 0] = 0

    def fit(Z, y):
        return np.linalg.solve(Z.T @ Z + pen, Z.T @ y)

    beta = fit(Z, y)
    res = y - Z @ beta
    err, base, simple = [], [], []
    zs = [0, 1, 2, 3]  # constante, retail, nuevo, edad
    for i in range(len(y)):
        m = np.ones(len(y), bool); m[i] = False
        bb = fit(Z[m], y[m])
        err.append(abs(np.exp(Z[i] @ bb) - np.exp(y[i])))
        base.append(abs(np.median(np.exp(y[m])) - np.exp(y[i])))
        bs = np.linalg.lstsq(Z[m][:, zs], y[m], rcond=None)[0]
        simple.append(abs(np.exp(Z[i, zs] @ bs) - np.exp(y[i])))
    # efecto por covariable en % (cambio de 1 desviacion tipica) y coeficiente en unidades originales
    coef = beta[1:] / sd.values
    efectos = pd.DataFrame({"covariable": [NOMBRES[c] for c in COLS], "coef": coef,
                            "efecto_pct": np.exp(coef) - 1}).set_index("covariable")
    return dict(beta=beta, mu=mu, sd=sd, sigma=float(res.std(ddof=len(beta))), n=len(y),
                r2=float(1 - res.var() / y.var()), mae=float(np.mean(err)), mae_base=float(np.mean(base)),
                mae_simple=float(np.mean(simple)), efectos=efectos, caract=caract)


def estimar(m: dict, indice, nuevo: bool, canal: str = "marketplace") -> dict | None:
    """Precio estimado (S/) y rango del 80 % para el empaque `indice` del catalogo."""
    x = m["caract"].loc[[indice]]
    if x["lr"].isna().any():
        return None
    X = _matriz(x.reset_index(drop=True), float(nuevo), float(canal == "ebay"), float(canal == "tailoy"))
    z = np.concatenate([[1.0], ((X - m["mu"]) / m["sd"]).values[0]])
    mu = float(z @ m["beta"]); s = m["sigma"]
    return dict(estimado=float(np.exp(mu)), p10=float(np.exp(mu - 1.2816 * s)), p90=float(np.exp(mu + 1.2816 * s)))
