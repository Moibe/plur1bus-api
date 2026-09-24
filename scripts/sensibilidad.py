"""Análisis de sensibilidad (tornado): qué supuesto mueve más el resultado.

Para cada supuesto de datos/supuestos.json con rango, corre el escenario base
con el valor bajo y con el alto, y ordena por cuánto cambia la métrica.

    python scripts/sensibilidad.py
    python scripts/sensibilidad.py --metrica poblacion_10_anios --top 15
    python scripts/sensibilidad.py --mes_union 6          # base distinta

Métricas útiles: dia_inicio_hambruna (default), dia_mitad_poblacion,
poblacion_10_anios, capacidad_de_carga, dias_de_comida_al_inicio.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor import supuestos as S  # noqa: E402
from motor.escenario import Escenario  # noqa: E402
from motor.simulacion import simular  # noqa: E402


def _metrica(escenario: Escenario, metrica: str) -> float | None:
    return simular(escenario).resumen.get(metrica)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--metrica", default="dia_inicio_hambruna")
    p.add_argument("--top", type=int, default=20)
    for nombre in Escenario.model_fields:
        p.add_argument(f"--{nombre}", dest=nombre, default=None)
    args = vars(p.parse_args())
    metrica, top = args.pop("metrica"), args.pop("top")
    base = Escenario(**{k: v for k, v in args.items() if v is not None})

    ref = _metrica(base, metrica)
    print(f"Métrica: {metrica} | base = {ref}\n")

    valores = S.cargar()["valores"]
    filas = []
    for clave, v in valores.items():
        bajo, alto = float(v["bajo"]), float(v["alto"])
        if bajo == alto:
            continue
        original = v["valor"]
        resultados = []
        for x in (bajo, alto):
            v["valor"] = x
            resultados.append(_metrica(base, metrica))
        v["valor"] = original
        a, b = resultados
        if a is None or b is None or ref is None:
            efecto = float("inf") if (a is None) != (b is None) else 0.0
        else:
            efecto = abs(b - a)
        filas.append((efecto, clave, bajo, alto, a, b))

    filas.sort(key=lambda f: -f[0])
    print(f"{'supuesto'.ljust(38)} {'bajo':>12} {'alto':>12}   {metrica} (bajo -> alto)")
    for efecto, clave, bajo, alto, a, b in filas[:top]:
        fmt = lambda x: "-" if x is None else (f"{x:,.0f}" if abs(x) >= 100 else f"{x:.3g}")  # noqa: E731
        print(f"{clave.ljust(38)} {fmt(bajo):>12} {fmt(alto):>12}   {fmt(a)} -> {fmt(b)}")


if __name__ == "__main__":
    main()
