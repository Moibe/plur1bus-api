"""Invariantes del motor: contabilidad de kcal, casos extremos y monotonía."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from motor.escenario import Escenario  # noqa: E402
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
