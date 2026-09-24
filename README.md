# plur1bus-api

Motor de cálculo de **Plur1bus**: ¿cuánto le dura la comida a la colmena de *Pluribus*?

En la serie, la colmena no puede matar ni dañar ninguna forma de vida, plantas incluidas. Solo come lo que
ya existía antes de la Unión, la fruta que cae sola, los animales que mueren de forma natural y el HDP
(proteína de origen humano) de quienes mueren. Este repo simula eso día por día, a escala global, con
datos reales (FAO, USDA, ONU) y los números del canon.

El front vive en el repo hermano [`plur1bus`](https://github.com/Moibe/plur1bus) (SvelteKit).

## Estructura

| Ruta | Qué es |
| --- | --- |
| [motor/simulacion.py](motor/simulacion.py) | El motor: población por cohorte y reserva corporal, inventarios que se echan a perder, animales, flujos |
| [motor/escenario.py](motor/escenario.py) | Las palancas del escenario (mes de la Unión, ración, ganado, resquicios...) con rangos y textos para la UI |
| [motor/supuestos.py](motor/supuestos.py) | Lee los supuestos base |
| [datos/supuestos.json](datos/supuestos.json) | Capa curada: cada valor con rango, unidad, fuentes y derivación |
| [datos/fuentes.json](datos/fuentes.json) | Set investigado y verificado: parámetros con cita, hechos del canon y huecos |
| [scripts/](scripts/) | Scripts de terminal: simular un escenario, análisis de sensibilidad |
| [main.py](main.py) | FastAPI |

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux
pip install -r requirements-dev.txt
```

## Scripts

```bash
python scripts/simular.py                                   # escenario base
python scripts/simular.py --mes_union 6 --racion_modo estirar
python scripts/simular.py --ganado_politica alimentar --json salidas/alimentar.json
python scripts/sensibilidad.py --metrica poblacion_10_anios # qué supuesto mueve más el resultado
```

Cualquier palanca del escenario se pasa como `--nombre valor` (ver `python scripts/simular.py --help`).

## API

```bash
uvicorn main:app --reload --port 8004
```

| Endpoint | Qué regresa |
| --- | --- |
| `GET /health` | `{"ok": true}` |
| `GET /escenario` | Esquema de las palancas con defaults, rangos, grupo y etiqueta |
| `POST /simular` | Resumen, fuentes de comida y serie semanal de un escenario |
| `GET /supuestos` | Supuestos base con sus fuentes |
| `GET /fuentes` | El set investigado completo |

Docs interactivas en http://127.0.0.1:8004/docs.

## Pruebas

```bash
pytest -q
```
