"""Arma datos/supuestos.json a partir del set investigado (datos/fuentes.json).

Cada supuesto del motor declara de qué parámetros investigados sale (`fuentes`)
y, si no se toma tal cual, cómo se deriva. Correr después de actualizar
fuentes.json:

    python herramientas/armar_supuestos.py
"""

import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "datos"


def v(valor, bajo, alto, unidad, descripcion, fuentes=(), derivacion=""):
    d = {"valor": valor, "bajo": bajo, "alto": alto, "unidad": unidad, "descripcion": descripcion, "fuentes": list(fuentes)}
    if derivacion:
        d["derivacion"] = derivacion
    return d


# Requerimientos por cohorte (FAO/WHO/UNU 2004, sedentario PAL 1.55):
# 0-4: 1,000 · 5-14: 1,650 · 15-64: 2,320 · 65+: 1,850 kcal/día.
F04, F514, F65 = 0.0782, 0.1658, 0.104
REQ_NINOS = (F04 * 1000 + F514 * 1650) / (F04 + F514)
PROMEDIO = (F04 + F514) * REQ_NINOS + (1 - F04 - F514 - F65) * 2320 + F65 * 1850

VALORES = {
    # --- Canon ---
    "poblacion_colmena": v(7348292411, 7348292411, 7348292411, "personas", "Población de la colmena según el video de John Cena (ep. 6).", ["canon_poblacion_colmena"]),
    "muertes_union": v(886477591, 886477591, 886477591, "personas", "Muertos durante la Unión (Zosia, ep. 2).", ["canon_muertes_union"]),
    "muertes_naturales_dia": v(100000, 100000, 241056, "personas/dia", "Muertes diarias por causas naturales y accidentes. Canon: 'casi 100,000' (Cena); Zosia cuenta 1,674 en 10 minutos en el ep. 8, o sea 241 mil al día.", ["canon_muertes_diarias", "canon_muertes_diarias_ep8", "muertes_dia_colmena"]),
    "natalidad_anual": v(0.0069, 0.0, 0.0161, "nacimientos/persona/anio", "Tasa de natalidad. Canon: 965 nacimientos en 10 minutos (ep. 8), unos 139 mil al día; antes de la Unión era de 16.1 por mil.", ["canon_nacimientos_diarios", "nacimientos_anio"], "138,960 × 365 / 7,348,292,411 = 0.0069 por persona al año."),
    # --- Población y demanda ---
    "frac_ninos": v(round(F04 + F514, 4), 0.241, 0.247, "fraccion", "Fracción de la población de 0 a 14 años (ONU, WPP 2024, año 2025).", ["frac_0_4", "frac_5_14"]),
    "frac_mayores": v(F65, 0.101, 0.106, "fraccion", "Fracción de la población de 65 años o más (ONU, WPP 2024, año 2025).", ["frac_65_mas"]),
    "kcal_dia_promedio": v(2050, 1815, 2450, "kcal/dia", "Requerimiento energético promedio de una colmena sedentaria (PAL 1.55). Activa sería ~2,379 (ADER de la FAO); John Cena necesita 2,400.", ["kcal_requerimiento_sedentario_poblacional", "kcal_requerimiento_promedio", "canon_kcal_dia_cena"]),
    "ratio_req_ninos": v(round(REQ_NINOS / PROMEDIO, 3), 0.62, 0.78, "fraccion", "Requerimiento de un niño (0-14) relativo al promedio.", ["kcal_nino_0_4", "kcal_nino_5_14"], f"Promedio ponderado de 0-4 (1,000) y 5-14 (1,650) = {REQ_NINOS:,.0f} kcal, entre el promedio poblacional de {PROMEDIO:,.0f}."),
    "ratio_req_adultos": v(round(2320 / PROMEDIO, 3), 1.05, 1.2, "fraccion", "Requerimiento de un adulto (15-64) relativo al promedio.", ["kcal_sedentario_adulto"], f"2,320 / {PROMEDIO:,.0f}."),
    "ratio_req_mayores": v(round(1850 / PROMEDIO, 3), 0.8, 1.0, "fraccion", "Requerimiento de un mayor (65+) relativo al promedio.", ["kcal_adulto_mayor_65"], f"1,850 / {PROMEDIO:,.0f}."),
    # --- Fisiología de la inanición ---
    "reserva_mediana_adultos": v(112000, 70000, 160000, "kcal", "Reserva corporal movilizable mediana de un adulto antes de morir de inanición (grasa utilizable más la mitad de la proteína).", ["reserva_energetica_movilizable_kcal", "grasa_movilizable_kg", "kcal_por_kg_grasa"], "Promedio de 130,000 kcal; con dispersión lognormal de sigma 0.6 la mediana es 130,000 / e^(0.6²/2) ≈ 112,000."),
    "reserva_mediana_ninos": v(30000, 15000, 45000, "kcal", "Reserva mediana de un niño (0-14): de ~15 mil kcal en menores de 5 a ~35 mil en escolares.", ["masa_promedio_poblacion_kg"], "Supuesto: 5-14 años, ~25 kg con 4-5 kg de grasa utilizable; 0-4 años, ~12 kg."),
    "reserva_mediana_mayores": v(95000, 60000, 130000, "kcal", "Reserva mediana de un mayor (65+): más grasa, pero menos tolerancia.", ["frac_grasa_corporal_adulto", "masa_fallecido_adulto_mayor_kg"]),
    "reserva_sigma": v(0.6, 0.4, 0.8, "adimensional", "Dispersión (sigma lognormal) de las reservas, del bajo peso (390 M de adultos) a la obesidad (890 M).", ["adultos_bajo_peso", "adultos_sobrepeso", "adultos_obesidad"], "Con sigma 0.6, el percentil 5 queda en ~42 mil kcal (bajo peso) y el 95 en ~300 mil (obesidad)."),
    "adaptacion_metabolica": v(0.65, 0.3, 0.8, "fraccion", "Caída máxima del gasto energético al agotarse la reserva (menos masa más termogénesis adaptativa).", ["reduccion_gasto_inanicion", "dias_supervivencia_ayuno_total", "frac_peso_final_semiinanicion_24sem"], "Calibrado para reproducir 62 días de ayuno total (huelguistas de 1981, reserva de ~90 mil kcal) y 24 semanas sin muertes con ~45% de la ración (Minnesota)."),
    "recuperacion_diaria": v(0.2, 0.0, 0.3, "fraccion", "Extra que una persona desnutrida puede comer al día para recuperar reserva, como fracción de su requerimiento.", [], "Supuesto del modelo."),
    "frac_muertes_ninos": v(0.097, 0.09, 0.105, "fraccion", "Fracción de las muertes naturales que son niños (0-14).", ["frac_muertes_0_4"], "0-4: 7.8% más 5-14: 1.9% (WPP 2024, año 2023)."),
    "frac_muertes_mayores": v(0.598, 0.58, 0.62, "fraccion", "Fracción de las muertes naturales que son mayores (65+).", ["frac_muertes_65_mas"]),
    # --- Cuerpos y HDP ---
    "kcal_cuerpo_adulto": v(125822, 100000, 143771, "kcal", "Energía comestible de un cuerpo adulto de 66 kg (Cole 2017); con esqueleto y piel, 143,771.", ["kcal_cuerpo_humano", "kcal_cuerpo_humano_total", "ref_kcal_cuerpo_humano_comestible"]),
    "masa_fallecido_promedio_kg": v(53, 47, 59, "kg", "Masa promedio de quien muere por causas naturales (sobre todo ancianos).", ["masa_fallecido_promedio_kg"]),
    "factor_cuerpo_ninos": v(0.3, 0.17, 0.45, "fraccion", "Energía del cuerpo de un niño relativa a la de un adulto.", ["masa_promedio_poblacion_kg"], "Niños de la Unión, ~20 kg, frente a los 66 kg de referencia."),
    "factor_cuerpo_mayores": v(0.85, 0.75, 0.95, "fraccion", "Energía del cuerpo de un mayor relativa a la de un adulto.", ["masa_fallecido_adulto_mayor_kg"], "~56 kg / 66 kg."),
    "factor_cuerpo_hambre": v(0.4, 0.3, 0.5, "fraccion", "Energía que queda en un cuerpo muerto de inanición relativa a uno normal: sin grasa y con 40% menos músculo.", ["frac_perdida_peso_letal"], "Un cuerpo emaciado rinde ~40-60 mil kcal frente a 125,822."),
    "rendimiento_hdp": v(0.75, 0.5, 0.9, "fraccion", "Fracción de la energía de un cuerpo que termina como HDP comestible (molienda, cocción, secado).", [], "Supuesto del modelo; el canon muestra molinos, cubas de cocción y polvo reconstituido."),
    "frac_recuperacion_cuerpos": v(0.9, 0.5, 1.0, "fraccion", "Fracción de los cuerpos que la colmena recupera y procesa.", ["cuerpos_union_recolectados", "procesamiento_hdp"], "Canon: recogen cadáveres y el almacén refrigerado Agri-Jet está lleno de partes envasadas al vacío."),
    # --- Cereal ---
    "kcal_kg_cereal": v(3536, 3482, 3567, "kcal/kg", "Energía del cereal almacenado, ponderada por existencias (trigo, maíz, arroz elaborado y granos menores).", ["kcal_kg_cereal_promedio", "kcal_kg_trigo", "kcal_kg_maiz", "kcal_kg_arroz"]),
    "frac_cereal_comestible": v(0.96, 0.9, 0.99, "fraccion", "Fracción del cereal almacenado apta para humanos: el grano forrajero es casi todo comestible, salvo el dañado o con micotoxinas.", ["frac_pienso_comestible_humano", "cereal_uso_pienso_mt", "frac_cultivos_micotoxinas_sobre_limite"], "38% del uso es pienso × 10% no apto ≈ 4%."),
    "perdida_cereal_anual": v(0.045, 0.01, 0.18, "fraccion/anio", "Pérdida anual del grano almacenado. En silos herméticos es menor al 1%; con pequeños productores en el trópico, de 18 a 36%.", ["perdida_almacen_anual", "perdida_almacen_anual_buena", "perdida_almacen_anual_pequeno_productor"]),
    "cereal_produccion_mt": v(3019, 2980, 3043, "Mt/anio", "Producción mundial de cereal 2025 (USDA PSD; FAO: 3,043 Mt). Solo cuenta si se permite recoger grano de plantas muertas.", ["cereal_produccion_2025_mt"]),
    # --- Otros inventarios ---
    "soya_mt": v(300, 125, 450, "Mt", "Soya almacenada en una fecha promedio del año (las existencias de cierre, 125 Mt, son el mínimo del ciclo).", ["soya_existencias_mt", "soya_existencias_promedio_anual_mt", "soya_produccion_mt"], "125 + 0.85 × 429 / 2 ≈ 307 Mt, redondeado a 300."),
    "oleaginosas_otras_mt": v(70, 20, 120, "Mt", "Colza, girasol, cacahuate y otras oleaginosas almacenadas en una fecha promedio.", ["oleaginosas_otras_existencias_mt", "colza_existencias_mt", "girasol_existencias_mt", "cacahuate_existencias_mt"], "Cierre de 20.6 Mt más la parte de las cosechas del año que aún no se consume."),
    "harina_proteica_mt": v(24, 22.5, 24.7, "Mt", "Harinas proteicas almacenadas (sobre todo pasta de soya).", ["harina_proteica_existencias_mt"]),
    "aceites_mt": v(32, 30, 40, "Mt", "Aceites vegetales almacenados; sin biodiésel, todo es comida.", ["aceites_veg_existencias_mt", "aceites_veg_frac_uso_alimentario"]),
    "azucar_mt": v(80, 43.5, 140, "Mt", "Azúcar almacenada: USDA da 43.5 Mt al cierre, la ISO ~79 Mt y el promedio anual ronda 100 Mt.", ["azucar_existencias_mt", "azucar_existencias_iso_mt", "azucar_existencias_promedio_mt"]),
    "legumbres_mt": v(45, 15, 80, "Mt", "Legumbres secas almacenadas (no hay cifra oficial mundial).", ["legumbres_existencias_mt", "legumbres_existencias_promedio_mt"]),
    "tuberculos_mt": v(115, 50, 190, "Mt", "Papa en almacén en una fecha promedio. La yuca no cuenta: se pudre en 2-3 días fuera de la tierra.", ["papa_en_almacen_mt", "yuca_produccion_mt"]),
    "kcal_kg_soya": v(4460, 4460, 4460, "kcal/kg", "Energía de la soya (hay que cocerla).", ["kcal_kg_soya"]),
    "kcal_kg_oleaginosas_otras": v(5000, 4500, 5840, "kcal/kg", "Energía promedio de otras oleaginosas.", ["kcal_kg_cacahuate"]),
    "kcal_kg_harina_proteica": v(3270, 3000, 3300, "kcal/kg", "Energía de la harina de soya desgrasada.", ["harina_proteica_existencias_mt"]),
    "kcal_kg_aceite": v(8840, 8840, 8920, "kcal/kg", "Energía del aceite vegetal.", ["kcal_kg_aceite"]),
    "kcal_kg_azucar": v(3870, 3850, 3870, "kcal/kg", "Energía del azúcar.", ["kcal_kg_azucar"]),
    "kcal_kg_legumbres": v(3480, 3330, 3780, "kcal/kg", "Energía promedio de las legumbres secas.", ["kcal_kg_legumbres"]),
    "kcal_kg_tuberculos": v(770, 770, 860, "kcal/kg", "Energía de la papa cruda.", ["kcal_kg_papa"]),
    "dias_inventario_cadena": v(32, 15, 60, "dias", "Días de venta guardados en tiendas (~10), distribución (~15) y despensas (~7), que la colmena centraliza desde el día 4.", ["dias_inventario_retail", "dias_inventario_mayoreo", "dias_despensa_hogar", "consolidacion_recursos"], "Sin manufactura, para no contar dos veces materias primas que ya están en las existencias."),
    "kcal_suministro_previo": v(3026, 2950, 3050, "kcal/persona/dia", "Suministro de comida por persona antes de la Unión (incluye desperdicio): es el ritmo al que se vaciaban esos inventarios.", ["kcal_suministro_per_capita_2024"]),
    "frac_cadena_perecedera": v(0.23, 0.18, 0.3, "fraccion", "Parte perecedera (en calorías) de ese inventario: frutas, verduras, lácteos y carne.", ["frac_pipeline_perecedero"]),
    "almacen_frio_mt": v(25, 10, 60, "Mt", "Comida en almacenes fríos del mundo (EE. UU. guarda 3.94 Mt).", ["almacen_frio_global_mt", "almacen_frio_eeuu_mt"]),
    "kcal_kg_congelados": v(2100, 1800, 2400, "kcal/kg", "Energía promedio de lo congelado.", ["almacen_frio_eeuu_kcal_kg"]),
    # --- Fruta caída ---
    "fruta_caida_kcal_anio1": v(3.68e14, 1.15e14, 8.29e14, "kcal/anio", "Fruta y nueces caídas recuperables el primer año (incluye el fruto suelto de la palma aceitera; sin palma serían 1.83e14).", ["windfall_kcal_anio1", "windfall_kcal_anio1_sin_palma", "frac_fruta_que_cae", "frac_recuperable_caida"]),
    "declive_huerto_anual": v(0.12, 0.05, 0.25, "fraccion/anio", "Caída anual del rendimiento de los huertos sin poda, deshierbe ni control de plagas.", ["declive_huerto_anual"]),
    "piso_silvestre": v(0.35, 0.15, 0.6, "fraccion", "Lo que sigue dando un árbol asilvestrado respecto al año 1.", ["rendimiento_feral_relativo"]),
    "frac_conservacion_fruta": v(0.5, 0.0, 0.8, "fraccion", "Fracción de la fruta caída que la colmena seca, enlata o prensa en vez de comerla fresca.", ["receta_bebida"], "Canon: procesan primero lo que se va a echar a perder y lo convierten en bebida estable."),
    # --- Mascotas ---
    "perros": v(9.87e8, 7.0e8, 1.0e9, "cabezas", "Perros en el mundo; más del 70% son de vida libre.", ["perros_mundo", "frac_perros_libres"]),
    "gatos": v(6.0e8, 4.8e8, 1.0e9, "cabezas", "Gatos en el mundo.", ["gatos_mundo"]),
    "kcal_dia_perro": v(1125, 630, 1410, "kcal/dia", "Requerimiento de un perro de 21.6 kg.", ["kcal_dia_perro"]),
    "kcal_dia_gato": v(226, 190, 300, "kcal/dia", "Requerimiento de un gato.", ["kcal_dia_gato"]),
    # --- Productos animales ---
    "leche_kcal_anio": v(971.4e9 * 650, 953.2e9 * 610, 984.8e9 * 715, "kcal/anio", "Energía de la producción mundial de leche (971 Mt × 650 kcal/kg).", ["leche_produccion_mt", "kcal_kg_leche", "regla_ordenio"]),
    "dias_lactancia": v(305, 200, 365, "dias", "Duración de la lactancia: sin partos nuevos, la leche se acaba en unos 10 meses.", ["dias_lactancia_estandar", "leche_requiere_partos"]),
    "huevo_kcal_anio": v(98.3e9 * 1290, 95.98e9 * 1260, 99.99e9 * 1430, "kcal/anio", "Energía de la producción mundial de huevo (98 Mt × 1,290 kcal/kg con cáscara).", ["huevo_produccion_mt", "kcal_kg_huevo"]),
    "miel_kcal_anio": v(1.959e9 * 3040, 1.943e9 * 3000, 1.988e9 * 3290, "kcal/anio", "Energía de la producción mundial de miel.", ["miel_produccion_mt", "kcal_kg_miel"]),
    "frac_recuperacion_cadaver_alimentado": v(0.6, 0.4, 0.8, "fraccion", "Carne recuperada de animales que mueren en granja (se detectan en horas).", ["frac_recuperacion_cadaver", "horas_ventana_cadaver"]),
    "frac_recuperacion_cadaver_liberado": v(0.15, 0.05, 0.3, "fraccion", "Carne recuperada de animales liberados que mueren en el campo (carroñeros, calor, enfermedad).", ["frac_recuperacion_cadaver", "descomposicion_estacional", "canon_carronieros"]),
}

TABLAS = {
    "cereal_en_mano_mt_por_mes": {
        "valores": [2076, 1874, 1676, 1540, 1481, 1405, 1385, 1454, 1496, 1738, 2096, 2185],
        "unidad": "Mt",
        "descripcion": "Cereal físicamente almacenado en el mundo el día 1 de cada mes (enero a diciembre).",
        "fuentes": [f"cereal_en_mano_mes_{m:02d}" for m in range(1, 13)],
        "derivacion": "Modelo propio: USDA PSD 2025/26 por país × calendario de cosecha AMIS, con consumo parejo y un factor de 0.85 calibrado con las existencias trimestrales de EE. UU. (NASS). El mínimo cae el 1 de julio y el máximo el 1 de diciembre.",
    },
    "cosecha_cereal_frac_por_mes": {
        "valores": [0.005, 0.006, 0.031, 0.06, 0.053, 0.076, 0.11, 0.10, 0.177, 0.223, 0.118, 0.041],
        "unidad": "fraccion",
        "descripcion": "Fracción de la cosecha mundial de cereal levantada en cada mes.",
        "fuentes": [f"cereal_frac_cosecha_mes_{m:02d}" for m in range(1, 13)],
    },
    "fruta_caida_frac_por_mes": {
        "valores": [0.0771, 0.075, 0.0658, 0.0658, 0.0658, 0.0817, 0.0863, 0.0955, 0.1047, 0.1047, 0.0955, 0.0821],
        "unidad": "fraccion",
        "descripcion": "Fracción de la fruta caída del año que cae en cada mes.",
        "fuentes": ["frac_windfall_tropical", "frac_windfall_templado_norte", "estacionalidad_bandas"],
        "derivacion": "76% tropical (coco, palma, plátano: parejo todo el año) + 23% del norte templado (hueso jun-sep, manzana ago-nov, nueces ago-oct, aceituna oct-feb) + 1% del sur.",
    },
}

GANADO = {
    "bovinos": {"nombre": "Bovinos", "cabezas": 1.574e9, "kcal_comestible_cabeza": 280 * 875, "vida_natural_dias": 17 * 365, "mortalidad_liberado_anual": 0.35, "alimento_kcal_dia": 1490, "frac_pastoreo": 0.0, "fuentes": ["bovinos_cabezas", "peso_vivo_bovino_kg", "kcal_kg_peso_vivo_bovino", "vida_natural_bovino_anios", "frac_rumiantes_sobreviven_pastoreo"]},
    "bufalos": {"nombre": "Búfalos", "cabezas": 2.12e8, "kcal_comestible_cabeza": 335 * 875, "vida_natural_dias": 20 * 365, "mortalidad_liberado_anual": 0.3, "alimento_kcal_dia": 500, "frac_pastoreo": 0.0, "fuentes": ["bufalos_cabezas", "peso_vivo_bufalo_kg"]},
    "cerdos": {"nombre": "Cerdos", "cabezas": 9.66e8, "kcal_comestible_cabeza": 40 * 1537, "vida_natural_dias": 12 * 365, "mortalidad_liberado_anual": 1.5, "alimento_kcal_dia": 2980, "frac_pastoreo": 0.0, "fuentes": ["cerdos_cabezas", "peso_vivo_cerdo_kg", "vida_natural_cerdo_anios", "mortalidad_anual_cerda"]},
    "ovinos_caprinos": {"nombre": "Ovejas y cabras", "cabezas": 2.519e9, "kcal_comestible_cabeza": 31.5 * 918, "vida_natural_dias": 13 * 365, "mortalidad_liberado_anual": 0.3, "alimento_kcal_dia": 150, "frac_pastoreo": 0.0, "fuentes": ["ovejas_cabezas", "cabras_cabezas", "peso_vivo_oveja_kg", "mortalidad_anual_ovino_caprino_adulto"]},
    "pollos_engorda": {"nombre": "Pollos de engorda", "cabezas": 8.855e9, "kcal_comestible_cabeza": 1.5 * 1041, "vida_natural_dias": 120, "mortalidad_liberado_anual": 20.0, "alimento_kcal_dia": 300, "frac_pastoreo": 0.0, "fuentes": ["pollos_engorda_cabezas", "vida_natural_pollo_engorda_dias", "broilers_no_sobreviven_libre_acceso"]},
    "gallinas_ponedoras": {"nombre": "Gallinas ponedoras", "cabezas": 8.53e9, "kcal_comestible_cabeza": 1.8 * 1041, "vida_natural_dias": 7 * 365, "mortalidad_liberado_anual": 2.0, "alimento_kcal_dia": 280, "frac_pastoreo": 0.0, "fuentes": ["gallinas_ponedoras_cabezas", "vida_natural_gallina_anios"]},
    "otras_aves": {"nombre": "Otras aves (traspatio, patos, pavos, gansos)", "cabezas": 1.16e10, "kcal_comestible_cabeza": 1.51 * 1041, "vida_natural_dias": 6 * 365, "mortalidad_liberado_anual": 0.5, "alimento_kcal_dia": 100, "frac_pastoreo": 0.0, "fuentes": ["otros_pollos_cabezas", "patos_cabezas", "pavos_cabezas", "gansos_cabezas"]},
}
NOTA_GANADO = (
    "kcal comestibles = peso vivo promedio del hato × kcal por kg vivo (canal × energía de la carne). "
    "Pienso = el grano que hoy consume cada especie (1,122 Mt de cereal al año repartidos según el pienso "
    "compuesto por sector), por cabeza."
)

POOLS = {
    "perecederos": {"nombre": "Frescos", "vida_media_dias": 10},
    "tuberculos": {"nombre": "Papa y tubérculos", "vida_media_dias": 150},
    "aceites": {"nombre": "Aceites vegetales", "vida_media_dias": 1000},
    "conservas": {"nombre": "Fruta seca o en conserva", "vida_media_dias": 2500},
    "procesados": {"nombre": "Comida empacada", "vida_media_dias": 3000},
    "carne_animal": {"nombre": "Carne de animales muertos", "vida_media_dias": 2500},
    "hdp": {"nombre": "HDP", "vida_media_dias": 2500},
    "congelados": {"nombre": "Congelados", "vida_media_dias": 3650},
    "oleaginosas": {"nombre": "Soya, oleaginosas y harinas", "vida_media_dias": 6000},
    "cereal": {"nombre": "Cereal", "vida_media_dias": None},
    "legumbres": {"nombre": "Legumbres", "vida_media_dias": 10000},
    "azucar": {"nombre": "Azúcar y miel", "vida_media_dias": 50000},
}


def main() -> None:
    ruta_fuentes = DATOS / "fuentes.json"
    ids: set[str] = set()
    if ruta_fuentes.exists():
        fuentes = json.loads(ruta_fuentes.read_text(encoding="utf-8"))
        ids = {p["id"] for p in fuentes.get("params", [])} | {f["id"] for f in fuentes.get("facts", [])}
    citadas = {f for d in [*VALORES.values(), *TABLAS.values(), *GANADO.values()] for f in d["fuentes"]}
    faltan = sorted(citadas - ids)
    if faltan:
        print("Aviso: fuentes citadas que no están en fuentes.json:", ", ".join(faltan))

    salida = {
        "version": "0.1.0",
        "nota": "Valores investigados y verificados con fuentes (FAO, USDA, ONU, OMS, literatura) más los números del canon. Los rangos son los que se exploran como palancas.",
        "valores": VALORES,
        "tablas": TABLAS,
        "ganado": GANADO,
        "nota_ganado": NOTA_GANADO,
        "pools": POOLS,
    }
    (DATOS / "supuestos.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"supuestos.json: {len(VALORES)} valores, {len(TABLAS)} tablas, {len(GANADO)} grupos de ganado")


if __name__ == "__main__":
    main()
