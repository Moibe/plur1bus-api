"""Corre un escenario desde la terminal e imprime el resumen.

Cualquier palanca del escenario se pasa como --nombre valor:

    python scripts/simular.py
    python scripts/simular.py --mes_union 6 --racion_modo estirar
    python scripts/simular.py --ganado_politica alimentar --json salidas/alimentar.json
    python scripts/simular.py --csv salidas/semanal.csv

--json guarda el resultado completo (lo mismo que regresa POST /simular);
--csv guarda la serie semanal principal.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor.escenario import Escenario  # noqa: E402
from motor.simulacion import simular  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Simula la comida de la colmena de Pluribus.")
    for nombre, campo in Escenario.model_fields.items():
        p.add_argument(f"--{nombre}", dest=nombre, default=None, help=campo.description)
    p.add_argument("--json", dest="_json", default=None, help="Ruta donde guardar el resultado completo en JSON.")
    p.add_argument("--csv", dest="_csv", default=None, help="Ruta donde guardar la serie semanal en CSV.")
    return p


def _millones(x: float | None) -> str:
    return "-" if x is None else f"{x / 1e6:,.0f} M"


def imprimir(r) -> None:
    s = r.resumen
    filas = [
        ("Población inicial", _millones(s["poblacion_inicial"])),
        ("Días de comida al inicio (ración completa)", f"{s['dias_de_comida_al_inicio']:,.0f}"),
        ("Inicio de la hambruna", f"{s['fecha_inicio_hambruna'] or '-'} (día {s['dia_inicio_hambruna']})"),
        ("Población a la mitad", f"{s['fecha_mitad_poblacion'] or '-'} (día {s['dia_mitad_poblacion']})"),
        ("Población a 10 años", _millones(s["poblacion_10_anios"])),
        ("Población mínima", f"{_millones(s['poblacion_minima'])} (día {s['dia_poblacion_minima']})"),
        ("Capacidad de carga (últimos 2 años)", _millones(s["capacidad_de_carga"])),
        ("Muertes de hambre", _millones(s["muertes_hambre"])),
        ("Muertes naturales", _millones(s["muertes_naturales"])),
        ("Nacimientos", _millones(s["nacimientos"])),
        ("Ración promedio", f"{s['racion_promedio']:.0%}"),
        ("Muertos de hambre en 10 años", f"{s['muertos_hambre_10_anios_frac']:.0%}"),
        ("¿Acierta Koumba? (la mayoría muere de hambre en 10 años)", "sí" if s["koumba_acierta"] else "no"),
    ]
    ancho = max(len(f) for f, _ in filas)
    for f, v in filas:
        print(f"{f.ljust(ancho)}  {v}")

    print("\nDe dónde salió la comida:")
    for fuente in sorted(r.fuentes, key=lambda x: -x["consumido_kcal"]):
        if fuente["consumido_kcal"] <= 0:
            continue
        print(f"  {fuente['nombre'].ljust(28)} {fuente['frac_consumo']:6.1%}   ({fuente['consumido_kcal']:.2e} kcal)")


def main() -> None:
    args = vars(_parser().parse_args())
    ruta_json, ruta_csv = args.pop("_json"), args.pop("_csv")
    escenario = Escenario(**{k: v for k, v in args.items() if v is not None})
    r = simular(escenario)
    imprimir(r)

    if ruta_json:
        Path(ruta_json).parent.mkdir(parents=True, exist_ok=True)
        with open(ruta_json, "w", encoding="utf-8") as f:
            json.dump({"escenario": escenario.model_dump(), "resumen": r.resumen, "fuentes": r.fuentes, "serie": r.serie}, f, ensure_ascii=False)
        print(f"\nResultado completo en {ruta_json}")
    if ruta_csv:
        Path(ruta_csv).parent.mkdir(parents=True, exist_ok=True)
        serie = r.serie
        columnas = ["dia", "fecha", "poblacion", "muertes_hambre", "muertes_naturales", "nacimientos", "racion", "reserva_corporal"]
        with open(ruta_csv, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(columnas)
            for i in range(len(serie["dia"])):
                w.writerow([serie[c][i] for c in columnas])
        print(f"Serie semanal en {ruta_csv}")


if __name__ == "__main__":
    main()
