"""Palancas del escenario: todo lo que el usuario (o el juego) puede mover.

Cada campo trae en `json_schema_extra` su grupo, etiqueta y paso, para que el
front arme los controles directo del esquema (GET /escenario) sin duplicar
rangos ni textos. Los defaults salen de datos/supuestos.json.
"""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from . import supuestos as S


def _p(grupo: str, etiqueta: str, paso: float | None = None, formato: str | None = None) -> dict:
    extra = {"grupo": grupo, "etiqueta": etiqueta}
    if paso is not None:
        extra["paso"] = paso
    if formato is not None:
        extra["formato"] = formato
    return extra


def _s(clave: str) -> float:
    return S.valor(clave)


class Escenario(BaseModel):
    # NaN e infinito no son escenarios: se rechazan con 422 en lugar de romper la simulación.
    model_config = ConfigDict(allow_inf_nan=False)

    # --- General ---------------------------------------------------------------
    mes_union: int = Field(
        7, ge=1, le=12,
        description="Mes en que ocurre la Unión. Decide cuánto grano había guardado: el 1 de julio es el mínimo del año (~1,385 Mt) y el 1 de diciembre el máximo (~2,185 Mt). El canon no da fecha, pero las pistas (una botella envasada el 8 de mayo, el calor del día 1 en Albuquerque) apuntan a finales de primavera o verano.",
        json_schema_extra=_p("General", "Mes de la Unión", 1, "mes"),
    )
    anios: int = Field(
        15, ge=1, le=30,
        description="Años a simular.",
        json_schema_extra=_p("General", "Horizonte (años)", 1),
    )

    # --- Demanda -----------------------------------------------------------------
    kcal_dia_promedio: float = Field(
        default_factory=lambda: _s("kcal_dia_promedio"), ge=1200, le=3000,
        description="Requerimiento energético promedio por persona al día (toda la población). Con PAL 1.4 la colmena ahorra energía; sedentaria típica serían ~2,070 kcal. Ojo: las 2,400 kcal de John Cena (~114 kg) son un déficit, no su requerimiento.",
        json_schema_extra=_p("Demanda", "kcal por persona al día", 50, "kcal"),
    )
    adaptacion_metabolica: float = Field(
        default_factory=lambda: _s("adaptacion_metabolica"), ge=0, le=0.8,
        description="Cuánto baja el gasto del cuerpo al agotarse la reserva (menos masa más termogénesis adaptativa). Calibrada en 0.7 contra el ayuno de los huelguistas de 1981, Minnesota y Leningrado.",
        json_schema_extra=_p("Demanda", "Adaptación metabólica", 0.05, "pct"),
    )
    natalidad: float = Field(
        1.0, ge=0, le=2.5,
        description="Multiplicador sobre la natalidad del canon (965 nacimientos cada 10 minutos, ep. 8) después de los embarazos que ya estaban en curso (primeros 9 meses). 2.35 regresa a la natalidad de antes de la Unión (16.1 por mil).",
        json_schema_extra=_p("Demanda", "Natalidad (x canon)", 0.05, "x"),
    )
    muertes_naturales_dia: float = Field(
        default_factory=lambda: _s("muertes_naturales_dia"), ge=0, le=250000,
        description="Muertes diarias por causas naturales y accidentes al inicio: casi 100,000 según Cena; 241,000 según el conteo de Zosia en el ep. 8. Escala con la población.",
        json_schema_extra=_p("Demanda", "Muertes naturales al día", 5000, "entero"),
    )

    # --- Reparto -----------------------------------------------------------------
    racion_modo: Literal["completa", "fija", "estirar"] = Field(
        "completa",
        description="completa: todos comen lo que necesitan hasta que se acaba. fija: una ración constante. estirar: la colmena calcula la ración para que la comida dure hasta el horizonte elegido.",
        json_schema_extra=_p("Reparto", "Política de ración"),
    )
    racion_fraccion: float = Field(
        0.8, ge=0.3, le=1,
        description="Ración como fracción del requerimiento (modo fija).",
        json_schema_extra=_p("Reparto", "Ración fija", 0.05, "pct"),
    )
    horizonte_estirar_anios: float = Field(
        10, ge=1, le=30,
        description="Hasta cuándo quiere la colmena que dure la comida (modo estirar). Koumba habla de diez años.",
        json_schema_extra=_p("Reparto", "Estirar hasta (años)", 0.5),
    )
    racion_minima: float = Field(
        0.6, ge=0.2, le=1,
        description="Ración mínima que la colmena acepta al estirar.",
        json_schema_extra=_p("Reparto", "Ración mínima al estirar", 0.05, "pct"),
    )

    # --- Existencias ---------------------------------------------------------------
    cereal_en_mano_mt: Optional[float] = Field(
        None, ge=0, le=5000,
        description="Cereal almacenado el día de la Unión. Vacío = se calcula con el mes.",
        json_schema_extra=_p("Existencias", "Cereal en almacén (Mt)", 50, "entero"),
    )
    perdida_cereal_anual: float = Field(
        default_factory=lambda: _s("perdida_cereal_anual"), ge=0, le=0.3,
        description="Pérdida anual del grano almacenado.",
        json_schema_extra=_p("Existencias", "Pérdida anual de grano", 0.01, "pct"),
    )
    factor_otros_stocks: float = Field(
        1.0, ge=0, le=2,
        description="Multiplicador sobre soya, oleaginosas, aceites, azúcar, legumbres y tubérculos.",
        json_schema_extra=_p("Existencias", "Otros inventarios (x)", 0.1, "x"),
    )
    dias_inventario_cadena: float = Field(
        default_factory=lambda: _s("dias_inventario_cadena"), ge=0, le=90,
        description="Días de consumo que había en tiendas, bodegas y despensas.",
        json_schema_extra=_p("Existencias", "Días en la cadena de suministro", 1, "entero"),
    )

    # --- Flujos --------------------------------------------------------------------
    fruta_caida_factor: float = Field(
        1.0, ge=0, le=3,
        description="Multiplicador sobre la fruta y nueces caídas recuperables.",
        json_schema_extra=_p("Flujos", "Fruta caída (x)", 0.1, "x"),
    )
    declive_huerto_anual: float = Field(
        default_factory=lambda: _s("declive_huerto_anual"), ge=0, le=0.5,
        description="Caída anual de rendimiento de los huertos sin poda, deshierbe ni control de plagas (matar insectos también está prohibido).",
        json_schema_extra=_p("Flujos", "Declive de huertos por año", 0.01, "pct"),
    )
    frac_conservacion_fruta: float = Field(
        default_factory=lambda: _s("frac_conservacion_fruta"), ge=0, le=1,
        description="Fracción de la fruta caída que se seca o enlata para después.",
        json_schema_extra=_p("Flujos", "Fruta que se conserva", 0.05, "pct"),
    )
    hdp_activo: bool = Field(
        True,
        description="Procesar a los muertos como HDP (canon).",
        json_schema_extra=_p("Flujos", "Usar HDP"),
    )
    frac_recuperacion_cuerpos: float = Field(
        default_factory=lambda: _s("frac_recuperacion_cuerpos"), ge=0, le=1,
        description="Fracción de los cuerpos (de la Unión y posteriores) que se recupera y procesa.",
        json_schema_extra=_p("Flujos", "Cuerpos recuperados", 0.05, "pct"),
    )

    # --- Animales ------------------------------------------------------------------
    ganado_politica: Literal["liberar", "alimentar"] = Field(
        "liberar",
        description="liberar: el ganado se suelta y muere en el campo (poca carne recuperable). alimentar: se le sigue dando de comer, con el mismo grano que come la gente.",
        json_schema_extra=_p("Animales", "Ganado"),
    )
    mascotas_politica: Literal["alimentar", "liberar"] = Field(
        "liberar",
        description="Canon: vaciaron los zoológicos y soltaron a los perros encadenados; solo cuidan a los que no se separan de su dueño. alimentar: seguir alimentando a las mascotas que tenían dueño (~200 M de perros y 220 M de gatos).",
        json_schema_extra=_p("Animales", "Mascotas"),
    )

    ordena_leche: float = Field(
        1.0, ge=0, le=1,
        description="Fracción de las vacas lecheras que se siguen ordeñando. Canon: el video de Cena dice que miles de millones de animales domésticos, sobre todo vacas, todavía necesitan ordeña.",
        json_schema_extra=_p("Animales", "Ordeña", 0.05, "pct"),
    )
    partos_ganado: bool = Field(
        False,
        description="Dejar que el ganado siga pariendo. Sin partos, la leche se acaba al terminar la lactancia en curso (~10 meses).",
        json_schema_extra=_p("Animales", "Partos del ganado"),
    )

    # --- Resquicios (fuera del canon estricto) --------------------------------------------
    resquicio_huevos: float = Field(
        0.0, ge=0, le=1,
        description="Fracción de la producción previa de huevo que se mantiene (requiere gallinas alimentadas).",
        json_schema_extra=_p("Resquicios", "Huevos", 0.05, "pct"),
    )
    resquicio_miel: float = Field(
        0.0, ge=0, le=1,
        description="Fracción de la producción previa de miel que se mantiene.",
        json_schema_extra=_p("Resquicios", "Miel", 0.05, "pct"),
    )
    cosecha_senescente: float = Field(
        0.0, ge=0, le=1,
        description="Recoger el grano de los cultivos que ya estaban sembrados cuando la planta muere sola al madurar. Solo aplica al primer ciclo.",
        json_schema_extra=_p("Resquicios", "Cosecha de plantas muertas", 0.05, "pct"),
    )
    siembra_senescente: float = Field(
        0.0, ge=0, le=1,
        description="Sembrar y recoger solo cuando la planta muere sola, como fracción de la cosecha normal, del segundo año en adelante.",
        json_schema_extra=_p("Resquicios", "Siembra sin matar", 0.05, "pct"),
    )


def palancas() -> dict:
    """Esquema JSON del escenario, con defaults ya resueltos (para armar controles)."""
    esquema = Escenario.model_json_schema()
    defaults = Escenario().model_dump()
    for clave, prop in esquema["properties"].items():
        prop["default"] = defaults[clave]
    return esquema
