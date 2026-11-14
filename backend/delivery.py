"""Costo y tiempo estimado de entrega con repartidores independientes en Lima.

SUPUESTOS (a validar en las entrevistas): tarifa base + tarifa por km en moto,
y velocidad media urbana con trafico. Son numeros de modelo, no datos medidos.
"""
from math import asin, cos, radians, sin, sqrt

TARIFA_BASE_PEN = 6.0
TARIFA_KM_PEN = 1.2
MIN_BASE = 20      # minutos de recojo
MIN_POR_KM = 4.0   # ~15 km/h promedio en Lima


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


def delivery_quote(km: float) -> dict:
    # distancia en calle ~ 1.3 x linea recta
    km_calle = km * 1.3
    return {
        "km": round(km_calle, 1),
        "envio_pen": round(TARIFA_BASE_PEN + TARIFA_KM_PEN * km_calle, 1),
        "eta_min": int(MIN_BASE + MIN_POR_KM * km_calle),
    }
