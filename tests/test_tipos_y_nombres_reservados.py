"""Important 7: el oraculo del repositorio no compilaba.

`eml-referencia.md` describe el plug-in publicado en el AppMarket y aprobado
por la revision real de Appian sin que el revisor pidiera cambios. Andamiarlo
y pasarle `javac` daba SEIS errores, y los dos motivos son fallos del
andamiaje, no del contrato:

  · `tipo_java` se emitia VERBATIM, asi que solo funcionaban los tipos de
    `java.lang`. Las nueve salidas `Timestamp` del EML salian sin import.

  · las salidas `ErrorOccurred` y `ErrorMessage` chocaban con los miembros que
    la plantilla de smart service ya hornea. R-F03 compara los nombres del
    contrato ENTRE SI, nunca contra los nombres reservados de la plantilla, asi
    que la colision no la veia nadie hasta `javac`.

La regla al corregirlo: el EML tiene que acabar en verde. Es el plug-in
aprobado — si nuestra regla lo rechaza, la equivocada es la regla.
"""

import pathlib
import shutil
import subprocess

import pytest

import andamiar
import contrato
import verificar_framework

RAIZ = pathlib.Path(__file__).resolve().parents[1]
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "contratos"
PLANTILLAS = RAIZ / "assets" / "plantillas"
CACHE = pathlib.Path.home() / ".gradle" / "caches" / "modules-2" / "files-2.1"


def _jar(grupo, artefacto):
    if not CACHE.is_dir():
        return None
    reales = [j for j in sorted((CACHE / grupo / artefacto).rglob("*.jar"))
              if not j.stem.endswith(("-sources", "-javadoc"))]
    return reales[0] if reales else None


SDK = _jar("com.appian", "appian-plug-in-sdk")
LOG4J = _jar("log4j", "log4j")


@pytest.fixture
def eml():
    return contrato.cargar(FIXTURES / "eml-referencia.md")


# --- tipos que no son de java.lang ----------------------------------------

@pytest.mark.parametrize(
    "declarado,emitido",
    [
        ("String", "String"),
        ("Long", "Long"),
        ("Boolean", "Boolean"),
        ("Timestamp", "java.sql.Timestamp"),
        ("Time", "java.sql.Time"),
        ("String[]", "String[]"),
        ("Timestamp[]", "java.sql.Timestamp[]"),
        ("com.raul.dominio.Cosa", "com.raul.dominio.Cosa"),
    ],
)
def test_el_tipo_declarado_se_resuelve_a_algo_que_javac_entiende(declarado, emitido):
    assert contrato.tipo_java_emitible(declarado) == emitido


def test_un_tipo_que_no_se_puede_emitir_lo_para_la_puerta():
    """Un tipo suelto que no es de java.lang y no viene cualificado no compila,
    y hasta ahora eso se descubria en `javac`, no en la puerta.
    """
    datos = contrato.cargar(FIXTURES / "smart-service-minimo.md")
    datos["entradas"][0]["tipo_java"] = "InputStream"
    faltantes = contrato.validar(datos)
    assert any("tipo_java" in f for f in faltantes), faltantes


# --- placeholder no nulo (Critico 1 del gate de ciclo 1) -------------------
#
# Mismos `emitido` que arriba (`test_el_tipo_declarado_se_resuelve_a_algo_
# que_javac_entiende`), menos "Long" y "com.raul.dominio.Cosa": el primero
# ya lo cubre smart-service-completo.md via el humo E2E, y el segundo tiene
# su propio test porque el resultado esperado es None, no un literal.

@pytest.mark.parametrize(
    "emitido,placeholder",
    [
        ("String", '""'),
        ("Boolean", "Boolean.FALSE"),
        ("java.sql.Timestamp", "new java.sql.Timestamp(0L)"),
        ("java.sql.Time", "new java.sql.Time(0L)"),
        ("String[]", "new String[0]"),
        ("java.sql.Timestamp[]", "new java.sql.Timestamp[0]"),
    ],
)
def test_placeholder_no_nulo_cubre_los_tipos_que_el_contrato_resuelve(emitido, placeholder):
    """Cada tipo que `tipo_java_emitible` puede devolver necesita un
    placeholder no nulo, o el cuerpo generado de `ejecutar()` no podria
    escribir esa salida sin usar `null` -- y SpotBugs marca UWF_NULL_FIELD
    sobre un campo solo escrito a null, tan roto para el build como no
    escribirlo en absoluto (UwF, el Critico 1 del gate de ciclo 1).
    """
    assert contrato.placeholder_no_nulo(emitido) == placeholder


def test_placeholder_no_nulo_no_inventa_para_un_tipo_cualificado_desconocido():
    """La contraparte: un tipo cualificado arbitrario (una CDT propia, por
    ejemplo) pasa `validar()` -- R-F04 y hermanas viven en las capas de
    verificacion, no aqui -- pero este modulo no conoce su constructor y no
    debe inventarlo. Documentado como hueco conocido en el informe del
    arreglo, no como un bug: `andamiar.construir_variables()` falla RUIDOSO
    (ValueError) si lo encuentra, en vez de escribir `null` o adivinar.
    """
    assert contrato.placeholder_no_nulo("com.raul.dominio.Cosa") is None


def test_placeholder_no_nulo_array_multidimensional_es_general():
    """Ningun fixture usa arrays multidimensionales hoy, pero la regla no
    depende de que exista un caso de uso real para ser correcta.
    """
    assert contrato.placeholder_no_nulo("String[][]") == "new String[0][]"


# --- nombres que la plantilla ya hornea -----------------------------------

def test_R_F03_ve_la_colision_con_los_nombres_de_la_plantilla(eml):
    """Con el TIPO equivocado, la salida NO puede mapearse sobre el miembro
    horneado y hay que decirlo: es una colision real.
    """
    datos = {**eml, "salidas": [
        {"nombre": "ErrorOccurred", "tipo_java": "String", "descripcion": "x"},
    ]}
    hallazgos = verificar_framework.comprobar(datos, "", [])
    assert [h for h in hallazgos if h.regla == "R-F03"], (
        "R-F03 compara los nombres del contrato entre si y no contra los reservados"
    )


def test_los_nombres_reservados_con_su_tipo_correcto_no_son_colision(eml):
    """Los del EML: `ErrorOccurred: Boolean` y `ErrorMessage: String` SON el
    contrato de error de la plantilla, no un choque. El plug-in aprobado los
    declara asi.
    """
    hallazgos = verificar_framework.comprobar(eml, "", [])
    assert [h for h in hallazgos if h.regla == "R-F03"] == []


def test_el_andamiador_no_duplica_los_miembros_horneados(eml):
    v = andamiar.construir_variables(eml)
    assert v["GETTERS"].count("getErrorOccurred") == 0
    assert v["GETTERS"].count("getErrorMessage") == 0
    assert "private Boolean ErrorOccurred;" not in v["CAMPOS_SALIDA"]


def test_las_claves_de_bundle_de_los_reservados_SI_se_emiten(eml):
    """Se salta el miembro Java, no la etiqueta: Appian sigue necesitando el
    displayName y el comment de esas dos salidas.
    """
    v = andamiar.construir_variables(eml)
    assert "output.ErrorOccurred.displayName" in v["CLAVES_SALIDAS"]
    assert "output.ErrorMessage.comment" in v["CLAVES_SALIDAS"]


# --- la prueba que zanja: el oraculo compila ------------------------------

@pytest.mark.skipif(shutil.which("javac") is None or SDK is None,
                    reason="hacen falta javac y el JAR del SDK")
def test_el_oraculo_del_AppMarket_se_andamia_y_COMPILA(tmp_path, eml):
    """Verificado en rojo: antes daba 6 errores de javac -- cuatro por los
    `Timestamp` sin resolver y dos por `getErrorOccurred`/`getErrorMessage`
    «already defined».
    """
    assert contrato.validar(eml) == []
    andamiar.generar(eml, PLANTILLAS, tmp_path / "proyecto", FIXTURES / "eml-referencia.md")

    fuentes = [str(p) for p in (tmp_path / "proyecto" / "src" / "main" / "java").rglob("*.java")]
    classpath = ";".join(str(j) for j in (SDK, LOG4J) if j is not None)
    proceso = subprocess.run(
        ["javac", "--release", "17", "-classpath", classpath,
         "-d", str(tmp_path / "clases"), *fuentes],
        capture_output=True, text=True,
    )
    assert proceso.returncode == 0, (
        f"el plug-in aprobado por Appian no compila al andamiarlo:\n{proceso.stderr}"
    )


# --- el identificador Java no es el nombre de Appian ----------------------
# Hallazgo de la verificacion final. Los nombres de input/output de Appian son
# PascalCase --asi los declara el plug-in aprobado-- y el andamiador los usaba
# VERBATIM como nombre del campo Java. SpotBugs marca `Nm` en cada uno («should
# be lowerCamelCase») y `./gradlew build` no llega a BUILD SUCCESSFUL: 27
# hallazgos sobre el oraculo.
#
# El plug-in aprobado lo resuelve separando las dos cosas, y es la unica forma
# que funciona: Appian ve el nombre a traves del ACCESOR
# (`getSourceDocument()` -> output `SourceDocument`), no del campo. Comprobado
# en `ReadEmailFileSmartService.java`:
#     private Long sourceDocument;                     <- campo, lowerCamelCase
#     public void setSourceDocument(Long sourceDocument)
#     @Order({"SourceDocument", ...})                  <- nombre de Appian
#     input.SourceDocument.displayName=...             <- nombre de Appian

def test_el_campo_java_es_lowerCamelCase_y_el_accesor_conserva_el_nombre(eml):
    v = andamiar.construir_variables(eml)
    assert "private Long sourceDocument;" in v["CAMPOS_ENTRADA"]
    assert "private Long SourceDocument;" not in v["CAMPOS_ENTRADA"]
    assert "public void setSourceDocument(Long sourceDocument)" in v["SETTERS"]
    assert "this.sourceDocument = sourceDocument;" in v["SETTERS"]
    assert "public String getDetectedFormat()" in v["GETTERS"]
    assert "return detectedFormat;" in v["GETTERS"]


def test_appian_sigue_viendo_el_nombre_del_contrato(eml):
    """Lo que NO se toca: `@Order` y las claves de bundle llevan el nombre de
    Appian, no el identificador Java. Cambiarlos rompería el despliegue.
    """
    v = andamiar.construir_variables(eml)
    assert '"SourceDocument"' in v["ORDEN_ENTRADAS"]
    assert "input.SourceDocument.displayName" in v["CLAVES_ENTRADAS"]
    assert "output.DetectedFormat.comment" in v["CLAVES_SALIDAS"]


def test_un_nombre_ya_en_lowerCamelCase_no_se_toca():
    datos = contrato.cargar(FIXTURES / "smart-service-minimo.md")
    v = andamiar.construir_variables(datos)
    assert "private Long documentoOrigen;" in v["CAMPOS_ENTRADA"]
    assert "public void setDocumentoOrigen(Long documentoOrigen)" in v["SETTERS"]
