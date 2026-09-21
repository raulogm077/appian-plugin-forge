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


def test_contrato_correcto_no_da_ningun_error():
    """Ni un error. El unico hallazgo admitido es el AVISO con el que R-F08
    declara que no ha podido comprobar la compatibilidad con una version
    desplegada, porque el contrato no declara ninguna: antes esa regla se
    saltaba en silencio, y un silencio se lee igual que un verde."""
    hallazgos = vf.comprobar(CONTRATO_BASE, XML_BASE, [])
    assert [h for h in hallazgos if h.severidad == "error"] == []
    assert {(h.regla, h.severidad) for h in hallazgos} == {("R-F08", "aviso")}


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
        str(tmp_path),
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


# --- R-F14 · que nadie apague la puerta para que el build pase --------------
#
# Los dos casos de abajo NO son hipoteticos: son lo que hicieron dos agentes
# distintos, en dos tipos de plug-in distintos, en las pruebas E2E del
# 19-sep-2026, cada uno por su cuenta y con el build en rojo delante.

GRADLE_SANO = """
spotbugs {
    ignoreFailures = false
    reportLevel = Confidence.valueOf('LOW')
}
"""

EXCLUDE_ANDAMIADO = """<?xml version="1.0" encoding="UTF-8"?>
<FindBugsFilter>
  <!-- ABIERTO, a proposito.
  <Match>
    <Class name="com.raul.appian.ejemplo.servlet.Ejemplo"/>
    <Bug pattern="SERVLET_PARAMETER"/>
  </Match>
  -->
</FindBugsFilter>
"""

EXCLUDE_CON_SECSP_ACTIVO = """<?xml version="1.0" encoding="UTF-8"?>
<FindBugsFilter>
  <Match>
    <Class name="com.raul.appian.ejemplo.servlet.Ejemplo"/>
    <Bug pattern="SECSP"/>
  </Match>
</FindBugsFilter>
"""


def test_un_reportLevel_relajado_no_pasa():
    gradle = GRADLE_SANO.replace("'LOW'", "'MEDIUM'")
    hallazgos = vf.comprobar_guardarrailes("smart-service", gradle, "", "")
    assert [h.regla for h in hallazgos] == ["R-F14"]
    assert "MEDIUM" in hallazgos[0].mensaje


def test_ignoreFailures_en_true_no_pasa():
    gradle = GRADLE_SANO.replace("ignoreFailures = false", "ignoreFailures = true")
    hallazgos = vf.comprobar_guardarrailes("smart-service", gradle, "", "")
    assert [h.regla for h in hallazgos] == ["R-F14"]


def test_un_build_gradle_sin_los_ajustes_tampoco_pasa():
    """Borrarlos apaga la puerta igual que cambiarlos, y mas discretamente."""
    hallazgos = vf.comprobar_guardarrailes("smart-service", "plugins { id 'java' }", "", "")
    assert {h.regla for h in hallazgos} == {"R-F14"}
    assert len(hallazgos) == 2  # uno por ajuste ausente


def test_el_andamiaje_recien_generado_pasa_la_regla():
    hallazgos = vf.comprobar_guardarrailes(
        "servlet", GRADLE_SANO, EXCLUDE_ANDAMIADO, ""
    )
    assert hallazgos == []


def test_activar_SECSP_sin_decidirlo_por_escrito_no_pasa():
    hallazgos = vf.comprobar_guardarrailes(
        "servlet", GRADLE_SANO, EXCLUDE_CON_SECSP_ACTIVO, "# Decisiones\n\nD1: usamos HMAC.\n"
    )
    assert [h.regla for h in hallazgos] == ["R-F14"]
    assert "SECSP" in hallazgos[0].mensaje


def test_activar_SECSP_habiendolo_decidido_por_escrito_si_pasa():
    """La exclusion es legitima; lo que no lo es es hacerla en silencio."""
    decisiones = (
        "# Decisiones\n\nD2: se excluye SECSP tras implementar `ejecutar()`: el valor se "
        "valida contra la firma HMAC y no llega a consulta, ruta ni comando.\n"
    )
    hallazgos = vf.comprobar_guardarrailes(
        "servlet", GRADLE_SANO, EXCLUDE_CON_SECSP_ACTIVO, decisiones
    )
    assert hallazgos == []


def test_TODA_exclusion_activa_hay_que_firmarla_sea_del_tipo_que_sea():
    """Este test decia antes lo contrario --«la regla solo aplica a
    servlets»-- y era justo el agujero: en cualquier otro tipo el
    `exclude.xml` ni se parseaba, asi que una exclusion añadida a mano en una
    function no la veia NADIE. El andamiaje solo deja la de SECSP comentada en
    servlets, pero el fichero existe en los cuatro tipos.
    """
    hallazgos = vf.comprobar_guardarrailes(
        "smart-service", GRADLE_SANO, EXCLUDE_CON_SECSP_ACTIVO, ""
    )
    assert [h.regla for h in hallazgos] == ["R-F14"]


def test_una_exclusion_QUE_NO_ES_LA_DEL_ANDAMIAJE_tampoco_pasa_gratis():
    """El caso real: el 20-sep un ejecutor añadio `THROWS` sobre una clase de
    dominio. Lo documento por su cuenta, asi que no hubo fallo — pero ninguna
    capa lo habria visto, porque la regla solo miraba SECSP/SERVLET_PARAMETER.
    """
    excluye_throws = EXCLUDE_CON_SECSP_ACTIVO.replace("SECSP", "THROWS")
    hallazgos = vf.comprobar_guardarrailes("function", GRADLE_SANO, excluye_throws, "")
    assert [h.regla for h in hallazgos] == ["R-F14"]
    assert "THROWS" in hallazgos[0].mensaje

    decidido = "# Decisiones\n\nD3: se excluye THROWS en el calculador: ...\n"
    assert vf.comprobar_guardarrailes("function", GRADLE_SANO, excluye_throws, decidido) == []


def test_firmar_UNA_exclusion_no_absuelve_a_las_DEMAS():
    """Suelo antivacuidad de la regla: antes bastaba con que `decisiones.md`
    mencionara cualquiera de las activas para que pasaran todas.
    """
    dos = EXCLUDE_CON_SECSP_ACTIVO.replace(
        '<Bug pattern="SECSP"/>', '<Bug pattern="SECSP"/><Bug pattern="THROWS"/>'
    )
    decisiones = "# Decisiones\n\nD2: se excluye SECSP porque el valor va firmado con HMAC.\n"
    hallazgos = vf.comprobar_guardarrailes("servlet", GRADLE_SANO, dos, decisiones)
    assert [h.regla for h in hallazgos] == ["R-F14"]
    assert "THROWS" in hallazgos[0].mensaje
    assert "SECSP" not in hallazgos[0].mensaje, "SECSP si estaba firmada: no debe reprocharse"


def test_un_Match_SIN_Bug_apaga_spotbugs_entero_y_se_dice():
    """El caso peor y el mas invisible: no excluye un patron, los silencia
    todos para lo que case. No tiene patron que nombrar, asi que el barrido de
    patrones no puede verlo ni aunque quisiera.
    """
    mudo = """<?xml version="1.0" encoding="UTF-8"?>
<FindBugsFilter>
  <Match>
    <Class name="com.raul.appian.ejemplo.dominio.Calculador"/>
  </Match>
</FindBugsFilter>
"""
    hallazgos = vf.comprobar_guardarrailes("function", GRADLE_SANO, mudo, "")
    assert [h.regla for h in hallazgos] == ["R-F14"]
    assert "<Match>" in hallazgos[0].mensaje


def test_un_exclude_xml_roto_se_dice_en_vez_de_tragarse():
    hallazgos = vf.comprobar_guardarrailes("servlet", GRADLE_SANO, "<FindBugsFilter>", "")
    assert [h.regla for h in hallazgos] == ["R-F14"]


def test_R_F14_viaja_dentro_de_comprobar_y_no_solo_suelta():
    """La costura: la regla puede existir y no estar enganchada a la puerta."""
    hallazgos = verificar_framework.comprobar(
        _contrato_minimo(), "", [clase(CLASE_R_F13, ["x"])],
        gradle=GRADLE_SANO.replace("'LOW'", "'HIGH'"),
    )
    assert "R-F14" in {h.regla for h in hallazgos}


def test_un_segundo_bloque_que_pisa_al_primero_tampoco_pasa():
    """Dejar el bloque bueno y anadir otro debajo es como se relaja una
    configuracion sin que el diff parezca que la relaja. Mirar solo la primera
    aparicion lo daba por bueno.
    """
    gradle = GRADLE_SANO + "\nspotbugsMain {\n    ignoreFailures = true\n}\n"
    hallazgos = vf.comprobar_guardarrailes("smart-service", gradle, "", "")
    assert [h.regla for h in hallazgos] == ["R-F14"]
    assert "true" in hallazgos[0].mensaje


def test_un_BOM_en_exclude_xml_se_dice_porque_SpotBugs_no_puede_leerlo():
    """El defecto vive en la DIVERGENCIA: Python tolera el BOM y SpotBugs no.

    Medido el 21-sep-2026 con Gradle sobre un proyecto real: SpotBugs dice
    «Unable to read filter ... Content is not allowed in prolog» y el build
    termina en BUILD SUCCESSFUL. El sentido del fallo es seguro --sin filtro no
    se excluye nada-- pero el sintoma no lo es: quien lo sufre ve hallazgos que
    creia excluidos y concluye que la herramienta esta rota. Paso de verdad: en
    una prueba E2E el ejecutor acabo lanzando `./gradlew build -x spotbugsMain`,
    o sea saltandose la puerta entera para rodear un BOM.

    En Windows sale solo: `Out-File` escribe UTF-8 CON BOM por defecto.
    """
    con_bom = "\ufeff" + EXCLUDE_CON_SECSP_ACTIVO
    decidido = "# Decisiones\n\nD2: se excluye SECSP, valor firmado con HMAC.\n"

    hallazgos = vf.comprobar_guardarrailes("servlet", GRADLE_SANO, con_bom, decidido)

    assert [h.regla for h in hallazgos] == ["R-F14"], (
        "un exclude.xml con BOM pasa en silencio: el validador lo lee y SpotBugs no"
    )
    assert "BOM" in hallazgos[0].mensaje
    assert "SIN BOM" in hallazgos[0].mensaje, "el mensaje tiene que decir como salir"


def test_el_BOM_no_impide_seguir_analizando_el_resto_del_fichero():
    """Suelo antivacuidad: el BOM se reporta Y se quita, para que las demas
    comprobaciones del fichero sigan corriendo. Si el hallazgo del BOM
    sustituyera al analisis, una exclusion sin firmar se escaparia detras de el.
    """
    con_bom = "\ufeff" + EXCLUDE_CON_SECSP_ACTIVO

    reglas = [h.regla for h in vf.comprobar_guardarrailes("servlet", GRADLE_SANO, con_bom, "")]

    assert len(reglas) == 2, f"esperaba BOM + exclusion sin firmar, salieron {reglas}"


# ─── R-F16 y R-F17 · lo que Appian resuelve del manifiesto al desplegar ───
#
# `javac` no lee el `appian-plugin.xml`. Un nombre de clase mal escrito ahi, o
# dos modulos con la misma key, llegan intactos hasta el servidor y fallan al
# cargar el modulo. R-F12 miraba el sentido contrario --que la clase DEL
# CONTRATO este declarada-- y solo una.

CLASE_DEL_XML = "com.raul.appian.ejemplo.smartservice.EjemploSmartService"


def test_R_F16_dispara_si_la_clase_del_manifiesto_no_esta_compilada():
    compiladas = [clase("com.raul.appian.ejemplo.smartservice.OtraCosa")]
    xml = XML_BASE.replace("EjemploSmartService", "EjemploSmartServic")
    hallazgos = vf.comprobar(CONTRATO_BASE, xml, compiladas)
    assert "R-F16" in reglas(hallazgos)
    assert any("EjemploSmartServic" in h.mensaje for h in hallazgos if h.regla == "R-F16")


def test_R_F16_no_dispara_cuando_la_clase_existe():
    assert "R-F16" not in reglas(vf.comprobar(CONTRATO_BASE, XML_BASE, [clase(CLASE_DEL_XML)]))


def test_R_F16_tambien_mira_las_clases_de_un_datatype():
    """Un `<datatype>` no es un modulo con bundle, pero sus `<class>` si las
    carga Appian por nombre."""
    xml = XML_BASE.replace(
        "</appian-plugin>",
        '  <datatype key="tipos" name="Tipos">'
        "<class>com.raul.appian.ejemplo.NoExiste</class></datatype></appian-plugin>",
    )
    hallazgos = vf.comprobar(CONTRATO_BASE, xml, [clase(CLASE_DEL_XML)])
    assert "R-F16" in reglas(hallazgos)
    assert any("NoExiste" in h.mensaje for h in hallazgos if h.regla == "R-F16")


def test_R_F16_calla_cuando_no_le_han_dado_clases():
    """Sin clases compiladas no se puede saber si la declarada existe. Callar
    aqui es correcto --la llamada unitaria de otra regla no fabrica clases-- y
    no abre un hueco: `main()` siempre las pasa, y R-J10 lo repite sobre el JAR.
    """
    xml = XML_BASE.replace("EjemploSmartService", "NoExisteEnNingunSitio")
    assert "R-F16" not in reglas(vf.comprobar(CONTRATO_BASE, xml, []))


def test_R_F17_dispara_con_dos_modulos_de_la_misma_key():
    xml = XML_BASE.replace(
        "</appian-plugin>",
        '  <smart-service name="Otro" key="ejemplo" class="com.raul.appian.ejemplo.Otro"/>'
        "</appian-plugin>",
    )
    hallazgos = vf.comprobar(CONTRATO_BASE, xml, [])
    assert "R-F17" in reglas(hallazgos)
    assert any("ejemplo" in h.mensaje for h in hallazgos if h.regla == "R-F17")


def test_R_F17_no_dispara_con_keys_distintas():
    xml = XML_BASE.replace(
        "</appian-plugin>",
        '  <smart-service name="Otro" key="otro" class="com.raul.appian.ejemplo.Otro"/>'
        "</appian-plugin>",
    )
    assert "R-F17" not in reglas(vf.comprobar(CONTRATO_BASE, xml, []))


# ─── R-F18, R-F19, R-F20 · mas cosas que solo fallan al desplegar ─────────


def _contrato_ss(entradas, salidas):
    return {**CONTRATO_BASE, "entradas": entradas, "salidas": salidas}


def test_R_F18_una_entrada_y_una_salida_con_el_mismo_nombre():
    """«Input and output names must be unique, or deployment fails.»"""
    datos = _contrato_ss([{"nombre": "doc", "tipo_java": "Long", "required": "ALWAYS",
                           "descripcion": "d"}],
                         [{"nombre": "doc", "tipo_java": "String", "descripcion": "r"}])
    assert "R-F18" in reglas(vf.comprobar(datos, XML_BASE, []))


def test_R_F18_dos_nombres_que_solo_difieren_en_la_caja():
    """javac los ve como dos campos distintos y el build pasa; Appian lee el
    nombre del ACCESOR, asi que para el son el mismo."""
    datos = _contrato_ss([{"nombre": "documento", "tipo_java": "Long", "required": "ALWAYS",
                           "descripcion": "d"},
                          {"nombre": "Documento", "tipo_java": "Long", "required": "ALWAYS",
                           "descripcion": "d"}],
                         [{"nombre": "resultado", "tipo_java": "String", "descripcion": "r"}])
    assert "R-F18" in reglas(vf.comprobar(datos, XML_BASE, []))


def test_una_salida_con_la_caja_cambiada_de_una_horneada_es_R_F03():
    """La plantilla escribe siempre `private Boolean errorOccurred;` y
    `getErrorOccurred()`. Un contrato que declare la salida `errorOccurred`
    --misma palabra, otra caja-- no se mapeaba sobre ese miembro, porque el
    emisor comparaba por nombre EXACTO: se emitia otra vez, y el `.java` salia
    con el campo y el getter DUPLICADOS. Reproducido andamiando un contrato
    real: «variable errorOccurred is already defined».

    Lo dice R-F03, que es la regla de las colisiones con lo horneado, con el
    nombre exacto que hay que escribir. R-F18 se aparta para no decir dos veces
    lo mismo con palabras distintas."""
    datos = _contrato_ss([{"nombre": "doc", "tipo_java": "Long", "required": "ALWAYS",
                           "descripcion": "d"}],
                         [{"nombre": "errorMessage", "tipo_java": "String", "descripcion": "r"}])
    hallazgos = vf.comprobar(datos, XML_BASE, [])
    assert "R-F03" in reglas(hallazgos)
    assert any("«ErrorMessage»" in h.mensaje for h in hallazgos if h.regla == "R-F03")
    assert "R-F18" not in reglas(hallazgos)


def test_una_salida_horneada_con_el_nombre_exacto_no_es_colision():
    """Con el nombre y el tipo correctos SI se mapea sobre el miembro
    horneado, y asi lo declara el plug-in aprobado del AppMarket."""
    datos = _contrato_ss([{"nombre": "doc", "tipo_java": "Long", "required": "ALWAYS",
                           "descripcion": "d"}],
                         [{"nombre": "ErrorMessage", "tipo_java": "String", "descripcion": "r"}])
    assert "R-F03" not in reglas(vf.comprobar(datos, XML_BASE, []))


def test_R_F18_no_dispara_con_nombres_distintos():
    assert "R-F18" not in reglas(vf.comprobar(CONTRATO_BASE, XML_BASE, []))


def test_R_F18_solo_aplica_a_smart_services():
    """Una function no tiene outputs: sus parametros son otra cosa."""
    datos = {**CONTRATO_BASE, "plugin": {**CONTRATO_BASE["plugin"], "tipo": "function"},
             "entradas": [{"nombre": "doc", "tipo_java": "Long", "descripcion": "d"}],
             "salidas": [{"nombre": "doc", "tipo_java": "String", "descripcion": "r"}]}
    assert "R-F18" not in reglas(vf.comprobar(datos, XML_BASE, []))


XML_CON_DATATYPE_ANTES = (
    '<appian-plugin key="com.raul.appian.ejemplo">'
    '<datatype key="tipos" name="Tipos"><class>com.raul.appian.ejemplo.T</class></datatype>'
    '<smart-service key="ejemplo" name="Ejemplo" '
    'class="com.raul.appian.ejemplo.smartservice.EjemploSmartService"/>'
    "</appian-plugin>"
)


def test_R_F19_datatype_declarado_despues_de_quien_lo_usa():
    """«each datatype module must be declared before the smart service or
    function that uses it». El orden de un XML no lo ve ninguna otra regla."""
    xml = (
        '<appian-plugin key="com.raul.appian.ejemplo">'
        '<smart-service key="ejemplo" name="Ejemplo" '
        'class="com.raul.appian.ejemplo.smartservice.EjemploSmartService"/>'
        '<datatype key="tipos" name="Tipos"><class>com.raul.appian.ejemplo.T</class></datatype>'
        "</appian-plugin>"
    )
    assert "R-F19" in reglas(vf.comprobar(CONTRATO_BASE, xml, []))


def test_R_F19_no_dispara_con_el_datatype_delante():
    assert "R-F19" not in reglas(vf.comprobar(CONTRATO_BASE, XML_CON_DATATYPE_ANTES, []))


def test_R_F19_no_dispara_sin_datatypes():
    assert "R-F19" not in reglas(vf.comprobar(CONTRATO_BASE, XML_BASE, []))


def test_R_F20_jakarta_xml_bind_no_lo_soporta_appian():
    """Compila, porque es el mismo paquete renombrado; el tipo no se registra
    al desplegar. «jakarta.xml.bind.annotation is not supported»."""
    clases = [clase("com.raul.appian.ejemplo.T")]
    clases[0].tipos_referenciados = {"jakarta.xml.bind.annotation.XmlType"}
    assert "R-F20" in reglas(vf.comprobar(CONTRATO_BASE, XML_BASE, clases))


def test_R_F20_javax_xml_bind_es_el_correcto():
    clases = [clase("com.raul.appian.ejemplo.T")]
    clases[0].tipos_referenciados = {"javax.xml.bind.annotation.XmlType"}
    assert "R-F20" not in reglas(vf.comprobar(CONTRATO_BASE, XML_BASE, clases))
