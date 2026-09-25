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
| [motor/i18n.py](motor/i18n.py) | Traduce los textos de las respuestas al idioma de `?lang=` |
| [datos/i18n/](datos/i18n/) | Un archivo por idioma; `es.json` es la fuente y se genera con `herramientas/extraer_textos.py` |
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

Todos los endpoints con texto aceptan `?lang=es|en|pt|fr|de|ar` (también `en-US`, etc.). Sin `lang`, o
con uno que no existe, responden en español. Solo se traducen textos: los números son idénticos en
todos los idiomas.

Docs interactivas en http://127.0.0.1:8004/docs.

## Idiomas

El español es el idioma fuente. Los textos originales viven donde siempre (`escenario.py`,
`supuestos.json`, los hechos del canon en `fuentes.json`) y `herramientas/extraer_textos.py` los junta en
`datos/i18n/es.json`, una clave por texto. Cada idioma es un archivo con las mismas claves; si a uno le
falta una clave, se usa el español.

Después de cambiar o agregar un texto:

```bash
python herramientas/extraer_textos.py              # regenera datos/i18n/es.json
# traduce las claves nuevas en datos/i18n/<idioma>.json
node ../plur1bus/scripts/validar-traducciones.mjs  # valida API y front contra el español
pytest -q tests/test_i18n.py
```

`test_i18n.py` falla si `es.json` quedó desfasado del código o si a un idioma le falta o le sobra una
clave. Los diccionarios se leen una vez por proceso: reinicia uvicorn tras editarlos (`--reload` solo vigila
los `.py`, salvo que le agregues `--reload-include '*.json'`).

## Pruebas

```bash
pytest -q
```
