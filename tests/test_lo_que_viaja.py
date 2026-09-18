"""Lo que sale de este repositorio y deja de tener detras el repo padre.

Dos cosas viajan solas, y las dos tenian el mismo agujero (ciclo 10):

- **El directorio del plugin**, que `/plugin install` copia a la cache tal cual.
  Sus artefactos (`build/`, `.pytest_cache/`, los `__pycache__/`) estaban
  ignorados, pero por reglas que viven en el `.gitignore` del REPO PADRE: un
  checkout aislado de `appian-plugin-forge/` se queda sin ellas. De ahi el
  `.gitignore` propio, y de ahi los tres guardianes de abajo -- el que impide que
  las dos listas de reglas diverjan, el que comprueba que ningun fichero
  versionado cae del lado ignorado, y el que comprueba que los artefactos si.
- **Las plantillas de `assets/plantillas/`**, que `andamiar.py` copia al proyecto
  GENERADO. Ahi el lector no tiene la skill delante: una cita a
  `referencias/<algo>.md` no lleva a ninguna parte. El linter de la skill no lo
  ve --su barrido solo abre `SKILL.md` y `referencias/*.md`, y `PROSA` no incluye
  `assets/plantillas/`--, asi que el perimetro de las plantillas es este fichero.

Los guardianes son deterministas y no dependen de la maquina: las llamadas a git
van con la configuracion global y de sistema apuntadas a un fichero que no
existe, para que un `core.excludesfile` del usuario no decida el resultado.
"""

import os
import pathlib
import subprocess

RAIZ = pathlib.Path(__file__).resolve().parents[1]
RAIZ_REPO = RAIZ.parent
PREFIJO_PLUGIN = "appian-plugin-forge/"
GITIGNORE_PLUGIN = RAIZ / ".gitignore"
GITIGNORE_REPO = RAIZ_REPO / ".gitignore"

# Las dos excepciones del repo padre, YA REBASADAS, como literal propio. Son el
# suelo antivacuidad de la derivacion --si las dos listas se quedaran vacias a la
# vez, la comparacion de secuencias se cumpliria sola-- y a la vez el guardian de
# que el padre no las pierda: son ficheros versionados a proposito como
# evidencia, y un `*.jar`/`*.log` sin su `!` se los traga en silencio.
EXCEPCIONES_ESPERADAS = (
    "!assets/plantillas/comun/gradle/wrapper/gradle-wrapper.jar",
    "!tests/fixtures/logs-de-build/*.log",
)

# Los cuatro artefactos que el aviso del ciclo 10 nombra, tal y como aparecen en
# disco. Van como rutas concretas y no como patrones: lo que se comprueba es la
# DECISION de git sobre un fichero, no que el texto del patron este escrito.
ARTEFACTOS = (
    "build/reports/inventario-api.json",
    ".pytest_cache/CACHEDIR.TAG",
    "scripts/__pycache__/andamiar.cpython-311.pyc",
    "tests/__pycache__/test_contrato.cpython-311.pyc",
)

# Ficheros versionados que las dos reglas mas peligrosas (`*.jar`, `*.log`)
# tragarian sin su excepcion. Literal propio: el barrido de abajo recorre TODO lo
# rastreado, y este trio es lo que impide que ese barrido pase por casar cero
# ficheros interesantes.
RASTREADOS_EN_RIESGO = (
    "assets/plantillas/comun/gradle/wrapper/gradle-wrapper.jar",
    "tests/fixtures/logs-de-build/function-exitoso.log",
    "tests/fixtures/logs-de-build/servlet-spotbugs-fallido.log",
)

DIR_PLANTILLAS = RAIZ / "assets" / "plantillas"

# Lo que una plantilla NO puede nombrar, porque en el proyecto generado no existe:
# `referencias/` es el directorio de la skill --y en forma corta solo resuelve
# desde dentro de el, que es el convenio que documenta el perimetro de la skill--
# y `${CLAUDE_PLUGIN_ROOT}` solo lo define Claude Code al cargar el plugin.
PROHIBIDO_EN_PLANTILLAS = ("referencias/", "${CLAUDE_PLUGIN_ROOT}")

# El .jar del wrapper no es texto. Se salta por nombre y no por heuristica de
# bytes: decodificarlo para buscarle cadenas solo podria producir falsos
# positivos.
EXTENSIONES_BINARIAS = (".jar",)

# Ancla literal del barrido de plantillas: es el fichero del hallazgo, y sin el
# en el conjunto barrido el verde no significaria nada. El suelo acompana al
# ancla porque un barrido que se quede corto no falla, adelgaza.
PLANTILLA_ANCLA = "comun/THIRD_PARTY_NOTICES.md.tmpl"
SUELO_PLANTILLAS = 15


def _entorno(tmp_path):
    """El entorno de las llamadas a git, con la config del usuario neutralizada.

    Un `core.excludesfile` del usuario --o un `~/.gitignore` con `*.log`--
    cambiaria la decision y pondria estos tests en rojo (o peor, en verde) segun
    la maquina. Se apunta a un fichero que no existe: git lee eso como config
    vacia, que es exactamente lo que se quiere.
    """
    sin_config = str(tmp_path / "no-existe.gitconfig")
    entorno = dict(os.environ)
    entorno["GIT_CONFIG_GLOBAL"] = sin_config
    entorno["GIT_CONFIG_SYSTEM"] = sin_config
    return entorno


def _git(argumentos, cwd, tmp_path):
    return subprocess.run(
        ["git", *argumentos],
        cwd=str(cwd),
        env=_entorno(tmp_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _repo_aislado(tmp_path):
    """Un repo de verdad con SOLO el `.gitignore` del plugin en la raiz.

    Es la unica forma de medir lo que decidiria un checkout aislado:
    `git check-ignore` contra el repo padre mediria las reglas del padre, que es
    justo lo contrario de lo que hay que comprobar.
    """
    aislado = tmp_path / "checkout-aislado"
    aislado.mkdir()
    inicio = _git(["init", "-q"], cwd=aislado, tmp_path=tmp_path)
    assert inicio.returncode == 0, inicio.stderr
    (aislado / ".gitignore").write_text(
        GITIGNORE_PLUGIN.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return aislado


def _ignorados(repo, tmp_path, rutas):
    """Cuales de `rutas` ignoraria `repo`.

    `--no-index` es obligatorio: sin el, `check-ignore` SALTA los ficheros
    rastreados y devolveria vacio sin mirar ni un patron -- un verde vacuo con la
    forma exacta de un verde bueno. Y se llama SIN `-v` a proposito: asi la
    salida es el booleano que interesa (solo se imprimen los ficheros
    IGNORADOS), mientras que con `-v` tambien salen los que casan una excepcion,
    que no lo estan.

    `-z` y BYTES, no modo texto: en Windows el modo texto de `subprocess`
    traduce al escribir cada `\\n` a `\\r\\n`, git se traga el `\\r` como parte
    del nombre del fichero y devuelve `"build/reports/x.json\\r"`
    entrecomillado. Medido. Con `-z` la separacion es NUL en los dos sentidos y
    no hay traduccion que valga.
    """
    proceso = subprocess.run(
        ["git", "check-ignore", "--no-index", "--stdin", "-z"],
        cwd=str(repo),
        env=_entorno(tmp_path),
        input=("\0".join(rutas) + "\0").encode("utf-8"),
        capture_output=True,
    )
    # 0 = alguno ignorado, 1 = ninguno. Cualquier otro codigo es un error de git
    # y no una respuesta: se deja explotar en vez de leerlo como «ninguno».
    assert proceso.returncode in (0, 1), proceso.stderr.decode("utf-8", "replace")
    return {p for p in proceso.stdout.decode("utf-8").split("\0") if p}


def _reglas(texto):
    return [
        linea.strip()
        for linea in texto.splitlines()
        if linea.strip() and not linea.lstrip().startswith("#")
    ]


def _rebasar(regla):
    """La regla del repo padre, tal y como aplica DENTRO del plugin, o None.

    Las dos unicas formas que hay que distinguir son las de git:

    - Sin barra interna (`build/`, `*.pyc`, `~$*`): casa a cualquier profundidad,
      asi que dentro del plugin significa lo mismo. Va literal.
    - Con barra: esta anclada al directorio de su `.gitignore`. Si apunta dentro
      del plugin se rebasa quitando el prefijo; si apunta a otro sitio de la raiz
      del padre --como `!gradle/wrapper/gradle-wrapper.jar`--, dentro del plugin
      no casaria nada y se descarta.
    """
    negada = regla.startswith("!")
    patron = regla[1:] if negada else regla
    if "/" not in patron.rstrip("/"):
        return regla
    if patron.startswith(PREFIJO_PLUGIN):
        return ("!" if negada else "") + patron[len(PREFIJO_PLUGIN):]
    return None


def test_el_gitignore_del_plugin_replica_las_reglas_del_repo_padre():
    """Dos listas de reglas que no se atan divergen; esta se ata por derivacion.

    El fichero del plugin no es una copia a mano: es lo que sale de rebasar el
    del padre. Anadir una regla arriba y olvidarla aqui deja el checkout aislado
    sin ella, que es justo el defecto que el `.gitignore` nuevo cierra.

    Se compara la SECUENCIA, no el conjunto: en git el orden decide, una
    excepcion solo vale despues del patron que excepciona.
    """
    assert GITIGNORE_PLUGIN.is_file(), (
        "el plugin no trae `.gitignore` propio; sin el, un checkout aislado de "
        "appian-plugin-forge/ no ignora ni build/ ni los __pycache__/"
    )
    esperado = [
        rebasada
        for rebasada in (
            _rebasar(r) for r in _reglas(GITIGNORE_REPO.read_text(encoding="utf-8"))
        )
        if rebasada is not None
    ]
    for excepcion in EXCEPCIONES_ESPERADAS:
        assert excepcion in esperado, (
            f"el `.gitignore` del repo padre ya no produce `{excepcion}`: alguien "
            f"quito la excepcion de un fichero versionado como evidencia"
        )
    obtenido = _reglas(GITIGNORE_PLUGIN.read_text(encoding="utf-8"))
    assert obtenido == esperado, (
        "el `.gitignore` del plugin y el del repo padre han divergido.\n"
        f"  sobran aqui: {[r for r in obtenido if r not in esperado]}\n"
        f"  faltan aqui: {[r for r in esperado if r not in obtenido]}"
    )


def test_un_checkout_aislado_del_plugin_no_ignora_nada_versionado(tmp_path):
    """La excepcion de los logs y la del wrapper, comprobadas donde importa.

    Un `.gitignore` mas profundo GANA a uno mas alto para el mismo fichero: si
    este trajera `*.jar` y `*.log` sin sus dos `!`, los tres ficheros de
    `RASTREADOS_EN_RIESGO` quedarian ignorados pese a la excepcion del padre. El
    barrido no se queda en esos tres: pasa TODO lo que git tiene rastreado bajo
    el plugin y exige que no salga ninguno.
    """
    listado = _git(["ls-files", "--", str(RAIZ)], cwd=RAIZ_REPO, tmp_path=tmp_path)
    assert listado.returncode == 0, listado.stderr
    rastreados = [
        linea[len(PREFIJO_PLUGIN):]
        for linea in listado.stdout.splitlines()
        if linea.startswith(PREFIJO_PLUGIN)
    ]
    for en_riesgo in RASTREADOS_EN_RIESGO:
        assert en_riesgo in rastreados, (
            f"`{en_riesgo}` ya no esta versionado: el barrido de abajo se quedaria "
            f"sin uno de los dos ficheros que ejercen las excepciones"
        )

    ignorados = _ignorados(_repo_aislado(tmp_path), tmp_path, rastreados)
    assert ignorados == set(), (
        "un checkout aislado del plugin ignoraria ficheros que estan versionados: "
        f"{sorted(ignorados)}"
    )


def test_un_checkout_aislado_del_plugin_si_ignora_los_artefactos(tmp_path):
    """La otra mitad: un `.gitignore` vacio pasaria el test de arriba.

    Son los cuatro artefactos que el aviso nombra. Se comprueban como rutas
    concretas contra git, no leyendo el texto del fichero: lo que arrastraria
    `/plugin install` es lo que git decide, no lo que el patron parece decir.
    """
    ignorados = _ignorados(_repo_aislado(tmp_path), tmp_path, ARTEFACTOS)
    assert ignorados == set(ARTEFACTOS), (
        "artefactos que un checkout aislado del plugin NO ignoraria y viajarian "
        f"en la instalacion: {sorted(set(ARTEFACTOS) - ignorados)}"
    )


def _citas_prohibidas(texto):
    return [prohibido for prohibido in PROHIBIDO_EN_PLANTILLAS if prohibido in texto]


def test_el_detector_de_citas_ve_lo_que_dice_ver():
    """Canario del detector, con el texto que tenia la plantilla antes del arreglo.

    Sin esto, estrechar `PROHIBIDO_EN_PLANTILLAS` --o dejarlo a cero-- pondria el
    barrido de abajo en verde sin mirar nada.
    """
    assert _citas_prohibidas(
        "Copyleft es rechazo automatico (`referencias/entrevista.md`, quinta pregunta)."
    ) == ["referencias/"]
    assert _citas_prohibidas("lee ${CLAUDE_PLUGIN_ROOT}/assets/plantillas/") == [
        "${CLAUDE_PLUGIN_ROOT}"
    ]
    assert _citas_prohibidas("una plantilla que no cita nada del forge") == []


def test_ninguna_plantilla_cita_rutas_que_solo_existen_dentro_del_forge():
    """Las plantillas las lee alguien que no tiene la skill delante.

    Todo lo que vive bajo `assets/plantillas/` acaba en el proyecto GENERADO
    --`andamiar.py` copia unas por el mapa de plantillas y otras (el wrapper de
    Gradle, el `.gitattributes`) aparte--, y alli `referencias/` y
    `${CLAUDE_PLUGIN_ROOT}` no llevan a ninguna parte. El linter de la skill no
    alcanza hasta aqui: su barrido solo abre `SKILL.md` y `referencias/*.md`.
    """
    barridas = {}
    for ruta in sorted(DIR_PLANTILLAS.rglob("*")):
        if not ruta.is_file() or ruta.suffix in EXTENSIONES_BINARIAS:
            continue
        relativa = ruta.relative_to(DIR_PLANTILLAS).as_posix()
        barridas[relativa] = ruta.read_text(encoding="utf-8")

    assert PLANTILLA_ANCLA in barridas, (
        f"el barrido no vio `{PLANTILLA_ANCLA}`, que es el fichero del hallazgo: "
        f"vio {sorted(barridas)}"
    )
    assert len(barridas) >= SUELO_PLANTILLAS, (
        f"solo se barrieron {len(barridas)} plantillas; un barrido que adelgaza "
        f"se pone verde solo"
    )

    hallazgos = []
    for relativa, texto in barridas.items():
        for numero, linea in enumerate(texto.splitlines(), start=1):
            for prohibido in _citas_prohibidas(linea):
                hallazgos.append(f"{relativa}:{numero} cita `{prohibido}`")
    assert hallazgos == [], (
        "una plantilla cita algo que en el proyecto generado no existe:\n  "
        + "\n  ".join(hallazgos)
    )
