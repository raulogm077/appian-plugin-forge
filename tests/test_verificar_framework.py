import pathlib
import sys

import pytest

import classfile
import contrato
import verificar_framework
import verificar_framework as vf

CONTRATO_BASE = {
    "plugin": {
        "key": "com.raul.appian.ejemplo",
        "nombre": "Ejemplo",
        "version": "1.0.0",
        "paquete": "com.raul.appian.ejemplo",
        "tipo": "smart-service",
        "perfil": "estandar",
        "application_version_min": "23.2",
    },
    "clase": {"nombre": "EjemploSmartService", "paleta": "Document Management"},
    "entradas": [{"nombre": "doc", "tipo_java": "Long", "required": "ALWAYS", "descripcion": "d"}],
    "salidas": [{"nombre": "resultado", "tipo_java": "String", "descripcion": "r"}],
    "capacidades": {},
}

XML_BASE = """<?xml version="1.0" encoding="UTF-8"?>
<appian-plugin name="Ejemplo" key="com.raul.appian.ejemplo">
  <plugin-info><version>1.0.0</version><application-version min="23.2"/></plugin-info>
  <smart-service name="Ejemplo" key="ejemplo" class="com.raul.appian.ejemplo.smartservice.EjemploSmartService"/>
</appian-plugin>
"""

def reglas(hallazgos):
    return {h.regla for h in hallazgos}


def clase(nombre, cadenas=(), metodos=()):
    return classfile.ClaseLeida(
        nombre_clase=nombre, major=61, tipos_referenciados=set(), cadenas=set(cadenas),
        metodos=list(metodos),
    )


def test_contrato_correcto_no_da_hallazgos():
    assert vf.comprobar(CONTRATO_BASE, XML_BASE, []) == []


def test_paleta_remapeada_en_silencio_es_error():
    datos = {**CONTRATO_BASE, "clase": {"nombre": "X", "paleta": "Document Management"}}
    clases = [clase("com.raul.X", cadenas={"Appian Smart Services"})]
    assert "R-F01" in reglas(vf.comprobar(datos, XML_BASE, clases))


def test_las_cuatro_paletas_validas_pasan():
    for valida in ("Workflow", "Automation Smart Services", "Deprecated Services", "#Deprecated#"):
        clases = [clase("com.raul.X", cadenas={valida})]
        assert "R-F01" not in reglas(vf.comprobar(CONTRATO_BASE, XML_BASE, clases))


def test_anotacion_de_paleta_insegura_es_error():
    # Quince de las treinta y dos anotaciones de conveniencia hornean una
    # categoria invalida, y la cadena horneada NO llega al bytecode del plug-in:
    # solo llega el nombre de la anotacion. Comprobado con javap sobre el SDK.
    for insegura in ("DocumentManagement", "Analytics", "Activities", "DataServices"):
        clases = [clase("com.raul.X",
                        cadenas={f"Lcom/appiancorp/suiteapi/process/palette/{insegura};"})]
        assert "R-F01" in reglas(vf.comprobar(CONTRATO_BASE, XML_BASE, clases)), insegura


def test_anotacion_de_paleta_segura_no_es_error():
    # Las 17 seguras: familia AutomationSmartServices*, familia Workflow*, y
    # ForumManagement, que fija «Deprecated Services» —valida—.
    for segura in ("AutomationSmartServicesDocumentManagement",
                   "AutomationSmartServicesIntegrationAPIs",
                   "WorkflowActivities", "ForumManagement"):
        clases = [clase("com.raul.X",
                        cadenas={f"Lcom/appiancorp/suiteapi/process/palette/{segura};"})]
        assert "R-F01" not in reglas(vf.comprobar(CONTRATO_BASE, XML_BASE, clases)), segura


def test_input_primitivo_debe_ser_always():
    datos = {**CONTRATO_BASE, "entradas": [
        {"nombre": "n", "tipo_java": "long", "required": "OPTIONAL", "descripcion": "d"}]}
    assert "R-F02" in reglas(vf.comprobar(datos, XML_BASE, []))


def test_nombres_de_entrada_y_salida_deben_ser_unicos():
    datos = {**CONTRATO_BASE,
             "entradas": [{"nombre": "x", "tipo_java": "String", "required": "ALWAYS", "descripcion": "d"}],
             "salidas": [{"nombre": "x", "tipo_java": "String", "descripcion": "r"}]}
    assert "R-F03" in reglas(vf.comprobar(datos, XML_BASE, []))


def test_tipo_no_inferible_es_error():
    datos = {**CONTRATO_BASE, "entradas": [
        {"nombre": "f", "tipo_java": "java.util.Date", "required": "ALWAYS", "descripcion": "d"}]}
    assert "R-F04" in reglas(vf.comprobar(datos, XML_BASE, []))


def test_use_keywords_exige_application_version_26_1():
    datos = {**CONTRATO_BASE, "plugin": {**CONTRATO_BASE["plugin"], "tipo": "function",
                                          "application_version_min": "23.2"}}
    clases = [clase("com.raul.F", cadenas={"useKeywords"})]
    assert "R-F05" in reglas(vf.comprobar(datos, XML_BASE, clases))


def test_metodos_sobrecargados_son_error():
    metodos = [classfile.MetodoLeido("procesar", "(Ljava/lang/String;)V", set()),
               classfile.MetodoLeido("procesar", "(I)V", set())]
    clases = [clase("com.raul.appian.ejemplo.F", metodos=metodos)]
    datos = {**CONTRATO_BASE, "plugin": {**CONTRATO_BASE["plugin"], "tipo": "function"}}
    assert "R-F06" in reglas(vf.comprobar(datos, XML_BASE, clases))


def test_new_initial_context_prohibido():
    clases = [clase("com.raul.X", cadenas={"javax/naming/InitialContext"})]
    assert "R-F07" in reglas(vf.comprobar(CONTRATO_BASE, XML_BASE, clases))


def test_cambio_de_firma_sin_clave_nueva_es_error():
    datos = {**CONTRATO_BASE, "version_anterior": {
        "key": "com.raul.appian.ejemplo",
        "firma": {"entradas": ["doc:Long", "extra:String"], "salidas": ["resultado:String"]}}}
    assert "R-F08" in reglas(vf.comprobar(datos, XML_BASE, []))


def test_misma_firma_con_misma_clave_no_es_error():
    datos = {**CONTRATO_BASE, "version_anterior": {
        "key": "com.raul.appian.ejemplo",
        "firma": {"entradas": ["doc:Long"], "salidas": ["resultado:String"]}}}
    assert "R-F08" not in reglas(vf.comprobar(datos, XML_BASE, []))


def test_cambiar_solo_el_tipo_de_un_input_tambien_dispara_r_f08():
    # Mismo nombre, tipo distinto: es un cambio de input a todos los efectos y
    # rompe igual los procesos vivos. Comparar solo nombres lo dejaba pasar.
    datos = {**CONTRATO_BASE, "version_anterior": {
        "key": "com.raul.appian.ejemplo",
        "firma": {"entradas": ["doc:String"], "salidas": ["resultado:String"]}}}
    assert "R-F08" in reglas(vf.comprobar(datos, XML_BASE, []))


def test_paquete_de_appian_esta_prohibido():
    # R-F10 no tenia ningun test que la disparase: red de regresion ausente.
    for prohibido in ("com.appiancorp.miplugin", "com.appian.miplugin"):
        datos = {**CONTRATO_BASE, "plugin": {**CONTRATO_BASE["plugin"], "paquete": prohibido}}
        assert "R-F10" in reglas(vf.comprobar(datos, XML_BASE, []))


def test_key_del_manifiesto_distinta_de_la_del_contrato_es_error():
    # R-F11 tampoco tenia test propio.
    xml = XML_BASE.replace('key="com.raul.appian.ejemplo"', 'key="com.otro.distinto"', 1)
    assert "R-F11" in reglas(vf.comprobar(CONTRATO_BASE, xml, []))


def test_xml_con_xmlns_es_aviso():
    xml = XML_BASE.replace("<appian-plugin ", '<appian-plugin xmlns="https://www.appian.com/plugins/v1" ')
    assert "R-F09" in reglas(vf.comprobar(CONTRATO_BASE, xml, []))


def test_clase_del_xml_debe_coincidir_con_el_contrato():
    xml = XML_BASE.replace("EjemploSmartService", "OtraClase")
    assert "R-F12" in reglas(vf.comprobar(CONTRATO_BASE, xml, []))


def test_main_sin_clases_compiladas_devuelve_1(tmp_path, monkeypatch, capsys):
    # Mismo verde vacuo que se corrigio en verificar_superficie: main() llama a
    # cargar_clases() directamente, sin pasar por la guarda de aquel main(), asi
    # que necesita la suya propia. Sin ella, analizar CERO clases no dispara
    # ninguna regla y la puerta sale en 0 (verde) sin haber comprobado nada.
    #
    # La key del contrato tiene que coincidir con la del manifiesto (la misma
    # que usa XML_BASE): si no coincidiera, dispararia R-F11 y el codigo SIN
    # CORREGIR devolveria 1 igualmente, por una razon ajena a esta guarda -- el
    # rojo dejaria de probar lo que dice probar.
    contrato_md = tmp_path / "contrato.md"
    contrato_md.write_text(
        '```toml\n[plugin]\nkey = "com.raul.appian.ejemplo"\n```\n', encoding="utf-8"
    )
    manifiesto_xml = tmp_path / "appian-plugin.xml"
    manifiesto_xml.write_text(XML_BASE, encoding="utf-8")
    directorio_vacio = tmp_path / "build_classes"
    directorio_vacio.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "verificar_framework.py", str(contrato_md), str(manifiesto_xml), str(directorio_vacio),
    ])

    codigo_salida = vf.main()

    assert codigo_salida == 1
    salida = capsys.readouterr().out
    assert "ERROR" in salida


# --- Important 3: R-F02 no estaba acotada por tipo ------------------------
# `Required` es del framework de proceso: no existe en una function, cuyos
# parametros no declaran `required` en absoluto. Sin acotar, R-F02 disparaba
# sobre TODO contrato de function con un parametro primitivo, exigiendole un
# `ALWAYS` que su plantilla no puede emitir.

def _contrato_function_con_primitivo():
    return {
        "plugin": {"key": "com.raul.appian.calc", "tipo": "function", "paquete": "com.raul.appian.calc",
                   "application_version_min": "26.1", "version": "1.0.0"},
        "clase": {"nombre": "CalcFunction"},
        "entradas": [{"nombre": "veces", "tipo_java": "int", "descripcion": "Repeticiones"}],
        "salidas": [],
    }


def test_R_F02_no_dispara_sobre_una_function():
    hallazgos = vf.comprobar(_contrato_function_con_primitivo(), "", [])
    assert [h for h in hallazgos if h.regla == "R-F02"] == [], (
        "R-F02 exige Required.ALWAYS en un tipo que no tiene Required"
    )


def test_R_F02_sigue_disparando_sobre_un_smart_service():
    datos = _contrato_function_con_primitivo()
    datos["plugin"]["tipo"] = "smart-service"
    datos["entradas"][0]["required"] = "OPTIONAL"
    hallazgos = vf.comprobar(datos, "", [])
    assert [h for h in hallazgos if h.regla == "R-F02"], "un primitivo OPTIONAL sigue siendo un fallo"


# --- R-F13: el andamiaje sin implementar no se certifica --------------------
# El agujero mas caro que ha tenido este sistema, y no hacia falta mala fe:
# proyecto recien andamiado + UN test trivial --el paso siguiente que pide la
# SKILL-- daba BUILD SUCCESSFUL y STATUS: READY_FOR_APPIAN_SUBMISSION sobre un
# plug-in cuyo `ejecutar()` solo lanzaba UnsupportedOperationException.
# Ninguna de las doce puertas anteriores miraba si el plug-in HACE algo.

CLASE_R_F13 = "com.raul.appian.ejemplo.Ejemplo"


def _contrato_minimo():
    return {
        "plugin": {"key": "com.raul.appian.ejemplo", "tipo": "smart-service",
                   "paquete": "com.raul.appian.ejemplo", "application_version_min": "23.2"},
        "clase": {"nombre": "Ejemplo"}, "entradas": [], "salidas": [],
    }


@pytest.mark.parametrize("marca", contrato.MARCAS_SIN_IMPLEMENTAR)
def test_R_F13_marca_el_cuerpo_del_andamiaje_de_cualquier_tipo(marca):
    """Las cuatro plantillas dejan su marca; las cuatro tienen que caer."""
    hallazgos = verificar_framework.comprobar(
        _contrato_minimo(), "", [clase(CLASE_R_F13, [marca])]
    )
    assert "R-F13" in {h.regla for h in hallazgos}, f"la marca «{marca}» no dispara R-F13"


def test_R_F13_no_dispara_sobre_un_plugin_implementado():
    """El caso negativo, que es el que hace util a la regla: un plug-in con
    logica de verdad no lleva la marca y no debe marcarse."""
    hallazgos = verificar_framework.comprobar(
        _contrato_minimo(), "",
        [clase(CLASE_R_F13, ["documentoOrigen", "resultado", "Error de lectura"])]
    )
    assert "R-F13" not in {h.regla for h in hallazgos}


def test_las_marcas_de_R_F13_son_las_que_las_plantillas_escriben_de_verdad():
    """La costura: si una plantilla cambiara su texto y la constante no, R-F13
    dejaria de disparar EN SILENCIO. Este test las ata a los ficheros reales.
    """
    plantillas = pathlib.Path(__file__).resolve().parents[1] / "assets" / "plantillas"
    fuentes = "\n".join(
        p.read_text(encoding="utf-8") for p in plantillas.rglob("Clase.java.tmpl")
    )
    for marca in contrato.MARCAS_SIN_IMPLEMENTAR:
        assert marca in fuentes, (
            f"la marca «{marca}» ya no la escribe ninguna plantilla: R-F13 no dispararia"
        )
    for linea in fuentes.splitlines():
        if "UnsupportedOperationException" in linea:
            assert any(m in linea for m in contrato.MARCAS_SIN_IMPLEMENTAR), (
                f"una plantilla lanza UnsupportedOperationException con un texto que R-F13 "
                f"no conoce: {linea.strip()}"
            )
