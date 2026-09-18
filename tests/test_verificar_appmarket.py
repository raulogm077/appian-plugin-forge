import pathlib
import sys

import classfile
import verificar_appmarket as va

FIXTURES_CONTRATOS = pathlib.Path(__file__).resolve().parent / "fixtures" / "contratos"


def clase(nombre="com.raul.X", tipos=(), cadenas=(), metodos=()):
    return classfile.ClaseLeida(
        nombre_clase=nombre, major=61, tipos_referenciados=set(tipos),
        cadenas=set(cadenas), metodos=list(metodos),
    )


def reglas(hallazgos):
    return {h.regla for h in hallazgos}


def test_clase_limpia_no_da_hallazgos():
    assert va.comprobar([clase()], "smart-service", {}) == []


def test_service_locator_en_smart_service_es_error():
    c = clase(tipos={"com.appiancorp.suiteapi.common.ServiceLocator"})
    assert "R-A01" in reglas(va.comprobar([c], "smart-service", {}))


def test_service_locator_en_servlet_es_legitimo():
    # El ejemplo oficial de Appian lo usa dentro de doGet: la regla es
    # «no en constructores», no «nunca» (auditoria §3.2).
    c = clase(tipos={"com.appiancorp.suiteapi.common.ServiceLocator"})
    assert "R-A01" not in reglas(va.comprobar([c], "servlet", {}))


def test_system_out_es_error():
    c = clase(tipos={"java.lang.System"}, cadenas={"out"})
    assert "R-A02" in reglas(va.comprobar([c], "smart-service", {}))


def test_print_stack_trace_es_error():
    c = clase(metodos=[], cadenas={"printStackTrace"})
    assert "R-A03" in reglas(va.comprobar([c], "smart-service", {}))


def test_acceso_al_sistema_de_ficheros_es_error():
    c = clase(tipos={"java.io.FileOutputStream"})
    assert "R-A04" in reglas(va.comprobar([c], "smart-service", {}))


def test_set_property_es_error():
    c = clase(cadenas={"setProperty"}, tipos={"java.lang.System"})
    assert "R-A05" in reglas(va.comprobar([c], "smart-service", {}))


def test_reflexion_sobre_appiancorp_es_error():
    c = clase(cadenas={"com.appiancorp.suiteapi.content.ContentService"}, tipos={"java.lang.Class"})
    assert "R-A06" in reglas(va.comprobar([c], "smart-service", {}))


def test_red_sin_declararla_en_el_contrato_es_error():
    c = clase(tipos={"java.net.HttpURLConnection"})
    assert "R-A07" in reglas(va.comprobar([c], "smart-service", {"sale_a_la_red": False}))


def test_red_declarada_en_el_contrato_es_legitima():
    c = clase(tipos={"java.net.HttpURLConnection"})
    assert "R-A07" not in reglas(va.comprobar([c], "smart-service", {"sale_a_la_red": True}))


def test_credenciales_deben_ir_por_el_secure_credentials_store():
    c = clase(cadenas={"password=hunter2xyz"})
    assert "R-A08" in reglas(va.comprobar([c], "smart-service", {"toca_credenciales": True}))


def test_bytecode_debe_ser_major_61():
    c = classfile.ClaseLeida("com.raul.X", 52, set(), set(), [])
    assert "R-A09" in reglas(va.comprobar([c], "smart-service", {}))


def test_contexto_de_administrator_prohibido():
    # Politica de AppMarket que la spec lista y que no tenia ninguna regla.
    for senal in ("getAdministratorServiceContext", "getAdministratorUser"):
        c = clase(cadenas={senal})
        assert "R-A10" in reglas(va.comprobar([c], "smart-service", {}))


def test_una_clase_propia_llamada_service_locator_no_dispara_r_a01():
    # «Service Locator» es un nombre de patron corriente en Java: sin exigir el
    # prefijo de Appian, una clase propia disparaba la regla en falso.
    c = clase(tipos={"com.raul.util.DatabaseServiceLocator"})
    assert "R-A01" not in reglas(va.comprobar([c], "smart-service", {}))


def test_r_a08_salta_aunque_el_contrato_no_declare_credenciales():
    # R-A08 es incondicional a proposito: un secreto embebido lo es tanto si el
    # contrato declaro que toca credenciales como si no. El test hermano usaba
    # toca_credenciales=True y pasaba igual con {}, asi que no dejaba constancia.
    c = clase(cadenas={"password=hunter2xyz"})
    assert "R-A08" in reglas(va.comprobar([c], "smart-service", {}))
    assert "R-A08" in reglas(va.comprobar([c], "smart-service", {"toca_credenciales": False}))


def test_main_sin_clases_compiladas_devuelve_1(tmp_path, monkeypatch, capsys):
    # Mismo verde vacuo que se corrigio en verificar_superficie.main(): este
    # main() llama a verificar_superficie.cargar_clases() directamente, sin
    # pasar por aquella guarda, asi que analizar CERO clases seguia saliendo
    # en verde (codigo 0) sin haber comprobado ninguna de las diez politicas
    # -- ni siquiera R-A09, la del bytecode a major version 61.
    directorio_vacio = tmp_path / "build_classes"
    directorio_vacio.mkdir()
    contrato_valido = FIXTURES_CONTRATOS / "smart-service-completo.md"
    monkeypatch.setattr(
        sys, "argv", ["verificar_appmarket.py", str(contrato_valido), str(directorio_vacio)]
    )

    codigo_salida = va.main()

    assert codigo_salida == 1
    salida = capsys.readouterr().out
    assert "ERROR" in salida
    assert "cero" in salida.lower() or "ninguna clase" in salida.lower()
