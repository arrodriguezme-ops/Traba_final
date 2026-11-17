"""Pass-through semiestructural: cuanto del costo en USD y del tipo de cambio llega al precio final en soles.

Modelo (log-log, efectos fijos de canal):  ln P_pen = a_canal + b_R * ln R_usd + b_TC * ln TC_epoca + g' controles + e
  b_R  : elasticidad del precio final al precio de lista en USD (retail de Hasbro)
  b_TC : pass-through del tipo de cambio (1 = traslado completo, <1 = incompleto)
Ademas: pass-through en niveles  dP/d(R*TC)  (soles de precio final por sol de costo de lista), comparable con los benchmarks teoricos.
Errores estandar por bootstrap agrupado por figura.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

EXCLUIR = "custom|lote|pack|accesorio|pieza_suelta|no_legends|precio_dudoso|incompleto|subasta|sin_identificar|replica|foto_de_catalogo|precio_muy_alto"
FORMALES = ["Falabella", "Oechsle", "Plaza Vea / Oechsle", "Tai Loy", "Tai Loy (historico Wayback)", "Seven Figuarts (historico Wayback)",
            "Toys Master (historico Wayback)"]
REVENTA = ["Facebook Marketplace", "eBay (sin envio ni aranceles)", "MercadoLibre Peru (2010-2011)"]

# Benchmarks teoricos de pass-through del costo mayorista al precio final con demanda lineal / elasticidad constante
BENCHMARKS = [("Competencia perfecta (costo marginal constante)", 1.0),
              ("Monopolio integrado, demanda lineal", 0.5),
              ("Doble marginalizacion, demanda lineal (2 capas)", 0.25),
              ("Doble marginalizacion, elasticidad constante", None)]  # >=1: depende de los margenes


POPULARES = (r"spider|peter parker|miles morales|gwen|venom|wolverine|logan|iron man|tony stark|thor|captain america|steve rogers|cyclops|ciclope|"
             r"x-?men|storm|rogue|gambit|jean grey|phoenix|beast|nightcrawler|magneto|professor x|emma frost|psylocke|colossus|bishop|"
             r"doctor strange|dr\.? strange|fantastic|mr\.? fantastic|human torch|invisible woman|the thing|reed richards|sue storm|johnny storm|ben grimm")
PELI_SPIDERVERSO = r"into the|across the|spider-?verse movie|\(movie\)|pelicula"
DELUXE_TXT = r"maximum|deluxe|retro"


def _marca_linea(x: pd.DataFrame) -> pd.DataFrame:
    """popular: personaje X-Men/Spider-verso (no de pelicula)/Avengers clasicos/4 Fantasticos/Strange.
    deluxe: lineas tipo Maximum/Deluxe (por titulo, nombre o slug del catalogo)."""
    from backend.figuras import _norm
    from backend.matching import load_catalog
    cat = load_catalog()
    baf = {(_norm(n), int(a)) for n, a in zip(cat["figura"], cat["anio"]) if pd.notna(a)}
    txt = (x["figura"].fillna("") + " " + x["titulo_original"].fillna("")).str.lower()
    x["popular"] = (txt.str.contains(POPULARES) & ~txt.str.contains(PELI_SPIDERVERSO)).astype(float)
    from backend.matching import DATA
    c = pd.read_csv(DATA / "marvel_legends_retail_historico.csv")
    slug = {(_norm(n), int(a)): str(sl).lower() for n, a, sl in zip(c["figura"], c["anio"], c["slug_figura"]) if pd.notna(a)}
    txt_cat = pd.Series([slug.get((_norm(n), int(a)), "") for n, a in zip(x["figura"], x["anio"])], index=x.index)
    x["deluxe_txt"] = (txt + " " + txt_cat).str.contains(DELUXE_TXT).astype(float)
    x["deluxe"] = x["deluxe_txt"]
    return x


def muestra(d: pd.DataFrame, solo_estandar: bool = True) -> pd.DataFrame:
    x = d[d["figura"].notna() & d["retail_usd"].notna() & d["precio_pen"].notna() & d["fecha"].notna()].copy()
    x = x[~x["marca_calidad"].fillna("").str.contains(EXCLUIR)]
    x = x[x["canal"].isin(FORMALES + REVENTA)]
    if solo_estandar:
        x = x[x["retail_usd"].between(14.99, 29.99)]  # 6" estandar: evita deluxe, 12" y packs
    x = x[(x["precio_pen"] > 10) & (x["precio_pen"] < 1500)]
    x = _marca_linea(x)
    x["grupo"] = np.where(x["canal"].isin(FORMALES), "Tiendas formales", "Reventa")
    x["lp"] = np.log(x["precio_pen"])
    x["lr"] = np.log(x["retail_usd"])
    x["ltc"] = np.log(x["tc_epoca"])
    x["nuevo"] = x["estado"].fillna("").str.contains("sellad|nuevo|caja", case=False).astype(float)
    x["edad"] = (x["anio_obs"] - x["anio"]).clip(lower=0).astype(float)
    x["cl"] = x["figura"].astype(str) + "|" + x["anio"].astype(int).astype(str)
    # un precio por figura-canal-fecha (evita contar dos veces el mismo aviso)
    x = x.drop_duplicates(["cl", "canal", "fecha", "vendedor", "precio_pen"])
    return x.reset_index(drop=True)


def _x(x: pd.DataFrame, tendencia: bool, controles: bool, fe_canal: bool = True, linea: bool = False) -> tuple[np.ndarray, list[str]]:
    cols = {"lr": x["lr"].values, "ltc": x["ltc"].values}
    if controles:
        cols["nuevo"] = x["nuevo"].values
        cols["edad"] = x["edad"].values
    if linea:
        cols["popular"] = x["popular"].values
        cols["deluxe"] = x["deluxe"].values
    if tendencia:
        cols["tendencia"] = (x["anio_obs"] - 2010).values.astype(float)
    nom = list(cols)
    M = [np.ones(len(x))] + list(cols.values())
    nom = ["const"] + nom
    if fe_canal:
        for c in sorted(x["canal"].unique())[1:]:
            M.append((x["canal"] == c).astype(float).values)
            nom.append(f"canal:{c}")
    return np.column_stack(M), nom


def _ols(X, y):
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    return b


def estimar(x: pd.DataFrame, tendencia=False, controles=True, linea=False, B: int = 300, semilla: int = 7):
    """Devuelve coeficientes (lr, ltc) con IC95 por bootstrap agrupado por figura-ano."""
    if len(x) < 30:
        return None
    X, nom = _x(x, tendencia, controles, linea=linea)
    y = x["lp"].values
    b = _ols(X, y)
    rng = np.random.default_rng(semilla)
    grupos = x.groupby("cl").indices
    claves = list(grupos)
    boots = []
    for _ in range(B):
        sel = rng.choice(len(claves), len(claves))
        idx = np.concatenate([grupos[claves[i]] for i in sel])
        try:
            boots.append(_ols(X[idx], y[idx]))
        except Exception:
            continue
    boots = np.array(boots)
    out = {"n": len(x), "figuras": len(claves), "r2": float(1 - ((y - X @ b) ** 2).sum() / ((y - y.mean()) ** 2).sum())}
    for k in ("lr", "ltc") + (("popular", "deluxe") if linea else ()):
        j = nom.index(k)
        out[k] = (float(b[j]), float(np.percentile(boots[:, j], 2.5)), float(np.percentile(boots[:, j], 97.5)))
    return out


def niveles(x: pd.DataFrame, B: int = 300, semilla: int = 7):
    """Pass-through en niveles: pendiente de precio final (S/) sobre costo de lista (R * TC), con efectos fijos de canal."""
    if len(x) < 30:
        return None
    c = (x["retail_usd"] * x["tc_epoca"]).values
    X = np.column_stack([np.ones(len(x)), c] + [(x["canal"] == k).astype(float).values for k in sorted(x["canal"].unique())[1:]])
    y = x["precio_pen"].values
    b = _ols(X, y)
    rng = np.random.default_rng(semilla)
    grupos = x.groupby("cl").indices
    claves = list(grupos)
    bs = []
    for _ in range(B):
        sel = rng.choice(len(claves), len(claves))
        idx = np.concatenate([grupos[claves[i]] for i in sel])
        bs.append(_ols(X[idx], y[idx])[1])
    return float(b[1]), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


def tabla(d: pd.DataFrame, B: int = 300) -> pd.DataFrame:
    base = muestra(d)
    filas = []
    espec = [("Todos los canales", base, False, False), ("Todos, controlando popular y deluxe", base, False, True),
             ("Solo populares, sin deluxe", base[(base["popular"] == 1) & (base["deluxe"] == 0)], False, True),
             ("Solo no populares, sin deluxe", base[(base["popular"] == 0) & (base["deluxe"] == 0)], False, True),
             ("Tiendas formales, con popular y deluxe", base[base["grupo"] == "Tiendas formales"], False, True),
             ("Reventa, con popular y deluxe", base[base["grupo"] == "Reventa"], False, True),
             ("Solo 2022-2026, con popular y deluxe", base[base["anio_obs"] >= 2022], False, True)]
    for nombre, x, tend, lin in espec:
        r = estimar(x, tendencia=tend, linea=lin, B=B)
        nv = niveles(x, B=B)
        if r is None:
            continue
        filas.append(dict(modelo=nombre, n=r["n"], figuras=r["figuras"], r2=r["r2"],
                          b_lista=r["lr"][0], b_lista_lo=r["lr"][1], b_lista_hi=r["lr"][2],
                          b_tc=r["ltc"][0], b_tc_lo=r["ltc"][1], b_tc_hi=r["ltc"][2],
                          b_pop=r.get("popular", (np.nan,))[0], b_dlx=r.get("deluxe", (np.nan,))[0], niv=nv[0] if nv else np.nan, niv_lo=nv[1] if nv else np.nan, niv_hi=nv[2] if nv else np.nan))
    return pd.DataFrame(filas)


if __name__ == "__main__":
    import sys
    from backend.matching import DATA
    sys.stdout.reconfigure(encoding="utf-8")
    d = pd.read_csv(DATA / "observaciones_precios.csv", parse_dates=["fecha"])
    m = muestra(d)
    print(len(m), m["grupo"].value_counts().to_dict(), m["anio_obs"].value_counts().sort_index().to_dict())
    print(m[["popular", "deluxe", "deluxe_txt"]].mean().round(2).to_dict())
    pd.set_option("display.width", 250)
    print(tabla(d, B=200).round(2).to_string())
