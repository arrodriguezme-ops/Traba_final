"""Convierte lo que dice el coleccionista (texto o voz transcrita) en una consulta estructurada.

Ejemplos: "quiero armar el BAF Khonshu, vivo en Miraflores", "busco Werewolf By Night hasta 90 soles".
Dos caminos:
  1. Claude con salida estructurada (tool use) si hay ANTHROPIC_API_KEY.
  2. Reglas + fuzzy matching, sin internet, como respaldo.
"""
import os
import re
from typing import Optional

from pydantic import BaseModel, Field
from rapidfuzz import fuzz

MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-5-5")


class Consulta(BaseModel):
    baf: Optional[str] = Field(None, description="Build-A-Figure que quiere armar, ej. 'Khonshu'")
    figura: Optional[str] = Field(None, description="Figura puntual que busca, ej. 'Werewolf By Night'")
    max_precio_pen: Optional[float] = Field(None, description="Presupuesto maximo en soles")
    distrito: Optional[str] = Field(None, description="Distrito de Lima donde recibe")
    origen: str = "reglas"


def _norm(x: str) -> str:
    x = x.lower().translate(str.maketrans("áéíóúü", "aeiouu"))
    return re.sub(r"[^a-z0-9 ]", "", x.replace("-", " "))


def parse_llm(texto: str, cat: dict) -> Consulta:
    import anthropic

    schema = Consulta.model_json_schema()
    schema["properties"].pop("origen", None)
    resp = anthropic.Anthropic().messages.create(
        model=MODEL, max_tokens=300,
        system=("Extrae la consulta de un coleccionista peruano de Marvel Legends. Usa nombres canonicos cuando "
                "coincidan; no inventes. Moneda: soles."
                f"\nBAF conocidos: {cat['bafs']}\nDistritos: {cat['distritos']}"),
        tools=[{"name": "registrar_consulta", "description": "Registra la consulta", "input_schema": schema}],
        tool_choice={"type": "tool", "name": "registrar_consulta"},
        messages=[{"role": "user", "content": texto}],
    )
    for b in resp.content:
        if b.type == "tool_use":
            return Consulta(**b.input, origen=f"llm:{MODEL}")
    raise RuntimeError("sin tool_use")


def _precio(t: str) -> Optional[float]:
    m = re.search(r"(?:s/\.?|soles?|menos de|hasta|maximo|max)\s*(\d{2,5})", t) or re.search(r"(\d{2,5})\s*(?:soles|s/)", t)
    return float(m.group(1)) if m else None


def _mejor(t: str, opciones: list, minimo: int = 90, min_len: int = 4) -> Optional[str]:
    """Opcion mas larga cuyo nombre aparece (con tolerancia a errores) dentro del texto."""
    mejor, largo = None, 0
    for o in opciones:
        on = _norm(o)
        if len(on) >= min_len and fuzz.partial_ratio(on, t) >= minimo and len(on) > largo:
            mejor, largo = o, len(on)
    return mejor


def parse_reglas(texto: str, cat: dict) -> Consulta:
    t = _norm(texto)
    baf = _mejor(t, cat["bafs"], 92)
    figura = _mejor(t, cat["figuras"], 92, 5)
    if figura and baf and _norm(figura) in _norm(baf):
        figura = None  # "Khonshu" es el BAF, no una figura suelta
    distrito = next((d for d in cat["distritos"] if _norm(d) in t), None)
    return Consulta(baf=baf, figura=figura, max_precio_pen=_precio(texto.lower()), distrito=distrito)


def parse(texto: str, cat: dict) -> Consulta:
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            return parse_llm(texto, cat)
        except Exception as e:
            print(f"[parser] LLM fallo ({e}); uso reglas")
    return parse_reglas(texto, cat)
