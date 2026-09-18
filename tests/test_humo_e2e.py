"""Humo de punta a punta: contrato real -> proyecto -> build -> certificado.

La retrospectiva de la Fase 1 (S2) lo justifica: 18 tareas cerradas con
revision limpia y 139 tests en verde, y el sistema no funcionaba de punta a
punta. Este modulo ejercita el unico tramo que ningun otro test toca: el
proyecto generado COMPILA con su propio wrapper y el orquestador de las
cuatro capas emite su certificado sobre ese build real.

Marcado `e2e` (minutos de Gradle): pytest.ini lo excluye de la suite rapida;
se invoca con `PYTHONUTF8=1 python -m pytest -m e2e tests/test_humo_e2e.py -v`.

Regla heredada de test_extremo_a_extremo.py: si algo sale rojo, la sospecha
recae PRIMERO sobre la plantilla o el validador. Nunca relajar una
comprobacion para que el fixture pase: investigar.
"""

import pathlib
import subprocess
import sys

import pytest

import andamiar
import contrato
import verificar_todo as vt

pytestmark = pytest.mark.e2e

RAIZ = pathlib.Path(__file__).resolve().parents[1]
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "contratos"
PLANTILLAS = RAIZ / "assets" / "plantillas"
TIMEOUT_BUILD = 900  # el build real del scaffold arreglado tardo 588s (9m48s) el
# 2026-08-09 (BUILD SUCCESSFUL, perfil estandar); 900 deja margen sin ocultar un
# cuelgue real, en vez del 600 anterior que dejaba solo ~12s de sobra.


@pytest.fixture(scope="module")
def proyecto(tmp_path_factory):
    """El proyecto andamiado desde el contrato mas rico del corpus."""
    destino = tmp_path_factory.mktemp("humo-smart-service")
    fixture_contrato = FIXTURES / "smart-service-completo.md"
    datos = contrato.cargar(fixture_contrato)
    errores = contrato.validar(datos)
    assert errores == [], f"la puerta determinista rechaza el fixture: {errores}"
    andamiar.generar(datos, PLANTILLAS, destino, fixture_contrato)
    # Critico 2 del gate de ciclo 1: sin esto, las cuatro puertas de
    # verificar_todo.py que leen docs/contrato.md sin condicion (framework,
    # AppMarket, bundles, empaquetado) y generar_dossier.py rompian con
    # FileNotFoundError sobre TODO proyecto recien andamiado.
    assert (destino / "docs" / "contrato.md").is_file(), (
        "generar() no escribio docs/contrato.md -- las puertas que lo leen sin "
        "condicion van a romper con FileNotFoundError"
    )
    return destino


@pytest.fixture(scope="module")
def build(proyecto):
    """`gradlew build` real, con el wrapper que viaja en el proyecto."""
    gradlew = proyecto / "gradlew.bat"
    assert gradlew.is_file(), "el andamiador no copio el wrapper de Gradle"
    res = subprocess.run(
        [str(gradlew), "build", "--console=plain"],
        cwd=proyecto, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=TIMEOUT_BUILD,
    )
    log = proyecto / "build-salida.txt"
    log.write_text(res.stdout + "\n" + res.stderr, encoding="utf-8")
    return res, log


def test_el_proyecto_generado_compila(build):
    res, log = build
    assert res.returncode == 0, (
        "gradlew build fallo sobre un proyecto recien andamiado; "
        f"ver {log}. NO relajar: es defecto de plantilla o de entorno."
    )


def _fila(texto: str, puerta: str) -> str:
    """La linea de la tabla del certificado para una puerta.

    Aislar la linea (y no buscar en el texto completo) importa: un texto
    como "NO VERIFICADO" puede aparecer en la EVIDENCIA de otra fila, y un
    assert sobre el certificado entero no distinguiria una puerta de otra.
    """
    for linea in texto.splitlines():
        if linea.startswith(f"| {puerta} |"):
            return linea
    raise AssertionError(f"el certificado no tiene fila para la puerta {puerta!r}")


def test_el_certificado_se_emite_sobre_el_build_real(proyecto, build):
    res, log = build
    cert_cli = subprocess.run(
        [sys.executable, str(RAIZ / "scripts" / "verificar_todo.py"),
         str(proyecto), "estandar",
         "--salida-build", str(log), "--codigo-build", str(res.returncode)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    certificado = proyecto / "docs" / "CERTIFICADO.md"
    assert certificado.is_file(), (
        f"verificar_todo no dejo certificado; stdout:\n{cert_cli.stdout[-2000:]}"
    )
    texto = certificado.read_text(encoding="utf-8")

    # Puertas que `verificar_todo` SIEMPRE nombra en la tabla, gane o pierda
    # el build (certificado_base() las siembra sin condicion).
    for puerta in [
        "Reglas del framework de Appian",
        "Politicas AppMarket",
        "Bundles y locales",
        "Compilacion · SDK 26.3 / release 17",
        "Superficie documentada · indice 26.3",
    ]:
        assert puerta in texto, f"el certificado no menciona la puerta {puerta!r}"

    # Los dos Criticos del gate de ciclo 1, cerrados: ya no queda ningun
    # FileNotFoundError sobre docs/contrato.md en el certificado (Critico 2
    # -- generar() ahora lo escribe), y el build ya no se cae en
    # `:spotbugsMain` (Critico 1 -- ejecutar() ya no deja UwF/UrF).
    assert "FileNotFoundError" not in texto, (
        f"el certificado todavia arrastra un FileNotFoundError:\n{texto}"
    )

    # Observado-y-clavado sobre smart-service-completo.md tras los dos
    # arreglos (perfil ESTANDAR; el fixture no declara tests unitarios ni
    # dependencias de terceros). Cada estado lleva su causa: no es "todo
    # verde porque el build paso", son mecanismos concretos de
    # verificar_todo.py y salida_build.py.
    ESTADOS_ESPERADOS = {
        # R-F13: el cuerpo de este proyecto es el del ANDAMIAJE --su
        # `ejecutar()` lanza UnsupportedOperationException-- asi que la capa 1
        # sale ROJA, y esa es la respuesta correcta. Un plug-in que no puede
        # ejecutarse no es un plug-in.
        #
        # Antes salia OK, y ese OK era el ultimo eslabon de un agujero
        # Critical: andamiaje + un test trivial => STATUS
        # READY_FOR_APPIAN_SUBMISSION sobre un plug-in que no hace nada, sin
        # falsificar nada y por el camino por defecto. Clavar el rojo aqui es
        # lo que impide que vuelva.
        "Reglas del framework de Appian": "NO VERIFICADO",
        "Politicas AppMarket": "OK",
        "Bundles y locales": "OK",
        # Critico 1: el build entero llega a BUILD SUCCESSFUL.
        "Compilacion · SDK 26.3 / release 17": "OK",
        "SpotBugs + FindSecBugs": "OK",
        "Superficie documentada · indice 26.3": "OK",
        # NO-SOURCE es legitimo (el fixture no declara tests unitarios) y
        # NO tumba la fila a NO VERIFICADO: `_resolver_delegadas` solo mira
        # si la tarea `:test` APARECE en el log (aparece, como NO-SOURCE),
        # asi que la puerta sale "verde"/OK con el aviso de insumo vacio en
        # la columna de INSUMO, no en el estado (verificar_todo.py,
        # `_tests_ejecutados` + `contrato.insumo_vacio`).
        "Tests unitarios": "OK",
        # El copyleft YA se juzga: `verificar_licencias.py` lee el SBOM que
        # genero `cyclonedxDirectBom`. El fixture no declara dependencias de
        # terceros --el SDK y log4j son compileOnly, los provee el
        # contenedor--, asi que son cero componentes, y cero es legitimo aqui:
        # por eso esta puerta no lleva unidad portante.
        "Licencias de terceros": "OK",
        # El bytecode DENTRO del JAR sigue sin comprobarse: un BUILD
        # SUCCESSFUL no lo mira, y delegar no es aprobar.
        "Bytecode del artefacto · major 61": "delegada",
        # Empaquetado (revisor de costuras, 4o consumidor de
        # docs/contrato.md): ya hay JAR (`:jar` no depende de
        # `:spotbugsMain`) y ya hay contrato -- verificar_jar.py corre
        # limpio sobre un fixture sin dependencias de terceros declaradas.
        "Empaquetado y cierre de dependencias": "OK",
        # No juzga OK/NO VERIFICADO: solo avisa si el SDK usado difiere de
        # la version real del entorno, y ese contraste (Fase 3) todavia no
        # esta mecanizado -- "info" es su unico estado posible hoy.
        "Deriva contra la version del entorno": "info",
        # Las dos ultimas filas del certificado: verificar_todo.py las
        # siembra siempre en rojo porque este humo nunca las ejecuta (R13 --
        # no hay contenedor OSGi equivalente en local; el despliegue a
        # Appian real exige aprobacion que este test no tiene). Clavarlas
        # protege el invariante de honestidad de E2E: si un dia salieran en
        # verde sin que nada cambiara en como se ejecutan, el humo debe caer.
        "Resolucion OSGi en la plataforma": "NO VERIFICADO",
        "Ejecucion en Appian real": "NO VERIFICADO",
    }
    for puerta, estado in ESTADOS_ESPERADOS.items():
        fila = _fila(texto, puerta)
        assert f"| {estado} |" in fila, (
            f"la puerta {puerta!r} deberia estar {estado!r} tras los dos arreglos; fila real: {fila}"
        )

    # El certificado ES la evidencia que el gate archiva (spec §4.1): se
    # imprime para que `pytest -s` lo deje en 03-humo-e2e.txt.
    print("\n--- CERTIFICADO.md del humo ---\n" + texto)


def test_el_dossier_se_genera_sobre_el_proyecto_real(proyecto):
    """El 5o consumidor de docs/contrato.md que el humo no cubria hasta esta
    tanda (revisor de costuras, `evidencia/13-revisor-de-costuras.md`):
    `generar_dossier.py` queda fuera del alcance de CERTIFICADO.md, asi que
    nada mas en el gate lo ejercitaba.

    Corre DESPUES de test_el_certificado_se_emite_sobre_el_build_real en
    este mismo modulo (mismo orden de declaracion; pytest no reordena sin un
    plugin que lo haga, y este proyecto no tiene ninguno instalado):
    DOSSIER.md incrusta el contenido de docs/CERTIFICADO.md (pieza 4 del
    dossier), y ese fichero solo existe una vez que verificar_todo.py ya
    corrio sobre este `proyecto`. El assert de abajo deja esa dependencia
    explicita en vez de fallar de forma confusa dentro de generar_dossier.py.
    """
    assert (proyecto / "docs" / "CERTIFICADO.md").is_file(), (
        "este test depende de que test_el_certificado_se_emite_sobre_el_build_real "
        "haya corrido antes sobre el mismo `proyecto` (fixture de modulo)"
    )
    dossier_cli = subprocess.run(
        [sys.executable, str(RAIZ / "scripts" / "generar_dossier.py"), str(proyecto)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert dossier_cli.returncode == 0, (
        f"generar_dossier.py fallo; stdout:\n{dossier_cli.stdout[-2000:]}\n"
        f"stderr:\n{dossier_cli.stderr[-2000:]}"
    )
    dossier = proyecto / "docs" / "DOSSIER.md"
    assert dossier.is_file(), "generar_dossier.py no dejo docs/DOSSIER.md"


def test_el_camino_RIGUROSO_tambien_deja_certificado(proyecto, build):
    """El humo corria solo en ESTANDAR, donde cuatro puertas ni existen.

    Lo levanto el auditor de verdes del ciclo 7 como hueco de la EVIDENCIA, no
    del codigo: la correccion que hizo portante la unidad de property tests, y
    despues la que impide degradar el perfil, no aparecian en ningun
    certificado archivado — las sostenian tests unitarios y nada mas. Este las
    ejerce sobre el proyecto REAL ya construido, asi que cuesta un par de
    segundos: no vuelve a invocar Gradle, reutiliza el mismo build.

    Las DOS ramas del perfil, y esto la primera version no lo cumplia: el
    fixture declara `perfil = "estandar"` y el test invocaba `riguroso`, o sea
    ejercia la rama de SUBIDA mientras el docstring decia cubrir la de
    degradacion. El auditor del ciclo 8 lo marco VACUA con razon. Abajo se
    ejercen las dos, la segunda volteando el perfil del contrato y
    restaurandolo.

    Lo que se afirma es que las cuatro filas ESTAN y que NINGUNA se resuelve a
    favor. Que salgan rojas o delegadas es el resultado correcto: el humo
    construye con el perfil estandar, asi que `mutationTest`,
    `jacocoTestCoverageVerification` y `releaseCheck` no se ejecutaron, y
    decirlo es justo la funcion del certificado.
    """
    res, log = build
    cert_cli = subprocess.run(
        [sys.executable, str(RAIZ / "scripts" / "verificar_todo.py"),
         str(proyecto), "riguroso",
         "--salida-build", str(log), "--codigo-build", str(res.returncode)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    texto = (proyecto / "docs" / "CERTIFICADO.md").read_text(encoding="utf-8")
    assert "**Perfil:** RIGUROSO" in texto, (
        f"el certificado no declara el perfil pedido; stdout:\n{cert_cli.stdout[-2000:]}"
    )

    rigurosas = ["Cobertura JaCoCo 95 / 85", "Mutacion PIT >= 85 %",
                 "Property tests y fuzz sembrado", "Build reproducible"]
    for puerta in rigurosas:
        assert puerta in texto, f"la fila «{puerta}» no aparece en el certificado RIGUROSO"

    # Y ninguna de las cuatro se cuela como pasada: el proyecto se construyo en
    # estandar, asi que nadie las ejecuto y el certificado tiene que decirlo.
    #
    # La seccion se ACOTA hasta la cabecera de la tabla. Sin acotarla, el
    # `split(...)[1]` arrastraba la tabla entera y el pie, asi que este bucle no
    # podia fallar mientras pasara el `assert puerta in texto` de arriba: la
    # fila de la tabla ya contiene el nombre. Un guardian contra el verde vacuo
    # que era, el mismo, un verde vacuo — levantado por el gate del ciclo 8.
    assert vt.NO_LISTO in texto
    motivos = texto.split("### Que impide enviarlo")[1].split("| Puerta |")[0]
    assert "|" not in motivos, f"la seccion de motivos sigue arrastrando tabla:\n{motivos}"
    for puerta in rigurosas:
        assert puerta in motivos, (
            f"«{puerta}» figura en la tabla pero no impide el envio, y nadie la ejecuto: "
            f"seria el verde vacuo que este certificado existe para no dejar pasar"
        )

    print("\n--- CERTIFICADO.md del humo RIGUROSO (rama SUBIDA) ---\n" + texto)

    # --- Rama DEGRADACION, sobre el mismo build ---------------------------
    # Un contrato que promete RIGUROSO verificado sin argumento: el defecto del
    # CLI es `estandar`, asi que este es exactamente el camino por el que las
    # cuatro filas desaparecian sin fallar. Es la correccion [ALTA] del ciclo 7
    # y hasta aqui no la respaldaba ningun certificado archivado.
    contrato_md = proyecto / "docs" / "contrato.md"
    original = contrato_md.read_text(encoding="utf-8")
    try:
        contrato_md.write_text(
            original.replace('perfil = "estandar"', 'perfil = "riguroso"'), encoding="utf-8"
        )
        assert 'perfil = "riguroso"' in contrato_md.read_text(encoding="utf-8"), (
            "el fixture dejo de declarar `perfil = \"estandar\"`: este test ya no voltea nada"
        )
        subprocess.run(
            [sys.executable, str(RAIZ / "scripts" / "verificar_todo.py"), str(proyecto),
             "--salida-build", str(log), "--codigo-build", str(res.returncode)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        degradado = (proyecto / "docs" / "CERTIFICADO.md").read_text(encoding="utf-8")
    finally:
        contrato_md.write_text(original, encoding="utf-8")

    assert "**Perfil:** RIGUROSO" in degradado, (
        "un contrato que declara RIGUROSO se verifico sin argumento y el certificado salio "
        "ESTANDAR: las cuatro puertas rigurosas desaparecen sin fallar"
    )
    assert "no se pidio ninguno" in degradado, (
        "el certificado no dice por que el perfil no es el que se lanzo"
    )
    for puerta in rigurosas:
        assert puerta in degradado, f"falta la fila «{puerta}» en la rama de degradacion"
    print("\n--- CERTIFICADO.md del humo RIGUROSO (rama DEGRADACION) ---\n" + degradado)
