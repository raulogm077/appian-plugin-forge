"""R-F08 de punta a punta: del dossier de la version anterior a la alarma.

Es la unica regla del sistema cuya factura la paga PRODUCCION —cambiar inputs
u outputs reutilizando la key rompe procesos vivos (auditoria §7.4)— y tenia
dos interruptores independientes, cada uno bastante para dejarla muda:

  1. Nadie poblaba `version_anterior`. El contrato no lo pedia, la SKILL no lo
     mencionaba y ningun fixture lo traia. Un bloque ausente se trataba como
     «no hay cambio» y pasaba en silencio.

  2. `generar_dossier` metia `key` DENTRO del objeto firma, mientras R-F08 lee
     `anterior.get("key")` como HERMANO de `firma`. Pegar la firma congelada
     del dossier —que la documentacion nombra como la unica fuente contra la
     que comparar— daba `None != key` y la regla callaba.

El test que de verdad cierra esto es el de ida y vuelta: se genera el dossier
de la v1, se saca de ahi el bloque que el propio dossier ofrece para pegar, se
pega en el contrato de la v2 y se comprueba que R-F08 salta. Si las dos
estructuras vuelven a divergir, ese test cae.
"""

import pathlib

import pytest

import contrato
import generar_dossier
import verificar_framework

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "contratos"


@pytest.fixture
def v1():
    return contrato.cargar(FIXTURES / "smart-service-minimo.md")


def _errores(datos, xml=""):
    return [h for h in verificar_framework.comprobar(datos, xml, []) if h.regla == "R-F08"]


# --- la estructura, que era el segundo interruptor -------------------------

def test_la_key_es_HERMANA_de_la_firma_no_hija(v1):
    """R-F08 lee `anterior["key"]`. Si la key vive dentro de `firma`, la
    comparacion es `None == "com.raul…"`, siempre falsa, y la regla calla.
    """
    congelada = generar_dossier.extraer_firma(v1)
    assert congelada["key"] == v1["plugin"]["key"]
    assert "firma" in congelada
    assert "key" not in congelada["firma"], "la key volvio a meterse dentro de la firma"
    assert congelada["firma"]["entradas"] == ["documentoOrigen:Long"]


def test_la_firma_congelada_encaja_donde_R_F08_la_busca(v1):
    """La forma que produce el dossier tiene que ser exactamente la que lee la
    regla, sin traduccion por medio.
    """
    v2 = {**v1, "entradas": [*v1["entradas"],
                             {"nombre": "motivo", "tipo_java": "String",
                              "required": "OPTIONAL", "descripcion": "Motivo"}]}
    v2["version_anterior"] = generar_dossier.extraer_firma(v1)
    assert _errores(v2), "R-F08 no salto pese a anadirse un input reutilizando la key"


# --- la ida y vuelta completa, que es la que importa -----------------------

def test_ida_y_vuelta_del_dossier_al_contrato(tmp_path, v1):
    """Del DOSSIER.md de la v1 al contrato de la v2, por el camino real: el
    bloque TOML que el propio dossier ofrece para pegar.

    El contrato es TOML y el dossier congelaba la firma solo en JSON, que no
    se puede pegar en un contrato. Era la otra mitad de por que nadie poblaba
    nunca `version_anterior`.
    """
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "contrato.md").write_text(
        (FIXTURES / "smart-service-minimo.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    generar_dossier.main_con_raiz(tmp_path)
    dossier = (tmp_path / "docs" / "DOSSIER.md").read_text(encoding="utf-8")

    # Se extrae tal cual, sin retocarlo: si hiciera falta editarlo a mano, la
    # regla seguiria dependiendo de que alguien no se equivoque.
    bloque = contrato.extraer_toml(dossier)
    assert "version_anterior" in bloque, "el dossier no ofrece un bloque pegable en el contrato"

    v2 = contrato.cargar(FIXTURES / "smart-service-minimo.md")
    v2["entradas"].append(
        {"nombre": "motivo", "tipo_java": "String", "required": "OPTIONAL", "descripcion": "M"}
    )
    v2["version_anterior"] = bloque["version_anterior"]

    assert _errores(v2), (
        "se anadio un input y se reutilizo la key, y R-F08 no dijo nada: es justo el cambio "
        "que rompe procesos vivos en produccion"
    )


# --- que no dispare cuando no debe ----------------------------------------

def test_no_salta_si_la_firma_no_cambio(v1):
    v2 = {**v1, "version_anterior": generar_dossier.extraer_firma(v1)}
    assert _errores(v2) == []


def test_no_salta_si_se_estrena_key(v1):
    """La correccion que la propia regla pide: clave nueva. Si siguiera
    saltando, empujaria a ignorarla.
    """
    v2 = {
        **v1,
        "plugin": {**v1["plugin"], "key": "com.raul.appian.archivar.v2"},
        "entradas": [],
        "version_anterior": generar_dossier.extraer_firma(v1),
    }
    assert _errores(v2) == []


def test_detecta_el_cambio_de_TIPO_con_el_mismo_nombre(v1):
    anterior = generar_dossier.extraer_firma(v1)
    v2 = {
        **v1,
        "entradas": [{**v1["entradas"][0], "tipo_java": "String"}],
        "version_anterior": anterior,
    }
    assert _errores(v2), "cambiar Long por String rompe los procesos vivos igual que anadir uno"


# --- la puerta determinista, sobre el bloque pegado ------------------------

@pytest.mark.parametrize(
    "malformado",
    [
        {"firma": {"entradas": [], "salidas": []}},                    # sin key
        {"key": "com.raul.appian.archivar"},                           # sin firma
        {"key": "com.raul.appian.archivar", "firma": {"entradas": []}},  # firma incompleta
    ],
)
def test_la_puerta_rechaza_una_version_anterior_malformada(v1, malformado):
    """Un `version_anterior` a medias es peor que ninguno: parece que hay
    linea base y no la hay, y la regla mas cara del sistema calla creyendo que
    comparo.
    """
    datos = {**v1, "version_anterior": malformado}
    faltantes = contrato.validar(datos)
    assert any("version_anterior" in f for f in faltantes), faltantes


def test_la_puerta_acepta_una_version_anterior_bien_formada(v1):
    datos = {**v1, "version_anterior": generar_dossier.extraer_firma(v1)}
    assert contrato.validar(datos) == []
