"""Precio retail de referencia y efecto de doble marginalizacion (sobreprecio de reventa).

Efecto = (Precio_rev - P_retail) / P_retail, con ambos precios en soles.
  - Precio_rev: precio que ofrece el vendedor en Lima (S/).
  - P_retail: precio de lista de Hasbro en USD convertido a S/ con TIPO_CAMBIO.
Retail por anio: precio estandar de una figura sencilla (Legendsverse, "How much have Marvel Legends
prices gone up?"). Antes de 2012 no hay dato: el vendedor lo ingresa a mano.
"""
from pathlib import Path

import pandas as pd

TIPO_CAMBIO = 3.45  # supuesto S/ por USD (editable en la app)
_RETAIL = pd.read_csv(Path(__file__).resolve().parent.parent / "data" / "retail_por_anio.csv").set_index("anio")["retail_usd"]


def retail_usd(anio):
    """Retail estandar en USD para el anio, o None si no hay dato."""
    try:
        return float(_RETAIL.get(int(anio)))
    except (TypeError, ValueError):
        return None


def efecto_doble_marginalizacion(precio_rev_pen: float, retail_usd_: float, tc: float = TIPO_CAMBIO):
    """(Precio_rev - P_retail) / P_retail. Devuelve None si no hay retail valido."""
    if not retail_usd_ or retail_usd_ <= 0:
        return None
    p_retail = retail_usd_ * tc
    return (precio_rev_pen - p_retail) / p_retail
