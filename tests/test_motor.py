"""Invariantes del motor: contabilidad de kcal, casos extremos y monotonía."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from motor.escenario import Escenario, palancas  # noqa: E402
from motor.simulacion import simular  # noqa: E402


def _r(**kw):
    return simular(Escenario(anios=kw.pop("anios", 6), **kw))


def test_canon_poblacion_inicial():
    assert _r(anios=1).resumen["poblacion_inicial"] == 7_348_292_411


def test_no_se_come_mas_de_lo_que_hubo():
    r = _r()
    inicial = sum(f["inicial_kcal"] for f in r.fuentes)
    entradas = sum(sum(v) for v in r.serie["entradas_kcal"].values())
    comido = sum(f["consumido_kcal"] for f in r.fuentes)
    assert comido <= inicial + entradas + 1.0


def test_sin_comida_nadie_sobrevive():
    # Sin inventario ni flujos, la gente muere al agotar su reserva, que en el
    # extremo más gordo de la distribución es de varios cientos de miles de kcal.
    r = _r(
        cereal_en_mano_mt=0, factor_otros_stocks=0, dias_inventario_cadena=0, fruta_caida_factor=0,
        hdp_activo=False, mascotas_politica="liberar", anios=4,
    )
    # la carne del ganado liberado todavía alimenta a unos cuantos un rato
    assert r.resumen["poblacion_final"] < 0.05 * r.resumen["poblacion_inicial"]
    assert r.resumen["dia_inicio_hambruna"] is not None
    assert r.resumen["dia_inicio_hambruna"] < 60


def test_con_comida_de_sobra_no_hay_hambruna():
    r = _r(cereal_en_mano_mt=5000, factor_otros_stocks=2, siembra_senescente=1, cosecha_senescente=1, anios=4)
    assert r.resumen["dia_inicio_hambruna"] is None
    assert r.resumen["muertes_hambre"] < 1e6


def test_mas_grano_retrasa_la_hambruna():
    poco = _r(cereal_en_mano_mt=1000).resumen["dia_inicio_hambruna"]
    mucho = _r(cereal_en_mano_mt=2500).resumen["dia_inicio_hambruna"]
    assert poco is not None and mucho is not None
    assert mucho > poco


def test_alimentar_al_ganado_adelanta_la_hambruna():
    liberar = _r(ganado_politica="liberar").resumen["dia_inicio_hambruna"]
    alimentar = _r(ganado_politica="alimentar").resumen["dia_inicio_hambruna"]
    assert alimentar < liberar


def test_hdp_aporta_poco():
    con = _r(hdp_activo=True)
    hdp = next(f for f in con.fuentes if f["clave"] == "hdp")
    assert hdp["frac_consumo"] < 0.05


def test_poblacion_nunca_negativa():
    r = _r(racion_modo="fija", racion_fraccion=0.5)
    assert min(r.serie["poblacion"]) >= 0
    for serie in r.serie["poblacion_cohortes"].values():
        assert min(serie) >= 0


@pytest.mark.parametrize("modo", ["completa", "fija", "estirar"])
def test_racion_entre_cero_y_uno(modo):
    r = _r(racion_modo=modo)
    assert all(0 <= x <= 1 + 1e-9 for x in r.serie["racion"])


def test_api_simular_y_escenario():
    c = TestClient(app)
    assert c.get("/health").json() == {"ok": True}
    esquema = c.get("/escenario").json()
    assert "mes_union" in esquema["properties"]
    assert esquema["properties"]["mes_union"]["grupo"] == "General"
    r = c.post("/simular", json={"anios": 2, "mes_union": 6})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["escenario"]["mes_union"] == 6
    assert len(cuerpo["serie"]["dia"]) == len(cuerpo["serie"]["poblacion"])
    assert c.post("/simular", json={"mes_union": 13}).status_code == 422


def test_racion_fija_con_comida_de_sobra_se_estabiliza():
    # Con 70% del requerimiento base el cuerpo adelgaza hasta gastar lo que come.
    # Mueren algunos de los que ya eran delgados, pero la población se estabiliza.
    r = _r(racion_modo="fija", racion_fraccion=0.7, cereal_en_mano_mt=5000, siembra_senescente=1, cosecha_senescente=1, anios=4)
    assert r.resumen["muertes_hambre"] < 0.15 * r.resumen["poblacion_inicial"]
    assert sum(r.serie["muertes_hambre"][-52:]) < 0.5 * sum(r.serie["muertes_hambre"][:52])
    assert min(r.serie["reserva_corporal"][-10:]) > 0.3


def test_estirar_retrasa_el_colapso():
    # Estirar mata antes a los más vulnerables, pero la mitad de la colmena aguanta más.
    completa = _r(racion_modo="completa").resumen["dia_mitad_poblacion"]
    estirar = _r(racion_modo="estirar", horizonte_estirar_anios=10).resumen["dia_mitad_poblacion"]
    assert estirar > completa


def test_leche_sin_partos_se_acaba():
    r = _r(ordena_leche=1.0, partos_ganado=False, anios=2)
    resquicios = r.serie["entradas_kcal"]["resquicios"]
    assert resquicios[0] > 0
    assert resquicios[-1] == 0


# --- Regresiones de la revisión adversarial del motor -------------------------------

ABUNDANCIA = dict(cereal_en_mano_mt=5000, factor_otros_stocks=2, siembra_senescente=1, cosecha_senescente=1)


def test_metricas_de_10_anios_no_dependen_del_horizonte():
    corto = simular(Escenario(anios=1)).resumen
    largo = simular(Escenario(anios=15)).resumen
    assert corto["muertos_hambre_10_anios_frac"] == pytest.approx(largo["muertos_hambre_10_anios_frac"])
    assert corto["koumba_acierta"] == largo["koumba_acierta"]
    assert corto["poblacion_10_anios"] == pytest.approx(largo["poblacion_10_anios"])
    assert corto["capacidad_de_carga"] == pytest.approx(largo["capacidad_de_carga"])
    assert len(simular(Escenario(anios=1)).serie["dia"]) == 53


def test_racion_reportada_es_contra_el_requerimiento_base():
    r = _r(racion_modo="fija", racion_fraccion=0.5, anios=3, **ABUNDANCIA)
    assert r.resumen["racion_promedio"] == pytest.approx(0.5, abs=0.02)


def test_animales_alimentados_no_mueren_de_hambre_si_sobra_comida():
    fija = _r(racion_modo="fija", racion_fraccion=0.8, ganado_politica="alimentar", anios=2, **ABUNDANCIA)
    completa = _r(racion_modo="completa", ganado_politica="alimentar", anios=2, **ABUNDANCIA)
    bov_fija = fija.serie["ganado_cabezas"]["bovinos"][-1]
    bov_completa = completa.serie["ganado_cabezas"]["bovinos"][-1]
    assert bov_fija == pytest.approx(bov_completa, rel=0.01)


def test_desnutricion_cronica_mata_con_raciones_muy_bajas():
    muy_baja = _r(racion_modo="fija", racion_fraccion=0.36, anios=4, **ABUNDANCIA).resumen
    suficiente = _r(racion_modo="fija", racion_fraccion=0.8, anios=4, **ABUNDANCIA).resumen
    assert muy_baja["muertes_hambre"] > 0.3 * muy_baja["poblacion_inicial"]
    # con 80% solo caen los que ya eran delgados (refugiados con 1,360-1,870 kcal: ~9% en 12 meses)
    assert suficiente["muertes_hambre"] < 0.1 * suficiente["poblacion_inicial"]


def test_estirar_no_se_come_la_cosecha_pasajera_como_si_durara():
    r = _r(racion_modo="estirar", horizonte_estirar_anios=10, racion_minima=0.3, cosecha_senescente=1, anios=2)
    # el primer año no debería comer a ración completa gracias a una cosecha que dura 5 meses
    assert r.resumen["racion_promedio"] < 0.9


def test_ultima_semana_parcial_se_reporta():
    r = _r(anios=1)
    assert r.serie["dias_tramo"][-1] == 365 - 7 * 52
    assert sum(r.serie["dias_tramo"]) == 365


def test_api_rechaza_nan_con_422():
    c = TestClient(app)
    r = c.post("/simular", content='{"kcal_dia_promedio": NaN}', headers={"Content-Type": "application/json"})
    assert r.status_code == 422
    assert c.post("/simular", json={"natalidad": 2.3, "anios": 1}).status_code == 200


def test_defaults_caen_en_el_paso_de_su_slider():
    # Si un default no cae en min + k*paso, el slider del front lo "corrige" al montarse
    # y la simulación corre con otro valor (pasó con la pérdida de grano: 4.5% -> 4%).
    for clave, p in palancas()["properties"].items():
        paso, d = p.get("paso"), p.get("default")
        if not paso or isinstance(d, bool) or not isinstance(d, (int, float)):
            continue
        pasos = (d - p.get("minimum", 0)) / paso
        assert abs(pasos - round(pasos)) < 1e-6, f"{clave}={d} no cae en pasos de {paso}"
