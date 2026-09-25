"""
API de cálculo de Plur1bus: ¿cuánto dura la comida de la colmena?

Arranca con:        uvicorn main:app --reload --port 8004
Docs interactivas:  http://127.0.0.1:8004/docs
"""

import math
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from motor import i18n, supuestos
from motor.escenario import Escenario, palancas
from motor.simulacion import simular

load_dotenv()

app = FastAPI(title="Plur1bus: supervivencia de la colmena", version="0.0.1")

# --- CORS ---------------------------------------------------------------------
# El front (SvelteKit) pega directo desde el navegador. Sin CORS_ORIGINS se
# acepta cualquier puerto de localhost/127.0.0.1: Vite sube de puerto solo si
# 5173 está ocupado, y así no se rompe en silencio. En un servidor se fija la
# lista: CORS_ORIGINS="https://mi-front.com".
origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=None if origins else r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


def _sin_no_finitos(x):
    """NaN/Infinity no son JSON válido: se devuelven como texto dentro del error."""
    if isinstance(x, float) and not math.isfinite(x):
        return str(x)
    if isinstance(x, dict):
        return {k: _sin_no_finitos(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_sin_no_finitos(v) for v in x]
    return x


@app.exception_handler(RequestValidationError)
async def error_de_validacion(_: Request, exc: RequestValidationError):
    # El handler por defecto truena (500) al serializar un NaN que venía en el body.
    return JSONResponse(status_code=422, content={"detail": _sin_no_finitos(jsonable_encoder(exc.errors()))})


@app.get("/health")
def health():
    return {"ok": True}


# Todos los endpoints con texto aceptan ?lang=es|en|pt|fr|de|ar (español si no viene
# o no se conoce). Los números no cambian: solo etiquetas, explicaciones y nombres.


@app.get("/escenario")
def escenario(lang: str = "es"):
    """Palancas del escenario con rangos, textos y defaults, para armar los controles."""
    return i18n.traducir_palancas(palancas(), i18n.normalizar(lang))


@app.post("/simular")
def post_simular(e: Escenario, lang: str = "es"):
    lang = i18n.normalizar(lang)
    r = simular(e)
    fuentes = [{**f, "nombre": i18n.nombre_pool(f["clave"], f["nombre"], lang)} for f in r.fuentes]
    return {"escenario": e.model_dump(), "resumen": r.resumen, "fuentes": fuentes, "serie": r.serie}


@app.get("/supuestos")
def get_supuestos(lang: str = "es"):
    """Valores base del modelo, cada uno con rango, unidad y las fuentes que lo respaldan."""
    base = i18n.traducir_supuestos(supuestos.cargar(), i18n.normalizar(lang))
    por_id = {p["id"]: p for p in supuestos.fuentes().get("params", [])}
    valores = {
        clave: {**v, "fuentes_detalle": [por_id[f] for f in v.get("fuentes", []) if f in por_id]}
        for clave, v in base["valores"].items()
    }
    return {**base, "valores": valores}


@app.get("/fuentes")
def get_fuentes(lang: str = "es"):
    """El set completo investigado y verificado: parámetros, hechos del canon y huecos."""
    fuentes = supuestos.fuentes()
    return {**fuentes, "facts": i18n.traducir_hechos(fuentes.get("facts", []), i18n.normalizar(lang))}
