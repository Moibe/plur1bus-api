"""
API de cálculo de Plur1bus: ¿cuánto dura la comida de la colmena?

Arranca con:        uvicorn main:app --reload --port 8004
Docs interactivas:  http://127.0.0.1:8004/docs
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from motor import supuestos
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


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/escenario")
def escenario():
    """Palancas del escenario con rangos, textos y defaults, para armar los controles."""
    return palancas()


@app.post("/simular")
def post_simular(e: Escenario):
    r = simular(e)
    return {"escenario": e.model_dump(), "resumen": r.resumen, "fuentes": r.fuentes, "serie": r.serie}


@app.get("/supuestos")
def get_supuestos():
    """Valores base del modelo, cada uno con rango, unidad y las fuentes que lo respaldan."""
    base = supuestos.cargar()
    por_id = {p["id"]: p for p in supuestos.fuentes().get("params", [])}
    valores = {
        clave: {**v, "fuentes_detalle": [por_id[f] for f in v.get("fuentes", []) if f in por_id]}
        for clave, v in base["valores"].items()
    }
    return {**base, "valores": valores}


@app.get("/fuentes")
def get_fuentes():
    """El set completo investigado y verificado: parámetros, hechos del canon y huecos."""
    return supuestos.fuentes()
