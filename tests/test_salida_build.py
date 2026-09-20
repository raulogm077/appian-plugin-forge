"""RESERVA 1 · el certificado no distinguia «paso» de «fallo» en 5 de 13 puertas.

La sexta instancia del verde vacuo, y la de mas arriba de todas. Esta
DEMOSTRADA, no supuesta: un servlet recien andamiado cuyo `./gradlew build`
termino en exit 1 con `spotbugsMain FAILED` producia un certificado con las
cinco filas delegadas BYTE A BYTE IDENTICAS a las de un `function` cuyo build
salio en BUILD SUCCESSFUL, `verificar_todo` salia con 0, y el dossier no
guardaba ni una huella del fallo.

Las cinco filas «delegada» declaraban el comando que las ejecutaria, pero nada
en el pipeline leia jamas su resultado: las unicas menciones a `gradlew` en el
orquestador eran texto descriptivo. El criterio de VERIFY de la SKILL --«cada
delegada tiene su salida real a la vista»-- era el unico de los tres que
ningun script comprobaba.

Los dos logs de `fixtures/logs-de-build/` son REALES: salen de ejecutar
`./gradlew build` sobre los dos proyectos que andamia este mismo repositorio,
con Gradle 8.14.3 y Java 17. No estan escritos a mano, y por eso el parser se
enfrenta a lo que Gradle imprime de verdad --`> Task :test NO-SOURCE` incluido,
que es un BUILD SUCCESSFUL sobre cero tests-- y no a lo que uno imagina que
imprime. No viven bajo `fixtures/build/` porque ese nombre lo tragaba la regla
`build/` del .gitignore, y un fixture ignorado en silencio es un test que no
corre en otra maquina.
"""

import pathlib
import zipfile

import pytest

import contrato
import salida_build
import verificar_todo as vt

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
CONTRATOS = FIXTURES / "contratos"
LOGS = FIXTURES / "logs-de-build"

LOG_SERVLET_FALLIDO = LOGS / "servlet-spotbugs-fallido.log"
LOG_FUNCTION_EXITOSO = LOGS / "function-exitoso.log"


# --- el parser, contra los dos logs REALES ---------------------------------


def test_el_log_real_de_un_build_fallido_se_lee_como_fallido():
    r = salida_build.analizar(LOG_SERVLET_FALLIDO.read_text(encoding="utf-8"), codigo=1)
    assert r.desenlace == salida_build.FALLIDO
    assert r.tareas[":spotbugsMain"] == "FAILED"
    assert ":spotbugsMain" in r.motivo


def test_el_log_real_de_un_build_correcto_se_lee_como_exitoso():
    r = salida_build.analizar(LOG_FUNCTION_EXITOSO.read_text(encoding="utf-8"), codigo=0)
    assert r.desenlace == salida_build.EXITOSO
    assert r.tareas[":compileJava"] == "OK"
    assert r.tareas[":spotbugsMain"] == "OK"
    # Lo que Gradle imprime de verdad cuando no hay ni un test: un
    # BUILD SUCCESSFUL sobre cero. Inventar el log se lo habria saltado.
    assert r.tareas[":test"] == "NO-SOURCE"


def test_un_log_truncado_no_se_lee_como_exitoso():
    """Sin marcador de cierre no se sabe como termino, y no saberlo NUNCA se
    resuelve a favor.
    """
    texto = LOG_FUNCTION_EXITOSO.read_text(encoding="utf-8").split("BUILD SUCCESSFUL")[0]
    assert salida_build.analizar(texto).desenlace == salida_build.INDETERMINADO


def test_un_codigo_de_salida_que_contradice_al_log_no_se_resuelve_a_favor():
    """Exit 0 con «BUILD FAILED» en el texto es un dato corrupto, no un exito.
    Es justo la forma que tendria un log manipulado o mal capturado.
    """
    r = salida_build.analizar(LOG_SERVLET_FALLIDO.read_text(encoding="utf-8"), codigo=0)
    assert r.desenlace == salida_build.INDETERMINADO
    assert "contradice" in r.motivo.lower()


def test_de_varias_ejecuciones_pegadas_vale_la_ULTIMA():
    """Un log al que se le va anadiendo cada `./gradlew build` del paso 4. La
    primera corrida fallo y la ultima paso: lo vigente es lo ultimo.
    """
    texto = (
        LOG_SERVLET_FALLIDO.read_text(encoding="utf-8")
        + "\n"
        + LOG_FUNCTION_EXITOSO.read_text(encoding="utf-8")
    )
    assert salida_build.analizar(texto).desenlace == salida_build.EXITOSO


# --- la trampa del cp1252, otra vez: PowerShell 5.1 redirige en UTF-16 -----


def test_un_log_redirigido_desde_powershell_se_lee_igual(tmp_path):
    """`./gradlew build > log 2>&1` desde PowerShell 5.1 escribe UTF-16LE con
    BOM. Leido como UTF-8 no aparece ningun marcador, y la puerta saldria roja
    por el motivo equivocado --«no consta el build»-- cuando el build existe y
    paso. Misma familia que la trampa del cp1252 ya documentada en el repo.
    """
    ruta = tmp_path / "salida-build.log"
    ruta.write_bytes(
        LOG_FUNCTION_EXITOSO.read_text(encoding="utf-8").encode("utf-16")
    )
    assert salida_build.analizar(salida_build.leer(ruta)).desenlace == salida_build.EXITOSO


def test_los_colores_de_consola_no_esconden_el_desenlace():
    texto = "\x1b[1m> Task :compileJava\x1b[0m\n\x1b[32mBUILD SUCCESSFUL\x1b[0m in 3s\n"
    assert salida_build.analizar(texto).desenlace == salida_build.EXITOSO


# --- el orquestador: el contraste, que es la prueba que cierra el hallazgo --


def _proyecto(raiz: pathlib.Path, tipo: str, log: pathlib.Path | str | None,
              clases: int = 1, tests: int | None = None) -> pathlib.Path:
    """Un proyecto generado de mentira con lo justo para el orquestador."""
    (raiz / "docs").mkdir(parents=True, exist_ok=True)
    (raiz / "docs" / "contrato.md").write_text(
        (CONTRATOS / f"{tipo}-minimo.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    destino_clases = raiz / "build" / "classes" / "java" / "main"
    destino_clases.mkdir(parents=True, exist_ok=True)
    for i in range(clases):
        (destino_clases / f"C{i}.class").write_bytes(b"\xca\xfe\xba\xbe")
    if tests is not None:
        resultados = raiz / "build" / "test-results" / "test"
        resultados.mkdir(parents=True, exist_ok=True)
        (resultados / "TEST-x.xml").write_text(
            f'<testsuite name="x" tests="{tests}" failures="0" errors="0"/>',
            encoding="utf-8",
        )
    libs = raiz / "build" / "libs"
    libs.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(libs / "x.jar", "w") as z:
        z.writestr("appian-plugin.xml", "<appian-plugin/>")
    if log is not None:
        # Ruta o TEXTO. El texto hace falta para los estados que no tienen
        # fixture en disco --un log truncado, que es `indeterminado`-- y su
        # ausencia era lo que dejaba vacuo al guardian de mas abajo: pasar
        # `None` no da `indeterminado`, da `ausente`, que es otro estado.
        texto = log if isinstance(log, str) else log.read_text(encoding="utf-8")
        destino = raiz / salida_build.RUTA_POR_DEFECTO
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding="utf-8")
    return raiz


def _puertas(cert):
    return {p.nombre: p for p in cert.puertas}


PUERTA_SPOTBUGS = "SpotBugs + FindSecBugs"
PUERTA_COMPILACION = "Compilacion · SDK 26.3 / release 17"


def test_EL_CONTRASTE_un_build_fallido_y_uno_correcto_no_certifican_igual(tmp_path):
    """La prueba que de verdad cierra el hallazgo. Una sola corrida no lo es:
    lo que demuestra el arreglo es que las dos ya NO se parecen.
    """
    fallido = _puertas(vt.ejecutar(
        _proyecto(tmp_path / "servlet", "servlet", LOG_SERVLET_FALLIDO), "estandar"
    ))
    correcto = _puertas(vt.ejecutar(
        _proyecto(tmp_path / "function", "function", LOG_FUNCTION_EXITOSO, tests=7), "estandar"
    ))

    assert fallido[PUERTA_SPOTBUGS].estado == "rojo"
    assert correcto[PUERTA_SPOTBUGS].estado == "verde"
    assert fallido[PUERTA_COMPILACION].estado == "rojo"
    assert correcto[PUERTA_COMPILACION].estado == "verde"

    delegadas = [n for n in vt.PUERTAS_DELEGADAS if n in fallido]
    assert [fallido[n].evidencia for n in delegadas] != [correcto[n].evidencia for n in delegadas], (
        "las filas delegadas siguen siendo indistinguibles entre un build que fallo y uno que paso"
    )


def test_la_fila_del_build_fallido_nombra_la_tarea_que_fallo(tmp_path):
    puertas = _puertas(vt.ejecutar(
        _proyecto(tmp_path, "servlet", LOG_SERVLET_FALLIDO), "estandar"
    ))
    assert ":spotbugsMain" in puertas[PUERTA_SPOTBUGS].evidencia


def test_sin_salida_de_build_la_fila_es_ROJA_y_no_delegada(tmp_path):
    """El minimo irrenunciable del encargo, y el mismo criterio que ya rige
    para el JAR ausente: no poder mirar no es «ya lo miraremos». Una fila que
    no puede distinguir exito de fracaso es peor que una en rojo, porque la
    primera miente y la segunda solo declara ignorancia.
    """
    puertas = _puertas(vt.ejecutar(_proyecto(tmp_path, "function", log=None), "estandar"))
    for nombre in vt.PUERTAS_DELEGADAS:
        if nombre in puertas:
            assert puertas[nombre].estado == "rojo", (
                f"«{nombre}» no consta ejecutada y no esta en rojo"
            )
            assert "salida-build.log" in puertas[nombre].evidencia, (
                "la evidencia no dice como aportar la salida del build"
            )


def test_un_log_anterior_al_ultimo_cambio_del_fuente_no_vale(tmp_path):
    """Rancio es lo mismo que ausente. Es exactamente el flujo del SECSP:
    descomentar la exclusion y NO volver a construir dejaria un log viejo
    certificando un codigo que ya no es el que se entrega.
    """
    raiz = _proyecto(tmp_path, "servlet", LOG_FUNCTION_EXITOSO)
    log = raiz / salida_build.RUTA_POR_DEFECTO
    fuente = raiz / "src" / "main" / "java" / "X.java"
    fuente.parent.mkdir(parents=True, exist_ok=True)
    fuente.write_text("class X {}", encoding="utf-8")
    import os
    os.utime(log, (1, 1))  # el log, anterior al fuente

    puertas = _puertas(vt.ejecutar(raiz, "estandar"))
    assert puertas[PUERTA_SPOTBUGS].estado == "rojo"
    assert "rancio" in puertas[PUERTA_SPOTBUGS].evidencia.lower()


def test_un_BUILD_SUCCESSFUL_sobre_cero_tests_no_es_un_verde_limpio(tmp_path):
    """`> Task :test NO-SOURCE` --que es lo que imprime el log REAL del
    `function` andamiado-- da BUILD SUCCESSFUL habiendo ejecutado cero tests.
    Es la forma exacta del verde vacuo, y la columna de insumo ya sabe
    marcarla: no hace falta una guarda nueva.
    """
    cert = vt.ejecutar(_proyecto(tmp_path, "function", LOG_FUNCTION_EXITOSO), "estandar")
    puerta = _puertas(cert)["Tests unitarios"]
    assert puerta.estado == "verde"
    assert contrato.insumo_vacio(puerta.insumo), f"insumo declarado: {puerta.insumo!r}"
    assert vt.AVISO_INSUMO_VACIO in vt.render_markdown(cert)
    assert cert.listo_para_sumision is False


def test_un_build_correcto_no_aprueba_lo_que_el_build_no_mira(tmp_path):
    """BUILD SUCCESSFUL no juzga el copyleft de una dependencia ni mira el
    bytecode de las copias DENTRO del JAR. Ponerlas en verde seria cambiar un
    verde vacuo por otro; dejarlas eternamente en rojo seria una alarma que
    salta siempre. Se quedan delegadas, con su matiz intacto.
    """
    puertas = _puertas(vt.ejecutar(
        _proyecto(tmp_path, "function", LOG_FUNCTION_EXITOSO, tests=7), "estandar"
    ))
    # «Licencias de terceros» SALIO de esta lista: su juicio ya no depende de
    # nadie, lo hace `verificar_licencias.py` sobre el SBOM.
    #
    # Este test corre en ESTANDAR, donde solo existe una de las dos puertas del
    # conjunto. El ciclo 6 lo marco VACUO: el ciclo 5 cambio la tupla escrita a
    # mano por `& set(puertas)` creyendo ampliar la cobertura, y la interseccion
    # seguia valiendo UNA. Cambio el mecanismo, no lo que se comprueba. La otra
    # mitad la cubre ahora `test_la_reproducibilidad_no_la_aprueba_un_releaseCheck`.
    esperadas_aqui = vt.PUERTAS_QUE_EL_BUILD_NO_APRUEBA & set(puertas)
    assert esperadas_aqui, "la interseccion es vacia: el bucle no comprobaria nada"
    for nombre in sorted(esperadas_aqui):
        assert puertas[nombre].estado == "delegada", (
            f"«{nombre}» se dio por aprobada con un BUILD SUCCESSFUL que no la comprueba"
        )
        assert "BUILD SUCCESSFUL" in puertas[nombre].evidencia, (
            "la fila no registra que el build se ejecuto ni como termino"
        )


def test_las_puertas_rigurosas_no_las_aprueba_un_gradlew_build(tmp_path):
    """`jacocoTestCoverageVerification`, `mutationTest` y `releaseCheck` no
    forman parte de `build`: si el log no las menciona, nadie las ejecuto.
    """
    puertas = _puertas(vt.ejecutar(
        _proyecto(tmp_path, "function", LOG_FUNCTION_EXITOSO, tests=7), "riguroso"
    ))
    for nombre in ("Cobertura JaCoCo 95 / 85", "Mutacion PIT >= 85 %", "Build reproducible"):
        assert puertas[nombre].estado == "rojo"
        assert "no aparece" in puertas[nombre].evidencia.lower()


def test_el_certificado_dice_si_el_build_se_ejecuto_y_como_termino(tmp_path):
    """El minimo irrenunciable, leido sobre el documento entregable."""
    md_fallido = vt.render_markdown(vt.ejecutar(
        _proyecto(tmp_path / "a", "servlet", LOG_SERVLET_FALLIDO), "estandar"
    ))
    md_ausente = vt.render_markdown(vt.ejecutar(
        _proyecto(tmp_path / "b", "servlet", log=None), "estandar"
    ))
    assert "BUILD FAILED" in md_fallido
    assert "BUILD FAILED" not in md_ausente
    assert md_fallido != md_ausente


def test_una_puerta_resuelta_por_el_build_declara_su_insumo(tmp_path):
    """El log real de un proyecto recien andamiado trae `:test NO-SOURCE`, asi
    que para ver un recuento distinto de cero hay que derivarlo: se le quita
    esa marca, que es lo que imprime Gradle cuando la bateria SI corre. Lo
    demas del log sigue siendo el real.
    """
    raiz = _proyecto(tmp_path, "function", log=None, clases=4, tests=7)
    destino = raiz / salida_build.RUTA_POR_DEFECTO
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        LOG_FUNCTION_EXITOSO.read_text(encoding="utf-8").replace(
            "> Task :test NO-SOURCE", "> Task :test"
        ),
        encoding="utf-8",
    )

    puertas = _puertas(vt.ejecutar(raiz, "estandar"))
    assert "4 clases" in puertas[PUERTA_COMPILACION].insumo
    assert "7 tests" in puertas["Tests unitarios"].insumo


def test_un_NO_SOURCE_manda_sobre_un_XML_de_una_corrida_anterior(tmp_path):
    """La regla que hizo fallar al test de arriba, y que es la correcta: si
    esta vez no habia tests, fueron cero, por muchos resultados que hubieran
    quedado en `build/test-results` de antes. Un recuento heredado seria un
    insumo inventado.
    """
    puertas = _puertas(vt.ejecutar(
        _proyecto(tmp_path, "function", LOG_FUNCTION_EXITOSO, tests=7), "estandar"
    ))
    assert puertas["Tests unitarios"].insumo == contrato.linea_de_insumo(tests=0)


def test_el_orquestador_acepta_la_ruta_del_log_por_argumento(tmp_path):
    """La via explicita: quien ejecuto el build dice donde dejo su salida."""
    raiz = _proyecto(tmp_path, "function", log=None, tests=7)
    aparte = tmp_path / "otro-sitio.log"
    aparte.write_text(LOG_FUNCTION_EXITOSO.read_text(encoding="utf-8"), encoding="utf-8")
    puertas = _puertas(vt.ejecutar(raiz, "estandar", salida_build=aparte))
    assert puertas[PUERTA_SPOTBUGS].estado == "verde"


@pytest.mark.parametrize("nombre", sorted(vt.PUERTAS_DELEGADAS))
def test_toda_puerta_delegada_tiene_una_tarea_de_gradle_asociada(nombre):
    """La invariante que impide que la tabla vuelva a crecer con filas mudas:
    o el orquestador sabe que tarea mirar, o la puerta esta en la lista de las
    que un build no puede aprobar. Sin esto, anadir una puerta delegada nueva
    la devolveria en silencio al estado del hallazgo.
    """
    assert nombre in vt.TAREAS_POR_PUERTA or nombre in vt.PUERTAS_QUE_EL_BUILD_NO_APRUEBA


def test_la_reproducibilidad_no_la_aprueba_un_releaseCheck(tmp_path):
    """La mitad que el bucle de arriba NO puede cubrir, porque «Build
    reproducible» solo existe en RIGUROSO.

    Es LA correccion del ciclo 5 y hasta el ciclo 6 no la guardaba nada: quitar
    esa puerta del conjunto dejaba la suite entera en verde, y con un log que
    ejecutara `:releaseCheck` la fila volvia al VERDE VACUO que aquel ciclo
    quito. Ningun fixture de log contenia `:releaseCheck`, asi que la rama ni
    siquiera se ejecutaba: se fabrica aqui.
    """
    # El proyecto PRIMERO y el log despues, con su fecha adelantada a mano. El
    # orden importaba sin decirlo: escribiendo el log antes, `docs/contrato.md`
    # quedaba mas nuevo, y este test mataba por accidente una mutacion sobre el
    # conjunto de insumos del build --con un mensaje que habla de
    # `:releaseCheck` y no menciona la frescura--. Un guardian que muere por
    # una razon que no es la suya no dice lo que parece. Levantado por el gate
    # del ciclo 16; la asimetria que aquello tapaba tiene test propio abajo.
    import os

    proyecto = _proyecto(tmp_path / "p", "function", LOG_FUNCTION_EXITOSO, tests=7)
    log = LOG_FUNCTION_EXITOSO.read_text(encoding="utf-8").replace(
        "BUILD SUCCESSFUL", "> Task :releaseCheck\nBUILD SUCCESSFUL", 1
    )
    ruta = tmp_path / "salida-build.log"
    ruta.write_text(log, encoding="utf-8")
    mas_nuevo = max(p.stat().st_mtime for p in proyecto.rglob("*") if p.is_file())
    os.utime(ruta, (mas_nuevo + 60, mas_nuevo + 60))
    puertas = _puertas(vt.ejecutar(proyecto, "riguroso", salida_build=ruta))

    fila = puertas["Build reproducible"]
    assert fila.estado == "delegada", (
        f"con `:releaseCheck` en verde la puerta salio «{fila.estado}»: un BUILD "
        f"SUCCESSFUL no puede aprobar una reproducibilidad que nadie comprueba"
    )
    assert "NO la comprueba" in fila.evidencia, fila.evidencia


def test_el_comando_de_captura_es_EL_MISMO_en_la_SKILL_y_en_el_script():
    """Dos sitios publican esta cadena, y pueden divergir en silencio.

    El paso 5 de la SKILL la escribe en un bloque para que un humano la copie,
    y `salida_build.COMANDO_DE_CAPTURA` la reutiliza en su mensaje de error
    --«se captura con: ...»--. Divergir significa que la puerta manda ejecutar
    una cosa y el error de esa misma puerta sugiere otra.

    Y el `mkdir -p build` va comprobado APARTE, con el literal escrito aqui,
    porque es la mitad que arregla el defecto: sin el, el shell abre la
    redireccion antes de lanzar Gradle y sobre un proyecto recien andamiado
    --donde `build/` no existe todavia, que es justo cuando esta puerta manda
    capturar por primera vez-- el comando falla con «No such file or
    directory» y no se construye nada. Comparar solo «las dos cadenas son
    iguales» dejaria pasar que las dos perdieran el `mkdir` a la vez.
    Levantado por el gate del ciclo 10.
    """
    import re

    raiz = pathlib.Path(__file__).resolve().parents[1]
    # TODA la skill, no solo `SKILL.md`. El gate del ciclo 12 encontro un TERCER
    # ejemplar del comando: al podar el paso 5, el detalle se mudo a
    # `referencias/certificado.md`, y ese es justo el sitio al que la SKILL
    # manda al lector para lo fino. El guardian miraba dos sitios y la copia
    # que podia divergir en silencio era la que nadie vigilaba.
    dir_skill = raiz / "skills" / "crear-plugin-appian"
    fuentes = [dir_skill / "SKILL.md", *sorted((dir_skill / "referencias").glob("*.md"))]

    # El barrido reconoce el comando por su FORMA --invoca `gradlew` y redirige a
    # algun sitio--, y a proposito NO por el nombre del fichero al que redirige.
    # Filtrar por «salida-build.log» era lo que dejaba sin dientes al aserto de
    # mas abajo: toda linea que llegaba a el ya contenia ese nombre por
    # construccion, asi que no podia fallar nunca. Filtrar por «gradlew build»
    # tampoco vale --dejaria fuera la traduccion a PowerShell, `.\\gradlew.bat`,
    # que es justo la copia que este guardian tenia que empezar a ver--. La
    # redireccion es lo unico que distingue un comando de una mencion en prosa.
    # Levantado por el /code-review del ciclo 12 y por el gate del ciclo 13.
    def es_comando_de_captura(linea: str) -> bool:
        return "gradlew" in linea and ">" in linea

    citadas = [
        (ruta.name, linea.strip())
        for ruta in fuentes
        for linea in ruta.read_text(encoding="utf-8").splitlines()
        if es_comando_de_captura(linea)
    ]
    assert citadas, "la SKILL dejo de publicar el comando de captura: nadie sabria como generarlo"
    # Suelo antivacuidad de la ampliacion: si el comando desaparece de las
    # referencias, este bucle vuelve a mirar un solo fichero sin decirlo.
    assert any(nombre != "SKILL.md" for nombre, _ in citadas), (
        "ninguna referencia publica ya el comando de captura: o se movio otra vez, o este "
        "guardian volvio a vigilar solo SKILL.md sin que nadie se entere"
    )

    # Las copias POSIX se comparan literales; la de PowerShell es otra lengua y
    # se le exige lo que NO puede divergir: el mismo fichero de log --que es lo
    # que el orquestador va a buscar-- y el `--console=plain`, que no es
    # opcional en ningun shell. Compararla con `COMANDO_DE_CAPTURA` habria
    # obligado a borrarla, y un usuario de Windows se queda sin comando.
    powershell = [(n, l) for n, l in citadas if "gradlew.bat" in l]
    assert powershell, (
        "ya no hay bloque de PowerShell con el comando de captura: en 5.1 el `&&` de la "
        "forma POSIX es error de parseo, asi que sin el no hay comando que copiar en Windows"
    )
    fichero_de_log = salida_build.RUTA_POR_DEFECTO.name
    # Suelo antivacuidad del aserto que viene justo debajo, y la razon de que el
    # filtro no mire el nombre del log: una copia que redirija a OTRO fichero
    # tiene que ENTRAR en `citadas`, o el aserto no puede fallar nunca. Se
    # comprueba contra el mismo predicado que construye la lista, no contra una
    # reescritura suya: si alguien vuelve a meter «salida-build.log» en el
    # filtro, esto se pone rojo antes de que la vacuidad vuelva a colarse.
    intrusa = ".\\gradlew.bat build --console=plain > build\\gradle-otro.log 2>&1"
    assert fichero_de_log not in intrusa, "la linea intrusa dejo de ser intrusa"
    assert es_comando_de_captura(intrusa), (
        "el filtro de `citadas` volvio a presuponer el nombre del fichero de log: una copia que "
        "redirija a otro sitio ya no entra en la lista, asi que el aserto que exige "
        f"«{fichero_de_log}» no podria fallar nunca -> «{intrusa}»"
    )
    for nombre, linea in powershell:
        assert fichero_de_log in linea, (
            f"`{nombre}` publica un comando de PowerShell que escribe en otro sitio que "
            f"«{fichero_de_log}»: el orquestador lo buscara donde no esta -> «{linea}»"
        )
        assert "--console=plain" in linea, (
            f"`{nombre}` publica un comando de PowerShell sin `--console=plain`: el log sale "
            f"con codigos de control y el lector no lo reconoce -> «{linea}»"
        )

    # Son DOS las formas canonicas: la corriente y la de RIGUROSO, que anade
    # `releaseCheck` porque tres de las cuatro puertas de ese perfil no forman
    # parte de `build`. Las dos viven en `salida_build` y las dos las publica
    # la skill; lo que no se admite es una tercera escrita a mano.
    canonicas = {salida_build.COMANDO_DE_CAPTURA, salida_build.COMANDO_DE_CAPTURA_RIGUROSO}
    for nombre, linea in citadas:
        if "gradlew.bat" in linea:
            continue
        assert linea in canonicas, (
            f"`{nombre}` publica «{linea}» y el script sugiere "
            f"«{salida_build.COMANDO_DE_CAPTURA}» o «{salida_build.COMANDO_DE_CAPTURA_RIGUROSO}»: "
            f"la puerta manda una cosa y su propio error sugiere otra"
        )
    # Suelo antivacuidad de la ampliacion: si la skill dejara de publicar el
    # comando de RIGUROSO, el bucle de arriba seguiria verde mirando solo la
    # forma corriente, y volveriamos al bucle que esto vino a cerrar --tres
    # puertas en rojo y ningun comando que copiar-.
    assert any(l == salida_build.COMANDO_DE_CAPTURA_RIGUROSO for _, l in citadas), (
        "la skill dejo de publicar el comando de captura de RIGUROSO: sin el, sus tres puertas "
        "que no forman parte de `build` salen rojas para siempre y nadie sabe con que arreglarlo"
    )

    # Las dos mitades del arreglo, con literales propios.
    assert re.match(r"mkdir -p build\s*&&\s*\./gradlew build", salida_build.COMANDO_DE_CAPTURA), (
        f"el comando volvio a redirigir a `build/` sin crearlo antes: {salida_build.COMANDO_DE_CAPTURA}"
    )
    assert "> build/salida-build.log 2>&1" in salida_build.COMANDO_DE_CAPTURA, salida_build.COMANDO_DE_CAPTURA
    assert salida_build.COMANDO_DE_CAPTURA.endswith(salida_build.RUTA_POR_DEFECTO.as_posix() + " 2>&1"), (
        f"el comando captura en un sitio y `RUTA_POR_DEFECTO` lee en otro: "
        f"{salida_build.COMANDO_DE_CAPTURA} frente a {salida_build.RUTA_POR_DEFECTO.as_posix()}"
    )


# --- Lo que la referencia afirma sobre el coste del `2>&1` de PowerShell ----
# `certificado.md` justifica meter la redireccion dentro de `cmd`. El ciclo 14
# midio que la justificacion escrita era falsa en tres puntos: solo la PRIMERA
# linea de stderr sale decorada, un build bueno no se estropea porque
# `BUILD SUCCESSFUL` va por stdout, y sobre todo la puerta NO cambia de color
# --lo que cambia es el motivo publicado--. La frase se reescribio; esto ancla
# la mitad comprobable, que es la que sostiene el argumento.


def test_un_log_ILEGIBLE_y_uno_FALLIDO_pintan_la_misma_puerta_del_MISMO_color(tmp_path):
    """Si algun dia `indeterminado` dejara de pintar rojo, la frase de
    `certificado.md` --«la puerta la pinta roja igual que fallido»-- pasaria a
    ser mentira, y con ella el motivo por el que se recomienda `cmd /c`.
    """
    truncado = LOG_FUNCTION_EXITOSO.read_text(encoding="utf-8").split("BUILD SUCCESSFUL")[0]
    assert salida_build.analizar(truncado).desenlace == salida_build.INDETERMINADO
    assert not salida_build.analizar(truncado).consta

    # El log truncado SE ESCRIBE en el proyecto. Pasar `None` --como hacia la
    # primera version de este test-- no escribe log ninguno, y eso es `ausente`,
    # no `indeterminado`: el estado que el test dice vigilar no llegaba nunca a
    # la puerta y se le podia quitar el rojo a `indeterminado` con los 546 tests
    # en verde. Levantado por el gate del ciclo 15.
    ilegible = _puertas(vt.ejecutar(
        _proyecto(tmp_path / "ilegible", "function", truncado), "estandar"
    ))
    fallido = _puertas(vt.ejecutar(
        _proyecto(tmp_path / "fallido", "servlet", LOG_SERVLET_FALLIDO), "estandar"
    ))
    for nombre in (PUERTA_SPOTBUGS, PUERTA_COMPILACION):
        assert ilegible[nombre].estado == fallido[nombre].estado == "rojo", (
            f"«{nombre}»: un build cuyo desenlace no consta y uno que fallo ya no pintan igual "
            f"({ilegible[nombre].estado} vs {fallido[nombre].estado}). La referencia dice que "
            f"si, y de ahi cuelga su argumento de por que `cmd /c` gana FIDELIDAD y no color"
        )
    # Y lo que SI cambia es el motivo, que es justo lo que la referencia promete.
    assert ilegible[PUERTA_SPOTBUGS].evidencia != fallido[PUERTA_SPOTBUGS].evidencia, (
        "los dos casos publican la misma evidencia, asi que no habria ninguna fidelidad que "
        "ganar y la recomendacion de `cmd /c` se quedaria sin motivo"
    )


# --- El guardian de FAMILIA: corregir un recurso y no reconstruir -----------
# Los ciclos 14 y 15 encontraron el mismo defecto tres veces, en tres
# artefactos derivados distintos (log, certificado, JAR). No es un fallo por
# artefacto: es que la nocion de «insumo» era mas estrecha que lo que el build
# consume. Este test vigila el ESCENARIO, no una instancia — el que fabrica el
# propio Proceso: el paso 6 manda corregir, la correccion canonica que la guia
# documenta como bloqueante vive en `src/main/resources/`, y volver al paso 5
# sin reconstruir dejaba pasar un JAR con el error dentro.


def _recurso_tocado_despues(raiz: pathlib.Path, relativa: str) -> pathlib.Path:
    """Escribe un recurso con fecha POSTERIOR a todo lo que ya hay en `raiz`."""
    import os

    ruta = raiz / relativa
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("corregido despues del build\n", encoding="utf-8")
    ya_hay = max(
        (p.stat().st_mtime for p in raiz.rglob("*") if p.is_file() and p != ruta),
        default=0.0,
    )
    os.utime(ruta, (ya_hay + 3600, ya_hay + 3600))
    return ruta


@pytest.mark.parametrize("recurso", [
    "src/main/resources/appian-plugin.xml",
    "src/main/resources/com/raul/appian/ejemplo/bundle_en_US.properties",
])
def test_corregir_un_RECURSO_sin_reconstruir_deja_el_log_RANCIO(recurso, tmp_path):
    """Los dos ficheros donde viven los bloqueantes de despliegue que la guia
    documenta —`paletteCategory` y el formato de claves del `.properties`— y
    que el glob de `.java` no veia.
    """
    raiz = _proyecto(tmp_path, "function", LOG_FUNCTION_EXITOSO, tests=7)
    tocado = _recurso_tocado_despues(raiz, recurso)

    resultado = salida_build.ingerir(raiz)
    assert resultado.desenlace == salida_build.RANCIO, (
        f"se corrigio `{recurso}` DESPUES del build y el log sigue contando como constancia "
        f"({resultado.desenlace}): certifica un artefacto que ya no es el que se entrega"
    )
    assert not resultado.consta
    assert tocado.name in resultado.motivo, (
        f"el motivo no nombra `{tocado.name}`, asi que el lector no sabe que hay que "
        f"reconstruir -> «{resultado.motivo}»"
    )


def test_esa_rancidez_LLEGA_A_LA_TABLA_y_no_se_queda_en_el_lector(tmp_path):
    """La mitad que importa de la costura: que el orquestador lo pinte. Sin
    esto, `ingerir` podria devolver RANCIO y el certificado salir verde igual.
    """
    raiz = _proyecto(tmp_path, "function", LOG_FUNCTION_EXITOSO, tests=7)
    _recurso_tocado_despues(raiz, "src/main/resources/appian-plugin.xml")

    puertas = _puertas(vt.ejecutar(raiz, "estandar"))
    delegadas = [n for n in vt.PUERTAS_DELEGADAS if n in puertas]
    assert delegadas, "no hay puertas delegadas en ESTANDAR: este test no mira nada"
    for nombre in delegadas:
        assert puertas[nombre].estado == "rojo", (
            f"«{nombre}» sale {puertas[nombre].estado} sobre un build cuyo log es anterior a "
            f"la ultima correccion: es el verde sobre un artefacto rancio que el gate del "
            f"ciclo 15 reprodujo"
        )


def test_TOCAR_EL_CONTRATO_ensucia_el_certificado_pero_NO_el_log_del_build(tmp_path):
    """La asimetria entre los dos conjuntos de insumos, por fin con guardian.

    `docs/contrato.md` esta en los insumos del CERTIFICADO --tres puertas lo
    leen-- y no en los del BUILD, porque `./gradlew build` no lo abre. Esa
    direccion estaba cubierta solo por accidente: la mataba un test cuyo tema
    es `:releaseCheck`, por el orden en que su fixture escribia los ficheros.
    Un reordenamiento inocuo la dejaba sin nadie. Levantado por el gate del
    ciclo 16.
    """
    import os

    raiz = _proyecto(tmp_path, "function", LOG_FUNCTION_EXITOSO, tests=7)
    cert = raiz / "docs" / "CERTIFICADO.md"
    cert.write_text("# Certificado\n", encoding="utf-8")

    contrato_md = raiz / "docs" / "contrato.md"
    ya_hay = max(p.stat().st_mtime for p in raiz.rglob("*") if p.is_file())
    os.utime(contrato_md, (ya_hay + 3600, ya_hay + 3600))

    # El log NO se ensucia: el build no lee el contrato.
    resultado = salida_build.ingerir(raiz)
    assert resultado.desenlace == salida_build.EXITOSO, (
        f"editar `docs/contrato.md` dejo RANCIO el log del build ({resultado.desenlace}), y el "
        f"build no lo lee: seria un rojo sobre un artefacto que nadie ha invalidado"
    )

    # El certificado SI: tres puertas leen ese contrato.
    posterior = salida_build.fuente_posterior_a(raiz, cert)
    assert posterior is not None and posterior.name == "contrato.md", (
        f"editar `docs/contrato.md` despues de certificar no marca rancio el certificado "
        f"({posterior}), y es insumo de tres puertas y de la firma congelada del dossier"
    )


# --- Los dos arreglos del ciclo 16 que no tenian NINGUN test ----------------
# El auditor del ciclo 17 los encontro asi: quitar las tres entradas nuevas de
# `FUENTES_QUE_INVALIDAN`, o volver al orden alfabetico de los JAR, dejaba la
# suite ENTERA en verde. No eran verdes vacuos --el trabajo estaba hecho y sus
# sondas lo comprobaron-- pero un revert silencioso se los llevaba sin que nada
# se enterase. Los dos guardianes entran por donde el arreglo se usa, no por
# donde se escribio.


@pytest.mark.parametrize("relativa", [
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "gradle/wrapper/gradle-wrapper.properties",
])
def test_los_INSUMOS_DE_RAIZ_del_jar_ensucian_el_log_del_build(relativa, tmp_path):
    """Los tres los consume el `jar`: los dos textos legales acaban en
    `META-INF` --y R-J07 los lee de dentro del artefacto-- y el wrapper fija la
    version de Gradle con la que se construyo.
    """
    raiz = _proyecto(tmp_path, "function", LOG_FUNCTION_EXITOSO, tests=7)
    tocado = _recurso_tocado_despues(raiz, relativa)

    resultado = salida_build.ingerir(raiz)
    assert resultado.desenlace == salida_build.RANCIO, (
        f"se toco `{relativa}` DESPUES del build y el log sigue contando como constancia "
        f"({resultado.desenlace}): ese fichero viaja dentro del JAR que el log certifica"
    )
    assert tocado.name in resultado.motivo, resultado.motivo


def test_la_capa_4_analiza_el_JAR_MAS_NUEVO_y_no_el_primero_por_orden(tmp_path):
    """`build` no limpia, asi que tras subir version conviven dos JAR. El orden
    alfabetico elegia el de version MENOR y las nueve reglas de empaquetado
    certificaban el artefacto que ya no se entrega.

    Las fechas van puestas a mano: con `st_mtime` iguales el sort estable cae al
    orden del `glob` y el guardian seria intermitente. Lo aviso porque la lente
    que levanto esto lo aviso primero.
    """
    import os

    raiz = _proyecto(tmp_path, "function", LOG_FUNCTION_EXITOSO, tests=7)
    libs = raiz / "build" / "libs"
    for p in libs.glob("*.jar"):
        p.unlink()

    viejo, nuevo = libs / "plugin-0.1.0.jar", libs / "plugin-0.2.0.jar"
    with zipfile.ZipFile(viejo, "w") as z:
        z.writestr("appian-plugin.xml", "<appian-plugin/>")
    with zipfile.ZipFile(nuevo, "w") as z:
        z.writestr("appian-plugin.xml", "<appian-plugin/>")
        for i in range(5):
            z.writestr(f"relleno{i}.txt", "x")
    os.utime(viejo, (1_000_000, 1_000_000))
    os.utime(nuevo, (1_003_600, 1_003_600))

    puerta = _puertas(vt.ejecutar(raiz, "estandar"))["Empaquetado y cierre de dependencias"]
    assert "6 entradas" in puerta.insumo, (
        f"la capa 4 analizo el JAR equivocado: dice «{puerta.insumo}» y el JAR vigente "
        f"—`{nuevo.name}`, el mas nuevo— tiene 6 entradas frente a la 1 del viejo. "
        f"Alfabeticamente el viejo va primero, que es el defecto que esto vigila"
    )
