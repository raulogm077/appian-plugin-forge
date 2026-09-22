import pathlib
import re
import xml.etree.ElementTree as ET

import pytest

import andamiar
import contrato
import verificar_bundles as vb

CONTRATO = {
    "plugin": {
        "key": "com.raul.appian.ejemplo", "nombre": "Ejemplo", "version": "1.0.0",
        "paquete": "com.raul.appian.ejemplo", "tipo": "smart-service", "perfil": "estandar",
        "application_version_min": "23.2", "descripcion": "Hace algo",
    },
    "clase": {"nombre": "EjemploSmartService", "paleta": "Document Management"},
    "bundle": {"nombre": "ejemplo"},
    "entradas": [
        {"nombre": "documentoOrigen", "tipo_java": "Long", "required": "ALWAYS", "descripcion": "El documento"},
        {"nombre": "sufijo", "tipo_java": "String", "required": "OPTIONAL", "descripcion": "Un sufijo"},
    ],
    "salidas": [{"nombre": "resultado", "tipo_java": "Long", "descripcion": "El resultado"}],
    "capacidades": {},
}


def test_orden_solo_lleva_entradas_nunca_salidas():
    v = andamiar.construir_variables(CONTRATO)
    assert v["ORDEN_ENTRADAS"] == '"documentoOrigen", "sufijo"'
    assert "resultado" not in v["ORDEN_ENTRADAS"]


def test_setters_llevan_input_y_getters_no():
    v = andamiar.construir_variables(CONTRATO)
    assert "@Input(required = Required.ALWAYS)" in v["SETTERS"]
    assert "@Input(required = Required.OPTIONAL)" in v["SETTERS"]
    assert "@Input" not in v["GETTERS"]


def test_paleta_se_traduce_a_anotacion_de_conveniencia():
    v = andamiar.construir_variables(CONTRATO)
    assert v["ANOTACION_PALETA"].startswith("AutomationSmartServices")
    assert "PaletteInfo" not in v["ANOTACION_PALETA"]


def test_claves_de_bundle_usan_el_convenio_del_tipo():
    """La CLAVE es un identificador que Appian resuelve y el VALOR es texto
    para el disenador; son dos cosas distintas y cada una tiene su regla.

    La clave lleva el nombre del ACP --el del accesor, con su mayuscula
    inicial--: un `input.documentoOrigen` no lo lee nadie, porque el accesor es
    `setDocumentoOrigen`. El valor va partido por sus mayusculas, que es lo que
    Appian escribe cuando no encuentra la clave; poner el identificador crudo
    dejaba al disenador algo PEOR que no poner nada."""
    v = andamiar.construir_variables(CONTRATO)
    assert "input.DocumentoOrigen.displayName=Documento Origen" in v["CLAVES_ENTRADAS"]
    assert "input.DocumentoOrigen.comment=El documento" in v["CLAVES_ENTRADAS"]
    assert "smartservice." not in v["CLAVES_ENTRADAS"]


def test_marcador_sin_resolver_es_error():
    try:
        andamiar.sustituir("hola {{NO_EXISTE}}", {"OTRA": "x"})
    except ValueError as e:
        assert "NO_EXISTE" in str(e)
    else:
        raise AssertionError("deberia haber lanzado ValueError")


def test_los_cuatro_tipos_se_andamian_sin_marcadores_sin_resolver():
    """La prueba que faltaba: sustituir contra las plantillas REALES.

    Los tests de arriba solo miran el diccionario de variables, asi que no
    detectaban que tres de los cuatro tipos tenian marcadores sin variable. Este
    recorre las plantillas de verdad, que es donde se rompe.
    """
    import pathlib as _pl
    plantillas = _pl.Path(__file__).resolve().parents[1] / "assets" / "plantillas"
    for tipo, extra in (
        ("smart-service", {"clase": {"nombre": "S", "paleta": "Document Management"}}),
        ("function", {"clase": {"nombre": "F"}, "funcion": {"nombre": "f"}}),
        ("writer-function", {"clase": {"nombre": "W"}, "funcion": {"nombre": "w"}}),
        ("servlet", {"clase": {"nombre": "V"}}),
    ):
        datos = {**CONTRATO, "plugin": {**CONTRATO["plugin"], "tipo": tipo}, **extra}
        variables = andamiar.construir_variables(datos)
        tipo_recursos = "function" if tipo == "writer-function" else tipo
        for rel in (f"{tipo}/Clase.java.tmpl",
                    f"{tipo_recursos}/appian-plugin.xml.tmpl"):
            ruta = plantillas / rel
            if not ruta.is_file():
                raise AssertionError(f"falta la plantilla {rel} para el tipo {tipo}")
            # sustituir() lanza ValueError si queda algun marcador sin resolver.
            andamiar.sustituir(ruta.read_text(encoding="utf-8"), variables)


def test_perfil_estandar_no_incluye_bloque_riguroso():
    v = andamiar.construir_variables(CONTRATO)
    assert v["BLOQUE_PERFIL"] == ""
    assert v["PLUGINS_PERFIL"] == ""


def test_use_keywords_solo_si_la_version_lo_permite():
    fn = {**CONTRATO, "plugin": {**CONTRATO["plugin"], "tipo": "function",
                                  "application_version_min": "23.2"}}
    assert andamiar.construir_variables(fn)["ANOTACION_FUNCTION"] == "@Function"
    fn26 = {**CONTRATO, "plugin": {**CONTRATO["plugin"], "tipo": "function",
                                    "application_version_min": "26.1"}}
    assert "useKeywords" in andamiar.construir_variables(fn26)["ANOTACION_FUNCTION"]


# ---------------------------------------------------------------------------
# Lo de aqui abajo no viene del brief. Generar un plugin de verdad para cada
# tipo (Step 3 no lo hacia, solo probaba construir_variables() de forma
# aislada) descubrio cuatro fallos reales del codigo literal (ronda 1),
# confirmados antes de tocar nada ejecutando ese mismo codigo sin modificar
# contra las plantillas reales (evidencia primaria, no solo lectura). Tres de
# los cuatro (A, B, C) los redescubrio por su cuenta la revision de la tarea
# 11 y el brief se regenero con sus propias correcciones para A/B/C (ronda 2,
# ya incorporadas abajo); el cuarto (D) no lo cubre el brief regenerado --
# ver la nota en Fallo D.
#
#   A. function/writer-function no calculaban DESCRIPCION_ES ni
#      CLAVES_PARAMETROS_ES, que bundle_es_ES.properties.tmpl exige.
#      ValueError: marcadores sin resolver: ['CLAVES_PARAMETROS_ES', 'DESCRIPCION_ES']
#   B. writer-function no tiene appian-plugin.xml.tmpl ni bundles propios
#      (la tarea 11 solo crea Clase.java.tmpl para este tipo); generar()
#      los buscaba en writer-function/ y, al no existir, is_file() los
#      saltaba EN SILENCIO -- el plug-in salia sin manifiesto ni bundles y
#      generar() no lo senalaba como error.
#   C. servlet/Clase.java.tmpl y appian-plugin.xml.tmpl usan PARAMETRO y
#      URL_PATTERN, que nadie calculaba (y el contrato, tarea 2, no reserva
#      campos para ellos).
#      ValueError: marcadores sin resolver: ['PARAMETRO']
#   D. el fragmento RIGUROSO trae su propio {{PAQUETE_RAIZ}} (targetClasses/
#      targetTests). sustituir() es de una sola pasada -- re.sub no
#      reescanea el texto de reemplazo --, asi que ese marcador quedaba
#      literal DENTRO de BLOQUE_PERFIL y sustituir() lo rechazaba al
#      insertarlo en build.gradle.tmpl, aunque PAQUETE_RAIZ si estuviera en
#      el diccionario de variables.
#      ValueError: marcadores sin resolver: ['PAQUETE_RAIZ']
#
# Las cuatro se corrigieron dentro de andamiar.py (construir_variables()
# y generar()); nada de esto toca contrato.py ni las plantillas. El informe
# de la tarea 12 trae el detalle y como se reprodujo cada una, en las dos
# rondas.
# ---------------------------------------------------------------------------

PLANTILLAS = pathlib.Path(__file__).resolve().parents[1] / "assets" / "plantillas"

# `generar()` exige el contrato de origen (Critico 2 del gate de ciclo 1).
# CONTRATO y _contrato() construyen el dict a mano, sin fichero real en
# disco que copiar -- de ahi el texto de relleno en vez de una ruta.
CONTRATO_ORIGEN_DUMMY = "contrato de prueba (test_andamiar.py, sin fichero real en disco)"


def _contrato(tipo: str, perfil: str = "estandar") -> dict:
    return {
        "plugin": {
            "key": "com.raul.appian.ejemplo", "nombre": "Ejemplo", "version": "1.0.0",
            "paquete": "com.raul.appian.ejemplo", "tipo": tipo, "perfil": perfil,
            "application_version_min": "23.2", "descripcion": "Hace algo",
        },
        "clase": {"nombre": "EjemploClase", "paleta": "Document Management"},
        "bundle": {"nombre": "ejemplo"},
        "entradas": [
            {"nombre": "documentoOrigen", "tipo_java": "Long", "required": "ALWAYS",
             "descripcion": "El documento"},
        ],
        "salidas": [{"nombre": "resultado", "tipo_java": "Long", "descripcion": "El resultado"}],
        "capacidades": {},
    }


def _sin_marcadores(ruta: pathlib.Path) -> bool:
    return "{{" not in ruta.read_text(encoding="utf-8")


# --- Fallo A ---

def test_function_lleva_descripcion_es_y_claves_parametros_es():
    v = andamiar.construir_variables(_contrato("function"))
    assert v["DESCRIPCION_ES"] == v["DESCRIPCION"]
    assert v["CLAVES_PARAMETROS_ES"] == v["CLAVES_PARAMETROS"]


def test_writer_function_lleva_descripcion_es_y_claves_parametros_es():
    v = andamiar.construir_variables(_contrato("writer-function"))
    assert v["DESCRIPCION_ES"] == v["DESCRIPCION"]
    assert v["CLAVES_PARAMETROS_ES"] == v["CLAVES_PARAMETROS"]


def test_generar_function_no_deja_marcadores_sin_resolver(tmp_path):
    escritos = andamiar.generar(_contrato("function"), PLANTILLAS, tmp_path, CONTRATO_ORIGEN_DUMMY)
    assert escritos
    for ruta in escritos:
        if ruta.suffix in (".java", ".xml", ".properties", ".gradle"):
            assert _sin_marcadores(ruta), f"{ruta} deja marcadores sin resolver"


# --- Fallo B ---

def test_generar_writer_function_incluye_manifiesto_y_bundles(tmp_path):
    escritos = andamiar.generar(_contrato("writer-function"), PLANTILLAS, tmp_path, CONTRATO_ORIGEN_DUMMY)

    manifiesto = tmp_path / "src/main/resources/appian-plugin.xml"
    assert manifiesto in escritos
    assert manifiesto.is_file()
    bundle_en = tmp_path / "src/main/resources/com/raul/appian/ejemplo/ejemplo_en_US.properties"
    assert bundle_en in escritos

    # Coherencia: el manifiesto declara la MISMA clase, en el MISMO paquete
    # que el .java realmente generado -- no un paquete inventado por el
    # alias hacia las plantillas de function.
    java = tmp_path / "src/main/java/com/raul/appian/ejemplo/function/EjemploClase.java"
    assert java.is_file()
    assert "package com.raul.appian.ejemplo.function;" in java.read_text(encoding="utf-8")
    assert 'class="com.raul.appian.ejemplo.function.EjemploClase"' in manifiesto.read_text(encoding="utf-8")


# --- Fallo C ---
# Ronda 2: el brief regenerado simplifico la seccion [servlet] a solo
# URL_PATTERN y PARAMETRO -- PARAM_NAME/PARAM_VALUE ya no hacen falta porque
# la plantilla comento su <init-param> de ejemplo (mecanismo real, pero no
# todo servlet lo necesita). PARAMETRO tampoco deriva ya de la primera
# entrada: es un literal de relleno fijo salvo que el contrato lo declare.

def test_servlet_recibe_valores_de_relleno_deterministas():
    v = andamiar.construir_variables(_contrato("servlet"))
    assert v["PARAMETRO"] == "valor"
    assert v["URL_PATTERN"] == "/ejemplo"  # a partir de NOMBRE_ARTEFACTO


def test_servlet_seccion_opcional_del_contrato_tiene_prioridad():
    datos = _contrato("servlet")
    datos["servlet"] = {"url_pattern": "/mi-ruta", "parametro": "idPeticion"}
    v = andamiar.construir_variables(datos)
    assert v["URL_PATTERN"] == "/mi-ruta"
    assert v["PARAMETRO"] == "idPeticion"


def test_el_smart_service_USA_la_clave_de_error_que_su_bundle_declara(tmp_path):
    """Una clave horneada en el bundle y que nadie invoca es una promesa muerta.

    `error.unexpected` viaja en los dos locales **con su hueco `{0}`**, que solo
    tiene sentido si alguien le pasa el identificador de correlacion. La
    plantilla no la usaba: construia el `SmartServiceException` pelado y cableaba
    la frase en castellano, asi que un Appian en `_en_US` ensenaba espanol y la
    clave no la leia nadie. Lo encontro un agente revisor en la tanda E2E del
    20-sep-2026, sobre un smart-service recien andamiado y sin tocar — o sea que
    lo arrastraba TODO smart-service generado por este forge.

    `userMessage(String, Object...)` existe: comprobado con `javap` sobre
    `com.appian:appian-plug-in-sdk:26.3`, que es la fuente que manda la skill.
    """
    escritos = andamiar.generar(_contrato("smart-service"), PLANTILLAS, tmp_path, CONTRATO_ORIGEN_DUMMY)
    assert escritos

    # Por el sufijo de locale, no por `.properties` a secas: el wrapper de
    # Gradle tambien acaba en `.properties` y colarlo aqui pondria el aserto de
    # paridad en rojo por un fichero que no es un bundle.
    bundles = [r for r in escritos if "_en_US" in r.name or "_es_ES" in r.name]
    assert bundles, "el smart-service dejo de llevar bundle: el aserto de abajo no mediria nada"
    declarantes = [
        r for r in bundles if "error.unexpected" in r.read_text(encoding="utf-8")
    ]
    assert len(declarantes) == len(bundles), (
        "algun locale dejo de declarar `error.unexpected`: "
        f"la declaran {[r.name for r in declarantes]} de {[r.name for r in bundles]}"
    )

    java = [r for r in escritos if r.suffix == ".java"]
    assert java, "no se genero ninguna clase java"
    fuente = "\n".join(r.read_text(encoding="utf-8") for r in java)
    assert '.userMessage("error.unexpected"' in fuente, (
        "el smart-service andamiado vuelve a no usar `error.unexpected`: la clave viaja en los "
        "dos bundles con su hueco {0} y no la invoca nadie"
    )
    assert "Se produjo un error" not in fuente, (
        "vuelve a haber una frase de error cableada en castellano en la plantilla: en un Appian "
        "con locale `_en_US` se veria en espanol, que es justo lo que el bundle existe para evitar"
    )


def test_generar_servlet_no_deja_marcadores_sin_resolver(tmp_path):
    escritos = andamiar.generar(_contrato("servlet"), PLANTILLAS, tmp_path, CONTRATO_ORIGEN_DUMMY)
    assert escritos
    for ruta in escritos:
        if ruta.suffix in (".java", ".xml"):
            assert _sin_marcadores(ruta), f"{ruta} deja marcadores sin resolver"
    manifiesto = tmp_path / "src/main/resources/appian-plugin.xml"
    ET.fromstring(manifiesto.read_text(encoding="utf-8"))


# --- Fallo D ---
# El brief regenerado (ronda 2) NO corrige este: su bloque `if riguroso:` es
# byte a byte el original, y su test nuevo nunca pasa perfil="riguroso", asi
# que no podia verlo. Mantengo la correccion de la ronda 1 con su evidencia
# (ValueError: ['PAQUETE_RAIZ'] ejecutando el codigo sin modificar) -- ver
# PREOCUPACIONES en el informe.

def test_bloque_perfil_riguroso_no_deja_paquete_raiz_sin_resolver():
    v = andamiar.construir_variables(_contrato("smart-service", perfil="riguroso"))
    assert "{{" not in v["BLOQUE_PERFIL"]
    assert "com.raul.appian.ejemplo" in v["BLOQUE_PERFIL"]


def test_perfil_riguroso_produce_bloques_completos_y_sin_marcadores():
    """La ruta que el test del brief regenerado no ejercita nunca (nunca pasa
    perfil="riguroso"), y por eso no podia atrapar el Fallo D. Pedida por el
    equipo tras la ronda 2: sin esta, la unica evidencia de la correccion
    vivia en un informe, no en la suite.

    Verificada con desactivar-y-ver-rojo: quitando `sustituir(texto, v)` del
    bloque `if riguroso:` de andamiar.py este test falla con
    `AssertionError: assert '{{' not in ...` (BLOQUE_PERFIL trae
    '{{PAQUETE_RAIZ}}' litera); restaurando la linea, vuelve a pasar.
    """
    v = andamiar.construir_variables(_contrato("smart-service", perfil="riguroso"))

    assert v["BLOQUE_PERFIL"] != ""
    assert "{{" not in v["BLOQUE_PERFIL"]
    assert "}}" not in v["BLOQUE_PERFIL"]

    assert v["PLUGINS_PERFIL"] != ""
    assert "{{" not in v["PLUGINS_PERFIL"]
    assert "}}" not in v["PLUGINS_PERFIL"]


def test_generar_smart_service_riguroso_no_falla(tmp_path):
    escritos = andamiar.generar(
        _contrato("smart-service", perfil="riguroso"), PLANTILLAS, tmp_path, CONTRATO_ORIGEN_DUMMY
    )
    build_gradle = tmp_path / "build.gradle"
    assert build_gradle in escritos
    contenido = build_gradle.read_text(encoding="utf-8")
    assert "{{" not in contenido

    # "Sale completo": ni el fragmento PLUGINS_PERFIL (dentro del bloque
    # plugins {}) ni el resto del perfil riguroso (los cinco bloques que trae
    # perfil-riguroso.gradle.tmpl) se quedan a medias al recomponerlos.
    assert "id 'info.solidsoft.pitest'" in contenido
    assert "dependencyLocking" in contenido
    assert "jacocoTestCoverageVerification" in contenido
    assert "pitest {" in contenido
    assert "tasks.register('mutationTest')" in contenido
    assert "tasks.register('verificarRevisionGit')" in contenido
    assert "tasks.register('releaseCheck')" in contenido
    # Contenido comun, para confirmar que lo riguroso no reemplaza el resto
    # del fichero -- solo se le añade a continuacion.
    assert "compileOnly 'com.appian:appian-plug-in-sdk:26.3'" in contenido


# ---------------------------------------------------------------------------
# Ronda 2, cambio de diseno pedido explicitamente (no es un fallo que yo
# encontrara): una plantilla mapeada que falta ya NO se salta en silencio
# (`continue`) -- es lo que escondia el Fallo B -- sino que generar() lanza
# FileNotFoundError. Nada en la ronda 1 fijaba este comportamiento.
# ---------------------------------------------------------------------------

def test_generar_lanza_si_falta_una_plantilla_mapeada(tmp_path):
    dir_plantillas_vacio = tmp_path / "plantillas-vacias"
    dir_plantillas_vacio.mkdir()
    with pytest.raises(FileNotFoundError):
        andamiar.generar(
            _contrato("smart-service"), dir_plantillas_vacio, tmp_path / "salida", CONTRATO_ORIGEN_DUMMY
        )


# ---------------------------------------------------------------------------
# Prueba de integracion: genera un plugin de verdad por cada tipo/perfil
# soportado en Fase 1 y comprueba (a) cero marcadores sin resolver en NINGUN
# fichero de texto, (b) appian-plugin.xml parsea como XML bien formado, (c)
# el .java generado es sintacticamente plausible.
# ---------------------------------------------------------------------------

CASOS_INTEGRACION = [
    ("smart-service", "estandar"),
    ("smart-service", "riguroso"),
    ("function", "estandar"),
    ("writer-function", "estandar"),
    ("servlet", "estandar"),
]


@pytest.mark.parametrize("tipo,perfil", CASOS_INTEGRACION)
def test_generar_plugin_real_sin_marcadores_y_bien_formado(tmp_path, tipo, perfil):
    escritos = andamiar.generar(_contrato(tipo, perfil=perfil), PLANTILLAS, tmp_path, CONTRATO_ORIGEN_DUMMY)
    assert escritos

    manifiesto = tmp_path / "src/main/resources/appian-plugin.xml"
    assert manifiesto.is_file()
    raiz_xml = ET.fromstring(manifiesto.read_text(encoding="utf-8"))
    assert raiz_xml.tag == "appian-plugin"

    ficheros_java = [r for r in escritos if r.suffix == ".java"]
    assert ficheros_java
    for java in ficheros_java:
        texto = java.read_text(encoding="utf-8")
        assert "{{" not in texto and "}}" not in texto
        assert texto.count("{") == texto.count("}")
        assert texto.count("(") == texto.count(")")
        assert texto.startswith("package ")

    for ruta in escritos:
        es_texto = ruta.suffix in (".java", ".xml", ".properties", ".gradle") or ruta.name in (
            ".gitignore", ".gitattributes",
        )
        if es_texto:
            assert _sin_marcadores(ruta), f"{ruta} deja marcadores {{...}} sin resolver"


# ---------------------------------------------------------------------------
# Critico 1 del gate de ciclo 1: el cuerpo de ejecutar() lee cada entrada y
# escribe cada salida propia con un placeholder no nulo, para que SpotBugs no
# marque UwF/UrF sobre el stub de un smart-service recien andamiado. El
# `throw` que hace el fallo ruidoso se queda FIJO en la plantilla (no se
# genera): ver assets/plantillas/smart-service/Clase.java.tmpl.
# ---------------------------------------------------------------------------

_CONTRATO_CUERPO_EJECUTAR = {
    "plugin": {
        "key": "com.raul.appian.ejemplo", "nombre": "Ejemplo", "version": "1.0.0",
        "paquete": "com.raul.appian.ejemplo", "tipo": "smart-service", "perfil": "estandar",
        "application_version_min": "23.2", "descripcion": "Hace algo",
    },
    "clase": {"nombre": "EjemploSmartService", "paleta": "Document Management"},
    "bundle": {"nombre": "ejemplo"},
    "entradas": [
        {"nombre": "documentoOrigen", "tipo_java": "Long", "required": "ALWAYS", "descripcion": "x"},
        {"nombre": "sufijo", "tipo_java": "String", "required": "OPTIONAL", "descripcion": "x"},
    ],
    "salidas": [
        {"nombre": "documentoResultado", "tipo_java": "Long", "descripcion": "x"},
        # Horneada (mismo nombre y tipo que SALIDAS_HORNEADAS): NO debe
        # aparecer en CUERPO_EJECUTAR -- la maneja run() en la plantilla.
        {"nombre": "ErrorOccurred", "tipo_java": "Boolean", "descripcion": "x"},
    ],
    "capacidades": {},
}


def test_cuerpo_ejecutar_lee_cada_entrada_y_escribe_cada_salida_propia():
    cuerpo = andamiar.construir_variables(_CONTRATO_CUERPO_EJECUTAR)["CUERPO_EJECUTAR"]
    assert "this.documentoResultado = 0L;" in cuerpo
    assert "errorOccurred" not in cuerpo, "la salida horneada no se toca aqui: la maneja run()"


def test_solo_las_entradas_ALWAYS_se_exigen_no_nulas():
    """Una entrada OPTIONAL puede llegar nula POR CONTRATO.

    Exigirla con `requireNonNull` --que es lo que hacia el andamiador para
    TODAS las entradas-- convierte el stub en un NullPointerException dentro
    de Appian en vez del `throw` de «sin implementar» que la plantilla pone a
    proposito: el fallo aparece lejos de su causa y disfrazado de otra cosa.
    """
    cuerpo = andamiar.construir_variables(_CONTRATO_CUERPO_EJECUTAR)["CUERPO_EJECUTAR"]
    assert 'requireNonNull(documentoOrigen, "documentoOrigen")' in cuerpo
    assert "requireNonNull(sufijo" not in cuerpo, (
        "`sufijo` es OPTIONAL: exigirla no nula contradice el contrato"
    )
    assert cuerpo.count("java.util.Objects.requireNonNull(") == 1


def test_una_entrada_opcional_se_sigue_leyendo_y_sin_registrar_su_valor():
    """Dos condiciones a la vez, y las dos importan.

    Leerla: si no, SpotBugs marca UrF sobre el campo y el build no pasa --que
    es justo el motivo por el que estas lineas existen (Critico 1 del ciclo 1)--.
    No registrar su VALOR: esta clase evita a proposito que ningun dato del
    usuario llegue al log, y el contrato puede declarar `datos_personales`.
    """
    cuerpo = andamiar.construir_variables(_CONTRATO_CUERPO_EJECUTAR)["CUERPO_EJECUTAR"]
    assert "sufijo == null" in cuerpo, "la entrada opcional tiene que LEERSE"
    assert 'LOG.debug("entrada opcional sin valor: sufijo")' in cuerpo
    assert '+ sufijo' not in cuerpo and 'sufijo)' not in cuerpo.replace("(sufijo == null)", ""), (
        "el valor de la entrada no puede llegar al log"
    )


def test_cuerpo_ejecutar_no_escribe_null_ni_deja_marcadores():
    """Lo que SpotBugs marca (UWF_NULL_FIELD) es un campo ASIGNADO a null.

    La comprobacion era `"null" not in cuerpo`, un proxy mas ancho que su
    propia intencion: tambien prohibia COMPARAR contra null, que es como se
    lee una entrada OPTIONAL sin exigirla. Se acota a la asignacion, que es
    lo que el mensaje decia desde el principio.
    """
    cuerpo = andamiar.construir_variables(_CONTRATO_CUERPO_EJECUTAR)["CUERPO_EJECUTAR"]
    asignaciones_a_null = [
        l for l in cuerpo.splitlines() if "=" in l and l.split("=", 1)[1].strip().rstrip(";") == "null"
    ]
    assert not asignaciones_a_null, (
        f"SpotBugs marca UWF_NULL_FIELD sobre un campo solo escrito a null: {asignaciones_a_null}"
    )
    assert "{{" not in cuerpo


def test_ejecutar_generado_mantiene_el_throw_fijo_tras_el_cuerpo():
    """Extremo a extremo dentro de lo que la suite rapida puede sin Gradle:
    sustituir() resuelve CUERPO_EJECUTAR sobre la plantilla REAL (no solo
    sobre el diccionario de variables) y el `throw` fijo sigue siendo la
    ULTIMA sentencia -- si fuera antes, el metodo saldria del stub sin haber
    tocado los campos que vienen despues. Usa sustituir() directamente, no
    generar(): esta comprobacion es de la plantilla de smart-service, no del
    escritor de ficheros (que tiene su propio contrato, ver Critico 2).
    """
    variables = andamiar.construir_variables(_CONTRATO_CUERPO_EJECUTAR)
    plantilla = (PLANTILLAS / "smart-service" / "Clase.java.tmpl").read_text(encoding="utf-8")
    texto = andamiar.sustituir(plantilla, variables)
    idx_asignacion = texto.index("this.documentoResultado = 0L;")
    idx_throw = texto.index(
        'throw new UnsupportedOperationException("ejecutar() sin implementar: ver docs/contrato.md");'
    )
    assert idx_asignacion < idx_throw


def test_construir_variables_falla_ruidoso_si_una_salida_no_tiene_placeholder():
    """La contraparte de `contrato.placeholder_no_nulo(...) is None`: quien
    llama (aqui) falla RUIDOSO -- no escribe `null` ni inventa un
    constructor para un tipo cualificado que no conoce.
    """
    datos = {**_CONTRATO_CUERPO_EJECUTAR, "salidas": [
        {"nombre": "cosa", "tipo_java": "com.raul.dominio.Cosa", "descripcion": "x"},
    ]}
    with pytest.raises(ValueError, match="placeholder"):
        andamiar.construir_variables(datos)


# ---------------------------------------------------------------------------
# Critico 2 del gate de ciclo 1: generar() exige el contrato de origen (4o
# parametro, OBLIGATORIO) y escribe docs/contrato.md. La variante Path
# (copia literal byte a byte desde un fichero real) la prueba
# test_forma_minima.py, que si tiene un fixture en disco; aqui solo la
# variante `str`, que es la que puede probar este modulo.
# ---------------------------------------------------------------------------

def test_generar_escribe_docs_contrato_md_desde_texto(tmp_path):
    texto = 'contrato de prueba\n\n```toml\n[plugin]\ntipo = "smart-service"\n```\n'
    escritos = andamiar.generar(_contrato("smart-service"), PLANTILLAS, tmp_path, texto)
    destino = tmp_path / "docs" / "contrato.md"
    assert destino in escritos
    assert destino.read_text(encoding="utf-8") == texto


def test_generar_sin_contrato_origen_es_un_error_de_firma(tmp_path):
    """Obligatorio, no opcional: un parametro opcional recrearia el mismo
    hueco en silencio para quien lo omitiera (Critico 2). Omitirlo tiene que
    fallar en la LLAMADA (TypeError), no generar un proyecto sin
    docs/contrato.md.
    """
    with pytest.raises(TypeError):
        andamiar.generar(_contrato("function"), PLANTILLAS, tmp_path)


# ---------------------------------------------------------------------------
# El bundle traducido y R-B05: el forge no puede escribir un artefacto sobre el
# que su propio validador avisa.
# ---------------------------------------------------------------------------

def test_escapar_no_ascii_es_idempotente_y_sale_del_bmp():
    assert contrato.escapar_no_ascii("anexion") == "anexion"
    assert contrato.escapar_no_ascii("anexión") == "anexi\\u00f3n"
    # Ya escapado, no se vuelve a escapar: son seis caracteres ASCII.
    assert contrato.escapar_no_ascii("anexi\\u00f3n") == "anexi\\u00f3n"
    # Fuera del BMP va el par subrogado, que es lo que entiende Java; `ord()`
    # a secas daria un `ὠ0` de cinco digitos que ningun cargador acepta.
    assert contrato.escapar_no_ascii("\U0001F600") == "\\ud83d\\ude00"


def test_el_bundle_traducido_de_un_contrato_en_espanol_no_dispara_su_R_B05(tmp_path):
    """La prueba que faltaba: andamiar en español y pasarle su propio validador.

    Se afirma sobre el FICHERO ESCRITO, no sobre las variables. La primera
    version de este test miraba `v['CLAVES_ENTRADAS_ES']` y por eso daba verde
    sobre un arreglo incompleto: `plugin.nombre` llega al bundle por
    `{{NOMBRE}}`, que no era ninguna de las cuatro variables `*_ES`, y el
    fichero seguia saliendo con la tilde cruda. Un test a la altura del arreglo
    habria fallado; a la altura del defecto, no.

    Cuando esto se escribio, ningun fixture de contrato llevaba una sola tilde,
    y por eso el hueco sobrevivio a 435 tests. Sigue igual hoy: los cuatro
    minimos no llevan ninguna, y `test_forma_minima` exige justo lo contrario
    como suelo --el texto que ve el usuario nace en ingles--. El suelo real de
    ESTE escapado vive en otro test, `test_forma_minima.py`
    (`test_el_guardian_del_NO_ASCII_tiene_algo_QUE_morder`), sobre el
    comentario horneado en `_es_ES`; este test sigue inyectando sus propias
    tildes a proposito: depende de su propio dato, no del corpus.
    """
    datos = _contrato("smart-service")
    datos["plugin"]["nombre"] = "Lector de anexión"          # llega por {{NOMBRE}}
    datos["entradas"][0]["descripcion"] = "Validación básica"  # llega por {{CLAVES_ENTRADAS_ES}}
    escritos = andamiar.generar(datos, PLANTILLAS, tmp_path, CONTRATO_ORIGEN_DUMMY)

    traducido = next(p for p in escritos if p.name.endswith("_es_ES.properties"))
    contenido = traducido.read_text(encoding="utf-8")
    assert not vb.PATRON_NO_ASCII.search(contenido), contenido
    assert "Lector de anexi\\u00f3n" in contenido
    assert "Validaci\\u00f3n b\\u00e1sica" in contenido
    # El texto horneado de la plantilla tambien queda cubierto, venga escapado
    # de origen o no: el escapador es idempotente.
    assert "ejecuci\\u00f3n" in contenido

    # `en_US` se escapa TAMBIEN, y desde el ciclo 17 R-B05 tambien lo JUZGA: la
    # regla no tiene exencion de locale por ninguno de los dos lados.
    # Antes se le eximia con el argumento de que «escapar alli seria
    # empeorar lo que si se lee», y estaba del reves: es el locale del que
    # Appian saca los textos de display, o sea el unico cuyo mojibake veria un
    # usuario. El escapado es seguro lea quien lea el `.properties`
    # --`Properties.load` en ISO-8859-1 o `ResourceBundle` en UTF-8-- y el
    # plug-in de referencia aprobado en AppMarket no tiene un solo no-ASCII en
    # su `en_US`. Levantado por el gate del ciclo 16.
    por_defecto = next(p for p in escritos if p.name.endswith("_en_US.properties"))
    texto_en_US = por_defecto.read_text(encoding="utf-8")
    assert not vb.PATRON_NO_ASCII.search(texto_en_US), texto_en_US
    assert "Lector de anexi\\u00f3n" in texto_en_US


# ---------------------------------------------------------------------------
# REANDAMIAR SOBRE EL PROPIO PROYECTO
#
# El caso mas normal que hay --corregir el contrato de un proyecto ya generado
# y volver a andamiar apuntando a su propio `docs/contrato.md`-- moria con
# `shutil.SameFileError` y una traza, DESPUES de haber escrito los catorce
# ficheros de plantilla. El proyecto quedaba a medias y el mensaje no decia
# que hacer. Levantado por el gate del ciclo 11 como [menor]; se cierra en el
# 12 porque «menor» describe la gravedad del sintoma, no la del desenlace.
# ---------------------------------------------------------------------------


def test_reandamiar_con_el_contrato_DEL_PROPIO_DESTINO_no_revienta(tmp_path):
    """Origen y destino son el MISMO fichero: no hay nada que copiar, y el
    andamiador tiene que terminar igual.
    """
    destino = tmp_path / "proyecto"
    ruta_contrato = destino / "docs" / "contrato.md"
    ruta_contrato.parent.mkdir(parents=True)
    texto = "# Contrato\n\nprosa que una reserializacion perderia\n"
    ruta_contrato.write_text(texto, encoding="utf-8")

    escritos = andamiar.generar(_contrato("smart-service"), PLANTILLAS, destino, ruta_contrato)

    assert ruta_contrato in escritos, (
        "el contrato del destino dejo de figurar entre los ficheros que el andamiador "
        "promete: los cinco consumidores lo leen sin comprobar que exista"
    )
    # Y sigue ahi, intacto: el desenlace correcto de «ya esta donde tiene que
    # estar» es no tocarlo, no vaciarlo.
    assert ruta_contrato.read_text(encoding="utf-8") == texto
    for ruta in escritos:
        assert ruta.is_file(), f"{ruta} se declaro escrita pero no existe"


def test_el_contrato_de_FUERA_del_destino_se_sigue_copiando(tmp_path):
    """El control de la guarda de arriba. Atrapar `SameFileError` no puede
    convertirse en «no copiar nunca»: cuando el origen es otro fichero, la
    copia literal byte a byte sigue siendo obligatoria (Critico 2).
    """
    origen = tmp_path / "fuera" / "contrato.md"
    origen.parent.mkdir(parents=True)
    origen.write_bytes(b"# Contrato\n\ncon LF crudos\ny prosa\n")
    destino = tmp_path / "proyecto"

    escritos = andamiar.generar(_contrato("smart-service"), PLANTILLAS, destino, origen)

    copia = destino / "docs" / "contrato.md"
    assert copia in escritos
    assert copia.read_bytes() == origen.read_bytes()


def test_cada_compileOnly_tiene_su_testImplementation():
    """Gradle no propaga `compileOnly` al sourceSet de test.

    Las tres dependencias que el contenedor provee en runtime van
    `compileOnly` --para que el validador de empaquetado compruebe que no
    acaban en META-INF/lib-- y por eso cada una necesita ADEMAS su linea de
    test: sin ella, el primer test que toque el adaptador no compila, y el
    sintoma («package javax.servlet.http does not exist») aparece mucho despues
    del andamiaje, cuando ya nadie mira la plantilla. Le paso a la de servlet,
    la unica de las tres que se quedo sin par: medido en una prueba E2E el
    20-sep-2026, escribiendo el primer test del adaptador de un servlet.
    """
    plantilla = (pathlib.Path(__file__).resolve().parents[1]
                 / "assets" / "plantillas" / "comun" / "build.gradle.tmpl")
    texto = plantilla.read_text(encoding="utf-8")
    compile_only = set(re.findall(r"compileOnly\s+'([^']+)'", texto))
    de_test = set(re.findall(r"testImplementation\s+'([^']+)'", texto))
    assert compile_only, "la plantilla dejo de declarar compileOnly: este test ya no mira nada"
    sin_par = compile_only - de_test
    assert not sin_par, (
        f"{sorted(sin_par)} va en compileOnly y no en testImplementation: un test del "
        f"adaptador no compilara, y el error saldra lejos de aqui"
    )


def test_la_function_NO_hornea_una_clave_de_error_que_no_puede_usar(tmp_path):
    """El reverso del test de arriba: una clave muerta tambien es una promesa.

    `error.unexpected` viajaba tambien en los bundles de `function` (y de
    `writer-function`, que reusa los mismos), donde **no la puede leer nadie**:
    el unico canal del SDK que resuelve una clave de bundle es
    `SmartServiceException.userMessage(...)`, y del lado de expresion no hay
    equivalente. Comprobado sobre el JAR de `com.appian:appian-plug-in-sdk:26.3`:
    de sus 988 clases, `userMessage` solo aparece en `SmartServiceException` y
    en su `Builder`.

    Dos razones para vigilarlo: el bundle de una function es lo que Appian lee
    para pintar la ayuda de la funcion, y una clave con un hueco `{0}` que nadie
    rellena invita a copiarla a un sitio donde tampoco funcione.
    """
    for tipo in ("function", "writer-function"):
        escritos = andamiar.generar(_contrato(tipo), PLANTILLAS, tmp_path / tipo,
                                    CONTRATO_ORIGEN_DUMMY)
        bundles = [r for r in escritos if "_en_US" in r.name or "_es_ES" in r.name]
        assert bundles, f"{tipo} dejo de llevar bundle: el aserto de abajo no mediria nada"
        con_clave = [r.name for r in bundles
                     if "error.unexpected=" in r.read_text(encoding="utf-8")]
        assert not con_clave, (
            f"{tipo} vuelve a hornear `error.unexpected` en {con_clave}, y del lado de "
            f"expresion no hay `userMessage` que la lea: es boilerplate muerto"
        )


# ---------------------------------------------------------------------------
# La puerta que le faltaba al andamiaje.
#
# `andamiar.py` se describia como «sustitucion de variables: sale bien
# siempre», y no era verdad. Un contrato con la salida `errorOccurred` en
# minuscula genera una clase con el campo Y el getter duplicados --javac da
# «variable errorOccurred is already defined»-- y NO compila. La regla que lo
# diagnostica, `R-F03`, existia, con el mensaje exacto... en la capa 1A, que
# corre en el paso 5 y EXIGE clases compiladas. El defecto que la regla
# describe impide compilar, asi que la regla era inalcanzable justo donde
# hacia falta.
#
# La puerta es GENERICA --todo error de las reglas que solo leen el contrato--
# y estos dos tests la atan como generica: si alguien la estrechara a `R-F03`,
# el de `R-F08` se pondria rojo.
# ---------------------------------------------------------------------------

def _escribir_contrato(tmp_path, cuerpo_toml):
    ruta = tmp_path / "contrato.md"
    ruta.write_text(f"# Contrato\n\n```toml\n{cuerpo_toml}\n```\n", encoding="utf-8")
    return ruta


_BASE_SMART_SERVICE = """
[plugin]
key = "com.ensayo.puerta"
nombre = "Puerta"
version = "1.0.0"
paquete = "com.ensayo.puerta"
tipo = "smart-service"
perfil = "estandar"
application_version_min = "23.2"
descripcion = "Ejercita la puerta del andamiaje."

[clase]
nombre = "PuertaSmartService"
paleta = "Data Services"

[bundle]
nombre = "puerta"

[[entradas]]
nombre = "entrada"
tipo_java = "String"
required = "ALWAYS"
descripcion = "Una entrada."

[capacidades]
parsea_formatos_ajenos = false
sale_a_la_red = false
toca_credenciales = false
datos_personales = false

[confirmacion]
usuario_confirmo = true
"""


def test_el_andamiaje_se_niega_ante_una_salida_que_choca_con_la_plantilla(tmp_path, monkeypatch, capsys):
    """R-F03: `errorOccurred` en minuscula da un .java que no compila."""
    ruta = _escribir_contrato(tmp_path, _BASE_SMART_SERVICE + """
[[salidas]]
nombre = "errorOccurred"
tipo_java = "Boolean"
descripcion = "Choca con el miembro de la plantilla."
""")
    destino = tmp_path / "destino"
    monkeypatch.setattr("sys.argv", ["andamiar.py", str(ruta), str(destino)])
    assert andamiar.main() == 1
    salida = capsys.readouterr().out
    assert "R-F03" in salida
    assert not destino.exists(), "no se genera NADA cuando la puerta rechaza"


def test_el_andamiaje_se_niega_ante_una_firma_que_rompe_procesos_vivos(tmp_path, monkeypatch, capsys):
    """R-F08, y esta a proposito: la puerta es GENERICA, no una copia de R-F03.

    Estrecharla a una sola regla dejaria pasar la de peor consecuencia del
    sistema --reutilizar la key cambiando inputs rompe procesos EN MARCHA--.
    """
    ruta = _escribir_contrato(tmp_path, _BASE_SMART_SERVICE + """
[[salidas]]
nombre = "resultado"
tipo_java = "Long"
descripcion = "El resultado."

[version_anterior]
key = "com.ensayo.puerta"
version = "1.0.0"

[version_anterior.firma]
clase = "PuertaSmartService"
entradas = ["entrada:Long"]
salidas = ["resultado:Long"]
""")
    destino = tmp_path / "destino"
    monkeypatch.setattr("sys.argv", ["andamiar.py", str(ruta), str(destino)])
    assert andamiar.main() == 1
    assert "R-F08" in capsys.readouterr().out
    assert not destino.exists()


def test_la_puerta_del_andamiaje_deja_pasar_los_contratos_legitimos(tmp_path, monkeypatch):
    """El otro lado, que es el que evita que la puerta se vuelva un estorbo:
    los ocho contratos de `tests/fixtures/contratos` que la puerta determinista
    admite tienen que seguir andamiando."""
    fixtures = pathlib.Path(__file__).resolve().parent / "fixtures" / "contratos"
    admitidos = [f for f in sorted(fixtures.glob("*.md"))
                 if not contrato.validar(contrato.cargar(f))]
    assert admitidos, "el corpus de fixtures no puede estar vacio"
    for f in admitidos:
        datos = contrato.cargar(f)
        assert andamiar.errores_de_contrato(datos) == [], f"{f.name} no deberia abortar"
