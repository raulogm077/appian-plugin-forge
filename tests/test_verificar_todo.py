import importlib.util
import pathlib
import re
import subprocess
import sys
import zipfile

import pytest

RAIZ_SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"

import contrato
import verificar_todo as vt


def test_la_CLI_del_orquestador_arranca_y_deja_certificado(tmp_path):
    """El `main()` de `verificar_todo.py`, ejecutado COMO PROCESO.

    El hueco que cierra: hasta ahora el unico sitio del repositorio que
    ejecutaba este script como proceso era el humo E2E, que la suite rapida
    deselecciona (`pytest.ini`, `-m "not e2e"`). Los 434 tests rapidos entraban
    por `vt.ejecutar(...)` en el mismo proceso, asi que un `NameError` en
    `main()` --un import que se fue de la cabecera, exactamente lo que paso--
    daba 434 verdes con la CLI del orquestador COMPLETAMENTE rota. Un fallo asi
    solo aparecia despues de construir con Gradle, minutos mas tarde.

    Sobre un proyecto vacio tarda ~2 s y no necesita build: no hay nada que
    verificar, asi que todas las puertas salen en rojo o pendientes y el
    certificado dice justo eso. Lo que se afirma aqui no es el veredicto --de
    eso van los demas tests-- sino que el proceso ARRANCA, escribe el fichero
    y sale con un codigo coherente.
    """
    proceso = subprocess.run(
        [sys.executable, str(RAIZ_SCRIPTS / "verificar_todo.py"), str(tmp_path), "estandar"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    certificado = tmp_path / "docs" / "CERTIFICADO.md"
    assert certificado.is_file(), f"no dejo certificado; stderr:\n{proceso.stderr[-2000:]}"
    assert not proceso.stderr.strip(), f"arranco con ruido en stderr:\n{proceso.stderr}"
    # Un proyecto sin construir NO esta listo, y el codigo de salida acompana:
    # hay puertas en rojo que no son las dos estructurales.
    assert proceso.returncode == 1
    assert vt.NO_LISTO in certificado.read_text(encoding="utf-8")


def _git(destino, *argumentos):
    return subprocess.run(
        ["git", "-C", str(destino), *argumentos], capture_output=True, text=True
    )


def _repo_con_un_commit(destino):
    destino.mkdir(parents=True, exist_ok=True)
    _git(destino, "init", "-q")
    (destino / "a.txt").write_text("x", encoding="utf-8")
    _git(destino, "add", ".")
    _git(destino, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x")
    return destino


def test_la_revision_no_se_resuelve_a_favor_sin_repositorio_ni_sin_commits(tmp_path):
    """No poder atar el certificado a un commit se DICE, no se calla."""
    assert "sin repositorio" in vt._revision_git(tmp_path / "no-existe")

    vacio = tmp_path / "sin-commits"
    vacio.mkdir()
    _git(vacio, "init", "-q")
    # `--porcelain=v2 --branch` responde `(initial)` aqui, y eso no es un sha.
    assert "sin ningun commit" in vt._revision_git(vacio)


def test_un_fichero_SIN_SEGUIMIENTO_ya_marca_el_arbol_como_sucio(tmp_path):
    """El caso por el que la revision NO se resuelve con `git describe --dirty`.

    `--dirty` se apoya en `diff-index` y IGNORA los ficheros sin seguimiento, asi
    que un arbol con un fuente nuevo sin anadir se declararia limpio y el
    certificado diria describir un commit que no contiene ese fichero. En un
    documento cuya funcion es la honestidad, esa diferencia no es un detalle:
    por eso se lee `status --porcelain=v2 --branch`, que si los ve.
    """
    repo = _repo_con_un_commit(tmp_path / "repo")
    limpio = vt._revision_git(repo)
    assert "sin commitear" not in limpio, limpio

    (repo / "nuevo.txt").write_text("y", encoding="utf-8")
    assert "sin commitear" in vt._revision_git(repo)
    # Y el sha sigue siendo el mismo: lo que cambia es la marca, no la revision.
    assert vt._revision_git(repo).startswith(limpio)


def cert(perfil="estandar", puertas=()):
    return vt.Certificado(perfil=perfil, puertas=list(puertas), listo_para_sumision=False)


def test_las_dos_filas_no_verificables_siempre_estan_y_en_rojo():
    c = vt.certificado_base("estandar")
    nombres = {p.nombre for p in c.puertas if p.estado == "rojo"}
    assert "Resolucion OSGi en la plataforma" in nombres
    assert "Ejecucion en Appian real" in nombres


def test_perfil_estandar_no_incluye_puertas_rigurosas():
    c = vt.certificado_base("estandar")
    nombres = {p.nombre for p in c.puertas}
    assert "Mutacion PIT >= 85 %" not in nombres


def test_perfil_riguroso_incluye_sus_puertas():
    c = vt.certificado_base("riguroso")
    nombres = {p.nombre for p in c.puertas}
    assert "Mutacion PIT >= 85 %" in nombres
    assert "Build reproducible" in nombres


def test_una_puerta_no_ejecutada_nunca_se_marca_como_pasada():
    c = vt.certificado_base("estandar")
    for p in c.puertas:
        assert p.estado != "verde" or p.evidencia, (
            f"la puerta «{p.nombre}» esta en verde sin evidencia"
        )


def test_el_markdown_declara_el_perfil():
    c = vt.certificado_base("riguroso")
    md = vt.render_markdown(c)
    assert "RIGUROSO" in md
    assert "NO VERIFICADO" in md


def test_todo_verde_es_falso_si_hay_una_puerta_roja():
    c = vt.certificado_base("estandar")
    assert vt.calcular_todo_verde(c.puertas) is False


# --- El estado de sumision: lo que el certificado ya calculaba y no publicaba
#
# `calcular_todo_verde` exige que TODAS las puertas esten verdes, y las dos
# ultimas van SIEMPRE en rojo por diseno: en un certificado real nunca podia
# ser cierto. Ademas no se imprimia en ninguna parte ni entraba en el codigo de
# salida, asi que el veredicto agregado mas riguroso del sistema era invisible.
# `estado_de_sumision` es el criterio de la SKILL (paso 5, tres partes),
# EXCLUYENDO las dos filas que el propio certificado declara no verificables.


def _todas_verdes(perfil="estandar"):
    """Un certificado en el mejor estado alcanzable de verdad."""
    import contrato

    c = vt.certificado_base(perfil)
    nunca = {n for n, _ in vt.PUERTAS_NUNCA_VERIFICABLES}
    for p in c.puertas:
        if p.nombre in nunca or p.estado == "informativa":
            continue
        if p.nombre in vt.PUERTAS_QUE_EL_BUILD_NO_APRUEBA:
            p.estado, p.evidencia = "delegada", "BUILD SUCCESSFUL, que NO la comprueba"
            continue
        p.estado, p.insumo = "verde", contrato.linea_de_insumo(clases=3)
    return c


def test_las_dos_filas_siempre_rojas_no_impiden_el_ready():
    """Son el limite honesto de la verificacion local, no un defecto del
    plug-in. Si contaran, el estado seria NOT_READY para siempre y una alarma
    que salta siempre ensena a ignorarla."""
    listo, motivos = vt.estado_de_sumision(_todas_verdes().puertas)
    assert listo is True, motivos


def test_una_puerta_pendiente_impide_el_ready():
    c = _todas_verdes()
    c.puertas[0].estado = "no-ejecutada"
    listo, motivos = vt.estado_de_sumision(c.puertas)
    assert listo is False
    assert any(c.puertas[0].nombre in m for m in motivos)


def test_un_verde_sobre_insumo_vacio_impide_el_ready():
    """La titular antifalso-verde del sistema, por fin con consecuencia: antes
    quedaba marcada en una celda y nadie la leia."""
    import contrato

    c = _todas_verdes()
    c.puertas[0].insumo = contrato.linea_de_insumo(clases=0)
    listo, motivos = vt.estado_de_sumision(c.puertas)
    assert listo is False
    assert any("insumo" in m for m in motivos)


def test_una_delegada_que_el_build_si_podia_aprobar_impide_el_ready():
    """Delegar no es aprobar. Solo las dos que un BUILD SUCCESSFUL no puede
    juzgar tienen derecho a quedarse en «delegada»."""
    c = _todas_verdes()
    puerta = next(p for p in c.puertas if p.nombre == "Tests unitarios")
    puerta.estado = "delegada"
    listo, motivos = vt.estado_de_sumision(c.puertas)
    assert listo is False
    assert any("Tests unitarios" in m for m in motivos)


def test_un_aviso_viaja_a_la_evidencia_aunque_la_puerta_salga_verde():
    """El modo degradado del escaner de superficie tiene que verse.

    Sin `assets/indice-tipos-26.3.json`, `verificar_superficie` valida contra
    una red gruesa de seis prefijos de paquete que «deja pasar clases no
    documentadas», e imprime un AVISO. Pero lo imprime ANTES del resumen, y la
    evidencia de una puerta verde era la ULTIMA linea: el certificado decia
    «Inventario de API escrito...» y nada mas. Una validacion mucho mas laxa,
    indistinguible de una completa. Un falso verde latente.
    """
    salida = (
        "AVISO: sin indice de tipos; filtro por paquete (declararlo en el certificado)\n"
        "INSUMO 9 clases, 4 tipos de appian\n"
        "Inventario de API escrito en build/reports/inventario-api.json (4 tipos)"
    )
    evidencia = vt._evidencia(salida, "", "verde")
    assert "sin indice de tipos" in evidencia, (
        f"el aviso no llego a la evidencia del certificado: {evidencia!r}"
    )
    assert "Inventario de API escrito" in evidencia, "y el resumen no debe perderse"


def test_sin_avisos_la_evidencia_sigue_siendo_la_ultima_linea():
    assert vt._evidencia("INSUMO 3 clases\n0 hallazgos (0 errores)", "", "verde") == (
        "0 hallazgos (0 errores)"
    )


def test_solo_una_puerta_puede_ser_informativa():
    """`informativa` no bloquea el READY, y es el UNICO estado compatible con
    READY que se asigna al nacer en vez de ganarse ejecutando algo.

    Que hoy sea correcto --la deriva contra la version del entorno no esta
    mecanizada, es insumo de la Fase 3-- no lo protege de manana: el dia que
    alguien marcara una segunda puerta como informativa para quitarsela de
    encima, tendria un pase libre al READY sin que nada se ejecutara. Esa es
    exactamente la via limpia que este sistema persigue en todas sus formas.
    """
    for perfil in ("estandar", "riguroso"):
        informativas = [
            p.nombre for p in vt.certificado_base(perfil).puertas if p.estado == "informativa"
        ]
        assert informativas == [vt.PUERTA_INFORMATIVA], (
            f"perfil {perfil}: se esperaba exactamente una puerta informativa "
            f"({vt.PUERTA_INFORMATIVA}), hay {informativas}"
        )


def _linea_de_status(md: str) -> str:
    """La linea del veredicto, aislada.

    Buscar la cadena en el documento entero no sirve: el pie explica que exige
    READY_FOR_APPIAN_SUBMISSION y menciona el termino de forma legitima. Lo que
    decide es la cabecera.
    """
    return next(l for l in md.splitlines() if l.startswith("**STATUS:"))


def test_el_certificado_publica_el_estado_de_sumision():
    assert vt.LISTO in _linea_de_status(vt.render_markdown(_todas_verdes()))


def test_el_certificado_dice_por_que_no_esta_listo():
    c = vt.certificado_base("estandar")  # recien creado: casi todo pendiente
    md = vt.render_markdown(c)
    assert _linea_de_status(md) == f"**STATUS: {vt.NO_LISTO}**"
    # Y no basta con decir que no: hay que decir QUE lo impide, puerta a puerta.
    assert "Que impide enviarlo" in md
    assert "Reglas del framework de Appian" in md


def test_la_cabecera_declara_el_indice_y_la_revision():
    """Sin el hash del indice, nada prueba contra que superficie se valido; sin
    la revision, nada ata el certificado a un estado del fuente. La SKILL ya
    prometia los dos y el certificado no los llevaba."""
    c = _todas_verdes()
    c.indice = "26.3 · sha256 9b8d1fa5"
    c.revision = "ace34b5"
    md = vt.render_markdown(c)
    assert "9b8d1fa5" in md
    assert "ace34b5" in md


def test_salida_en_blanco_no_lanza_indexerror(monkeypatch, tmp_path):
    """Ronda de correccion 1 (equipo): `[-1:][0]` sobre una lista vacia lanza
    IndexError cuando la salida combinada del subprocess es solo espacios en
    blanco -- verdadera para el `or` (no vacia), pero `.splitlines()` de la
    cadena ya sin espacios (tras strip()) es una lista vacia. Se provoca
    forzando esa salida en las cuatro invocaciones reales via monkeypatch de
    subprocess.run: no hace falta ningun fichero real del proyecto porque el
    subprocess nunca llega a ejecutarse de verdad.
    """

    class ProcesoFalso:
        returncode = 1
        stdout = "   \n   "
        stderr = ""

    monkeypatch.setattr("subprocess.run", lambda *a, **k: ProcesoFalso())

    cert = vt.ejecutar(tmp_path, "estandar")  # no debe lanzar IndexError

    puertas_con_invocacion = (
        "Reglas del framework de Appian",
        "Politicas AppMarket",
        "Bundles y locales",
        "Superficie documentada · indice 26.3",
    )
    por_nombre = {p.nombre: p for p in cert.puertas}
    for nombre in puertas_con_invocacion:
        assert por_nombre[nombre].estado == "rojo"
        assert por_nombre[nombre].evidencia == "sin salida"


# ---------------------------------------------------------------------------
# C3 · la capa 4 entera no se ejecutaba nunca, y el criterio de salida de la
# SKILL era insatisfacible tal como se entregaba.
#
# `verificar_jar.py` --nueve reglas documentadas-- no tenia ningun llamador en
# el repositorio, y el orquestador enganchaba 4 de las 11 puertas: las otras
# siete se quedaban en «pendiente» para siempre. La SKILL, mientras tanto,
# exigia que ninguna puerta quedara en pendiente. Nadie podia cumplirlo.
#
# La correccion tiene dos mitades y las dos importan: enganchar lo que SI se
# puede ejecutar (la capa 4, sobre el JAR ya construido) y declarar con su
# motivo lo que no (lo que ejecuta Gradle en el paso BUILD). Un criterio que
# dice la verdad vale mas que uno que nadie puede cumplir.
# ---------------------------------------------------------------------------


def test_ninguna_puerta_se_queda_sin_explicacion():
    """La invariante del certificado: cada fila dice o su resultado o por que
    no lo tiene. «pendiente» a secas era la unica sin explicacion, y era la
    mayoria de la tabla.
    """
    c = vt.certificado_base("riguroso")
    sin_explicar = [p.nombre for p in c.puertas if p.estado == "no-ejecutada" and not p.evidencia]
    ejecutables = set(vt.PUERTAS_CON_INVOCACION)
    assert [n for n in sin_explicar if n not in ejecutables] == [], (
        "hay puertas en «pendiente» sin motivo y sin invocacion que las ejecute"
    )


def test_la_capa_4_tiene_llamador():
    assert "Empaquetado y cierre de dependencias" in vt.PUERTAS_CON_INVOCACION


def test_una_puerta_delegada_no_cuenta_como_verde():
    """Delegar no es aprobar. Si `delegada` colara como verde, el mecanismo
    de declarar motivos se convertiria en la via para blanquear puertas.
    """
    puertas = [vt.Puerta("X", "ambos", "verde", "ok"), vt.Puerta("Y", "ambos", "delegada", "Gradle")]
    assert vt.calcular_todo_verde(puertas) is False


def test_las_puertas_delegadas_declaran_quien_las_ejecuta():
    c = vt.certificado_base("riguroso")
    delegadas = [p for p in c.puertas if p.estado == "delegada"]
    assert delegadas, "ninguna puerta declara delegacion; el resto de la tabla mentiria"
    for p in delegadas:
        assert p.evidencia, f"la puerta delegada «{p.nombre}» no dice quien la ejecuta"
    md = vt.render_markdown(c)
    assert "delegada" in md


def _proyecto_minimo(raiz: pathlib.Path, con_jar: bool) -> pathlib.Path:
    """Un proyecto generado de mentira, con lo justo para que el orquestador
    encuentre lo que busca. No compila nada: aqui solo se comprueba el
    cableado del orquestador, no las reglas.

    `docs/contrato.md` se fabrica a mano aqui a proposito (aislar el
    cableado de `verificar_todo` de `andamiar.generar()`): la costura REAL
    entre las dos --que `generar()` de verdad escriba ese fichero-- la cubre
    ahora el humo E2E (`test_humo_e2e.py`, Critico 2 del gate de ciclo 1).
    """
    (raiz / "docs").mkdir(parents=True, exist_ok=True)
    (raiz / "docs" / "contrato.md").write_text(
        (pathlib.Path(__file__).resolve().parent / "fixtures" / "contratos"
         / "smart-service-minimo.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    if con_jar:
        libs = raiz / "build" / "libs"
        libs.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(libs / "archivar.jar", "w") as z:
            z.writestr("appian-plugin.xml", "<appian-plugin/>")
    return raiz


def test_sin_JAR_la_puerta_de_empaquetado_es_ROJA_no_pendiente(tmp_path):
    """Coherente con como tratan los validadores de clases la ausencia de
    clases: no poder mirar el artefacto no es «ya lo miraremos», es no
    verificado.
    """
    cert = vt.ejecutar(_proyecto_minimo(tmp_path, con_jar=False), "estandar")
    puerta = {p.nombre: p for p in cert.puertas}["Empaquetado y cierre de dependencias"]
    assert puerta.estado == "rojo"
    assert "JAR" in puerta.evidencia


def test_con_JAR_la_capa_4_se_ejecuta_de_verdad(tmp_path):
    """El JAR de este test esta deliberadamente incompleto —solo lleva el
    descriptor—, asi que la puerta tiene que salir ROJA citando reglas R-J.
    Verde aqui significaria que la invocacion no llego a correr.
    """
    cert = vt.ejecutar(_proyecto_minimo(tmp_path, con_jar=True), "estandar")
    puerta = {p.nombre: p for p in cert.puertas}["Empaquetado y cierre de dependencias"]
    assert puerta.estado == "rojo"
    assert puerta.evidencia and puerta.evidencia != "sin salida"


# --- Important 2: la evidencia de una puerta roja parecia un exito ---------
# La evidencia era la ULTIMA linea de stdout, y `verificar_superficie` imprime
# «Inventario de API escrito en ...» DESPUES de sus lineas ERROR. Una puerta en
# rojo se certificaba con una evidencia que se lee como si todo hubiera ido
# bien -- en el documento cuyo unico cometido es no mentir sobre lo que se
# comprobo.

SALIDA_CON_ERROR_Y_COLA_DE_EXITO = (
    "ERROR com.raul.X referencia API no documentada: com.appiancorp.internal.Y\n"
    "ERROR com.raul.X referencia API no documentada: com.appiancorp.internal.Z\n"
    "Inventario de API escrito en build/reports/inventario-api.json (7 tipos)"
)


def test_la_evidencia_de_una_puerta_roja_es_el_motivo_del_rojo():
    evidencia = vt._evidencia(SALIDA_CON_ERROR_Y_COLA_DE_EXITO, "", "rojo")
    assert evidencia.startswith("ERROR")
    assert "Inventario de API escrito" not in evidencia
    assert "+1 más" in evidencia, "no dice que habia mas motivos que el primero"


def test_la_evidencia_de_una_puerta_verde_sigue_siendo_el_resumen():
    evidencia = vt._evidencia("0 hallazgos (0 errores)", "", "verde")
    assert evidencia == "0 hallazgos (0 errores)"


def test_una_puerta_roja_no_se_certifica_con_una_linea_que_parece_un_exito(monkeypatch, tmp_path):
    """La misma correccion, por el camino real del orquestador."""

    class ProcesoFalso:
        returncode = 1
        stdout = SALIDA_CON_ERROR_Y_COLA_DE_EXITO
        stderr = ""

    monkeypatch.setattr("subprocess.run", lambda *a, **k: ProcesoFalso())
    cert = vt.ejecutar(_proyecto_minimo(tmp_path, con_jar=True), "estandar")
    for puerta in cert.puertas:
        if puerta.estado == "rojo" and puerta.nombre in vt.PUERTAS_CON_INVOCACION:
            assert puerta.evidencia.startswith("ERROR"), (
                f"«{puerta.nombre}» esta en rojo y su evidencia parece un exito: "
                f"{puerta.evidencia}"
            )


# ---------------------------------------------------------------------------
# Las costuras que el gate del ciclo 7 encontro SIN GUARDIAN. Es la tercera
# aparicion seguida de esa familia --c5, c6, c7-- y las tres veces el arreglo
# funcionaba: lo que faltaba era algo que se pusiera rojo si desaparecia.
# ---------------------------------------------------------------------------

FIXTURES_CONTRATOS = pathlib.Path(__file__).resolve().parent / "fixtures" / "contratos"


def _proyecto(tmp_path, fixture):
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "contrato.md").write_text(
        (FIXTURES_CONTRATOS / fixture).read_text(encoding="utf-8"), encoding="utf-8"
    )
    return tmp_path


def _ordenes(monkeypatch, raiz, perfil):
    """Ejecuta el orquestador capturando las ORDENES que reparte a sus hijos."""
    vistas = []

    def espia(comando, *a, **k):
        vistas.append(list(comando))
        class P:
            returncode, stdout, stderr = 1, "", ""
        return P

    monkeypatch.setattr("subprocess.run", espia)
    return vt.ejecutar(raiz, perfil), vistas


def test_el_paquete_de_dominio_del_contrato_LLEGA_al_escaner(monkeypatch, tmp_path):
    """D19 solo muerde si el orquestador le pasa el paquete. Nadie lo miraba.

    El ciclo 7 borro esa linea y la suite entera siguio en verde (451 passed),
    porque el unico test de la costura ejercitaba `verificar_superficie` con
    paquetes ad hoc, nunca con el convenio ni con el cableado. Y la celda de
    insumo tampoco lo delata: sin paquete dice `0 clases de dominio`, que es
    exactamente lo que dice un proyecto que no usa el convenio.

    El literal va ESCRITO AQUI a proposito. Derivarlo de `contrato` volveria a
    dejar un test que se pregunta a si mismo, que es el otro defecto que este
    mismo ciclo levanto.
    """
    _, ordenes = _ordenes(monkeypatch, _proyecto(tmp_path, "function-minimo.md"), "estandar")
    superficie = [o for o in ordenes if o[1].endswith("verificar_superficie.py")]
    assert len(superficie) == 1, f"el escaner de superficie no se invoco una vez: {superficie}"
    assert "com.raul.appian.saludo.dominio" in superficie[0], (
        f"el paquete de dominio del contrato no llega al escaner, asi que D19 recorre "
        f"cero clases y aprueba sin mirar. Orden emitida: {superficie[0]}"
    )


def test_un_contrato_SIN_paquete_no_apaga_D19_con_un_prefijo_de_mentira(tmp_path):
    """`.dominio` a secas es un prefijo que ninguna clase casa jamas."""
    assert contrato.paquete_de_dominio({"plugin": {}}) == "", (
        "un contrato sin paquete fabricaba el prefijo «.dominio», que no casa ninguna clase: "
        "D19 aprobaba sobre cero, mudo e indistinguible de un proyecto sin ese convenio"
    )
    assert contrato.paquete_de_dominio({"plugin": {"paquete": "com.x"}}) == "com.x.dominio"


def test_el_perfil_lo_manda_el_CONTRATO_y_no_el_argumento(monkeypatch, tmp_path):
    """Un plug-in RIGUROSO verificado como estandar perdia sus cuatro puertas.

    No fallaban: desaparecian de la tabla, y el certificado quedaba mas limpio
    por haber mirado menos. Ademas `estandar` es el DEFECTO del CLI, asi que
    bastaba olvidarse del argumento. El dossier llegaba a publicar las dos
    afirmaciones contrarias en el mismo fichero.
    """
    cert, _ = _ordenes(monkeypatch, _proyecto(tmp_path, "eml-referencia.md"), "estandar")
    assert cert.perfil == "riguroso", (
        "el certificado degrado a ESTANDAR un plug-in cuyo contrato declara RIGUROSO"
    )
    filas = {p.nombre for p in cert.puertas}
    assert "Mutacion PIT >= 85 %" in filas and "Property tests y fuzz sembrado" in filas, (
        f"faltan las filas rigurosas: {sorted(filas)}"
    )
    # Y se DICE por que, en el documento, no en la consola de quien lo lanzo.
    assert "lo pide el contrato" in cert.nota_perfil
    assert cert.nota_perfil in vt.render_markdown(cert)


def test_sin_contrato_legible_el_perfil_pedido_sigue_valiendo(monkeypatch, tmp_path):
    """La correccion no puede volver ilanzable un proyecto a medio andamiar."""
    cert, _ = _ordenes(monkeypatch, tmp_path, "riguroso")
    assert cert.perfil == "riguroso"
    assert cert.nota_perfil == ""


def test_ninguna_constante_nombra_una_puerta_QUE_NO_EXISTE():
    """Una comparacion que nunca casa no falla: se salta la rama en silencio.

    Medido en el ciclo 7 sobre `PUERTA_PROPERTY_TESTS`: mutar la constante
    dejaba 451 tests en verde y devolvia esa fila al verde vacuo que el ciclo 6
    acababa de quitarle. Los dos tests que debian verlo pasaban la constante en
    vez del literal, asi que se preguntaban a si mismos.

    Las cuatro constantes ya NO se enumeran aqui a mano. El gate del ciclo 9 lo
    reprocho, y con razon: enumerarlas tiene el mismo modo de fallo que la
    guarda combate --un quinto `PUERTA_*` no entra en la lista y nadie lo
    mira--. Se descubren del modulo ya importado, que a esas alturas si tiene
    todos los nombres ligados.

    Lo que este test sigue aportando ahora que la guarda del modulo revienta al
    importar: mira los valores RESUELTOS en tiempo de ejecucion contra las
    filas que `certificado_base` construye de verdad, no contra el fuente. Si
    la guarda cayera, este es el otro lado; si el que cae es este, la guarda
    impide siquiera importar el fichero de tests.
    """
    nombres = {p.nombre for p in vt.certificado_base("riguroso").puertas}
    descubiertas = sorted(
        n for n, v in vars(vt).items() if n.startswith("PUERTA_") and isinstance(v, str)
    )
    # ANCLA LITERAL, escrita aqui: sin ella el bucle de abajo encoge con lo que
    # vigila --constantes renombradas o movidas-- y pasa por vacio, que es
    # exactamente el defecto que el ciclo 8 encontro en el guardian de los
    # sufijos de property test.
    assert set(descubiertas) >= {
        "PUERTA_INFORMATIVA", "PUERTA_EMPAQUETADO", "PUERTA_LICENCIAS",
        "PUERTA_PROPERTY_TESTS",
    }, f"faltan constantes de puerta conocidas; el modulo solo trae {descubiertas}"
    for constante in descubiertas:
        assert getattr(vt, constante) in nombres, (
            f"{constante} nombra una puerta que no existe: la rama que dependa de ella "
            f"no se ejecutaria nunca, y no fallaria"
        )
    # El literal, escrito aqui, para que renombrar la fila EN LAS DOS TABLAS a
    # la vez tampoco pase inadvertido.
    assert vt.PUERTA_PROPERTY_TESTS == "Property tests y fuzz sembrado"


_FUENTE_ORQUESTADOR = (RAIZ_SCRIPTS / "verificar_todo.py").read_text(encoding="utf-8")
# Un `PUERTA_*` que no nombra ninguna fila de ninguna de las tres listas.
_FANTASMA = 'PUERTA_FANTASMA = "Puerta que no figura en ninguna lista"'
# La linea tras la que se inyecta la variante "arriba". Es la ultima constante
# del bloque de cabecera, y su literal ya esta anclado mas arriba en este mismo
# fichero, asi que un renombrado no deja este test mutando la nada en silencio.
_ANCLA_ARRIBA = 'PUERTA_PROPERTY_TESTS = "Property tests y fuzz sembrado"\n'


def _importar_copia(tmp_path, nombre, fuente):
    """Importa una copia del orquestador y devuelve el modulo, o revienta.

    El alta en `sys.modules` no es adorno: `@dataclasses.dataclass` resuelve
    las anotaciones --que con `from __future__ import annotations` llegan como
    cadenas-- buscando el modulo por su nombre, y sin ese registro falla con un
    `AttributeError` que no tiene nada que ver con lo que aqui se mide. Se
    retira siempre, tambien cuando la guarda revienta, para no dejar la copia
    visible al resto de la bateria.
    """
    ruta = tmp_path / f"{nombre}.py"
    ruta.write_text(fuente, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = modulo
    try:
        spec.loader.exec_module(modulo)
    finally:
        sys.modules.pop(nombre, None)
    return modulo


def test_un_PUERTA_declarado_ABAJO_DEL_TODO_tambien_revienta_al_importar(tmp_path):
    """La guarda de huerfanas tiene que ver el modulo ENTERO, no su mitad alta.

    Hallazgo [media] del gate del ciclo 9, medido alli a mano: `_HUERFANAS` se
    derivaba de `globals()` en tiempo de modulo, asi que solo veia los nombres
    YA ligados. El mismo `PUERTA_FANTASMA` reventaba el import declarado en la
    linea 59 y dejaba la suite entera en verde declarado sobre la linea 760 --y
    el sitio natural para una constante nueva es justo ese, junto a
    `SCRIPT_POR_PUERTA`--. El comentario de la guarda afirmaba cubrir "un
    quinto `PUERTA_*`": una afirmacion de cobertura mas fuerte que la real.

    Esto lo mecaniza en las dos direcciones. La variante de abajo se inyecta
    DESPUES del bloque `__main__`, que es el peor caso: cualquier guarda que
    dependa de su propia posicion en el fichero la deja pasar.
    """
    assert _ANCLA_ARRIBA in _FUENTE_ORQUESTADOR, (
        "cambio la constante que este test usa de ancla; sin ella la variante "
        "'arriba' no inyecta nada y pasaria por no haber mutado"
    )

    # Control: la copia SIN mutar importa limpia. Sin esto, un fallo cualquiera
    # de importacion --una ruta mal construida, por ejemplo-- se leeria como
    # "la guarda funciona" en las dos variantes de abajo.
    sano = _importar_copia(tmp_path, "vt_copia_intacta", _FUENTE_ORQUESTADOR)
    assert sano.PUERTA_LICENCIAS == "Licencias de terceros"

    variantes = {
        "vt_copia_fantasma_arriba": _FUENTE_ORQUESTADOR.replace(
            _ANCLA_ARRIBA, _ANCLA_ARRIBA + _FANTASMA + "\n", 1
        ),
        "vt_copia_fantasma_abajo": _FUENTE_ORQUESTADOR + "\n" + _FANTASMA + "\n",
    }
    for nombre, fuente in variantes.items():
        with pytest.raises(AssertionError) as fallo:
            _importar_copia(tmp_path, nombre, fuente)
        assert "PUERTA_FANTASMA" in str(fallo.value), (
            f"{nombre} revento, pero el mensaje no nombra la constante culpable: "
            f"{fallo.value}"
        )


def test_una_TABLA_con_una_clave_que_no_es_una_puerta_revienta_al_importar(tmp_path):
    """El otro lado de la misma familia, y el que falla EN FAVOR.

    La guarda de constantes vigila cuatro escalares. Las tablas indexadas por
    nombre de puerta son cinco, y una clave mal escrita en ellas tampoco casa
    con ninguna fila: su rama no se ejecuta y no falla. Tres de las cinco se
    delatan solas --la fila se queda pendiente y `estado_de_sumision` bloquea
    el READY-- pero `PUERTAS_MEDIDAS_EN_TESTS` no: `_insumo_delegado` cae a
    medir CLASES COMPILADAS en vez de tests, y un `> Task :test NO-SOURCE`
    dentro de un BUILD SUCCESSFUL sale verde con «7 clases». Es la familia
    [ALTA] del ciclo 6 que motivo esa tabla, viva en la tabla misma.

    Se muta la clave que mas dano hace y una de las que se delatan solas, para
    que el test no dependa de cual sea la peor. Los literales van escritos
    AQUI: derivarlos de las tablas los haria cambiar con ellas.

    Las anclas llevan el NOMBRE DE LA TABLA delante, y no es adorno: la
    primera version mutaba `'"Tests unitarios",'` a secas, que casa antes con
    la entrada de `PUERTAS_AMBOS_PERFILES` treinta lineas mas arriba. El test
    pasaba --renombrar la puerta deja huerfanas a tres tablas-- pero nunca
    ejercia el escenario que este docstring vende, que es el de la tabla que
    falla EN FAVOR. Lo levanto la revision de codigo posterior al ciclo 10.
    """
    mutaciones = {
        "vt_tabla_tests": (
            'PUERTAS_MEDIDAS_EN_TESTS = {\n    "Tests unitarios",',
            'PUERTAS_MEDIDAS_EN_TESTS = {\n    "Tests unitarioss",',
        ),
        "vt_tabla_script": (
            '"Bundles y locales": "verificar_bundles.py",',
            '"Bundles y locale": "verificar_bundles.py",',
        ),
    }
    for nombre, (viejo, nuevo) in mutaciones.items():
        assert _FUENTE_ORQUESTADOR.count(viejo) == 1, (
            f"la mutacion {nombre} no tiene un ancla UNICA: "
            f"{_FUENTE_ORQUESTADOR.count(viejo)} coincidencias"
        )
        with pytest.raises(AssertionError) as fallo:
            _importar_copia(tmp_path, nombre, _FUENTE_ORQUESTADOR.replace(viejo, nuevo, 1))
        assert "no nombran ninguna puerta" in str(fallo.value), fallo.value

    # Una tabla nueva AL FINAL DEL FICHERO, que es lo que la version anterior
    # de la guarda no veia: filtraba `globals()` en su propia linea, o sea que
    # heredaba el punto ciego de posicion que la guarda de escalares acababa de
    # quitarse. Hoy lee el fuente y la ve este donde este.
    with pytest.raises(AssertionError) as fallo:
        _importar_copia(
            tmp_path, "vt_tabla_al_final",
            _FUENTE_ORQUESTADOR + '\nTABLA_SEXTA = {"Tests unitarios": 1, "Tests unitarioss": 2}\n',
        )
    assert "TABLA_SEXTA" in str(fallo.value), fallo.value

    # Y el suelo de la deteccion: si dejara de reconocer las tablas, esta
    # guarda vigilaria el conjunto vacio y pasaria en verde sobre nada.
    ciego = _FUENTE_ORQUESTADOR.replace(
        "if nombre != \"_TODAS_LAS_PUERTAS\" and set(claves) & _TODAS_LAS_PUERTAS",
        "if False",
        1,
    )
    with pytest.raises(AssertionError) as fallo:
        _importar_copia(tmp_path, "vt_deteccion_ciega", ciego)
    assert "dejo de ver" in str(fallo.value), fallo.value


def test_un_PUERTA_que_no_es_un_literal_no_se_cuela_sin_clasificar(tmp_path):
    """Leer el fuente tiene su propio punto ciego, y se cierra declarandolo.

    Un `PUERTA_X = OTRA_COSA` no se puede clasificar sin ejecutar el modulo. La
    salida facil --ignorarlo-- devolveria el agujero por la puerta de atras:
    una constante fuera del conjunto auditado es indistinguible de una que no
    existe. Asi que se rechaza y se dice por que.
    """
    fuente = _FUENTE_ORQUESTADOR + "\nPUERTA_ALIAS = PUERTAS_RIGUROSO[0]\n"
    with pytest.raises(AssertionError) as fallo:
        _importar_copia(tmp_path, "vt_copia_alias", fuente)
    assert "PUERTA_ALIAS" in str(fallo.value)
    assert "literal" in str(fallo.value)

    # El desempaquetado liga nombres igual que un `=` a secas, y mirar solo la
    # forma comoda seria el mismo punto ciego con otra cara.
    fuente = _FUENTE_ORQUESTADOR + '\nPUERTA_UNO, PUERTA_DOS = "a", "b"\n'
    with pytest.raises(AssertionError) as fallo:
        _importar_copia(tmp_path, "vt_copia_tupla", fuente)
    assert "PUERTA_UNO" in str(fallo.value) and "PUERTA_DOS" in str(fallo.value)


def _entradas_excluidas(bloque: str) -> list[str]:
    """Toda entrada de `excludedTestClasses`, sea cual sea su forma.

    Reconoce el patron ENTERO --`'**.*FuzzTest'`, `'com.x.SlowTest'`,
    `'**.integration.*'`, con comillas simples o dobles-- en vez de extraer el
    sufijo de una sola forma. Y lo que no sabe leer lo DECLARA: una entrada que
    el parser no reconoce no se quedaba fuera del build, se quedaba fuera del
    conjunto auditado, que es peor porque la igualdad seguia pasando.
    """
    sin_comentarios = re.sub(r"//[^\n]*", "", bloque)
    crudas = [t.strip() for t in sin_comentarios.split(",")]
    crudas = [t for t in crudas if t]
    sin_clasificar = [t for t in crudas if not re.fullmatch(r"'[^']*'|\"[^\"]*\"", t)]
    assert not sin_clasificar, (
        f"entradas de `excludedTestClasses` que este guardian no sabe leer: "
        f"{sin_clasificar}. Se declaran en vez de ignorarse: una entrada fuera del "
        f"conjunto auditado es indistinguible de una que no existe"
    )
    return [t[1:-1] for t in crudas]


def test_el_parser_de_exclusiones_de_PIT_reconoce_TODA_ENTRADA():
    """El guardian del convenio no puede tener puntos ciegos propios.

    [baja] del gate del ciclo 9, medido alli: con el parser viejo
    --`re.findall(r"'\\*\\*\\.\\*(\\w+)'")`-- anadir `'com.x.SlowTest'` o
    `'**.integration.*'` a la plantilla dejaba el conjunto en los tres de
    siempre y la igualdad seguia pasando. Lo que la SKILL publica si estaba
    cubierto; lo que no tenia respaldo era la promesa del comentario de que
    una exclusion nueva obliga a decidir de que lado cae.

    Insumo y expectativa son literales escritos AQUI: este test no lee la
    plantilla, asi que no puede encoger con ella.
    """
    assert _entradas_excluidas(
        "'**.*FuzzTest', 'com.x.SlowTest', '**.integration.*', \"**.*ConComillaDoble\""
    ) == ["**.*FuzzTest", "com.x.SlowTest", "**.integration.*", "**.*ConComillaDoble"]
    # Una coma final y un comentario de linea no son entradas.
    assert _entradas_excluidas("'a', // ojo con esto\n 'b',") == ["a", "b"]
    # Y lo que no sabe leer no lo deja fuera en silencio.
    with pytest.raises(AssertionError, match="no sabe leer"):
        _entradas_excluidas("'a', UNA_CONSTANTE_DE_GRADLE")


def test_PIT_excluye_exactamente_los_sufijos_QUE_LA_PUERTA_CUENTA():
    """El convenio publicado y el que el build aplica tienen que ser el mismo.

    Divergieron: la puerta contaba `*PropertyTest` y la plantilla no lo excluia,
    asi que PIT lo ATACABA --`targetTests = ['<paquete>.*Test']`-- con
    `mutationThreshold = 85` y `failWhenNoMutations = true` esperando. Quien
    siguiera el convenio que la SKILL publica se metia en eso.
    """
    tmpl = (pathlib.Path(__file__).resolve().parents[1] / "assets" / "plantillas"
            / "perfil-riguroso.gradle.tmpl").read_text(encoding="utf-8")
    excluidos = re.search(r"excludedTestClasses\s*=\s*\[([^\]]*)\]", tmpl)
    assert excluidos, "la plantilla del perfil riguroso ya no declara `excludedTestClasses`"
    de_la_plantilla = set(_entradas_excluidas(excluidos.group(1)))

    # LOS DOS LADOS CONTRA LITERALES ESCRITOS AQUI, y por igualdad.
    #
    # La primera version hacia `for sufijo in vt.SUFIJOS_PROPERTY_TEST: assert
    # ... in excluidos`, o sea derivaba su expectativa de la constante que
    # debia anclar. El ciclo 8 lo midio: CAMBIAR un sufijo la ponia roja, pero
    # QUITARLO encogia el bucle junto con el aserto y dejaba 462 en verde. Dos
    # lentes lo vieron por vias independientes, y la SKILL publicaba mientras
    # tanto que «mutar cualquiera de los dos lados pone la suite en rojo»:
    # una afirmacion de cobertura mas fuerte que la cobertura real, en el
    # documento cuyo cometido es no mentir.
    assert set(vt.SUFIJOS_PROPERTY_TEST) == {"FuzzTest", "PropertyTest"}, (
        f"el convenio de property test cambio y la SKILL sigue publicando el viejo: "
        f"{sorted(vt.SUFIJOS_PROPERTY_TEST)}"
    )
    # `PerformanceTest` es el unico que PIT excluye y la puerta NO cuenta: un
    # test de rendimiento tampoco debe mutarse, pero no es un property test.
    # Va aqui, explicito, para que anadir una exclusion nueva obligue a decidir
    # de que lado cae en vez de colarse en un subconjunto.
    #
    # La igualdad es contra el PATRON ENTERO, no contra el sufijo que un regex
    # supiera extraer, y esa es la correccion del [baja] del gate del ciclo 9:
    # el parser era `re.findall(r"'\*\*\.\*(\w+)'")`, de modo que anadir
    # `'com.x.SlowTest'` o `'**.integration.*'` a la plantilla no rompia nada
    # --la entrada no desaparecia del build, desaparecia del CONJUNTO
    # AUDITADO-- y esta promesa de "obliga a decidir de que lado cae" no tenia
    # respaldo. `_entradas_excluidas` reconoce toda entrada o la rechaza.
    assert de_la_plantilla == {"**.*FuzzTest", "**.*PropertyTest", "**.*PerformanceTest"}, (
        f"PIT excluye {sorted(de_la_plantilla)} y la puerta cuenta "
        f"{sorted(vt.SUFIJOS_PROPERTY_TEST)}: lo que la puerta cuenta y PIT no excluye lo "
        f"MUTA, con `mutationThreshold = 85` y `failWhenNoMutations = true` esperando"
    )


def test_pedir_RIGUROSO_sobre_un_contrato_estandar_si_se_respeta(monkeypatch, tmp_path):
    """La asimetria es el punto: bajar el liston engana, subirlo no.

    Sin esto la correccion del perfil se pasaba de frenada — «manda el
    contrato» a secas impedia comprobar un plug-in estandar contra el liston
    alto, que es una operacion legitima y que dos tests ya ejercian.
    """
    cert, _ = _ordenes(monkeypatch, _proyecto(tmp_path, "function-minimo.md"), "riguroso")
    assert cert.perfil == "riguroso"
    assert "Mutacion PIT >= 85 %" in {p.nombre for p in cert.puertas}
    assert "el contrato declara ESTANDAR" in cert.nota_perfil


def test_un_inventario_ILEGIBLE_no_se_publica_como_uno_ausente(tmp_path):
    """No poder mirar se dice; es la regla del fichero, aplicada aqui tarde.

    Con `except: return ""` los dos casos salian iguales --sin linea de
    indice-- y la cabecera de un certificado con el inventario corrupto era
    indistinguible de la de uno sano.
    """
    assert vt._indice_usado(tmp_path / "no-existe.json") == ""

    roto = tmp_path / "inventario-api.json"
    roto.write_text("{esto no es json", encoding="utf-8")
    assert "ILEGIBLE" in vt._indice_usado(roto)

    sano = tmp_path / "sano.json"
    sano.write_text('{"version_indice": "26.3", "hash_indice": "abc123def456ghi7"}',
                    encoding="utf-8")
    assert vt._indice_usado(sano).startswith("26.3")


def test_sin_perfil_pedido_la_nota_no_inventa_una_peticion():
    """El defecto lo aplica `_resolver_perfil`, no argparse.

    Con `default="estandar"` la nota decia «se lanzo como ESTANDAR» sobre
    alguien que no escribio el argumento: una afirmacion falsa, pequena y
    gratuita, en el documento cuyo unico cometido es no mentir.
    """
    datos = {"plugin": {"perfil": "riguroso"}}
    perfil, nota = vt._resolver_perfil(None, datos)
    assert perfil == "riguroso"
    assert "no se pidio ninguno" in nota and "se lanzo como" not in nota

    perfil, nota = vt._resolver_perfil("estandar", datos)
    assert perfil == "riguroso" and "se lanzo como ESTANDAR" in nota

    # Y sin contrato, el defecto sigue siendo el de siempre.
    assert vt._resolver_perfil(None, None) == ("estandar", "")


def test_las_capacidades_SUBEN_el_perfil_aunque_el_contrato_declare_estandar():
    """La puerta de atras por la que las cuatro filas rigurosas desaparecian.

    `_resolver_perfil` cerro la degradacion por el lado del CLI en el ciclo 7,
    pero un contrato podia declarar `sale_a_la_red = true` y a la vez
    `perfil = "estandar"`: `contrato.validar` no lo mira --solo exige que las
    claves esten-- y `main` lo decia como AVISO con `return 0`. Resultado: se
    verificaba en ESTANDAR y las cuatro puertas rigurosas no fallaban,
    DESAPARECIAN. Lo levanto el gate del ciclo 9.

    Las cuatro capacidades van escritas AQUI como literales, no derivadas de
    `contrato.CAPACIDADES_QUE_PROPONEN_RIGUROSO`: un bucle sobre la constante
    que deberia anclar encoge con ella y no puede fallar, que es el defecto
    que el ciclo 8 encontro en el guardian de los sufijos de property test.
    """
    cuatro = ("parsea_formatos_ajenos", "sale_a_la_red", "toca_credenciales", "datos_personales")
    for capacidad in cuatro:
        datos = {"plugin": {"perfil": "estandar"}, "capacidades": {capacidad: True}}
        perfil, nota = vt._resolver_perfil(None, datos)
        assert perfil == "riguroso", (
            f"«{capacidad}» proponia RIGUROSO y el certificado se resolvio a {perfil}: "
            f"las cuatro puertas rigurosas no fallan, desaparecen"
        )
        assert capacidad in nota, (
            f"la nota no dice QUE capacidad subio el perfil, y sin eso manda a leerse "
            f"el contrato entero: {nota!r}"
        )

    # Control negativo: con las cuatro a false el perfil no se mueve, y no se
    # inventa una nota. Sin esto, un `_resolver_perfil` que devolviera siempre
    # RIGUROSO pasaria el bucle de arriba entero.
    datos = {"plugin": {"perfil": "estandar"}, "capacidades": dict.fromkeys(cuatro, False)}
    assert vt._resolver_perfil(None, datos) == ("estandar", "")

    # Y lo que de verdad importa: las cuatro filas ESTAN en el certificado que
    # sale de ahi. Los nombres, tambien literales.
    cert = vt.certificado_base(
        *vt._resolver_perfil(None, {"plugin": {"perfil": "estandar"},
                                    "capacidades": {"toca_credenciales": True}})
    )
    nombres = [p.nombre for p in cert.puertas]
    for puerta in ("Cobertura JaCoCo 95 / 85", "Mutacion PIT >= 85 %",
                   "Property tests y fuzz sembrado", "Build reproducible"):
        assert puerta in nombres, f"falta la fila «{puerta}» en el certificado subido"


def test_las_capacidades_NO_TAPAN_un_perfil_declarado_que_no_existe():
    """Las dos cosas se dicen, y la mas estricta manda.

    La primera version de la rama de capacidades corria ANTES que la que
    detecta un perfil inexistente, y su guarda solo miraba si alguno de los
    otros dos era ya `riguroso`. Con `perfil = "RIGUROSO"` en mayusculas
    --erratas de ese calibre son el caso realista-- mas una capacidad exigente,
    el certificado salia RIGUROSO con una nota que trataba el valor invalido
    como una declaracion legitima: el «no existe» desaparecia, que es justo lo
    que el docstring de `_resolver_perfil` promete que no pasa. Lo levanto la
    revision del ciclo 9.

    La revision posterior al ciclo 10 encontro que la version siguiente lo
    seguia tapando por el otro lado --la rama de `[capacidades]` ilegibles
    retornaba ANTES-- y que un perfil invalido se resolvia al PEDIDO, o sea a
    favor. Hoy toda averia lleva al liston alto y la nota las enumera todas.
    """
    invalido = {"plugin": {"perfil": "super-riguroso"}}

    perfil, nota = vt._resolver_perfil(None, {**invalido, "capacidades": {}})
    assert perfil == "riguroso", (
        f"un perfil que no existe se resolvio a favor, y con el se van las cuatro filas "
        f"rigurosas sin fallar: {perfil}"
    )
    assert "no existe" in nota and "super-riguroso" in nota

    perfil, nota = vt._resolver_perfil(
        None, {**invalido, "capacidades": {"sale_a_la_red": True}}
    )
    assert perfil == "riguroso"
    assert "no existe" in nota, f"las capacidades taparon el perfil invalido: {nota!r}"

    # Las DOS averias a la vez: la nota tiene que nombrarlas las dos. Encadenar
    # `return`s hacia que la primera tapara a la segunda.
    perfil, nota = vt._resolver_perfil(None, {**invalido, "capacidades": "pendiente"})
    assert perfil == "riguroso"
    assert "no existe" in nota and "super-riguroso" in nota, (
        f"la averia de `[capacidades]` volvio a tapar al perfil invalido: {nota!r}"
    )
    assert "`[capacidades]`" in nota, f"y la suya tambien tiene que estar: {nota!r}"

    # Y no delega el rojo en nadie: ningun validador de capa 1 lee
    # `plugin.perfil` --comprobado a grep sobre los cinco--, asi que la nota
    # anterior anunciaba un rojo que no llegaba nunca. En el fichero cuyo unico
    # cometido es no mentir, prometer una fila ajena que no existe es el mismo
    # defecto que un verde vacuo, con el signo cambiado.
    assert "capa 1" not in nota, (
        f"la nota vuelve a delegar en una capa que no comprueba el perfil: {nota!r}"
    )


def test_un_perfil_PEDIDO_que_no_existe_no_hace_desaparecer_las_filas_rigurosas():
    """El agujero mas caro de los tres, y el unico del lado de la ORDEN.

    `argparse` no llevaba `choices` y `_resolver_perfil` solo miraba el perfil
    DECLARADO, asi que una errata de una letra --`rigoroso`-- se devolvia tal
    cual; `certificado_base` la comparaba con `PERFIL_ESTRICTO`, salia falso, y
    las cuatro filas rigurosas no fallaban: DESAPARECIAN, mientras la cabecera
    imprimia «Perfil: RIGOROSO», que a ojo se lee como correcto. Trece filas
    donde tenia que haber diecisiete, y ni una en rojo por ello.
    Revision de codigo posterior al ciclo 10.
    """
    sano = {"plugin": {"perfil": "estandar"},
            "capacidades": dict.fromkeys(("sale_a_la_red",), False)}

    for errata in ("rigoroso", "RIGUROSO", "riguros"):
        perfil, nota = vt._resolver_perfil(errata, sano)
        assert perfil in contrato.PERFILES, (
            f"«{errata}» viajo tal cual hasta el certificado: {perfil}"
        )
        assert perfil == "riguroso", f"se resolvio a favor: {perfil}"
        assert errata in nota, f"la nota no dice cual fue la errata: {nota!r}"

        # Lo que de verdad importa: las cuatro filas ESTAN.
        nombres = [p.nombre for p in vt.certificado_base(perfil, nota).puertas]
        for puerta in ("Cobertura JaCoCo 95 / 85", "Mutacion PIT >= 85 %",
                       "Property tests y fuzz sembrado", "Build reproducible"):
            assert puerta in nombres, f"«{errata}» hizo desaparecer la fila «{puerta}»"

    # Control: los dos validos no producen nota de averia.
    assert vt._resolver_perfil("estandar", sano) == ("estandar", "")


def test_una_seccion_plugin_ILEGIBLE_no_tumba_el_orquestador():
    """`plugin = "smart-service"` en vez de `[plugin]`, o `[[plugin]]`.

    Es la guarda que `[capacidades]` ya tenia y su hermana no, una linea mas
    arriba: `datos.get("plugin", {}).get("perfil")` estallaba con
    `AttributeError` sobre un `str` y se llevaba por delante a `ejecutar()`,
    que no lo envuelve en ningun `try` -- sin certificado, que es peor que
    cualquier fila roja. Revision de codigo posterior al ciclo 10.
    """
    for basura in ("smart-service", [{"perfil": "estandar"}], 7):
        perfil, nota = vt._resolver_perfil(None, {"plugin": basura})
        assert perfil == "riguroso", (
            f"no poder leer `[plugin]` ({basura!r}) se resolvio a favor: {perfil}"
        )
        assert "`[plugin]`" in nota and "no es una tabla" in nota, nota


def test_un_contrato_con_SECCIONES_ILEGIBLES_deja_certificado_igual(tmp_path):
    """La mitad que el guardian de arriba prometia y no ejercia.

    Su docstring decia que un `[plugin]` mal formado ya no «se lleva por
    delante a `ejecutar()`», pero solo llamaba a `_resolver_perfil`. El gate
    del ciclo 11 lo midio y encontro el hueco: `_resolver_perfil` degradaba
    bien y UNA LINEA DESPUES `ejecutar()` moria en
    `contrato.paquete_de_dominio`, que hacia el mismo `.get` encadenado sobre
    el `str`. Sin certificado, que es peor que cualquier fila roja: no queda
    documento que leer.

    Este test entra por `ejecutar()`, que es el camino que el usuario recorre,
    y solo afirma lo irrenunciable: que el proceso TERMINA y deja certificado.
    Que las filas salgan rojas es el resultado correcto y de eso van los demas.
    """
    proyecto = tmp_path / "proyecto"
    (proyecto / "docs").mkdir(parents=True)
    # Las tres secciones mal formadas a la vez, cada una de un tipo distinto,
    # para que el test no dependa de cual se toque primero.
    (proyecto / "docs" / "contrato.md").write_text(
        "# Contrato roto\n\n```toml\n"
        'plugin = "smart-service"\n'
        'clase = 7\n'
        'entradas = ["nombre"]\n'
        "```\n",
        encoding="utf-8",
    )

    # COMO PROCESO, que es el camino que recorre quien usa esto: `ejecutar`
    # devuelve el certificado y quien lo ESCRIBE es `main`. Entrar por la
    # funcion habria dejado sin ejercer justo el tramo donde el fallo se nota.
    proceso = subprocess.run(
        [sys.executable, str(RAIZ_SCRIPTS / "verificar_todo.py"), str(proyecto)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    certificado = proyecto / "docs" / "CERTIFICADO.md"
    assert certificado.is_file(), (
        f"un contrato ilegible dejo de producir certificado; stderr:\n{proceso.stderr[-2000:]}"
    )
    assert "Traceback" not in proceso.stderr, (
        f"el orquestador murio con traza en vez de certificar:\n{proceso.stderr[-2000:]}"
    )
    texto = certificado.read_text(encoding="utf-8")
    assert vt.NO_LISTO in texto, "un contrato ilegible no puede salir listo para enviar"
    # Y la cabecera dice QUE paso, en vez de callarlo.
    assert "`[plugin]`" in texto, f"la cabecera no declara la averia:\n{texto[:800]}"


def test_unas_capacidades_ILEGIBLES_no_tumban_el_orquestador_ni_se_resuelven_a_favor():
    """`capacidades = "pendiente"` en vez de `[capacidades]`.

    `datos.get("capacidades", {})` solo repone el defecto cuando la clave
    FALTA: con un valor de otro tipo el `.get` de dentro estallaba sobre un
    `str` y se llevaba por delante a `ejecutar()`, que no lo envuelve en
    ningun `try`. Un contrato mal tecleado dejaba de producir certificado
    --ninguna fila en rojo, ningun documento-- que es el peor desenlace
    posible en el fichero cuyo cometido es no callarse. Revision del ciclo 9.
    """
    for basura in ("pendiente", ["sale_a_la_red"], 3):
        perfil, nota = vt._resolver_perfil(
            None, {"plugin": {"perfil": "estandar"}, "capacidades": basura}
        )
        assert perfil == "riguroso", (
            f"no poder leer las capacidades ({basura!r}) se resolvio a favor: {perfil}"
        )
        assert "no es una tabla" in nota, nota

    # Y la ausencia de la seccion NO es un valor ilegible: ahi no hay nada que
    # leer y el perfil se decide por las otras dos vias, como siempre.
    assert vt._resolver_perfil(None, {"plugin": {"perfil": "estandar"}}) == ("estandar", "")


# ---------------------------------------------------------------------------
# LA RAIZ QUE NO EXISTE
#
# Hallazgo [info] del gate del ciclo 11, arrastrado como pre-existente al
# rango: con una raiz inexistente el orquestador CREABA `<raiz>/docs/` y
# escribia dentro un certificado entero. Las diez filas rojas, asi que no era
# un verde vacuo -- era un documento con forma de veredicto cuyo contenido
# real es «te equivocaste de ruta», dicho diez veces en FileNotFoundError.
# ---------------------------------------------------------------------------


def test_una_raiz_INEXISTENTE_se_rechaza_sin_escribir_ni_crear_nada(tmp_path):
    """Lo que se afirma son las tres cosas que NO pasan: no se crea el arbol,
    no se escribe certificado, y el codigo distingue esto de «hay rojas».
    """
    fantasma = tmp_path / "no" / "existe"
    proceso = subprocess.run(
        [sys.executable, str(RAIZ_SCRIPTS / "verificar_todo.py"), str(fantasma), "estandar"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )

    assert proceso.returncode == 2, (
        f"la raiz inexistente no se rechazo con 2 (codigo {proceso.returncode}). `1` esta "
        f"tomado por «hay filas rojas», que es una verificacion que SI ocurrio:\n"
        f"{proceso.stdout[-1500:]}"
    )
    assert not fantasma.exists(), (
        "el orquestador creo el arbol de una raiz que no existia: una errata en la ruta "
        "deja directorios nuevos en el sitio equivocado"
    )
    assert "Traceback" not in proceso.stderr, proceso.stderr[-1500:]
    # Y dice QUE pasa y donde, que es lo unico accionable aqui.
    assert "no existe" in proceso.stderr and str(fantasma) in proceso.stderr, proceso.stderr


def test_un_fichero_como_raiz_tampoco_se_toma_por_un_proyecto(tmp_path):
    """La otra mitad de `is_dir()`. Un fichero existe, asi que un `exists()`
    pelado lo habria dejado pasar hasta el primer `FileNotFoundError`.
    """
    fichero = tmp_path / "contrato.md"
    fichero.write_text("# no soy un proyecto\n", encoding="utf-8")
    proceso = subprocess.run(
        [sys.executable, str(RAIZ_SCRIPTS / "verificar_todo.py"), str(fichero), "estandar"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    assert proceso.returncode == 2, proceso.stdout[-1500:]
    assert "no es un directorio" in proceso.stderr, proceso.stderr


def test_una_raiz_que_SI_existe_sin_docs_sigue_certificando(tmp_path):
    """El control de las dos guardas de arriba. Rechazar la raiz inexistente no
    puede convertirse en exigir un arbol ya montado: un proyecto real recien
    andamiado puede no tener `docs/` todavia, y ahi el `mkdir` del final es
    justo lo que tiene que ocurrir.
    """
    proceso = subprocess.run(
        [sys.executable, str(RAIZ_SCRIPTS / "verificar_todo.py"), str(tmp_path), "estandar"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    assert proceso.returncode != 2, f"se rechazo una raiz que si existe:\n{proceso.stderr[-1500:]}"
    assert (tmp_path / "docs" / "CERTIFICADO.md").is_file()


# ---------------------------------------------------------------------------
# EL CRITERIO DE SALIDA DEL PASO 3, ANCLADO DONDE SE OBSERVA
#
# «El destino esta dentro de un repositorio git» es criterio de salida del paso
# ANDAMIAJE en la SKILL, y el gate del ciclo 11 lo anoto como [info]: no tenia
# test, «su efecto si es observable en la cabecera del certificado».
#
# Lo que NO hacia falta anadir: `_revision_git` ya esta cubierta por los dos
# tests de mas arriba --sin repositorio, sin commits, arbol sucio-- y repetirlo
# aqui habria sido cobertura de mentira. Lo que faltaba es la COSTURA: que el
# criterio escrito en la SKILL y el dato que el certificado publica sigan
# hablando de lo mismo. Un criterio cuyo efecto nadie publica es un criterio
# que nadie puede comprobar al aplicarlo a mano.
#
# La regla de la casa --el aserto no deriva su expectativa de lo que vigila--:
# se vigila la PROSA de la SKILL y la expectativa sale del render real de un
# certificado. Dos fuentes independientes.
# ---------------------------------------------------------------------------

SKILL_MD = (
    pathlib.Path(__file__).resolve().parents[1]
    / "skills" / "crear-plugin-appian" / "SKILL.md"
)


def test_el_criterio_del_paso_3_habla_de_algo_que_el_certificado_publica(tmp_path):
    """Los dos extremos: la SKILL pide repositorio git en el paso 3, y la
    cabecera del certificado dice en que revision esta -- o que no hay ninguna.
    """
    texto = SKILL_MD.read_text(encoding="utf-8")
    lineas = texto.splitlines()
    inicio = next(i for i, l in enumerate(lineas) if l.startswith("### 3 ·"))
    fin = next(i for i, l in enumerate(lineas[inicio + 1:], inicio + 1) if l.startswith("### "))
    paso3 = "\n".join(lineas[inicio:fin])
    assert "git" in paso3.lower(), (
        "el paso 3 dejo de exigir que el destino este dentro de un repositorio git: "
        "el criterio que este test ancla desaparecio de la prosa"
    )

    # Y el certificado lo publica, sobre un proyecto SIN repositorio: es el caso
    # en que callarlo dejaria creer que el documento esta atado a un commit.
    cert = vt.ejecutar(tmp_path, "estandar", None, None)
    cabecera = vt.render_markdown(cert).split("###", 1)[0]
    assert "Revision del fuente" in cabecera, (
        f"la cabecera del certificado dejo de publicar la revision:\n{cabecera}"
    )
    assert "sin repositorio git" in cabecera, (
        f"un proyecto sin git no salio declarado como tal en la cabecera:\n{cabecera}"
    )
