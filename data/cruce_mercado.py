"""Cruza retail historico (Legendsverse), tiendas peruanas, avisos reales e importaciones (Veritrade).

Salidas (solo datos derivados; los archivos de Veritrade NO se suben al repo):
  data/importaciones_ml_resumen.csv  importaciones de Marvel Legends por anio y tipo de importador
  data/tiendas_pe_cruzado.csv        cada producto de tienda con su figura, anio, retail y sobreprecio
  data/cadena_precios.csv            FOB -> retail EE. UU. -> tienda en Peru -> reventa (mediana por anio)

Uso: python data/cruce_mercado.py [carpeta_con_los_xls_de_veritrade]
  Sin carpeta, se omite la parte de importaciones y se reutiliza importaciones_ml_resumen.csv si existe.
"""
import glob
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT.parent))
from backend.pricing import TIPO_CAMBIO  # noqa: E402

# Lineas de Hasbro que NO son Marvel Legends aunque digan Marvel/Legends en la DUA
NO_ML = r"9\.5 ?IN|OLYMPUS|TITAN HERO|MASTERVERSE|MOTU|BEND AND FLEX|EPIC HERO|ROLEPLAY|MASK|GLOVE|BLASTER"
ES_ML = r"MARVEL LEGENDS?|\bLEGENDS? SERIES\b|\b(AVN|MVL|SPD|XMN|XMEN|X-MEN|GOTG|BPN|CAP|IRM|DPL)\b[^,|]{0,25}\bLEG(END|ENDS)?\b"


def importaciones(carpeta: str) -> pd.DataFrame:
    cols = ["Fecha", "Importador", "Qty 1", "U$ FOB Tot", "U$ FOB Und 1", "Descripcion Comercial", "Descripcion1"]
    fr = []
    for f in sorted(glob.glob(str(Path(carpeta) / "**" / "*.xls"), recursive=True)):
        d = pd.read_csv(f, sep="\t", usecols=cols, encoding="latin-1", low_memory=False)
        fr.append(d)
    d = pd.concat(fr, ignore_index=True)
    txt = (d["Descripcion Comercial"].fillna("") + " " + d["Descripcion1"].fillna("")).str.upper()
    d = d[txt.str.contains(ES_ML.replace('(', '(?:'), regex=True) & ~txt.str.contains(NO_ML, regex=True)].copy()
    d["anio"] = pd.to_datetime(d["Fecha"], errors="coerce").dt.year
    imp = d["Importador"].astype(str).str.upper()
    d["tipo_importador"] = imp.map(lambda s: "Hasbro Peru (distribuidor oficial)" if "HASBRO" in s
                                   else "Otras empresas (tiendas y revendedores)")
    g = d.groupby(["anio", "tipo_importador"]).agg(
        filas=("Fecha", "size"), importadores=("Importador", "nunique"), unidades=("Qty 1", "sum"),
        fob_total_usd=("U$ FOB Tot", "sum"), fob_und_mediana_usd=("U$ FOB Und 1", "median")).reset_index()
    g["fob_und_promedio_usd"] = (g["fob_total_usd"] / g["unidades"]).round(2)
    return g.round(2)


# Palabras que nombran la linea o el empaque, no al personaje
LINEA = set("""figura figuras accion action figure de del la el los las y and the of marvel marvels legends legend series
hasbro cm pulgadas in retro collection coleccion avengers vengadores doomsday xmen 97 anniversary aniversario 80th 85th
60th 50th 20th rivals gamerverse exclusive exclusivo comic ver version no way home brand new day infinity saga studios
spiderman universe mcu gotg guardians galaxia galaxy wave baf build pack set edition edicion especial original nuevo
sellado caja oficial juguete coleccionable vintage classic clasico serie deadpool wolverine fantastic four astonishing
across spiderverse beyond earths mightiest secret wars disney plus series2 2pack 3pack con sin miedo hombre""".split())


def _tok(t: str) -> set:
    t = str(t).lower().replace("spider-man", "spiderman").replace("x-men", "xmen").replace("’", "'").replace("'s", "")
    return {w for w in re.findall(r"[a-z0-9]+", t) if len(w) >= 2}


def cruza_tiendas(ret: pd.DataFrame) -> pd.DataFrame:
    t = pd.read_csv(ROOT / "tiendas_pe.csv", dtype={"ean": str})
    t = t[t["es_legends"] & t["precio_pen"].notna() & (t["precio_pen"] > 0)].copy()
    # Plaza Vea y Oechsle (mismo grupo) publican los mismos productos de los mismos vendedores: se cuenta una vez
    t = t.sort_values("tienda").drop_duplicates(["titulo", "precio_pen", "vendedor"])
    # Las tiendas venden stock reciente: se compara contra empaques Hasbro de 2019 en adelante.
    # Regla conservadora: todas las palabras del nombre de la figura deben estar en el titulo; gana el nombre mas
    # largo (y, si empatan, el mas reciente). Confianza "alta" solo si al titulo no le sobran palabras que no sean de
    # linea/empaque: asi "Retro Spider-Man Tarantula" no se confunde con "Spider-Man".
    cand = ret[(ret["anio"] >= 2019) & ret["retail_usd"].notna()].sort_values("anio", ascending=False)
    cand = cand.assign(_t=cand["figura"].map(_tok))
    filas = []
    for r in t.itertuples():
        T = _tok(r.titulo)
        ok = cand[cand["_t"].map(lambda N: bool(N) and N <= T)]
        if ok.empty:
            filas.append((None, None, None, None, None, "sin figura"))
            continue
        c = ok.loc[ok["_t"].map(len).sort_values(ascending=False, kind="stable").index[0]]
        sobra = {w for w in T - c["_t"] - LINEA if not w.isdigit() or len(w) > 2}
        conf = "alta" if not sobra else "baja"
        filas.append((c["figura"], int(c["anio"]), c["retail_usd"], c["valor_mercado_usd"], int(c["n_figuras_pack"] or 1),
                      conf))
    t[["figura", "anio", "retail_usd", "valor_mercado_usd", "n_figuras_pack", "confianza"]] = pd.DataFrame(
        filas, index=t.index)
    p_retail = t["retail_usd"] * TIPO_CAMBIO
    t["efecto_dm"] = ((t["precio_pen"] - p_retail) / p_retail).where(t["confianza"] == "alta").round(3)
    return t


def cadena(ret: pd.DataFrame, tiendas: pd.DataFrame, imp: pd.DataFrame | None) -> pd.DataFrame:
    reales = pd.read_csv(ROOT / "listings_reales.csv")
    reales = reales[reales["precio_pen"].notna() & reales["fuente"].eq("Facebook Marketplace")]
    filas = []
    for a in range(2019, 2027):
        r = ret[(ret["anio"] == a) & (ret["n_figuras_pack"] == 1)]["retail_usd"].median()
        fob = None
        if imp is not None:
            h = imp[(imp["anio"] == a) & imp["tipo_importador"].str.startswith("Hasbro")]
            fob = h["fob_und_promedio_usd"].iloc[0] if len(h) else None
        ta = tiendas[(tiendas["anio"] == a) & (tiendas["confianza"] == "alta")]
        ti = ta["precio_pen"].median()
        filas.append({"anio": a, "fob_und_hasbro_peru_usd": fob, "retail_hasbro_eeuu_usd": r,
                      "retail_pen_al_tc": round(r * TIPO_CAMBIO, 2) if r == r else None,
                      "tienda_pe_mediana_pen": ti, "n_tienda": len(ta)})
    c = pd.DataFrame(filas)
    c.attrs["marketplace_mediana_pen"] = reales["precio_pen"].median()
    return c


def main() -> None:
    ret = pd.read_csv(ROOT / "marvel_legends_retail_historico.csv")
    imp = None
    if len(sys.argv) > 1:
        imp = importaciones(sys.argv[1])
        imp.to_csv(ROOT / "importaciones_ml_resumen.csv", index=False)
    elif (ROOT / "importaciones_ml_resumen.csv").exists():
        imp = pd.read_csv(ROOT / "importaciones_ml_resumen.csv")
    tiendas = cruza_tiendas(ret)
    tiendas.to_csv(ROOT / "tiendas_pe_cruzado.csv", index=False)
    c = cadena(ret, tiendas, imp)
    c.to_csv(ROOT / "cadena_precios.csv", index=False)
    pd.set_option("display.width", 200)
    if imp is not None:
        print(imp.to_string(index=False))
    alta = tiendas["confianza"] == "alta"
    print(f"\nTiendas: {len(tiendas)} productos Legends con precio; figura identificada con confianza alta: {alta.sum()}")
    print(tiendas.assign(alta=alta).groupby("tienda").agg(n=("titulo", "size"), alta=("alta", "sum"),
                                        mediana_pen=("precio_pen", "median"), efecto_mediano=("efecto_dm", "median")))
    print("\n", c.to_string(index=False))
    print("Mediana Facebook Marketplace (avisos reales):", c.attrs["marketplace_mediana_pen"])


if __name__ == "__main__":
    main()
