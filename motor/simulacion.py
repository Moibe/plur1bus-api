"""Motor de la simulación: un paso por día desde la Unión.

Toda la contabilidad es en kcal. Tres piezas:

- Población: 3 cohortes (niños, adultos, mayores) x N_BINS niveles de reserva
  corporal (cuantiles de una lognormal: del bajo peso a la obesidad). Cada bin
  guarda cuántas personas hay y qué fracción de su reserva inicial les queda.
  Si comen menos de lo que gastan, la reserva baja y el cuerpo gasta menos
  (adaptación). Con la reserva baja crece el riesgo de morir por desnutrición,
  y al llegar a cero se muere de inanición. Si sobra comida, se recupera.
- Inventarios ("pools"): todo lo que ya existía el día de la Unión, más lo que
  va entrando (fruta caída, HDP, carne de animales muertos, leche, resquicios).
  Cada pool se echa a perder a su ritmo y se come primero lo que se pudre antes.
- Animales: el ganado muere de forma natural (su carne entra a un pool) y, si
  la política es alimentarlo, come del mismo inventario que la gente, igual
  que las mascotas. Los animales no se adaptan como el cuerpo humano, así que
  reciben su pienso completo mientras alcance; si no alcanza, todos (gente y
  animales) reciben la misma fracción de su plan.

Aunque se pidan pocos años, se simula internamente al menos lo necesario para
las métricas de largo plazo (10 años de Koumba y la capacidad de carga); la
serie y los totales se recortan al horizonte pedido.
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
UMBRAL_HAMBRUNA_MIN = 1000  # piso para no marcar hambruna por una fracción de persona
POCO = 1e-3  # personas o cabezas por bin por debajo de esto son cero (evita subnormales lentos)
DIAS_10_ANIOS = int(round(10 * DIAS_ANIO))
MAX_DIAS = int(round(30 * DIAS_ANIO))
VIDA_LARGA_DIAS = 365  # pools que duran más que esto pierden algo mientras se estiran


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


def _anios_hasta_piso(declive: float, piso: float) -> float:
    """Años hasta que la fruta caída baja a su nivel silvestre."""
    if declive <= 0 or piso >= 1:
        return 0.0
    return math.log(piso) / math.log(1 - declive)


def _lactancia(dias: int, partos: bool) -> np.ndarray:
    """Fracción de la leche previa que se produce cada día (antes de contar al hato vivo).

    Sin partos: la lactancia en curso cae en línea recta a cero, y las vacas que ya
    estaban preñadas paren repartidas en los días de gestación que les faltan; cada
    una da una lactancia completa.
    """
    if partos:
        return np.ones(dias)
    lact = S.valor("dias_lactancia")
    gest = S.valor("dias_gestacion_vaca")
    prenadas = S.valor("frac_vacas_prenadas")
    t = np.arange(dias, dtype=float)
    en_curso = np.clip(1 - t / lact, 0, None)
    # vacas que paren entre 0 y gest días y siguen lactando: τ en [max(0, t-lact), min(t, gest)]
    nuevas = prenadas * np.clip(np.minimum(t, gest) - np.maximum(0, t - lact), 0, None) / gest
    return en_curso + nuevas


def simular(e: Escenario) -> Resultado:
    dias_pedidos = int(round(e.anios * DIAS_ANIO))
    piso = S.valor("piso_silvestre")
    anios_piso = _anios_hasta_piso(e.declive_huerto_anual, piso)
    # ventana de "largo plazo": un año después de que la fruta llegó a su piso, por dos años
    carga_ini = int(round((anios_piso + 1) * DIAS_ANIO))
    carga_fin = carga_ini + int(round(2 * DIAS_ANIO))
    dias = min(MAX_DIAS, max(dias_pedidos, DIAS_10_ANIOS + 1, carga_fin))
    meses, dias_mes, fechas = _calendario(e.mes_union, dias)

    # --- Población -------------------------------------------------------------
    n0 = S.valor("poblacion_colmena")
    frac = np.array([S.valor("frac_ninos"), 0.0, S.valor("frac_mayores")])
    frac[1] = 1.0 - frac[0] - frac[2]
    ratios = np.array([S.valor("ratio_req_ninos"), S.valor("ratio_req_adultos"), S.valor("ratio_req_mayores")])
    req_base = ratios / float((frac * ratios).sum()) * e.kcal_dia_promedio  # kcal/persona/día por cohorte
    req_base_bins = req_base[:, None] * np.ones((3, N_BINS))

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
    umbral_desnutricion = S.valor("umbral_desnutricion")
    riesgo_desnutricion = S.valor("riesgo_desnutricion_max")

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
    duradero = np.array([
        k == "cereal" or (info_pools[k]["vida_media_dias"] or 0) >= VIDA_LARGA_DIAS for k in claves
    ])

    mes0 = e.mes_union - 1
    cereal_mt = e.cereal_en_mano_mt if e.cereal_en_mano_mt is not None else S.tabla("cereal_en_mano_mt_por_mes")[mes0]
    f_otros = e.factor_otros_stocks
    poblacion_previa = n0 + S.valor("muertes_union")  # la cadena estaba surtida para antes de la Unión
    consumo_previo = poblacion_previa * S.valor("kcal_suministro_previo")
    en_cadena = e.dias_inventario_cadena * consumo_previo
    kcal_cuerpo_promedio = float((frac * kcal_cuerpo).sum())
    kcal_kg_grano = S.valor("kcal_kg_cereal") * S.valor("frac_cereal_comestible")

    pools = np.zeros(len(claves))
    pools[idx["cereal"]] = cereal_mt * MT * kcal_kg_grano
    pools[idx["oleaginosas"]] = f_otros * MT * (
        S.valor("soya_mt") * S.valor("kcal_kg_soya")
        + S.valor("oleaginosas_otras_mt") * S.valor("kcal_kg_oleaginosas_otras")
        + S.valor("harina_proteica_mt") * S.valor("kcal_kg_harina_proteica")
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
    cosecha_mes = S.tabla("cosecha_cereal_frac_por_mes")
    cosecha_kcal_anio = S.valor("cereal_produccion_mt") * MT * kcal_kg_grano
    huevo_dia = e.resquicio_huevos * S.valor("huevo_kcal_anio") / DIAS_ANIO if alimentar else 0.0
    miel_dia = e.resquicio_miel * S.valor("miel_kcal_anio") / DIAS_ANIO

    # Flujos PASAJEROS, conocidos de antemano: la cosecha en pie (si se permite) y la
    # leche de la lactancia que ya venía. "Estirar" los cuenta como cantidad total que
    # falta por llegar, no como un ritmo que dura todo el horizonte.
    cosecha_pie = np.array([
        e.cosecha_senescente * cosecha_kcal_anio * cosecha_mes[meses[t]] / dias_mes[t] if t < DIAS_COSECHA_EN_PIE else 0.0
        for t in range(dias)
    ])
    leche = e.ordena_leche * S.valor("leche_kcal_anio") / DIAS_ANIO * _lactancia(dias, e.partos_ganado)
    pasajero_restante = np.append(np.cumsum((cosecha_pie + (0 if e.partos_ganado else leche))[::-1])[::-1], 0.0)

    dias_estirar = e.horizonte_estirar_anios * DIAS_ANIO
    # ritmo de los flujos RECURRENTES (fruta, HDP, carne, huevo, miel, siembra), suavizado
    recurrente_medio = fruta_anio1 / DIAS_ANIO + e.muertes_naturales_dia * kcal_cuerpo_promedio * aprovecha_cuerpo

    # --- Registro diario -----------------------------------------------------------
    reg_pob = np.zeros((dias, 3))
    reg_hambre = np.zeros(dias)
    reg_natural = np.zeros(dias)
    reg_nacer = np.zeros(dias)
    reg_racion = np.zeros(dias)
    reg_reserva = np.zeros(dias)
    reg_consumo = np.zeros((dias, len(claves)))
    reg_pools = np.zeros((dias, len(claves)))
    reg_entradas = np.zeros((dias, 4))  # fruta, hdp, carne, resquicios (leche, huevo, miel, grano)
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

        pools[idx["azucar"]] += miel_dia
        leche_hoy = leche[t] * cabezas[i_bov] / cabezas0[i_bov] if i_bov is not None and cabezas0[i_bov] > 0 else 0.0
        huevo_hoy = huevo_dia * cabezas[i_pon] / cabezas0[i_pon] if i_pon is not None and cabezas0[i_pon] > 0 else 0.0
        pools[idx["perecederos"]] += leche_hoy + huevo_hoy

        siembra = e.siembra_senescente * cosecha_kcal_anio * cosecha_mes[m] / dias_mes[t] if t >= DIAS_ANIO else 0.0
        pools[idx["cereal"]] += cosecha_pie[t] + siembra
        extra = miel_dia + leche_hoy + huevo_hoy + cosecha_pie[t] + siembra

        # 2. Lo que se necesita hoy
        req = req_base[:, None] * (1 - adaptacion * (1 - reserva))  # gasto de hoy, kcal/persona/día
        nec_humanos = float((n * req).sum())
        nec_base = float((n * req_base_bins).sum())
        nec_animales = float((cabezas * pienso).sum()) + mascotas_kcal
        if necesidad_inicial is None:
            necesidad_inicial = nec_humanos + nec_animales
        disponible = float(pools.sum())

        # Plan de la colmena: cuánto le toca a cada quien si alcanza. En "completa"
        # cada cuerpo come lo que gasta hoy (más un extra si viene de un bache); en
        # "fija" y "estirar" la ración es una fracción del requerimiento BASE, así
        # que el cuerpo se adapta, adelgaza y puede estabilizarse en un peso menor.
        if e.racion_modo == "completa":
            por_recuperar = np.minimum(recuperacion * req_base[:, None], (1 - reserva) * r0)
            plan_persona = req + por_recuperar
        else:
            if e.racion_modo == "fija":
                fraccion_plan = e.racion_fraccion
            else:  # estirar: que alcance hasta la fecha objetivo
                faltan = dias_estirar - t
                horizonte = faltan if faltan >= 1 else 30.0  # pasada la fecha, se planea mes a mes
                # lo duradero pierde, en promedio, la mitad del horizonte de su deterioro
                guardado = float((pools * np.where(duradero, (1 - decae) ** (min(horizonte, MAX_DIAS) / 2), 1.0)).sum())
                pasajero = pasajero_restante[t + 1] if t + 1 < len(pasajero_restante) else 0.0
                total = guardado + pasajero + recurrente_medio * horizonte - nec_animales * horizonte
                fraccion_plan = min(1.0, max(e.racion_minima, total / (nec_base * horizonte))) if nec_base > 0 else 1.0
            plan_persona = fraccion_plan * req_base_bins
        meta = float((n * plan_persona).sum()) + nec_animales

        comido = min(meta, disponible)
        falta = comido
        for i in orden:  # se come primero lo que se echa a perder antes
            if falta <= 0:
                break
            toma = min(pools[i], falta)
            pools[i] -= toma
            reg_consumo[t, i] = toma
            falta -= toma

        alcanza = comido / meta if meta > 0 else 0.0  # si no hay para el plan, todos reciben menos parejo
        ingesta = plan_persona * alcanza
        # ración = lo que come la gente frente a su requerimiento normal (no frente al gasto ya reducido)
        racion = min(1.0, float((n * ingesta).sum()) / nec_base) if nec_base > 0 else 0.0

        # 3. Reservas corporales, desnutrición y muertes de hambre
        reserva += (ingesta - req) / r0
        np.minimum(reserva, 1.0, out=reserva)
        muere = reserva <= 0
        hambre_cohorte = np.where(muere, n, 0.0).sum(axis=1)
        n[muere] = 0.0
        reserva[muere] = 1.0
        # con la reserva baja crece el riesgo de morir (infecciones, falla orgánica)
        riesgo = riesgo_desnutricion * np.clip((umbral_desnutricion - reserva) / umbral_desnutricion, 0.0, 1.0) ** 2
        desnutridos = n * riesgo
        n -= desnutridos
        hambre_cohorte += desnutridos.sum(axis=1)
        n[n < POCO] = 0.0

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

        # 5. Animales: muertes naturales y hambre si no alcanza el pienso
        muertes_ganado = cabezas * tasa_ganado
        if alimentar and alcanza < 1:
            muertes_ganado += cabezas * (pienso > 0) * (1 - alcanza) / DIAS_ANIMAL_SIN_COMIDA
        muertes_ganado = np.minimum(muertes_ganado, cabezas)
        cabezas -= muertes_ganado
        cabezas[cabezas < POCO] = 0.0
        carne = float((muertes_ganado * kcal_cabeza).sum()) * recupera_ganado
        pools[idx["carne_animal"]] += carne
        # las mascotas también envejecen y, si no alcanza la comida, se mueren de hambre
        mascotas_kcal *= max(0.0, 1 - 1 / VIDA_MASCOTA_DIAS - (1 - alcanza) / DIAS_ANIMAL_SIN_COMIDA)

        # 6. Se echa a perder lo que se echa a perder
        pools *= 1 - decae
        pools[pools < 1.0] = 0.0  # menos de 1 kcal en todo el mundo es nada

        recurrente_hoy = fruta + hdp + carne + huevo_hoy + miel_dia + siembra + (leche_hoy if e.partos_ganado else 0.0)
        recurrente_medio += (recurrente_hoy - recurrente_medio) / 90.0

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
        dias_pedidos, fechas, claves, info_pools, grupos, inventario_inicial, necesidad_inicial or 1.0,
        n0, (carga_ini, carga_fin), reg_pob, reg_hambre, reg_natural, reg_nacer, reg_racion, reg_reserva,
        reg_consumo, reg_pools, reg_entradas, reg_cabezas,
    )


def _primer_dia(condicion: np.ndarray) -> int | None:
    donde = np.flatnonzero(condicion)
    return int(donde[0]) if donde.size else None


def _armar_resultado(
    dias, fechas, claves, info_pools, grupos, inventario_inicial, necesidad_inicial,
    n0, ventana_carga, reg_pob, reg_hambre, reg_natural, reg_nacer, reg_racion, reg_reserva,
    reg_consumo, reg_pools, reg_entradas, reg_cabezas,
) -> Resultado:
    pob_completa = reg_pob.sum(axis=1)

    # Largo plazo: siempre sobre la corrida interna completa (al menos 10 años).
    dia_10 = DIAS_10_ANIOS - 1
    hambre_10 = reg_hambre[: dia_10 + 1].sum()
    vivieron_10 = n0 + reg_nacer[: dia_10 + 1].sum()  # los que había más los que nacieron
    ini, fin = ventana_carga
    fin = min(fin, len(pob_completa))
    ini = min(ini, fin - 1)

    # Todo lo demás, recortado al horizonte pedido.
    pob = pob_completa[:dias]
    hambre = reg_hambre[:dias]
    consumo = reg_consumo[:dias]
    # la hambruna empieza el día en que el hambre mata más que todas las demás causas juntas
    dia_hambruna = _primer_dia(hambre > np.maximum(reg_natural[:dias], UMBRAL_HAMBRUNA_MIN))
    dia_mitad = _primer_dia(pob <= n0 / 2)
    minimo = int(np.argmin(pob))
    vivos = pob > 1
    consumo_total = consumo.sum(axis=0)
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
        "poblacion_10_anios": float(pob_completa[dia_10]),
        "poblacion_final": float(pob[-1]),
        "poblacion_minima": float(pob[minimo]),
        "dia_poblacion_minima": minimo,
        "capacidad_de_carga": float(pob_completa[ini:fin].mean()),
        "capacidad_ventana_anios": [round(ini / DIAS_ANIO, 1), round(fin / DIAS_ANIO, 1)],
        "muertes_hambre": float(hambre.sum()),
        "muertes_naturales": float(reg_natural[:dias].sum()),
        "nacimientos": float(reg_nacer[:dias].sum()),
        "muertos_hambre_10_anios_frac": float(hambre_10 / vivieron_10),
        # promedio ponderado por gente viva (no por semana): una semana con 90 M vale menos que una con 7,000 M
        "racion_promedio": float((reg_racion[:dias] * pob).sum() / pob.sum()) if vivos.any() else 0.0,
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
    tramo = [min(7, dias - s) for s in semanas]  # la última semana puede ser parcial

    def suma_semanal(x: np.ndarray) -> list:
        return [float(x[s:s + 7].sum()) for s in semanas]

    def cierre(x: np.ndarray) -> list:
        return [float(x[min(s + 6, dias - 1)]) for s in semanas]

    serie = {
        "dia": semanas,
        "dias_tramo": tramo,
        "fecha": [fechas[s].isoformat() for s in semanas],
        "poblacion": cierre(pob),
        "poblacion_cohortes": {c: cierre(reg_pob[:dias, j]) for j, c in enumerate(COHORTES)},
        "muertes_hambre": suma_semanal(hambre),
        "muertes_naturales": suma_semanal(reg_natural[:dias]),
        "nacimientos": suma_semanal(reg_nacer[:dias]),
        "racion": [float(reg_racion[s:s + 7].mean()) for s in semanas],
        "reserva_corporal": cierre(reg_reserva[:dias]),
        "consumo_kcal": {k: suma_semanal(consumo[:, i]) for i, k in enumerate(claves)},
        "inventario_kcal": {k: cierre(reg_pools[:dias, i]) for i, k in enumerate(claves)},
        "entradas_kcal": {
            k: suma_semanal(reg_entradas[:dias, j]) for j, k in enumerate(("fruta_caida", "hdp", "carne_animal", "resquicios"))
        },
        "ganado_cabezas": {g: cierre(reg_cabezas[:dias, j]) for j, g in enumerate(grupos)},
    }
    return Resultado(resumen=resumen, serie=serie, fuentes=fuentes)
