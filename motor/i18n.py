"""Traducciones de los textos que manda la API (palancas, supuestos, alimentos, canon).

El español es el idioma fuente: los textos originales viven en escenario.py,
supuestos.json y fuentes.json, y `herramientas/extraer_textos.py` los junta en
datos/i18n/es.json con una clave por texto. Cada idioma es un archivo con las
mismas claves (datos/i18n/<idioma>.json). Si a un idioma le falta una clave,
se usa el español.
"""

import copy
import json
from functools import lru_cache
from pathlib import Path

IDIOMAS = ("es", "en", "pt", "fr", "de", "ar")
IDIOMA_FUENTE = "es"
CARPETA = Path(__file__).resolve().parent.parent / "datos" / "i18n"


def normalizar(lang: str | None) -> str:
    """'en', 'en-US' o 'EN_us' -> 'en'; cualquier otra cosa -> español."""
    codigo = (lang or IDIOMA_FUENTE).strip().lower().replace("_", "-").split("-")[0]
    return codigo if codigo in IDIOMAS else IDIOMA_FUENTE


@lru_cache(maxsize=None)
def textos(lang: str) -> dict[str, str]:
    ruta = CARPETA / f"{lang}.json"
    if not ruta.exists():
        return {}
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def t(lang: str, clave: str, defecto: str) -> str:
    return textos(lang).get(clave) or textos(IDIOMA_FUENTE).get(clave) or defecto


def traducir_palancas(esquema: dict, lang: str) -> dict:
    esquema = copy.deepcopy(esquema)
    for campo, p in esquema["properties"].items():
        p["etiqueta"] = t(lang, f"palancas.{campo}.etiqueta", p["etiqueta"])
        if "description" in p:
            p["description"] = t(lang, f"palancas.{campo}.descripcion", p["description"])
        p["grupo"] = t(lang, f"grupos.{p['grupo']}", p["grupo"])
    return esquema


def nombre_pool(clave: str, defecto: str, lang: str) -> str:
    return t(lang, f"pools.{clave}", defecto)


def traducir_supuestos(base: dict, lang: str) -> dict:
    base = copy.deepcopy(base)
    for clave in ("nota", "nota_ganado"):
        if clave in base:
            base[clave] = t(lang, clave, base[clave])
    for clave, v in base["valores"].items():
        v["descripcion"] = t(lang, f"supuestos.{clave}.descripcion", v["descripcion"])
        if v.get("derivacion"):
            v["derivacion"] = t(lang, f"supuestos.{clave}.derivacion", v["derivacion"])
        v["unidad"] = t(lang, f"unidades.{v['unidad']}", v["unidad"])
    for clave, tabla in base["tablas"].items():
        tabla["descripcion"] = t(lang, f"tablas.{clave}.descripcion", tabla["descripcion"])
        if tabla.get("derivacion"):
            tabla["derivacion"] = t(lang, f"tablas.{clave}.derivacion", tabla["derivacion"])
        tabla["unidad"] = t(lang, f"unidades.{tabla['unidad']}", tabla["unidad"])
    for clave, g in base["ganado"].items():
        g["nombre"] = t(lang, f"ganado.{clave}", g["nombre"])
    for clave, pool in base["pools"].items():
        pool["nombre"] = nombre_pool(clave, pool["nombre"], lang)
    return base


def traducir_hechos(hechos: list[dict], lang: str) -> list[dict]:
    """Solo los del canon se muestran en la app, así que solo esos tienen traducción."""
    salida = []
    for h in hechos:
        if h.get("dimension") == "canon":
            h = dict(h)
            h["statement"] = t(lang, f"hechos.{h['id']}.statement", h["statement"])
            if h.get("model_implication"):
                h["model_implication"] = t(lang, f"hechos.{h['id']}.model_implication", h["model_implication"])
        salida.append(h)
    return salida
