"""Linter de nuestras propias skills.

Exige seis secciones. Las cinco primeras son las del linter de
addyosmani/agent-skills (commit f493377, scripts/lib/skill-lint.js); la sexta,
## Process, es un endurecimiento propio: su skill-anatomy.md la llama «el
corazon de la skill» pero su linter no la exige (spec §7.1).
"""

from __future__ import annotations

import ast
import dataclasses
import json
import pathlib
import re

SECCIONES_REQUERIDAS: list[tuple[str, tuple[str, ...]]] = [
    ("## Overview", ()),
    ("## When to Use", ()),
    ("## Process", ("## Core Process", "## Workflow", "## El proceso")),
    ("## Common Rationalizations", ()),
    ("## Red Flags", ()),
    ("## Verification", ()),
]

# Las exenciones viven aqui, en el codigo, y NO en el frontmatter: una skill no
# puede auto-eximirse. Mismo mecanismo que SECTION_EXEMPT_SKILLS del linter de
# referencia. Cada entrada lleva su justificacion.
SKILLS_EXENTAS_DE_SECCIONES: dict[str, str] = {}

LIMITE_DESCRIPTION = 1024
PATRON_DIRECTORIO = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
PATRON_DISPARADOR = re.compile(r"Use when|Use (before|after|during)", re.IGNORECASE)
PATRON_SOLO_NEGATIVO = re.compile(r"(do not|don't|never) use", re.IGNORECASE)


# --- La gramatica de las citas, en UN solo sitio ----------------------------
#
# Todo lo de este bloque es la gramatica de PRODUCCION del convenio de cita.
# `tests/test_skill_lint.py` la IMPORTA en vez de escribir su propia copia:
# habia dos gramaticas para el mismo convenio --una aqui y otra alli-- y
# estrechar cualquiera de las dos dejaba a la otra en verde, que es la misma
# forma de «arreglo sin guardian» que el propio fichero de tests argumenta un
# nivel mas arriba. Los nombres van sin guion bajo porque cruzan el modulo.

# El prefijo con que la prosa escribe la ruta entera desde la raiz del plugin.
PREFIJO_PLUGIN = "${CLAUDE_PLUGIN_ROOT}/"

# El token de ruta de una cita a referencia: todo lo que precede a
# `referencias/` hasta el primer espacio, backtick, parentesis o coma. Se
# captura el token ENTERO --prefijo incluido-- y no solo el nombre de fichero,
# porque es lo unico que permite distinguir la forma completa de la corta: con
# solo la cola, un prefijo equivocado se leeria como forma corta y resolveria
# por casualidad al fichero correcto.
TOKEN_ANTES_DE_REFERENCIAS = r"[^\s`(),]*referencias/"
PATRON_CITA_REFERENCIA = TOKEN_ANTES_DE_REFERENCIAS + r"[A-Za-z0-9_.-]+\.md"

# Las clases admiten digitos, guiones, puntos y MAYUSCULAS a proposito: con
# `[a-z_]+` una cita a `run_evals2.py` o a
# `assets/plantillas/function/Clase.java.tmpl` no fallaba, DESAPARECIA del
# conjunto auditado --lo que el regex no ve, no existe--. El prefijo literal y
# la extension siguen anclando el patron, asi que ensanchar la clase no abre
# superficie de falso positivo.
PATRON_SCRIPT = r"scripts/([A-Za-z0-9_.-]+\.py)"
PATRON_ASSET = r"assets/([A-Za-z0-9_./-]+\.\w+)"

# La tercera familia: los ficheros de `tests/` que la prosa cita como EJEMPLO.
# Hoy no casa nada --el corpus los cita por directorio, no por ruta de
# fichero--, y se declara asi a proposito: cerrar la familia antes de que
# aparezca la primera cita por ruta cuesta una linea, y descubrirla despues
# cuesta un fichero muerto en la prosa.
# ANCLADO al prefijo, a diferencia de sus dos hermanos: `scripts/` y `assets/`
# son directorios que solo existen en la raiz del plugin, pero `tests/` aparece
# tambien dentro del proyecto generado --`build/reports/tests/test/index.html`
# es la ruta natural del informe de JUnit--. Sin ancla, esa cita casaria como
# `tests/test/index.html`, se resolveria contra la raiz de ESTE plugin, no
# existiria, y el linter se pondria rojo sobre una cita correcta. Un rojo falso
# se arregla aflojando la puerta, que es como mueren las puertas.
# Levantado por la revision de codigo del ciclo 11.
PATRON_TEST = re.escape(PREFIJO_PLUGIN) + r"tests/([A-Za-z0-9_./-]+\.\w+)"

# Las tres familias de ruta A FICHERO, en un solo sitio: el bucle que las
# resuelve las recorre, asi que anadir una cuarta es anadir un par.
FAMILIAS_DE_RUTA: tuple[tuple[str, str], ...] = (
    ("scripts", PATRON_SCRIPT),
    ("assets", PATRON_ASSET),
    ("tests", PATRON_TEST),
)

# Una cita a un DIRECTORIO del plugin: `${CLAUDE_PLUGIN_ROOT}/tests/fixtures/contratos/`.
# Es la unica forma con que la prosa nombra hoy la familia de `tests/` --27
# citas de directorio en el corpus real, ninguna a un fichero-- asi que sin
# esta comprobacion el par de arriba seria un guardian que no guarda nada.
# Ancla en el prefijo literal porque un `${CLAUDE_PLUGIN_ROOT}/...` se resuelve
# SIEMPRE contra la raiz del plugin: no hay ambiguedad con las rutas del
# proyecto generado, que la prosa nunca escribe con ese prefijo.
PATRON_DIRECTORIO_CITADO = r"\$\{CLAUDE_PLUGIN_ROOT\}/([A-Za-z0-9_./-]+/)"

# El nombre de despacho de un agente, `<plugin>:<agente>`, anclado por los DOS
# backticks: sin anclar, cualquier `https://x` o `clave: valor` de la prosa
# entraria en el conjunto. Medido sobre la prosa real de la skill: con los dos
# backticks, cero falsos positivos --solo las cuatro citas a los tres agentes--.
PATRON_DESPACHO = r"`([a-z0-9-]+):([a-z0-9-]+)`"

# Un simbolo de script citado en prosa: `contrato.insumo_vacio`. Exactamente la
# misma forma tiene un NOMBRE DE FICHERO --`andamiar.py`, `DOSSIER.md`--, donde
# el sufijo no es un simbolo sino una extension; medido sobre la prosa real,
# tres `<modulo>.py` casan este patron con un modulo que si esta anclado. Por
# eso la lista de extensiones, que es lo unico que separa las dos lecturas.
PATRON_SIMBOLO = r"`([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)`"
EXTENSIONES_QUE_NO_SON_SIMBOLO = frozenset(
    {
        "py", "md", "json", "xml", "txt", "yml", "yaml", "toml", "ini", "cfg",
        "java", "jar", "zip", "class", "gradle", "properties", "tmpl", "sh",
        "bat", "html", "css", "js", "lock",
    }
)


def citas_de_despacho(texto: str) -> set[tuple[str, str]]:
    """Los `<plugin>:<agente>` que cita un texto, sin juzgar ninguno."""
    return set(re.findall(PATRON_DESPACHO, texto))


def citas_de_simbolo(fuentes: list[tuple[str, str]]) -> list[tuple[str, str, str]]:
    """Los `<modulo>.<simbolo>` del corpus, con su origen.

    El conjunto de modulos se ancla en los `scripts/<modulo>.py` que ese MISMO
    corpus cita por ruta, no en los que hay en disco: anclar en el disco
    convertiria `plugin.key` en un falso positivo el dia que existiera un
    `scripts/plugin.py`, y ademas haria que el conjunto auditado dependiera de
    lo que vigila. El precio de anclar en la prosa es que renombrar un modulo
    y actualizar SOLO sus citas por ruta deja sus citas de simbolo huerfanas y
    sin auditar; eso lo sujeta el suelo antivacuidad de
    `test_el_linter_VE_las_tres_familias_en_la_skill_real`, que exige ver los
    cinco simbolos por su nombre literal.
    """
    modulos = set()
    for _, texto in fuentes:
        for script in re.findall(PATRON_SCRIPT, texto):
            modulos.add(script[: -len(".py")])
    citas = {
        (origen, modulo, simbolo)
        for origen, texto in fuentes
        for modulo, simbolo in re.findall(PATRON_SIMBOLO, texto)
        if modulo in modulos and simbolo not in EXTENSIONES_QUE_NO_SON_SIMBOLO
    }
    return sorted(citas)


@dataclasses.dataclass
class LintResult:
    errors: list[str]
    warnings: list[str]
    exempt: bool


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Extrae el frontmatter YAML simple (clave: valor) y el cuerpo.

    No usa PyYAML —no esta en la biblioteca estandar—: el frontmatter de una
    skill son pares clave-valor planos, y un parser de tres lineas es
    suficiente y sin dependencias.
    """
    if not text.startswith("---"):
        return {}, text
    cierre = text.find("\n---", 3)
    if cierre == -1:
        return {}, text
    bloque = text[3:cierre]
    cuerpo = text[cierre + 4 :]
    campos: dict[str, str] = {}
    for linea in bloque.splitlines():
        if ":" in linea and not linea.lstrip().startswith("#"):
            clave, _, valor = linea.partition(":")
            campos[clave.strip()] = valor.strip()
    return campos, cuerpo


def validar_description(description: str) -> list[str]:
    errores: list[str] = []
    if len(description) > LIMITE_DESCRIPTION:
        errores.append(
            f"description tiene {len(description)} caracteres — supera el limite de {LIMITE_DESCRIPTION}"
        )
    if not PATRON_DISPARADOR.search(description):
        errores.append("description sin condicion de disparo: falta «Use when» (o «Use before/after/during»)")
    elif PATRON_SOLO_NEGATIVO.search(description) and not re.search(
        r"Use when", description, re.IGNORECASE
    ):
        errores.append("description con disparador solo negativo")
    return errores


def lint_skill(
    dir_name: str,
    skills_dir: pathlib.Path,
    known_skills: set[str],
    raiz: pathlib.Path | None = None,
) -> LintResult:
    """Lint de una skill. `raiz` es la del PLUGIN, no la de las skills.

    Se pasa explicita porque las tres familias de citas nuevas --rutas a
    `scripts/*.py` y `assets/*`, nombres de despacho de agente y simbolos de
    script-- se resuelven contra ella. El defecto `skills_dir.parent` existe para
    `scripts/run_evals.py`, que llama con tres argumentos y cuyo `skills_dir` ES
    `<raiz>/skills`.

    Lo que NO hay aqui es un `if not (raiz / "scripts").is_dir(): return []`
    para que las skills sinteticas de la suite no se rompan: eso seria una
    puerta que se salta sin fallar. No hace falta ninguna: una cita a
    `scripts/x.py` resuelta contra una raiz que no tiene `scripts/` es un ERROR
    ruidoso, y «no aplica» significa aqui una sola cosa --que la prosa no cita
    nada de esa familia--, que es exactamente el caso de esas skills.
    """
    if raiz is None:
        raiz = skills_dir.parent
    errores: list[str] = []
    avisos: list[str] = []
    exenta = dir_name in SKILLS_EXENTAS_DE_SECCIONES

    if not PATRON_DIRECTORIO.match(dir_name):
        errores.append(f"el directorio «{dir_name}» no es kebab-case en minusculas")

    ruta = skills_dir / dir_name / "SKILL.md"
    if not ruta.is_file():
        return LintResult([f"no existe {ruta}"], avisos, exenta)

    texto = ruta.read_text(encoding="utf-8")
    campos, cuerpo = parse_frontmatter(texto)

    if not campos:
        errores.append("falta el frontmatter")
    else:
        if "name" not in campos:
            errores.append("falta el campo «name» en el frontmatter")
        elif campos["name"] != dir_name:
            errores.append(
                f"el campo name «{campos['name']}» no coincide con el nombre del directorio «{dir_name}»"
            )
        if "description" not in campos:
            errores.append("falta el campo «description» en el frontmatter")
        else:
            errores.extend(validar_description(campos["description"]))

    if not exenta:
        for canonica, alias in SECCIONES_REQUERIDAS:
            aceptadas = (canonica, *alias)
            if not any(a in cuerpo for a in aceptadas):
                errores.append(f"falta la seccion {canonica}")

    for referida in re.findall(r"`skills/([a-z0-9-]+)/SKILL\.md`", cuerpo):
        if referida not in known_skills:
            avisos.append(f"referencia a una skill desconocida: {referida}")

    propia = skills_dir / dir_name
    fuentes, ilegibles = fuentes_de_la_skill(propia, cuerpo)
    errores.extend(ilegibles)
    errores.extend(_referencias_rotas(dir_name, propia, fuentes))
    # Las otras TRES familias de citas, que hasta el ciclo 10 no miraba nadie:
    # `scripts/*.py` y `assets/*`, los nombres de despacho de los agentes y los
    # simbolos de script. Mismo argumento que el barrido de referencias:
    # renombrar `verificar_bundles.py` dejaba este linter en OK y la skill
    # apuntando a la nada, y el linter es lo que ejecuta quien usa el plugin sin
    # tener la suite.
    errores.extend(_rutas_del_plugin_rotas(raiz, fuentes))
    errores.extend(_agentes_rotos(raiz, fuentes))
    errores.extend(_simbolos_rotos(raiz, fuentes))

    return LintResult(errores, avisos, exenta)


def fuentes_de_la_skill(
    propia: pathlib.Path, cuerpo: str
) -> tuple[list[tuple[str, str]], list[str]]:
    """El corpus que se barre: `SKILL.md` y cada `referencias/*.md`.

    Se devuelve aparte la lista de errores de lectura. Una referencia ILEGIBLE
    SE DECLARA, no tumba el linter: antes de que este barrido existiera nada
    abria esos ficheros, asi que un `.md` guardado en cp1252 --plausible en
    Windows y con prosa acentuada-- no podia romper nada; ahora si, y `main()`
    moriria con traza en vez de imprimir la linea `ERROR` que su lector sabe
    leer. No poder mirarla no se resuelve a favor: cuenta como error, no como
    referencia sana.

    Una skill sin `referencias/` es legitima --los fixtures de la suite lo
    son-- y aqui no es un error, solo nada que barrer.
    """
    fuentes: list[tuple[str, str]] = [("SKILL.md", cuerpo)]
    errores: list[str] = []
    dir_referencias = propia / "referencias"
    if dir_referencias.is_dir():
        for md in sorted(dir_referencias.glob("*.md")):
            try:
                fuentes.append((f"referencias/{md.name}", md.read_text(encoding="utf-8")))
            except (UnicodeDecodeError, OSError) as fallo:
                errores.append(f"referencias/{md.name} no se puede leer como UTF-8: {fallo}")
    return fuentes, errores


def _referencias_rotas(
    dir_name: str, propia: pathlib.Path, fuentes: list[tuple[str, str]]
) -> list[str]:
    """Los `referencias/x.md` que la skill cita y no existen.

    Una referencia renombrada no rompe nada visible --la skill sigue cargando,
    y este linter decia OK-- y el agente que la ejecuta se encuentra la ruta
    muerta en mitad del trabajo. Se admiten las DOS formas con que se citan: la
    completa desde la raiz del plugin y la corta desde la propia skill. Las dos
    se resuelven contra el directorio de ESTA skill; una cita a la referencia
    de otra skill no la juzga esta puerta, y por eso la clasificacion de mas
    abajo la descarta. Levantado por el gate del ciclo 9, sobre el hallazgo de que
    renombrar `entrevista.md` dejaba la suite en verde y este linter en OK.

    El barrido cubre el cuerpo de `SKILL.md` Y el contenido de cada
    `referencias/*.md`, porque las referencias se citan ENTRE SI: hoy
    `entrevista.md` cita `tipos-de-plugin.md` y `tipos-de-plugin.md` cita
    `entrevista.md` de vuelta. Mientras el barrido fue solo el de `SKILL.md`,
    corromper una de esas dos citas dejaba este linter en OK -- reproducido por
    la revision de codigo posterior al ciclo 9, sobre una copia del arbol. Cada error dice QUE fichero
    cita, porque ya no hay un solo origen posible.

    La clasificacion se hace sobre el TOKEN de ruta entero
    (`PATRON_CITA_REFERENCIA`), que es el mismo objeto que importan los tests,
    y no sobre dos regex que capturan solo la cola. Efecto medido del cambio:
    una cita malformada `${CLAUDE_PLUGIN_ROOT}/referencias/x.md` --sin
    `skills/<skill>/` en medio-- antes no casaba ningun patron y desaparecia;
    ahora se lee como forma corta y su fichero se comprueba. Que la forma sea
    la admitida sigue juzgandolo el test, que es donde vive el convenio de
    orden. Desde el ciclo 11 esa misma cita malformada produce ADEMAS un error
    de `_rutas_del_plugin_rotas`, porque `${CLAUDE_PLUGIN_ROOT}/referencias/`
    no es un directorio de la raiz del plugin: dos errores por una cita, y los
    dos ciertos.
    """
    errores: list[str] = []
    dir_referencias = propia / "referencias"
    entera_de_esta_skill = f"skills/{dir_name}/referencias/"
    for origen, texto in fuentes:
        citadas: set[str] = set()
        for token in re.findall(PATRON_CITA_REFERENCIA, texto):
            cola = token[len(PREFIJO_PLUGIN) :] if token.startswith(PREFIJO_PLUGIN) else token
            if cola.startswith(entera_de_esta_skill):
                citadas.add(cola[len(entera_de_esta_skill) :])
            elif cola.startswith("referencias/"):
                citadas.add(cola[len("referencias/") :])
            # Lo demas es una cita a las referencias de OTRA skill: no la juzga
            # esta puerta.
        errores.extend(
            f"{origen} cita `referencias/{fichero}`, que no existe"
            for fichero in sorted(citadas)
            if not (dir_referencias / fichero).is_file()
        )
    return errores


def _rutas_del_plugin_rotas(raiz: pathlib.Path, fuentes: list[tuple[str, str]]) -> list[str]:
    """Los `scripts/*.py`, `assets/*`, `tests/*` y directorios que la skill cita
    y no existen.

    Es la familia mas numerosa --catorce rutas hoy-- y la que la SKILL manda
    EJECUTAR, no leer: renombrar `verificar_bundles.py` dejaba este linter en OK
    y a quien siguiera la skill invocando un fichero que ya no esta. Se resuelve
    contra `raiz`, la del plugin, porque asi es como la prosa las escribe:
    `${CLAUDE_PLUGIN_ROOT}/scripts/verificar_todo.py`.

    Desde el ciclo 11 se miran dos formas mas, por el hallazgo de que
    `tests/fixtures/contratos/` --los EJEMPLOS que la skill manda mirar «antes
    que el fuente»-- era la unica familia sin puerta:

    - `PATRON_TEST`, el par que faltaba en la familia de ficheros. Medido: hoy
      no casa nada, porque el corpus cita esa familia por directorio.
    - `PATRON_DIRECTORIO_CITADO`, que es lo que la hace no vacua: las 27 citas
      de directorio del corpus real se resuelven, y renombrar
      `tests/fixtures/contratos/` pasa a ser un ERROR en vez de un OK.

    Lo que ESTA PUERTA SIGUE SIN VER, y se declara aqui para que no se lea como
    olvido: los cinco contratos canonicos que la SKILL cita por NOMBRE PELADO
    (`function-minimo.md`, `smart-service-completo.md`...) detras de esa cita de
    directorio. La regla natural --«un nombre pelado citado en el mismo parrafo
    que un directorio del plugin tiene que existir dentro de el»-- se midio
    sobre el corpus real y abre falso positivo a la primera: el parrafo de la
    SKILL que cita `assets/plantillas/` y `scripts/` nombra tambien
    `appian-plugin.xml` y `build.gradle`, que son ficheros del proyecto
    GENERADO y no existen aqui. Un rojo permanente se arregla aflojando la
    puerta, asi que la puerta no se pone. Quien sujeta esos cinco nombres es
    `CONTRATOS_CANONICOS`, en la suite, por los dos lados.
    """
    errores: list[str] = []
    for origen, texto in fuentes:
        for familia, patron in FAMILIAS_DE_RUTA:
            errores.extend(
                f"{origen} cita `{familia}/{relativo}`, que no existe"
                for relativo in sorted(set(re.findall(patron, texto)))
                if not (raiz / familia / relativo).is_file()
            )
        errores.extend(
            f"{origen} cita el directorio `{relativo}`, que no existe"
            for relativo in sorted(set(re.findall(PATRON_DIRECTORIO_CITADO, texto)))
            if not (raiz / relativo).is_dir()
        )
    return errores


def _nombre_del_plugin(raiz: pathlib.Path) -> str | None:
    """El `name` de `.claude-plugin/plugin.json`, o None si no se puede leer."""
    try:
        manifiesto = json.loads(
            (raiz / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    nombre = manifiesto.get("name")
    return nombre if isinstance(nombre, str) and nombre else None


def _agentes_rotos(raiz: pathlib.Path, fuentes: list[tuple[str, str]]) -> list[str]:
    """Los `<plugin>:<agente>` que la skill cita y no se pueden despachar.

    El prefijo de despacho es el `name` de `.claude-plugin/plugin.json` (regla
    observada por el gate del ciclo 5), asi que se lee de ahi en vez de
    cablearlo: cablearlo haria que renombrar el plugin dejara las citas
    apuntando a la nada sin que nada se pusiera rojo.

    Se juzga una cita cuando su prefijo ES el del plugin --y entonces el agente
    tiene que existir-- o cuando su sufijo nombra un agente que existe y el
    prefijo NO es el del plugin, que es como se ve un renombrado a medias. Un
    `clave:valor` cualquiera de la prosa no cae en ninguno de los dos casos.

    Sin manifiesto no hay forma de resolver el prefijo. Eso no se resuelve a
    favor: si el corpus no cita ningun `a:b`, no aplica y no hay nada que decir;
    si cita alguno, se declara NO COMPROBADO como error en vez de dejarlo pasar
    en silencio.
    """
    citas = sorted(
        {(origen, prefijo, sufijo) for origen, texto in fuentes for prefijo, sufijo in citas_de_despacho(texto)}
    )
    if not citas:
        return []
    nombre = _nombre_del_plugin(raiz)
    if nombre is None:
        return [
            f"{origen} cita `{prefijo}:{sufijo}` y no se puede leer «.claude-plugin/plugin.json»: "
            f"el nombre de despacho queda SIN COMPROBAR"
            for origen, prefijo, sufijo in citas
        ]
    errores: list[str] = []
    for origen, prefijo, sufijo in citas:
        existe = (raiz / "agents" / f"{sufijo}.md").is_file()
        if prefijo == nombre and not existe:
            errores.append(f"{origen} cita al agente `{prefijo}:{sufijo}`, que no existe")
        elif prefijo != nombre and existe:
            errores.append(
                f"{origen} cita al agente `{sufijo}` con el prefijo «{prefijo}», "
                f"que no es el nombre del plugin («{nombre}»)"
            )
    return errores


def _simbolos_de_modulo(ruta: pathlib.Path) -> tuple[set[str], str | None]:
    """Los nombres que un script define en su nivel superior, o el fallo.

    Se leen con `ast` y no con un regex sobre el fuente: una mencion en un
    comentario o en un docstring contaria como definicion, que es justo lo que
    esta comprobacion existe para no hacer.
    """
    try:
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError) as fallo:
        return set(), str(fallo)
    nombres: set[str] = set()
    for nodo in arbol.body:
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nombres.add(nodo.name)
        elif isinstance(nodo, ast.Assign):
            nombres.update(t.id for t in nodo.targets if isinstance(t, ast.Name))
        elif isinstance(nodo, ast.AnnAssign) and isinstance(nodo.target, ast.Name):
            nombres.add(nodo.target.id)
    return nombres, None


def _simbolos_rotos(raiz: pathlib.Path, fuentes: list[tuple[str, str]]) -> list[str]:
    """Los `<modulo>.<simbolo>` que la skill nombra y el script ya no define.

    Cinco hoy, y son instrucciones ejecutables: la skill manda mirar
    `contrato.ANOTACION_POR_PALETA` o comprobar `verificar_todo.estado_de_sumision`.
    Renombrar cualquiera de los cinco no rompe ningun import --nadie importa
    desde la prosa-- asi que la suite seguia verde y este linter en OK.

    Va en el LINTER y no solo en un test por el mismo argumento que cerro el
    barrido de referencias: quien usa el plugin no tiene la suite, y abrir el
    `.py` para mirar cuesta un `ast.parse`. El modulo que no se puede leer se
    declara igual que la referencia ilegible; si ademas se cita por ruta,
    `_rutas_del_plugin_rotas` ya habra dicho que el fichero no existe.
    """
    errores: list[str] = []
    cache: dict[str, tuple[set[str], str | None]] = {}
    for origen, modulo, simbolo in citas_de_simbolo(fuentes):
        if modulo not in cache:
            cache[modulo] = _simbolos_de_modulo(raiz / "scripts" / f"{modulo}.py")
        disponibles, fallo = cache[modulo]
        if fallo is not None:
            errores.append(
                f"{origen} cita `{modulo}.{simbolo}` y `scripts/{modulo}.py` no se puede leer: {fallo}"
            )
        elif simbolo not in disponibles:
            errores.append(
                f"{origen} cita `{modulo}.{simbolo}`, que `scripts/{modulo}.py` no define"
            )
    return errores


def main() -> int:
    raiz = pathlib.Path(__file__).resolve().parents[1]
    skills_dir = raiz / "skills"
    if not skills_dir.is_dir():
        print(f"No existe {skills_dir}")
        return 1
    conocidas = {d.name for d in skills_dir.iterdir() if d.is_dir()}
    total_errores = 0
    for nombre in sorted(conocidas):
        resultado = lint_skill(nombre, skills_dir, conocidas, raiz=raiz)
        marca = " (secciones exentas)" if resultado.exempt else ""
        for e in resultado.errors:
            print(f"ERROR {nombre}: {e}")
        for w in resultado.warnings:
            print(f"AVISO {nombre}: {w}")
        if not resultado.errors:
            print(f"OK    {nombre}{marca}")
        total_errores += len(resultado.errors)
    return 1 if total_errores else 0


if __name__ == "__main__":
    raise SystemExit(main())
