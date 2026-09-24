"""Supuestos base del modelo, leídos de datos/supuestos.json.

supuestos.json es la capa curada: cada valor trae rango (bajo/alto), unidad,
descripción, las fuentes que lo respaldan (ids de datos/fuentes.json, el set
investigado y verificado) y, cuando no se toma tal cual, la derivación.
El motor solo lee de aquí; cambiar un número no requiere tocar código.
"""

import json
from functools import lru_cache
from pathlib import Path

DATOS = Path(__file__).resolve().parent.parent / "datos"


@lru_cache(maxsize=1)
def cargar() -> dict:
    with open(DATOS / "supuestos.json", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def fuentes() -> dict:
    ruta = DATOS / "fuentes.json"
    if not ruta.exists():
        return {"params": [], "facts": []}
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def valor(clave: str) -> float:
    return float(cargar()["valores"][clave]["valor"])


def rango(clave: str) -> tuple[float, float]:
    v = cargar()["valores"][clave]
    return float(v["bajo"]), float(v["alto"])


def tabla(clave: str) -> list[float]:
    return [float(x) for x in cargar()["tablas"][clave]["valores"]]


def ganado() -> dict[str, dict]:
    return cargar()["ganado"]


def pools() -> dict[str, dict]:
    return cargar()["pools"]
