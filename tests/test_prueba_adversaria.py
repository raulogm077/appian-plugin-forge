"""Lo que encontro la prueba adversaria del 21-sep-2026, con su repro.

Un agente probador lanzo entradas rotas, ficheros en UTF-16 y `exclude.xml`
manipulados contra los scripts (`Temp/forge-pruebas/robustez/caso-NN.*`). De
sus hallazgos se cerraron los que dejaban MENTIR al certificado y los que
reventaban con traza donde hacia falta un mensaje. Cada test de aqui es uno de
esos casos, con su numero, para que el corpus de la prueba siga siendo
reproducible desde la suite.
"""

import os
import pathlib
import subprocess
import sys
import time
import zipfile

import pytest

import andamiar
import contrato
import salida_build
import verificar_framework as vf
import verificar_superficie as vs

RAIZ = pathlib.Path(__file__).resolve().parents[1]
RAIZ_SCRIPTS = RAIZ / "scripts"
PLANTILLAS = RAIZ / "assets" / "plantillas"
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
CONTRATOS = FIXTURES / "contratos"
LOG_FUNCTION_EXITOSO = FIXTURES / "logs-de-build" / "function-exitoso.log"

GRADLE_SANO = """
spotbugs {
    ignoreFailures = false
    reportLevel = Confidence.valueOf('LOW')
}
"""

EXCLUDE_VACIO = """<?xml version="1.0" encoding="UTF-8"?>
<FindBugsFilter>
</FindBugsFilter>
"""


# --- caso 18c · R-F14 y las exclusiones sin `pattern` ------------------------


@pytest.mark.parametrize("bloque", [
    '<Match><Bug category="SECURITY"/></Match>',
    '<Match><Bug code="XSS"/></Match>',
    '<Match><Package name="~.*"/><Bug category="SECURITY"/></Match>',
    '<Match><Bug pattern="" code="XSS"/></Match>',
    '<Match><Bug PATTERN="SECXSS2"/></Match>',
])
def test_un_Bug_sin_pattern_es_una_exclusion_demasiado_ancha(bloque):
    """`<Match><Bug category="SECURITY"/></Match>` apagaba FindSecBugs ENTERO y el
    certificado salia READY: R-F14 solo leia el atributo `pattern`, y un <Bug>
    sin el no dejaba nombre que exigir en decisiones.md. Mencionar la familia
    en decisiones no absuelve: no hay patron que firmar.
    """
    xml = EXCLUDE_VACIO.replace("</FindBugsFilter>", bloque + "\n</FindBugsFilter>")
    decisiones = "# Decisiones\n\nSECURITY, XSS y SECXSS2: mencionados, que no es firmarlos.\n"
    hallazgos = vf.comprobar_guardarrailes("function", GRADLE_SANO, xml, decisiones)
    assert [h.regla for h in hallazgos] == ["R-F14"], [h.mensaje for h in hallazgos]
    assert "sin atributo `pattern`" in hallazgos[0].mensaje


def test_varios_patrones_en_un_solo_Bug_siguen_siendo_legitimos_si_van_firmados():
    """SpotBugs admite `pattern="A,B"`; la regla nueva no lo confunde con ancho."""
    xml = EXCLUDE_VACIO.replace(
        "</FindBugsFilter>",
        '<Match><Bug pattern="THROWS,CRLF_INJECTION_LOGS"/></Match>\n</FindBugsFilter>',
    )
    decisiones = "# Decisiones\n\nSe excluyen THROWS y CRLF_INJECTION_LOGS: el dominio no registra.\n"
    assert vf.comprobar_guardarrailes("function", GRADLE_SANO, xml, decisiones) == []


# --- caso 18a · la rancidez tambien ve los BORRADOS ---------------------------


def _proyecto_de_mentira(raiz: pathlib.Path) -> pathlib.Path:
    """Lo justo para que `ingerir` tenga un log que leer: contrato, una clase,
    un JAR y el log real de un build de function que termino bien."""
    (raiz / "docs").mkdir(parents=True, exist_ok=True)
    (raiz / "docs" / "contrato.md").write_text(
        (CONTRATOS / "function-minimo.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    clases = raiz / "build" / "classes" / "java" / "main"
    clases.mkdir(parents=True, exist_ok=True)
    (clases / "C0.class").write_bytes(b"\xca\xfe\xba\xbe")
    libs = raiz / "build" / "libs"
    libs.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(libs / "x.jar", "w") as z:
        z.writestr("appian-plugin.xml", "<appian-plugin/>")
    log = raiz / salida_build.RUTA_POR_DEFECTO
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(LOG_FUNCTION_EXITOSO.read_text(encoding="utf-8"), encoding="utf-8")
    return raiz


def _andamiado_con_fuentes_anteriores_al_log(raiz: pathlib.Path) -> pathlib.Path:
    """Lo convierte en un proyecto ANDAMIADO: `build.gradle` y las demas fuentes
    que invalidan, todas con fecha anterior al log, para que la comparacion de
    marcas de tiempo no dispare por su cuenta."""
    antes = (raiz / salida_build.RUTA_POR_DEFECTO).stat().st_mtime - 3600
    for nombre in salida_build.FUENTES_QUE_INVALIDAN:
        ruta = raiz / nombre
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("x\n", encoding="utf-8")
        os.utime(ruta, (antes, antes))
    return raiz


def test_borrar_una_fuente_que_invalida_deja_el_log_RANCIO(tmp_path):
    """Borrar `LICENSE`, `THIRD_PARTY_NOTICES.md` y `exclude.xml` dejaba READY un
    arbol que Gradle ya no puede construir, porque la rancidez solo comparaba
    marcas de tiempo de los ficheros que EXISTEN."""
    raiz = _andamiado_con_fuentes_anteriores_al_log(_proyecto_de_mentira(tmp_path))
    assert salida_build.ingerir(raiz).desenlace == salida_build.EXITOSO  # linea base

    (raiz / "LICENSE").unlink()
    resultado = salida_build.ingerir(raiz)
    assert resultado.desenlace == salida_build.RANCIO
    assert not resultado.consta
    assert "LICENSE" in resultado.motivo, resultado.motivo


def test_un_arbol_a_mano_sin_build_gradle_no_se_declara_rancio_por_ausencias(tmp_path):
    """Los arboles de mentira de la suite no llevan las cinco fuentes y no tienen
    por que: sin `build.gradle` no hay proyecto andamiado y la comprobacion de
    ausencias no aplica. Es la guarda que evita poner en rojo el resto de la suite."""
    raiz = _proyecto_de_mentira(tmp_path)
    assert not (raiz / "build.gradle").exists()
    assert salida_build.ingerir(raiz).desenlace == salida_build.EXITOSO


def test_fuente_posterior_a_tambien_ve_los_borrados(tmp_path):
    """La misma mecanica sobre el certificado: un insumo que YA NO ESTA es el que
    lo deja rancio, y se nombra."""
    raiz = _andamiado_con_fuentes_anteriores_al_log(_proyecto_de_mentira(tmp_path))
    artefacto = raiz / "docs" / "CERTIFICADO.md"
    artefacto.write_text("cert\n", encoding="utf-8")
    futuro = time.time() + 3600
    os.utime(artefacto, (futuro, futuro))
    assert salida_build.fuente_posterior_a(raiz, artefacto) is None

    (raiz / "THIRD_PARTY_NOTICES.md").unlink()
    assert salida_build.fuente_posterior_a(raiz, artefacto) == raiz / "THIRD_PARTY_NOTICES.md"


# --- caso 18f · la exclusion que hornea la plantilla de smart-service ---------

CONTRATO_ORIGEN_DUMMY = "contrato de prueba (test_prueba_adversaria.py, sin fichero real)"


def _contrato(tipo: str) -> dict:
    return {
        "plugin": {
            "key": "com.raul.appian.ejemplo", "nombre": "Ejemplo", "version": "1.0.0",
            "paquete": "com.raul.appian.ejemplo", "tipo": tipo, "perfil": "estandar",
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


def test_el_smart_service_nace_con_su_exclusion_FIRMADA_en_decisiones(tmp_path):
    """Al generalizar R-F14 a los cuatro tipos, todo smart service recien
    andamiado nacia NOT_READY: la plantilla activa `CRLF_INJECTION_LOGS` y nadie
    la firmaba. La firma es del andamiaje, con el mismo argumento que lleva el
    XML, y R-F14 sale limpia sobre el proyecto recien generado sin que nadie
    escriba nada."""
    escritos = andamiar.generar(_contrato("smart-service"), PLANTILLAS, tmp_path, CONTRATO_ORIGEN_DUMMY)
    decisiones = tmp_path / "docs" / "decisiones.md"
    assert decisiones in escritos
    texto = decisiones.read_text(encoding="utf-8")
    assert "CRLF_INJECTION_LOGS" in texto
    assert "com.raul.appian.ejemplo.smartservice.EjemploClase" in texto

    exclusiones = (tmp_path / "config" / "spotbugs" / "exclude.xml").read_text(encoding="utf-8")
    gradle = (tmp_path / "build.gradle").read_text(encoding="utf-8")
    assert vf.comprobar_guardarrailes("smart-service", gradle, exclusiones, texto) == []


def test_una_function_nace_con_decisiones_sin_ninguna_exclusion(tmp_path):
    andamiar.generar(_contrato("function"), PLANTILLAS, tmp_path, CONTRATO_ORIGEN_DUMMY)
    texto = (tmp_path / "docs" / "decisiones.md").read_text(encoding="utf-8")
    assert texto.startswith("# Decisiones")
    assert "CRLF_INJECTION_LOGS" not in texto


def test_regenerar_NO_pisa_un_decisiones_que_ya_existe(tmp_path):
    """Regenerar sobre un proyecto en marcha no puede borrar decisiones ya
    tomadas: el fichero solo se escribe si no existe."""
    (tmp_path / "docs").mkdir()
    propio = tmp_path / "docs" / "decisiones.md"
    propio.write_text("# Mis decisiones\n\nD1: la mia.\n", encoding="utf-8")
    escritos = andamiar.generar(_contrato("smart-service"), PLANTILLAS, tmp_path, CONTRATO_ORIGEN_DUMMY)
    assert propio not in escritos
    assert propio.read_text(encoding="utf-8") == "# Mis decisiones\n\nD1: la mia.\n"


# --- caso 10a · un .class truncado nombra el fichero --------------------------


def test_un_class_truncado_nombra_el_fichero(tmp_path):
    """Un `.class` cortado a la mitad moria con `IndexError: index out of range`,
    sin decir cual."""
    truncada = tmp_path / "Truncada.class"
    truncada.write_bytes(b"\xca\xfe\xba\xbe\x00\x00\x00\x3d\x00\x10\x07")
    with pytest.raises(ValueError) as info:
        vs.cargar_clases(tmp_path)
    assert "Truncada.class" in str(info.value)
    assert "gradlew build" in str(info.value)


# --- casos 04, 05 y 18d · lo que la puerta determinista dejaba pasar ----------


def _completo() -> dict:
    return contrato.cargar(CONTRATOS / "smart-service-completo.md")


def _faltantes_con(**cambios) -> list[str]:
    """Muta el contrato completo campo a campo (`plugin__key=123`) y lo valida."""
    datos = _completo()
    for ruta, valor in cambios.items():
        seccion, campo = ruta.split("__")
        if seccion in ("entradas", "salidas"):
            datos[seccion][0][campo] = valor
        else:
            datos.setdefault(seccion, {})[campo] = valor
    return contrato.validar(datos)


def test_el_contrato_completo_sigue_sin_faltantes_tras_las_reglas_nuevas():
    assert _faltantes_con() == []


@pytest.mark.parametrize("ruta, valor", [
    ("plugin__application_version_min", 26),
    ("plugin__key", 123),
    ("plugin__version", 1.0),
    ("plugin__nombre", True),
    ("clase__nombre", 5),
    ("entradas__nombre", 7),
    ("entradas__tipo_java", 7),
    ("salidas__nombre", 7),
])
def test_un_escalar_sin_comillas_es_FALTA_y_no_un_TypeError(ruta, valor):
    """`application_version_min = 26` sin comillas es un entero para TOML: pasaba
    la puerta y `andamiar.py` moria con `TypeError` minutos despues; `key = 123`
    mataba a la propia puerta en `fullmatch`."""
    faltantes = _faltantes_con(**{ruta: valor})
    campo = ruta.split("__")[1]
    assert any(campo in f and "comillas" in f for f in faltantes), faltantes


@pytest.mark.parametrize("valor", ["abc", "v26.3", "26"])
def test_una_version_minima_sin_forma_de_version_es_FALTA(valor):
    faltantes = _faltantes_con(plugin__application_version_min=valor)
    assert any("application_version_min" in f for f in faltantes), faltantes


@pytest.mark.parametrize("valor", ["26.3", "24.1", "26.3.1"])
def test_una_version_minima_con_forma_de_version_pasa(valor):
    assert _faltantes_con(plugin__application_version_min=valor) == []


def test_una_capacidad_escrita_como_cadena_es_FALTA():
    """`sale_a_la_red = "no"` es una cadena no vacia, o sea VERDADERO: proponia
    RIGUROSO por un «no»."""
    faltantes = _faltantes_con(capacidades__sale_a_la_red="no")
    assert any("capacidades.sale_a_la_red" in f and "true o false" in f for f in faltantes), faltantes


@pytest.mark.parametrize("ruta, valor", [
    ("entradas__nombre", "nom bre"),
    ("entradas__nombre", "1nombre"),
    ("entradas__nombre", "nombre;System.exit(0);String x"),
    ("entradas__nombre", "class"),
    ("salidas__nombre", "resul-tado"),
    ("funcion__nombre", "saludo con espacio"),
])
def test_un_nombre_que_no_es_identificador_es_FALTA(ruta, valor):
    """`andamiar.py` escribe estos nombres VERBATIM en `@Parameter String <nombre>`,
    en `<function key>` y en las claves del bundle: `nom bre` pasaba la puerta y
    fallaba en javac, justo lo que la puerta existe para adelantar."""
    faltantes = _faltantes_con(**{ruta: valor})
    seccion, campo = ruta.split("__")
    esperado = f"{seccion}[0].{campo}" if seccion in ("entradas", "salidas") else f"{seccion}.{campo}"
    assert any(f.startswith(esperado) for f in faltantes), faltantes


def test_los_nombres_camelCase_y_con_guion_bajo_siguen_pasando():
    assert _faltantes_con(entradas__nombre="paisPorDefecto", salidas__nombre="valor_1") == []


# --- casos 03 y 06 · contratos que no se pueden ni abrir ----------------------


def _ilegible(ruta) -> str:
    with pytest.raises(contrato.ContratoIlegible) as info:
        contrato.cargar(ruta)
    return str(info.value)


def test_un_contrato_en_UTF16_dice_que_lo_escribio_PowerShell(tmp_path):
    """`>` en PowerShell 5.1 escribe UTF-16LE con BOM, y todos los scripts morian
    con `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff`."""
    ruta = tmp_path / "contrato.md"
    ruta.write_bytes((CONTRATOS / "function-minimo.md").read_text(encoding="utf-8").encode("utf-16"))
    mensaje = _ilegible(ruta)
    assert "UTF-16" in mensaje and "PowerShell" in mensaje


def test_un_contrato_con_BOM_UTF8_sigue_cargando(tmp_path):
    ruta = tmp_path / "contrato.md"
    ruta.write_bytes(b"\xef\xbb\xbf" + (CONTRATOS / "function-minimo.md").read_bytes())
    assert contrato.validar(contrato.cargar(ruta)) == []


def _nada(ruta):
    return None


def _directorio(ruta):
    ruta.mkdir()


def _vacio(ruta):
    ruta.write_text("", encoding="utf-8")


def _sin_bloque(ruta):
    ruta.write_text("# Solo prosa\n", encoding="utf-8")


def _clave_duplicada(ruta):
    ruta.write_text('```toml\n[plugin]\nkey = "a"\nkey = "b"\n```\n', encoding="utf-8")


def _cp1252(ruta):
    ruta.write_bytes(b'```toml\n[plugin]\nnombre = "Se\xf1al"\n```\n')


@pytest.mark.parametrize("preparar, esperado", [
    (_nada, "no existe"),
    (_directorio, "directorio"),
    (_vacio, "vacio"),
    (_sin_bloque, "```toml"),
    (_clave_duplicada, "no es TOML valido"),
    (_cp1252, "no esta en UTF-8"),
])
def test_un_contrato_que_no_se_puede_abrir_lo_dice_en_castellano(tmp_path, preparar, esperado):
    ruta = tmp_path / "contrato.md"
    preparar(ruta)
    assert esperado in _ilegible(ruta)


@pytest.mark.parametrize("script", ["contrato.py", "andamiar.py"])
def test_la_CLI_no_revienta_con_un_contrato_ilegible(tmp_path, script):
    ruta = tmp_path / "contrato.md"
    ruta.write_bytes("# nada".encode("utf-16"))
    argumentos = [sys.executable, str(RAIZ_SCRIPTS / script), str(ruta)]
    if script == "andamiar.py":
        argumentos.append(str(tmp_path / "salida"))
    proceso = subprocess.run(
        argumentos, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60
    )
    assert proceso.returncode == 2, proceso.stderr
    assert "ERROR contrato" in proceso.stdout and "UTF-16" in proceso.stdout
    assert "Traceback" not in proceso.stderr


# --- lo que encontro el primer ensayo con una dependencia real (libphonenumber)


def test_el_contrato_con_dependencia_carga_y_llega_al_build_gradle(tmp_path):
    """El fixture canonico de `dependencias`: clave de raiz, antes de `[plugin]`.
    Ninguno de los cinco fixtures anteriores la declaraba, asi que no habia
    ejemplo que seguir."""
    datos = contrato.cargar(CONTRATOS / "function-con-dependencia.md")
    assert contrato.validar(datos) == []
    assert datos["dependencias"] == ["com.googlecode.libphonenumber:libphonenumber:9.0.39"]
    andamiar.generar(datos, PLANTILLAS, tmp_path, CONTRATOS / "function-con-dependencia.md")
    gradle = (tmp_path / "build.gradle").read_text(encoding="utf-8")
    assert "implementation 'com.googlecode.libphonenumber:libphonenumber:9.0.39'" in gradle
    notices = (tmp_path / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "libphonenumber" in notices and "PENDIENTE DE COMPLETAR" in notices


@pytest.mark.parametrize("despues_de", ["[[salidas]]", "[capacidades]", "[confirmacion]"])
def test_dependencias_escrita_despues_de_una_tabla_es_FALTA_y_no_silencio(despues_de):
    """TOML cuelga una clave de raiz escrita tras una tabla de ESA tabla: el
    contrato daba «OK» y `build.gradle` salia sin `implementation`. El fallo
    aparecia en `compileJava`, lejos de la causa."""
    texto = (CONTRATOS / "function-minimo.md").read_text(encoding="utf-8")
    bloque = texto.split("```toml\n")[1].split("\n```")[0]
    # La clave va al FINAL de la tabla elegida: justo antes de la siguiente
    # cabecera `[`, o al final del bloque si es la ultima.
    inicio = bloque.index(despues_de)
    siguiente = bloque.find("\n[", inicio + len(despues_de))
    corte = len(bloque) if siguiente == -1 else siguiente
    roto = bloque[:corte] + '\ndependencias = ["com.example:lib:1.0"]\n' + bloque[corte:]
    faltantes = contrato.validar(contrato.extraer_toml("```toml\n" + roto + "\n```\n"))
    assert any(f.startswith("dependencias:") and "RAIZ" in f for f in faltantes), faltantes


def test_R_F15_exige_el_lockfile_que_RIGUROSO_promete():
    """`dependencyLocking` sin `gradle.lockfile` no fija nada; Gradle no lo
    escribe ni lo exige por su cuenta."""
    gradle = GRADLE_SANO + "\ndependencyLocking {\n    lockAllConfigurations()\n}\n"
    datos = _contrato("function")
    xml = '<appian-plugin><function-category>x</function-category></appian-plugin>'
    sin = vf.comprobar(datos, xml, [], gradle=gradle, exclusiones=EXCLUDE_VACIO, lockfile=False)
    assert "R-F15" in {h.regla for h in sin}
    assert any("write-locks" in h.mensaje for h in sin if h.regla == "R-F15")
    con = vf.comprobar(datos, xml, [], gradle=gradle, exclusiones=EXCLUDE_VACIO, lockfile=True)
    assert "R-F15" not in {h.regla for h in con}
    # Sin `dependencyLocking` (ESTANDAR) el lockfile no se exige.
    estandar = vf.comprobar(datos, xml, [], gradle=GRADLE_SANO, exclusiones=EXCLUDE_VACIO, lockfile=False)
    assert "R-F15" not in {h.regla for h in estandar}


def _sbom_con(*coordenadas):
    componentes = []
    for coordenada in coordenadas:
        grupo, nombre, version = coordenada.split(":")
        componentes.append({"group": grupo, "name": nombre, "version": version,
                            "licenses": [{"license": {"id": "Apache-2.0"}}]})
    return {"components": componentes}


def test_R_L03_un_NOTICES_sin_cerrar_no_pasa_si_hay_dependencias():
    import verificar_licencias as vl

    sbom = _sbom_con("com.googlecode.libphonenumber:libphonenumber:9.0.39")
    a_medias = "- `com.googlecode.libphonenumber:libphonenumber:9.0.39` — licencia: **PENDIENTE DE COMPLETAR**\n"
    reglas = [h.regla for h in vl.comprobar_notices(sbom, a_medias)]
    assert reglas == ["R-L03"]

    cerrado = "- `com.googlecode.libphonenumber:libphonenumber:9.0.39` — Apache-2.0\n"
    assert vl.comprobar_notices(sbom, cerrado) == []

    sin_mencion = "# Third-party notices\n\nNada.\n"
    assert [h.regla for h in vl.comprobar_notices(sbom, sin_mencion)] == ["R-L03"]


def test_R_L03_no_aplica_sin_dependencias_ni_sin_fichero():
    import verificar_licencias as vl

    assert vl.comprobar_notices({"components": []}, "PENDIENTE DE COMPLETAR") == []
    assert vl.comprobar_notices(_sbom_con("a:b:1"), None) == []
