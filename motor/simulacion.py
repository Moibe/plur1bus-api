"""Motor de la simulación: un paso por día desde la Unión.

Toda la contabilidad es en kcal. Tres piezas:

- Población: 3 cohortes (niños, adultos, mayores) x N_BINS niveles de reserva
  corporal (cuantiles de una lognormal: del bajo peso a la obesidad). Cada bin
  guarda cuántas personas hay y qué fracción de su reserva inicial les queda.
  Si comen menos de lo que gastan, la reserva baja; al llegar a cero, mueren
  de inanición. Si sobra comida, recuperan reserva poco a poco.
- Inventarios ("pools"): todo lo que ya existía el día de la Unión, más lo que
  va entrando (fruta caída, HDP, carne de animales muertos, resquicios). Cada
  pool se echa a perder a su ritmo y se come primero lo que se pudre antes.
- Animales: el ganado muere de forma natural (su carne entra a un pool) y, si
  la política es alimentarlo, come del mismo inventario que la gente, igual
  que las mascotas. La colmena reparte parejo: todos reciben la misma
  fracción de lo que necesitan.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import NormalDist

import numpy as np

from . import supuestos as S
from .escenario import Escenario

COHORTES = ("ninos", "adultos", "mayores")
N_BINS = 60
DIAS_ANIO = 365.25
MT = 1e9  # kg en un millón de toneladas
ANIO_UNION = 2025
DIAS_EMBARAZOS_EN_CURSO = 270  # los bebés que ya venían nacen igual
DIAS_COSECHA_EN_PIE = 150  # lo que se cosecha en ~5 meses ya estaba sembrado
DIAS_ANIMAL_SIN_COMIDA = 45
VIDA_MASCOTA_DIAS = 12 * DIAS_ANIO
UMBRAL_HAMBRUNA_DIA = 1000  # muertes de hambre al día que marcan el inicio de la hambruna


@dataclass
class Resultado:
    resumen: dict
    serie: dict[str, list] = field(default_factory=dict)
    fuentes: list[dict] = field(default_factory=list)


def _cuantiles_lognormal(mediana: float, sigma: float, n: int) -> np.ndarray:
    nd = NormalDist()
    return np.array([mediana * math.exp(sigma * nd.inv_cdf((i + 0.5) / n)) for i in range(n)])


def _decaimiento_diario(vida_media_dias: float | None, perdida_anual: float | None = None) -> float:
    if perdida_anual is not None:
        return 1.0 - (1.0 - perdida_anual) ** (1.0 / DIAS_ANIO)
    if not vida_media_dias:
        return 0.0
    return 1.0 - 0.5 ** (1.0 / vida_media_dias)


def _calendario(mes_union: int, dias: int) -> tuple[np.ndarray, np.ndarray, list[date]]:
    """Índice de mes (0-11) y días del mes para cada día simulado."""
    inicio = date(ANIO_UNION, mes_union, 1)
    meses = np.empty(dias, dtype=np.int64)
    dias_mes = np.empty(dias)
    fechas = []
    for t in range(dias):
        d = inicio + timedelta(days=t)
        siguiente = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        meses[t] = d.month - 1
        dias_mes[t] = (siguiente - date(d.year, d.month, 1)).days
        fechas.append(d)
    return meses, dias_mes, fechas


def simular(e: Escenario) -> Resultado:
    dias = int(round(e.anios * DIAS_ANIO))
    meses, dias_mes, fechas = _calendario(e.mes_union, dias)

    # --- Población -------------------------------------------------------------
    n0 = S.valor("poblacion_colmena")
    frac = np.array([S.valor("frac_ninos"), 0.0, S.valor("frac_mayores")])
    frac[1] = 1.0 - frac[0] - frac[2]
    ratios = np.array([S.valor("ratio_req_ninos"), S.valor("ratio_req_adultos"), S.valor("ratio_req_mayores")])
    req_base = ratios / float((frac * ratios).sum()) * e.kcal_dia_promedio  # kcal/persona/día por cohorte

    sigma = S.valor("reserva_sigma")
    r0 = np.vstack([
        _cuantiles_lognormal(S.valor("reserva_mediana_" + c), sigma, N_BINS) for c in COHORTES
    ])  # kcal de reserva inicial por persona, (3, N_BINS)
    n = np.repeat((frac * n0 / N_BINS)[:, None], N_BINS, axis=1)
    reserva = np.ones_like(n)  # fracción de la reserva inicial que queda

    muertes_frac = np.array([S.valor("frac_muertes_ninos"), 0.0, S.valor("frac_muertes_mayores")])
    muertes_frac[1] = 1.0 - muertes_frac[0] - muertes_frac[2]
    tasa_muerte = muertes_frac * e.muertes_naturales_dia / (frac * n0)  # por persona por día
    tasa_nacer = S.valor("natalidad_anual") / DIAS_ANIO
    tasa_crecer = np.array([1 / (15 * DIAS_ANIO), 1 / (50 * DIAS_ANIO)])  # niño->adulto, adulto->mayor
    recuperacion = S.valor("recuperacion_diaria")
    adaptacion = e.adaptacion_metabolica

    factor_cuerpo = np.array([S.valor("factor_cuerpo_ninos"), 1.0, S.valor("factor_cuerpo_mayores")])
    kcal_cuerpo = S.valor("kcal_cuerpo_adulto") * factor_cuerpo  # por cohorte
    aprovecha_cuerpo = (S.valor("rendimiento_hdp") * e.frac_recuperacion_cuerpos) if e.hdp_activo else 0.0
    factor_hambre = S.valor("factor_cuerpo_hambre")

    # --- Inventarios -------------------------------------------------------------
    info_pools = S.pools()
    claves = list(info_pools)
    idx = {k: i for i, k in enumerate(claves)}
    decae = np.array([
        _decaimiento_diario(None, e.perdida_cereal_anual) if k == "cereal"
        else _decaimiento_diario(info_pools[k]["vida_media_dias"])
        for k in claves
    ])
    orden = np.argsort(-decae, kind="stable")  # primero lo que se pudre antes

    mes0 = e.mes_union - 1
    cereal_mt = e.cereal_en_mano_mt if e.cereal_en_mano_mt is not None else S.tabla("cereal_en_mano_mt_por_mes")[mes0]
    f_otros = e.factor_otros_stocks
    poblacion_previa = n0 + S.valor("muertes_union")  # la cadena estaba surtida para antes de la Unión
    consumo_previo = poblacion_previa * e.kcal_dia_promedio
    en_cadena = e.dias_inventario_cadena * consumo_previo
    kcal_cuerpo_promedio = float((frac * kcal_cuerpo).sum())

    pools = np.zeros(len(claves))
    pools[idx["cereal"]] = cereal_mt * MT * S.valor("kcal_kg_cereal")
    pools[idx["oleaginosas"]] = f_otros * MT * (
        S.valor("soya_mt") * S.valor("kcal_kg_soya")
        + S.valor("oleaginosas_otras_mt") * S.valor("kcal_kg_oleaginosas_otras")
    )
    pools[idx["aceites"]] = f_otros * MT * S.valor("aceites_mt") * S.valor("kcal_kg_aceite")
    pools[idx["azucar"]] = f_otros * MT * S.valor("azucar_mt") * S.valor("kcal_kg_azucar")
    pools[idx["legumbres"]] = f_otros * MT * S.valor("legumbres_mt") * S.valor("kcal_kg_legumbres")
    pools[idx["tuberculos"]] = f_otros * MT * S.valor("tuberculos_mt") * S.valor("kcal_kg_tuberculos")
    pools[idx["perecederos"]] = en_cadena * S.valor("frac_cadena_perecedera")
    pools[idx["procesados"]] = en_cadena * (1 - S.valor("frac_cadena_perecedera"))
    pools[idx["congelados"]] = MT * S.valor("almacen_frio_mt") * S.valor("kcal_kg_congelados")
    pools[idx["hdp"]] = S.valor("muertes_union") * kcal_cuerpo_promedio * aprovecha_cuerpo
    inventario_inicial = pools.copy()

    # --- Animales ----------------------------------------------------------------
    info_ganado = S.ganado()
    grupos = list(info_ganado)
    cabezas = np.array([float(info_ganado[g]["cabezas"]) for g in grupos])
    cabezas0 = cabezas.copy()
    kcal_cabeza = np.array([float(info_ganado[g]["kcal_comestible_cabeza"]) for g in grupos])
    alimentar = e.ganado_politica == "alimentar"
    tasa_ganado = np.array([
        1 / float(info_ganado[g]["vida_natural_dias"])
        + (0.0 if alimentar else float(info_ganado[g]["mortalidad_liberado_anual"]) / DIAS_ANIO)
        for g in grupos
    ])
    recupera_ganado = S.valor("frac_recuperacion_cadaver_alimentado" if alimentar else "frac_recuperacion_cadaver_liberado")
    pienso = np.array([
        float(info_ganado[g]["alimento_kcal_dia"]) * (1 - float(info_ganado[g]["frac_pastoreo"]))
        for g in grupos
    ]) if alimentar else np.zeros(len(grupos))
    i_bov = grupos.index("bovinos") if "bovinos" in grupos else None
    i_pon = grupos.index("gallinas_ponedoras") if "gallinas_ponedoras" in grupos else None

    mascotas_kcal = (
        S.valor("perros") * S.valor("kcal_dia_perro") + S.valor("gatos") * S.valor("kcal_dia_gato")
        if e.mascotas_politica == "alimentar" else 0.0
    )

    # --- Flujos ------------------------------------------------------------------
    fruta_anio1 = S.valor("fruta_caida_kcal_anio1") * e.fruta_caida_factor
    fruta_mes = S.tabla("fruta_caida_frac_por_mes")
    piso = S.valor("piso_silvestre")
    cosecha_mes = S.tabla("cosecha_cereal_frac_por_mes")
    cosecha_kcal_anio = S.valor("cereal_produccion_mt") * MT * S.valor("kcal_kg_cereal")
    leche_dia = e.resquicio_leche * S.valor("leche_kcal_anio") / DIAS_ANIO if alimentar else 0.0
    huevo_dia = e.resquicio_huevos * S.valor("huevo_kcal_anio") / DIAS_ANIO if alimentar else 0.0
    miel_dia = e.resquicio_miel * S.valor("miel_kcal_anio") / DIAS_ANIO

    dias_estirar = e.horizonte_estirar_anios * DIAS_ANIO
    entrada_media = fruta_anio1 / DIAS_ANIO + e.muertes_naturales_dia * kcal_cuerpo_promedio * aprovecha_cuerpo

    # --- Registro diario -----------------------------------------------------------
    reg_pob = np.zeros((dias, 3))
    reg_hambre = np.zeros(dias)
    reg_natural = np.zeros(dias)
    reg_nacer = np.zeros(dias)
    reg_racion = np.zeros(dias)
    reg_reserva = np.zeros(dias)
    reg_consumo = np.zeros((dias, len(claves)))
    reg_pools = np.zeros((dias, len(claves)))
    reg_entradas = np.zeros((dias, 4))  # fruta, hdp, carne, resquicios/cosecha
    reg_cabezas = np.zeros((dias, len(grupos)))
    necesidad_inicial = None

    for t in range(dias):
        m = meses[t]
        vivos = n.sum()
        if vivos < 1:
            reg_pools[t:] = pools
            reg_cabezas[t:] = cabezas
            break

        # 1. Lo que entra hoy
        anio = t / DIAS_ANIO
        fruta = fruta_anio1 * max(piso, (1 - e.declive_huerto_anual) ** anio) * fruta_mes[m] / dias_mes[t]
        pools[idx["conservas"]] += fruta * e.frac_conservacion_fruta
        pools[idx["perecederos"]] += fruta * (1 - e.frac_conservacion_fruta)

        extra = miel_dia
        pools[idx["azucar"]] += miel_dia
        lacteos = 0.0
        if i_bov is not None and cabezas0[i_bov] > 0:
            lacteos += leche_dia * cabezas[i_bov] / cabezas0[i_bov]
        if i_pon is not None and cabezas0[i_pon] > 0:
            lacteos += huevo_dia * cabezas[i_pon] / cabezas0[i_pon]
        pools[idx["perecederos"]] += lacteos
        extra += lacteos

        grano = 0.0
        if t < DIAS_COSECHA_EN_PIE:
            grano += e.cosecha_senescente * cosecha_kcal_anio * cosecha_mes[m] / dias_mes[t]
        if t >= DIAS_ANIO:
            grano += e.siembra_senescente * cosecha_kcal_anio * cosecha_mes[m] / dias_mes[t]
        pools[idx["cereal"]] += grano
        extra += grano

        # 2. Lo que se necesita hoy
        req = req_base[:, None] * (1 - adaptacion * (1 - reserva))  # kcal/persona/día
        nec_humanos = float((n * req).sum())
        por_recuperar = np.minimum(recuperacion * req_base[:, None], (1 - reserva) * r0)
        nec_recuperar = float((n * por_recuperar).sum())
        nec_animales = float((cabezas * pienso).sum())
        nec_mascotas = mascotas_kcal
        necesidad = nec_humanos + nec_animales + nec_mascotas
        if necesidad_inicial is None:
            necesidad_inicial = necesidad
        disponible = float(pools.sum())

        if e.racion_modo == "completa":
            meta = necesidad + nec_recuperar
        elif e.racion_modo == "fija":
            meta = e.racion_fraccion * necesidad
        else:  # estirar: que alcance hasta la fecha objetivo contando lo que va entrando
            dias_restantes = max(30.0, dias_estirar - t)
            plan = (disponible + entrada_media * dias_restantes) / (necesidad * dias_restantes)
            meta = min(1.0, max(e.racion_minima, plan)) * necesidad

        comido = min(meta, disponible)
        falta = comido
        for i in orden:  # se come primero lo que se echa a perder antes
            if falta <= 0:
                break
            toma = min(pools[i], falta)
            pools[i] -= toma
            reg_consumo[t, i] = toma
            falta -= toma

        racion = min(1.0, comido / necesidad) if necesidad > 0 else 0.0
        sobrante = max(0.0, comido - necesidad)

        # 3. Reservas corporales y muertes de hambre
        reserva -= req * (1 - racion) / r0
        if sobrante > 0 and nec_recuperar > 0:
            reserva += por_recuperar * (sobrante / nec_recuperar) / r0
            np.minimum(reserva, 1.0, out=reserva)
        muere = reserva <= 0
        hambre_cohorte = np.where(muere, n, 0.0).sum(axis=1)
        n[muere] = 0.0
        reserva[muere] = 1.0

        # 4. Demografía: muertes naturales, nacimientos y envejecimiento
        naturales = n * tasa_muerte[:, None]
        n -= naturales
        natural_cohorte = naturales.sum(axis=1)

        nacen = tasa_nacer * vivos * (1.0 if t < DIAS_EMBARAZOS_EN_CURSO else e.natalidad)
        if nacen > 0:
            nuevos = nacen / N_BINS
            reserva[0] = (n[0] * reserva[0] + nuevos) / (n[0] + nuevos)
            n[0] += nuevos
        for c in (0, 1):
            pasan = n[c] * tasa_crecer[c]
            destino = n[c + 1] + pasan
            reserva[c + 1] = np.where(destino > 0, (n[c + 1] * reserva[c + 1] + pasan * reserva[c]) / np.maximum(destino, 1e-12), 1.0)
            n[c] -= pasan
            n[c + 1] = destino

        hdp = (
            float((natural_cohorte * kcal_cuerpo).sum()) + float((hambre_cohorte * kcal_cuerpo).sum()) * factor_hambre
        ) * aprovecha_cuerpo
        pools[idx["hdp"]] += hdp

        # 5. Animales: muertes naturales, hambre si no alcanza el pienso
        muertes_ganado = cabezas * tasa_ganado
        if alimentar and racion < 1:
            muertes_ganado += cabezas * (pienso > 0) * (1 - racion) / DIAS_ANIMAL_SIN_COMIDA
        muertes_ganado = np.minimum(muertes_ganado, cabezas)
        cabezas -= muertes_ganado
        carne = float((muertes_ganado * kcal_cabeza).sum()) * recupera_ganado
        pools[idx["carne_animal"]] += carne
        # las mascotas también envejecen y, si no alcanza la comida, se mueren de hambre
        mascotas_kcal *= 1 - 1 / VIDA_MASCOTA_DIAS - (1 - racion) / DIAS_ANIMAL_SIN_COMIDA

        # 6. Se echa a perder lo que se echa a perder
        pools *= 1 - decae

        entrada_hoy = fruta + hdp + carne + extra
        entrada_media += (entrada_hoy - entrada_media) / 90.0

        reg_pob[t] = n.sum(axis=1)
        reg_hambre[t] = hambre_cohorte.sum()
        reg_natural[t] = natural_cohorte.sum()
        reg_nacer[t] = nacen
        reg_racion[t] = racion
        vivos_hoy = n.sum()
        reg_reserva[t] = float((n * reserva).sum() / vivos_hoy) if vivos_hoy > 0 else 0.0
        reg_pools[t] = pools
        reg_entradas[t] = (fruta, hdp, carne, extra)
        reg_cabezas[t] = cabezas

    return _armar_resultado(
        e, fechas, claves, info_pools, grupos, info_ganado, inventario_inicial, necesidad_inicial or 1.0,
        n0, reg_pob, reg_hambre, reg_natural, reg_nacer, reg_racion, reg_reserva,
        reg_consumo, reg_pools, reg_entradas, reg_cabezas,
    )


def _primer_dia(condicion: np.ndarray) -> int | None:
    donde = np.flatnonzero(condicion)
    return int(donde[0]) if donde.size else None


def _armar_resultado(
    e, fechas, claves, info_pools, grupos, info_ganado, inventario_inicial, necesidad_inicial,
    n0, reg_pob, reg_hambre, reg_natural, reg_nacer, reg_racion, reg_reserva,
    reg_consumo, reg_pools, reg_entradas, reg_cabezas,
) -> Resultado:
    dias = len(fechas)
    pob = reg_pob.sum(axis=1)
    dia_hambruna = _primer_dia(reg_hambre >= UMBRAL_HAMBRUNA_DIA)
    dia_mitad = _primer_dia(pob <= n0 / 2)
    dia_10 = int(round(10 * DIAS_ANIO)) - 1
    ultimos = pob[-int(2 * DIAS_ANIO):] if dias >= 5 * DIAS_ANIO else None
    minimo = int(np.argmin(pob))

    consumo_total = reg_consumo.sum(axis=0)
    total_comido = float(consumo_total.sum()) or 1.0

    def fecha(d):
        return fechas[d].isoformat() if d is not None else None

    resumen = {
        "poblacion_inicial": n0,
        "dias_de_comida_al_inicio": float(inventario_inicial.sum() / necesidad_inicial),
        "dia_inicio_hambruna": dia_hambruna,
        "fecha_inicio_hambruna": fecha(dia_hambruna),
        "dia_mitad_poblacion": dia_mitad,
        "fecha_mitad_poblacion": fecha(dia_mitad),
        "poblacion_10_anios": float(pob[dia_10]) if dias > dia_10 else None,
        "poblacion_final": float(pob[-1]),
        "poblacion_minima": float(pob[minimo]),
        "dia_poblacion_minima": minimo,
        "capacidad_de_carga": float(ultimos.mean()) if ultimos is not None else None,
        "muertes_hambre": float(reg_hambre.sum()),
        "muertes_naturales": float(reg_natural.sum()),
        "nacimientos": float(reg_nacer.sum()),
        # sobre todos los que vivieron en esos 10 años (los que había más los que nacieron)
        "muertos_hambre_10_anios_frac": float(
            reg_hambre[: dia_10 + 1].sum() / (n0 + reg_nacer[: dia_10 + 1].sum())
        ),
        "racion_promedio": float(reg_racion[pob > 1].mean()) if (pob > 1).any() else 0.0,
    }
    # Koumba: "la mayoría morirá de hambre en los próximos diez años"
    resumen["koumba_acierta"] = resumen["muertos_hambre_10_anios_frac"] > 0.5

    fuentes = [
        {
            "clave": k,
            "nombre": info_pools[k]["nombre"],
            "inicial_kcal": float(inventario_inicial[i]),
            "consumido_kcal": float(consumo_total[i]),
            "frac_consumo": float(consumo_total[i] / total_comido),
        }
        for i, k in enumerate(claves)
    ]

    semanas = list(range(0, dias, 7))

    def suma_semanal(x: np.ndarray) -> list:
        return [float(x[s:s + 7].sum()) for s in semanas]

    serie = {
        "dia": semanas,
        "fecha": [fechas[s].isoformat() for s in semanas],
        "poblacion": [float(pob[min(s + 6, dias - 1)]) for s in semanas],
        "poblacion_cohortes": {
            c: [float(reg_pob[min(s + 6, dias - 1), j]) for s in semanas] for j, c in enumerate(COHORTES)
        },
        "muertes_hambre": suma_semanal(reg_hambre),
        "muertes_naturales": suma_semanal(reg_natural),
        "nacimientos": suma_semanal(reg_nacer),
        "racion": [float(reg_racion[s:s + 7].mean()) for s in semanas],
        "reserva_corporal": [float(reg_reserva[min(s + 6, dias - 1)]) for s in semanas],
        "consumo_kcal": {k: suma_semanal(reg_consumo[:, i]) for i, k in enumerate(claves)},
        "inventario_kcal": {k: [float(reg_pools[min(s + 6, dias - 1), i]) for s in semanas] for i, k in enumerate(claves)},
        "entradas_kcal": {
            k: suma_semanal(reg_entradas[:, j]) for j, k in enumerate(("fruta_caida", "hdp", "carne_animal", "resquicios"))
        },
        "ganado_cabezas": {g: [float(reg_cabezas[min(s + 6, dias - 1), j]) for s in semanas] for j, g in enumerate(grupos)},
    }
    return Resultado(resumen=resumen, serie=serie, fuentes=fuentes)
