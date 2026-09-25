"""Traducciones de la API: es.json al día con los textos del código, cada idioma
con exactamente las mismas claves, y ?lang= aplicado en todos los endpoints con texto."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from herramientas.extraer_textos import extraer  # noqa: E402
from main import app  # noqa: E402
from motor import i18n, supuestos  # noqa: E402

cliente = TestClient(app)
TRADUCCIONES = [lang for lang in i18n.IDIOMAS if lang != i18n.IDIOMA_FUENTE]


def test_es_json_al_dia_con_el_codigo():
    """Si falla: corre `python herramientas/extraer_textos.py` y traduce las claves nuevas."""
    assert i18n.textos("es") == extraer()


@pytest.mark.parametrize("lang", TRADUCCIONES)
def test_cada_idioma_tiene_las_mismas_claves(lang):
    fuente, destino = i18n.textos("es"), i18n.textos(lang)
    assert sorted(set(fuente) - set(destino)) == [], "claves sin traducir"
    assert sorted(set(destino) - set(fuente)) == [], "claves que ya no existen en es.json"
    assert [k for k, v in destino.items() if not str(v).strip()] == [], "textos vacíos"


def test_normalizar():
    assert i18n.normalizar("en-US") == "en"
    assert i18n.normalizar("AR_eg") == "ar"
    assert i18n.normalizar("xx") == "es"
    assert i18n.normalizar(None) == "es"


def test_escenario_traduce_textos_y_no_toca_numeros():
    es = cliente.get("/escenario", params={"lang": "es"}).json()["properties"]
    en = cliente.get("/escenario", params={"lang": "en"}).json()["properties"]
    assert es.keys() == en.keys()
    textos = i18n.textos("en")
    for campo, p in en.items():
        assert p["etiqueta"] == textos[f"palancas.{campo}.etiqueta"]
        sin_textos = {k: v for k, v in p.items() if k not in ("etiqueta", "description", "grupo")}
        assert sin_textos == {k: v for k, v in es[campo].items() if k not in ("etiqueta", "description", "grupo")}


def test_idioma_desconocido_cae_al_espanol():
    assert cliente.get("/escenario", params={"lang": "xx"}).json() == cliente.get("/escenario").json()


def test_simular_traduce_los_nombres_de_las_fuentes():
    r = cliente.post("/simular", params={"lang": "fr"}, json={"anios": 1})
    assert r.status_code == 200
    textos = i18n.textos("fr")
    for f in r.json()["fuentes"]:
        assert f["nombre"] == textos[f"pools.{f['clave']}"]


def test_supuestos_y_hechos_traducidos():
    textos = i18n.textos("de")
    original = supuestos.cargar()
    s = cliente.get("/supuestos", params={"lang": "de"}).json()
    for clave, v in s["valores"].items():
        assert v["descripcion"] == textos[f"supuestos.{clave}.descripcion"]
        assert v["unidad"] == textos[f"unidades.{original['valores'][clave]['unidad']}"]
    canon = [h for h in cliente.get("/fuentes", params={"lang": "de"}).json()["facts"] if h.get("dimension") == "canon"]
    assert canon
    for h in canon:
        assert h["statement"] == textos[f"hechos.{h['id']}.statement"]
