import pathlib
import shutil
import subprocess

import pytest

import classfile

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "java"


@pytest.fixture(scope="module")
def clase_compilada(tmp_path_factory):
    if shutil.which("javac") is None:
        pytest.skip("javac no esta en el PATH")
    destino = tmp_path_factory.mktemp("clases")
    subprocess.run(
        ["javac", "--release", "17", "-d", str(destino), str(FIXTURES / "Ejemplo.java")],
        check=True,
        capture_output=True,
    )
    return destino / "ejemplo" / "Ejemplo.class"


def test_lee_major_version_17(clase_compilada):
    leida = classfile.leer(clase_compilada)
    assert leida.major == 61


def test_lee_nombre_de_clase(clase_compilada):
    leida = classfile.leer(clase_compilada)
    assert leida.nombre_clase == "ejemplo.Ejemplo"


def test_detecta_tipo_referenciado_sin_import(clase_compilada):
    # Ejemplo.java usa java.util.ArrayList con nombre cualificado, sin import.
    leida = classfile.leer(clase_compilada)
    assert "java.util.ArrayList" in leida.tipos_referenciados


def test_detecta_tipo_solo_presente_en_descriptor(clase_compilada):
    # El tipo de retorno java.util.List aparece en el descriptor del metodo.
    leida = classfile.leer(clase_compilada)
    assert "java.util.List" in leida.tipos_referenciados


def test_recoge_cadenas_del_pool(clase_compilada):
    leida = classfile.leer(clase_compilada)
    assert "canario-en-el-pool" in leida.cadenas


def test_tipos_de_descriptor_extrae_varios():
    tipos = classfile.tipos_de_descriptor("(Ljava/lang/String;I)Ljava/util/List;")
    assert tipos == {"java.lang.String", "java.util.List"}


# --- C2: la clase interna, del `$` del bytecode al `.` del indice ---------
# El indice documentado guarda `SmartServiceException.Builder`, con punto, y
# NO tiene ni una sola entrada con `$` (906 tipos, cero con `$`). El bytecode
# escribe `SmartServiceException$Builder`. Conservar el `$` reportaba como
# «API no documentada» una linea que escribio el propio andamiador, sobre el
# 100 % de los smart services: el peor tipo de falso positivo, porque entrena
# a ignorar la unica puerta de superficie que hay.

INTERNA_BYTECODE = "com/appiancorp/suiteapi/process/exceptions/SmartServiceException$Builder"
INTERNA_INDICE = "com.appiancorp.suiteapi.process.exceptions.SmartServiceException.Builder"


def test_normalizar_traduce_el_dolar_de_la_clase_interna():
    assert classfile._normalizar(INTERNA_BYTECODE) == INTERNA_INDICE


def test_tipos_de_descriptor_tambien_traduce_el_dolar():
    # La otra via de entrada al mismo dato: los descriptores tienen el mismo
    # `$` y su propia conversion, asi que necesitan la misma correccion.
    assert classfile.tipos_de_descriptor(f"L{INTERNA_BYTECODE};") == {INTERNA_INDICE}


def test_la_forma_normalizada_es_la_que_el_indice_documenta():
    """Cierra el circulo: no basta con cambiar `$` por `.`, tiene que dar
    exactamente la cadena que el indice congelado contiene.
    """
    import json

    indice = json.loads(
        (pathlib.Path(__file__).resolve().parents[1] / "assets" / "indice-tipos-26.3.json")
        .read_text(encoding="utf-8")
    )
    tipos = set(indice["tipos"])
    assert classfile._normalizar(INTERNA_BYTECODE) in tipos
    assert not [t for t in tipos if "$" in t], "el indice no guarda ninguna forma con `$`"


def test_long_y_double_ocupan_dos_slots(clase_compilada):
    # Si el lector no saltara el slot extra de LONG/DOUBLE, el pool se
    # desalinearia y el nombre de clase saldria mal.
    leida = classfile.leer(clase_compilada)
    assert leida.nombre_clase == "ejemplo.Ejemplo"
    assert leida.metodos
