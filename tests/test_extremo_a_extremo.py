"""Prueba de extremo a extremo contra el proyecto de referencia.

El EML esta publicado en el AppMarket y su revision no pidio cambios, asi que
si nuestros validadores lo rechazan, la sospecha recae PRIMERO sobre el
validador. Nunca relajar una regla para que este fixture pase: investigar.

Y ese oraculo estaba puesto sin usarse. Las llamadas a la capa 1A pasaban la
lista de clases VACIA, asi que ninguna regla de bytecode se ejercitaba: el
fichero decia comprobar el plug-in aprobado y en realidad no miraba ni uno de
sus `.class`. Lo que costo es medible — el EML usa
`new SmartServiceException.Builder(getClass(), cause)`
(`ReadEmailFileSmartService.java:127`), y con el `$` de las clases internas sin
normalizar el escaner de superficie habria marcado un plug-in APROBADO POR
APPIAN como «referencia API no documentada». El defecto del Critical 2 estaba
delante del oraculo, y al oraculo le faltaba un solo paso para hablar.

Ese paso es este modulo: se cargan los `.class` REALES del plug-in aprobado y
se pasan por las reglas de bytecode.
"""

import pathlib

import pytest

import contrato
import verificar_appmarket
import verificar_bundles
import verificar_framework
import verificar_superficie

REFERENCIA = pathlib.Path(r"C:\Users\rgmoya\Documents\Plugin Read EML (Codex)")
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "contratos"
INDICE = pathlib.Path(__file__).resolve().parents[1] / "assets" / "indice-tipos-26.3.json"
CLASES_REFERENCIA = REFERENCIA / "build" / "classes" / "java" / "main"

pytestmark = pytest.mark.skipif(
    not REFERENCIA.is_dir(), reason="el proyecto de referencia no esta disponible"
)


@pytest.fixture(scope="module")
def datos():
    return contrato.cargar(FIXTURES / "eml-referencia.md")


@pytest.fixture(scope="module")
def clases():
    """Los `.class` REALES del plug-in aprobado, no una lista vacia.

    Sin esto, las llamadas de abajo pasaban `[]` y las reglas de bytecode no
    se ejercitaban jamas: el oraculo estaba puesto y nadie lo consultaba.
    """
    if not CLASES_REFERENCIA.is_dir():
        pytest.skip(
            f"el proyecto de referencia no esta compilado ({CLASES_REFERENCIA}); "
            f"ejecutar `./gradlew classes` alli"
        )
    cargadas = verificar_superficie.cargar_clases(CLASES_REFERENCIA)
    # Analizar cero clases no es verificar, y aqui menos que en ningun sitio:
    # todo el valor de este modulo es que las clases son las de verdad.
    assert cargadas, "no se cargo ninguna clase del proyecto de referencia"
    return cargadas


def test_el_contrato_de_referencia_esta_completo(datos):
    assert contrato.validar(datos) == []


def test_los_bundles_reales_del_eml_pasan_la_capa_1c(datos):
    raiz = REFERENCIA / "src" / "main" / "resources"
    bundles = {
        str(p.relative_to(raiz)).replace("\\", "/"): p.read_text(encoding="utf-8")
        for p in raiz.rglob("*.properties")
    }
    hallazgos = verificar_bundles.comprobar(datos, bundles)
    errores = [h for h in hallazgos if h.severidad == "error"]
    assert errores == [], f"el EML esta publicado y aprobado; revisar el validador: {errores}"


def test_el_manifiesto_real_del_eml_pasa_la_capa_1a(datos, clases):
    """Ahora con las clases REALES. Antes se llamaba con `[]` y las reglas que
    dependen del bytecode —R-F01, R-F01b, R-F05, R-F06, R-F07— no se
    ejercitaban.
    """
    xml = (REFERENCIA / "src" / "main" / "resources" / "appian-plugin.xml").read_text(
        encoding="utf-8"
    )
    hallazgos = verificar_framework.comprobar(datos, xml, clases)
    errores = [h for h in hallazgos if h.severidad == "error"]
    assert errores == [], f"el EML esta publicado y aprobado; revisar el validador: {errores}"


def test_las_politicas_de_appmarket_pasan_sobre_el_bytecode_real(datos, clases):
    hallazgos = verificar_appmarket.comprobar(
        clases, datos["plugin"]["tipo"], datos.get("capacidades", {})
    )
    errores = [h for h in hallazgos if h.severidad == "error"]
    assert errores == [], f"el EML esta publicado y aprobado; revisar el validador: {errores}"


def test_el_escaner_de_superficie_aprueba_el_plugin_APROBADO(datos, clases):
    """El test de regresion natural del Critical 2, y el que faltaba.

    El EML usa `new SmartServiceException.Builder(getClass(), cause)`. En el
    bytecode eso es `SmartServiceException$Builder`, y el indice documentado
    guarda la forma con punto: conservando el `$`, el escaner marcaba como
    «API no documentada» un plug-in que Appian aprobo sin pedir cambios.

    Verificado con desactivar-y-ver-rojo: devolviendo `_normalizar` a
    `.replace("/", ".")` sin tocar el `$`, este test falla con
    `com.appiancorp.suiteapi.process.exceptions.SmartServiceException$Builder`.
    """
    import json

    indice = json.loads(INDICE.read_text(encoding="utf-8"))
    informe = verificar_superficie.analizar(clases, indice)

    assert not informe.modo_degradado
    assert informe.no_documentados == [], (
        f"el escaner rechaza API de un plug-in APROBADO por Appian; la sospecha recae "
        f"PRIMERO sobre el validador: {informe.no_documentados}"
    )
    # Que el caso concreto esta de verdad presente: sin esto, el assert de
    # arriba podria pasar por vacuidad si el EML dejara de usar la clase
    # interna, y nadie se enteraria de que el test ya no prueba nada.
    assert "com.appiancorp.suiteapi.process.exceptions.SmartServiceException.Builder" in (
        informe.inventario
    ), "el EML ya no referencia la clase interna: este test dejo de cubrir el Critical 2"


def test_el_eml_no_usa_una_paleta_remapeada(datos, clases):
    """Sobre BYTECODE, no sobre el texto del `.java`.

    La version anterior buscaba cadenas en el fuente, y eso funciona solo
    porque el EML declara la paleta con `@PaletteInfo` y una cadena literal:
    es estructuralmente ciega a R-F01b. Si el plug-in usara una anotacion de
    conveniencia —lo que la documentacion oficial recomienda—, la cadena no
    aparaceria en ningun `.java` y la comprobacion pasaria igual sin haber
    mirado nada. R-F01b existe justo para ese caso, y solo se puede ver en el
    bytecode.
    """
    hallazgos = verificar_framework.comprobar(datos, "", clases)
    assert [h for h in hallazgos if h.regla == "R-F01"] == []

    cadenas = set()
    for c in clases:
        cadenas |= c.cadenas
    assert "Automation Smart Services" in cadenas
    assert "Appian Smart Services" not in cadenas
