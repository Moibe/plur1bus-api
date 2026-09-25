"""Junta en datos/i18n/es.json todos los textos en español que muestra la API.

Es la fuente de las traducciones: cada idioma (datos/i18n/<idioma>.json) debe
tener exactamente estas claves. Correr después de cambiar textos en
escenario.py, supuestos.json o los hechos del canon en fuentes.json:

    python herramientas/extraer_textos.py

La prueba test_i18n.py falla si es.json quedó desfasado o si a un idioma le
falta o le sobra una clave.
"""

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from motor import supuestos as S  # noqa: E402
from motor.escenario import palancas  # noqa: E402
from motor.i18n import CARPETA  # noqa: E402

# Las unidades se guardan como identificadores sin acentos; así se muestran en español.
UNIDADES_ES = {
    "adimensional": "adimensional",
    "cabezas": "cabezas",
    "dias": "días",
    "fraccion": "fracción",
    "fraccion/anio": "fracción por año",
    "fraccion/dia": "fracción por día",
    "kcal": "kcal",
    "kcal/anio": "kcal por año",
    "kcal/dia": "kcal/día",
    "kcal/kg": "kcal/kg",
    "kcal/persona/dia": "kcal por persona al día",
    "kg": "kg",
    "Mt": "Mt",
    "Mt/anio": "Mt por año",
    "nacimientos/persona/anio": "nacimientos por persona al año",
    "personas": "personas",
    "personas/dia": "personas por día",
}


def extraer() -> dict[str, str]:
    textos: dict[str, str] = {}

    for campo, p in palancas()["properties"].items():
        textos[f"palancas.{campo}.etiqueta"] = p["etiqueta"]
        textos[f"palancas.{campo}.descripcion"] = p["description"]
        textos[f"grupos.{p['grupo']}"] = p["grupo"]

    base = S.cargar()
    textos["nota"] = base["nota"]
    textos["nota_ganado"] = base["nota_ganado"]
    unidades = set()
    for clave, v in base["valores"].items():
        textos[f"supuestos.{clave}.descripcion"] = v["descripcion"]
        if v.get("derivacion"):
            textos[f"supuestos.{clave}.derivacion"] = v["derivacion"]
        unidades.add(v["unidad"])
    for clave, tabla in base["tablas"].items():
        textos[f"tablas.{clave}.descripcion"] = tabla["descripcion"]
        if tabla.get("derivacion"):
            textos[f"tablas.{clave}.derivacion"] = tabla["derivacion"]
        unidades.add(tabla["unidad"])
    for u in unidades:
        if u not in UNIDADES_ES:
            raise SystemExit(f"Unidad sin texto en español: {u!r} (agrégala a UNIDADES_ES)")
        textos[f"unidades.{u}"] = UNIDADES_ES[u]
    for clave, g in base["ganado"].items():
        textos[f"ganado.{clave}"] = g["nombre"]
    for clave, pool in base["pools"].items():
        textos[f"pools.{clave}"] = pool["nombre"]

    for h in S.fuentes().get("facts", []):
        if h.get("dimension") == "canon":
            textos[f"hechos.{h['id']}.statement"] = h["statement"]
            if h.get("model_implication"):
                textos[f"hechos.{h['id']}.model_implication"] = h["model_implication"]

    return dict(sorted(textos.items()))


def main() -> None:
    CARPETA.mkdir(parents=True, exist_ok=True)
    textos = extraer()
    (CARPETA / "es.json").write_text(json.dumps(textos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"datos/i18n/es.json: {len(textos)} textos")


if __name__ == "__main__":
    main()
