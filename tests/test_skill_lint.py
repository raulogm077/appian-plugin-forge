import json
import pathlib
import re

import skill_lint

# La raiz del plugin, una sola vez. Estaba recalculada en cuatro tests y
# arrastrada como parametro por `_texto`/`_prosa` solo por eso; es la misma
# forma que ya usan `test_licencia_del_plugin.py`, `test_humo_e2e.py`,
# `test_escaner_superficie.py`, `test_insumo_declarado.py` y
# `test_tipos_y_nombres_reservados.py`.
RAIZ = pathlib.Path(__file__).resolve().parents[1]
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "skills"


def test_skill_conforme_no_da_errores():
    resultado = skill_lint.lint_skill("skill-buena", FIXTURES, {"skill-buena"})
    assert resultado.errors == []


_PLANTILLA_DE_SKILL = """---
name: skill-con-referencias
description: Hace una cosa. Use when el usuario pide esa cosa.
---

## Overview
## When to Use
## Process
## Common Rationalizations
## Red Flags
## Verification

{citas}
"""

# Las DOS formas de cita que el linter admite, escritas una vez. Los dos tests
# de referencias rotas las ejercen las dos, y con el texto copiado en cada uno
# se podia estrechar una forma en un test y dejarla ancha en el otro sin que
# nada lo delatara.
CITA_CORTA = "`referencias/{}`"
CITA_ENTERA = "`${{CLAUDE_PLUGIN_ROOT}}/skills/skill-con-referencias/referencias/{}`"


def _skill_sintetica(tmp_path):
    """El arbol minimo sobre el que se ejerce el linter: una skill con una
    referencia VIVA y nada mas.

    Sintetica y no un fixture del repositorio a proposito: un fixture ataria
    estos tests a lo que escriban otros. Lo que se escribe DENTRO --la
    `SKILL.md` y las citas de cada pasada-- se queda en cada test, porque no es
    andamiaje: en el segundo test la `SKILL.md` limpia es el control que hace
    que el guardian guarde algo.
    """
    skills = tmp_path / "skills"
    skill = skills / "skill-con-referencias"
    (skill / "referencias").mkdir(parents=True)
    (skill / "referencias" / "viva.md").write_text("contenido", encoding="utf-8")
    return skills, skill


def test_una_referencia_citada_QUE_NO_EXISTE_es_error(tmp_path):
    """El linter que la propia SKILL manda ejecutar tiene que ver la ruta rota.

    El gate del ciclo 9 midio el agujero por el otro lado: renombrar
    `entrevista.md` dejaba la SKILL apuntando a la nada, la suite en verde y
    `skill_lint.py` en OK. El perimetro de la suite ya se cerro; esto cierra el
    linter, que es lo que ejecuta quien usa el plugin sin tener la suite.

    Se ejercen las DOS formas de cita, cada una en su direccion, sobre una
    skill sintetica: un fixture del repositorio ataria este test a lo que
    escriban otros.

    Este test cubre la mitad que cita `SKILL.md`. La otra --lo que las
    referencias se citan ENTRE SI-- la cubre
    `test_una_referencia_rota_citada_DENTRO_DE_OTRA_REFERENCIA_es_error`, y
    hasta la revision posterior al ciclo 9 no la cubria nadie: la frase de arriba prometia el linter
    entero y solo era cierta para esta mitad.
    """
    skills, skill = _skill_sintetica(tmp_path)

    def lint(citas):
        (skill / "SKILL.md").write_text(
            _PLANTILLA_DE_SKILL.format(citas=citas), encoding="utf-8"
        )
        return skill_lint.lint_skill(
            "skill-con-referencias", skills, {"skill-con-referencias"}
        ).errors

    # Control: con las dos formas apuntando a un fichero que existe, cero
    # errores. Sin esto, un linter que devolviera error siempre pasaria el
    # resto del test.
    assert lint(
        f"Ver {CITA_CORTA.format('viva.md')} y {CITA_ENTERA.format('viva.md')}."
    ) == []

    for forma in (CITA_CORTA, CITA_ENTERA):
        errores = lint(f"Ver {forma.format('muerta.md')}.")
        # El error dice QUE fichero cita, no solo que algo cita: desde que el
        # barrido tiene mas de un origen posible, un error sin origen obliga a
        # buscar la cita a mano por toda la skill.
        assert any("muerta.md" in e and "SKILL.md" in e for e in errores), (
            f"el linter no ve una referencia rota citada como {forma.format('muerta.md')}: "
            f"{errores}"
        )


def test_una_referencia_rota_citada_DENTRO_DE_OTRA_REFERENCIA_es_error(tmp_path):
    """El otro lado del barrido: las referencias se citan ENTRE SI.

    El linter solo miraba el cuerpo de `SKILL.md`, y su docstring prometia
    cerrar "el linter, que es lo que ejecuta quien usa el plugin sin tener la
    suite" -- cierto solo para lo que cita `SKILL.md` directamente. La lente del
    revision de codigo posterior al ciclo 9 lo midio sobre una copia del arbol: `referencias/entrevista.md`
    cita `tipos-de-plugin.md` y este cita `entrevista.md` de vuelta, y
    corrompiendo la cita que vive DENTRO de `tipos-de-plugin.md` el linter
    devolvia `errors == []`.

    Se ejercen las DOS formas de cita, como en el test de arriba, sobre una
    skill sintetica: un fixture del repositorio ataria este test a lo que
    escriban otros. La `SKILL.md` de la skill sintetica se deja limpia a
    proposito -- si ella tambien citara el fichero muerto, el barrido viejo
    bastaria para poner el test en verde y no guardaria nada.
    """
    skills, skill = _skill_sintetica(tmp_path)

    # La `SKILL.md` limpia NO va en el helper: es el control de ESTE test. Si
    # citara el fichero muerto, el barrido viejo --solo el cuerpo de la
    # SKILL-- bastaria para ponerlo en verde y no guardaria nada.
    (skill / "SKILL.md").write_text(
        _PLANTILLA_DE_SKILL.format(citas=f"Ver {CITA_ENTERA.format('viva.md')}."),
        encoding="utf-8",
    )

    def lint(citas):
        (skill / "referencias" / "citadora.md").write_text(citas, encoding="utf-8")
        return skill_lint.lint_skill(
            "skill-con-referencias", skills, {"skill-con-referencias"}
        ).errors

    # Control: con las dos formas apuntando a un fichero que existe, cero
    # errores. Sin esto, un linter que devolviera error siempre pasaria el resto
    # del test.
    assert lint(
        f"Ver {CITA_CORTA.format('viva.md')} y {CITA_ENTERA.format('viva.md')}."
    ) == []

    for forma in (CITA_CORTA, CITA_ENTERA):
        errores = lint(f"Ver {forma.format('muerta.md')}.")
        assert any(
            "muerta.md" in e and "referencias/citadora.md" in e for e in errores
        ), (
            f"el linter no ve una referencia rota citada DENTRO de otra referencia como "
            f"{forma.format('muerta.md')}: {errores}"
        )


def test_una_referencia_ILEGIBLE_se_declara_y_no_tumba_el_linter(tmp_path):
    """El coste que trajo abrir ficheros que antes nadie abria.

    Hasta que el barrido de referencias existio, `lint_skill` no leia ningun
    `referencias/*.md`, asi que uno guardado en cp1252 --plausible: Windows y
    prosa acentuada-- no podia romper nada. Ahora si: el `read_text` lanzaba
    `UnicodeDecodeError` FUERA de la funcion y `main()` moria con traza en vez
    de imprimir la linea `ERROR <skill>: ...` que su lector sabe leer. Y no
    poder mirar una referencia no se resuelve a favor: cuenta como error.
    Levantado por la revision de codigo posterior al ciclo 10.
    """
    skills, skill = _skill_sintetica(tmp_path)
    (skill / "SKILL.md").write_text(
        _PLANTILLA_DE_SKILL.format(citas=f"Ver {CITA_ENTERA.format('viva.md')}."),
        encoding="utf-8",
    )
    # Bytes que no son UTF-8 valido: «á» en cp1252 es 0xE1 suelto.
    (skill / "referencias" / "rota.md").write_bytes(b"prosa con acento: \xe1\n")

    resultado = skill_lint.lint_skill(
        "skill-con-referencias", skills, {"skill-con-referencias"}
    )
    assert any("rota.md" in e and "UTF-8" in e for e in resultado.errors), (
        f"la referencia ilegible no se declaro como error: {resultado.errors}"
    )
    # Y la sana de al lado se sigue barriendo: una ilegible no puede llevarse
    # por delante el analisis de las demas.
    assert not any("viva.md" in e for e in resultado.errors), resultado.errors


# --- Las otras TRES familias de citas, en el linter -------------------------
#
# El barrido de referencias cubria UNA familia de cuatro. La SKILL cita ademas
# rutas a `scripts/*.py` y `assets/*`, los nombres de despacho de los tres
# agentes y cinco simbolos de script, y ninguna de esas tres tenia guardian EN
# EL LINTER: renombrar `verificar_bundles.py` dejaba `skill_lint.py` en OK con
# la skill mandando ejecutar un fichero que ya no esta (gate del ciclo 10,
# Mayor 3). Mismo argumento que cerro el barrido de referencias: el linter es lo
# que ejecuta quien usa el plugin sin tener la suite.
#
# Los tres tests corren sobre un arbol SINTETICO --skill y raiz de plugin-- y le
# pasan la raiz EXPLICITA a `lint_skill`. Es la unica forma honesta: una guarda
# del tipo `if not (raiz / "scripts").is_dir(): return []` para que las skills
# sinteticas no se rompan seria una puerta que se salta sin fallar. No hace
# falta, porque «no aplica» aqui significa una sola cosa --que la prosa no cita
# nada de esa familia-- y eso ya no produce errores por si solo.


def _raiz_sintetica(tmp_path):
    """La raiz de plugin minima contra la que se resuelven las tres familias.

    Sintetica y no la del repositorio por lo mismo que la skill sintetica: el
    arbol real ata estos tests a lo que escriban otros. Lo que si se ejerce del
    real es la GRAMATICA, que se importa de `skill_lint`.
    """
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "forge-de-prueba", "version": "0.0.1"}), encoding="utf-8"
    )
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "agente-vivo.md").write_text(
        "---\nname: agente-vivo\n---\n", encoding="utf-8"
    )
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "modulo_vivo.py").write_text(
        "CONSTANTE_VIVA = 1\n\n\ndef funcion_viva():\n    return CONSTANTE_VIVA\n",
        encoding="utf-8",
    )
    (tmp_path / "assets" / "plantillas").mkdir(parents=True)
    (tmp_path / "assets" / "plantillas" / "Viva.java.tmpl").write_text("x", encoding="utf-8")
    # La familia de `tests/`, que hasta el ciclo 11 no miraba nadie: son los
    # EJEMPLOS que la skill manda mirar antes que el fuente.
    (tmp_path / "tests" / "fixtures" / "contratos").mkdir(parents=True)
    (tmp_path / "tests" / "fixtures" / "contratos" / "canonico-vivo.md").write_text(
        "x", encoding="utf-8"
    )


def _lintador(tmp_path):
    """Devuelve `lint(citas) -> errores` sobre la skill sintetica de `tmp_path`."""
    skills, skill = _skill_sintetica(tmp_path)
    _raiz_sintetica(tmp_path)

    def lint(citas):
        (skill / "SKILL.md").write_text(
            _PLANTILLA_DE_SKILL.format(citas=citas), encoding="utf-8"
        )
        return skill_lint.lint_skill(
            "skill-con-referencias", skills, {"skill-con-referencias"}, raiz=tmp_path
        ).errors

    return lint


def test_una_RUTA_A_SCRIPT_ASSET_O_TEST_citada_QUE_NO_EXISTE_es_error(tmp_path):
    """La familia mas numerosa: catorce rutas que la SKILL manda EJECUTAR.

    El perimetro de la suite ya las cubria para los cinco ficheros de `PROSA`;
    esto cierra el linter, que es lo que corre sin la suite delante.

    El tercer par --`tests/`-- entro en el ciclo 11 y se ejerce aqui aunque hoy
    no case nada en la prosa real: el corpus cita esa familia por DIRECTORIO
    (`tests/fixtures/contratos/`), no por ruta de fichero, asi que la puerta
    que hoy la sostiene es la de directorios, en el test de abajo. Ejercerlo
    igual es lo que impide que el par se anada y se pueda quitar sin que nada
    se ponga rojo.
    """
    lint = _lintador(tmp_path)

    # Control: con las tres rutas apuntando a ficheros que existen, cero
    # errores. Sin esto, un linter que devolviera error siempre pasaria el resto.
    assert lint(
        "Ejecuta `${CLAUDE_PLUGIN_ROOT}/scripts/modulo_vivo.py` sobre "
        "`${CLAUDE_PLUGIN_ROOT}/assets/plantillas/Viva.java.tmpl`, y mira "
        "`${CLAUDE_PLUGIN_ROOT}/tests/fixtures/contratos/canonico-vivo.md`."
    ) == []

    for ruta in (
        "scripts/modulo_muerto.py",
        "assets/plantillas/Muerta.java.tmpl",
        "tests/fixtures/contratos/canonico-muerto.md",
    ):
        errores = lint("Ejecuta `${CLAUDE_PLUGIN_ROOT}/" + ruta + "`.")
        assert any(ruta in e and "SKILL.md" in e for e in errores), (
            f"el linter no ve la ruta rota `{ruta}`: {errores}"
        )


def test_una_CITA_A_UN_DIRECTORIO_DEL_PLUGIN_QUE_NO_EXISTE_es_error(tmp_path):
    """La forma con la que la prosa cita HOY la familia de `tests/`.

    Hallazgo del gate del ciclo 11: `${CLAUDE_PLUGIN_ROOT}/tests/fixtures/contratos/`
    --los ejemplos que la SKILL manda mirar «antes que el fuente»-- era la unica
    familia de citas sin ninguna puerta. Renombrar el directorio dejaba el
    linter en OK y la skill apuntando a la nada.

    Se ejerce con un directorio que NO es `scripts/` ni `assets/` a proposito:
    con uno de esos dos, un linter que solo mirara las familias de fichero
    pasaria igual.

    Lo que esta puerta NO alcanza --y por que no se intento-- esta escrito en
    el docstring de `skill_lint._rutas_del_plugin_rotas`: los cinco contratos
    canonicos se citan por nombre pelado, y la regla del parrafo abre falso
    positivo a la primera. Quien los sujeta es `CONTRATOS_CANONICOS`, mas
    abajo.
    """
    lint = _lintador(tmp_path)

    # Control: el directorio que existe no produce error.
    assert lint("Mira `${CLAUDE_PLUGIN_ROOT}/tests/fixtures/contratos/` primero.") == []

    errores = lint("Mira `${CLAUDE_PLUGIN_ROOT}/tests/fixtures/canonicos/` primero.")
    assert any("tests/fixtures/canonicos/" in e and "SKILL.md" in e for e in errores), (
        f"el linter no ve la cita a un directorio que no existe: {errores}"
    )

    # Y una ruta de FICHERO tambien nombra a su directorio: renombrar
    # `assets/plantillas/` con las citas de fichero intactas se veria.
    errores = lint("Copia `${CLAUDE_PLUGIN_ROOT}/plantillas/Viva.java.tmpl`.")
    assert any("plantillas/" in e for e in errores), (
        f"un prefijo de directorio equivocado no produjo ningun error: {errores}"
    )


def test_una_CITA_A_UN_AGENTE_QUE_NO_EXISTE_es_error(tmp_path):
    """Los tres nombres de despacho, que solo miraba un test de la suite.

    Se ejercen los tres modos de rotura, porque son distintos: el agente que no
    existe, el prefijo que ya no es el del plugin --un renombrado a medias, que
    es como se rompen de verdad-- y el arbol sin manifiesto, donde el prefijo no
    se puede resolver y eso NO se resuelve a favor.
    """
    lint = _lintador(tmp_path)

    assert lint("Lanza `forge-de-prueba:agente-vivo` con la tarea.") == []
    # Y un `clave:valor` cualquiera de la prosa no es una cita de despacho: si
    # lo fuera, esta puerta seria un rojo permanente y acabaria desactivada.
    assert lint("El bloque lleva `clave:valor` y nada mas.") == []

    errores = lint("Lanza `forge-de-prueba:agente-muerto` con la tarea.")
    assert any("agente-muerto" in e and "SKILL.md" in e for e in errores), errores

    errores = lint("Lanza `otro-forge:agente-vivo` con la tarea.")
    assert any("otro-forge" in e and "agente-vivo" in e for e in errores), (
        f"un prefijo que no es el del plugin tiene que fallar, no desaparecer: {errores}"
    )

    # Sin manifiesto no hay prefijo que resolver. Con una cita delante, eso se
    # declara SIN COMPROBAR; sin ninguna, no aplica y no se dice nada.
    (tmp_path / ".claude-plugin" / "plugin.json").unlink()
    errores = lint("Lanza `forge-de-prueba:agente-vivo` con la tarea.")
    assert any("SIN COMPROBAR" in e for e in errores), (
        f"sin manifiesto la cita de despacho se resolvio a favor: {errores}"
    )
    assert lint("Aqui no se cita ningun agente.") == []


def test_un_SIMBOLO_DE_SCRIPT_citado_QUE_NO_EXISTE_es_error(tmp_path):
    """Los cinco `contrato.x` / `verificar_todo.x` que la SKILL nombra.

    Van en el LINTER y no solo en un test: son instrucciones ejecutables --«mira
    `contrato.ANOTACION_POR_PALETA`»-- y renombrar el simbolo no rompe ningun
    import, porque nadie importa desde la prosa. El coste es abrir el `.py`, que
    es un `ast.parse`.

    El ancla del barrido es la cita POR RUTA del propio corpus, no el disco: sin
    `scripts/modulo_vivo.py` citado, `modulo_vivo.lo_que_sea` no se lee como
    simbolo. Es la limitacion conocida --renombrar el modulo y actualizar solo
    sus rutas deja los simbolos huerfanos-- y quien la sujeta es el suelo
    literal de `test_el_linter_VE_las_tres_familias_en_la_skill_real`.
    """
    lint = _lintador(tmp_path)
    ancla = "Ejecuta `${CLAUDE_PLUGIN_ROOT}/scripts/modulo_vivo.py`. "

    assert lint(ancla + "Mira `modulo_vivo.funcion_viva` y `modulo_vivo.CONSTANTE_VIVA`.") == []

    for simbolo in ("modulo_vivo.funcion_muerta", "modulo_vivo.CONSTANTE_MUERTA"):
        errores = lint(ancla + f"Mira `{simbolo}`.")
        assert any(simbolo in e and "SKILL.md" in e for e in errores), (
            f"el linter no ve el simbolo inexistente `{simbolo}`: {errores}"
        )

    # Un `<modulo>.<extension>` es una cita al FICHERO, no a un simbolo. Sin
    # esta distincion `andamiar.py`, `verificar_jar.py` y `verificar_licencias.py`
    # --los tres estan en la prosa real-- serian rojos permanentes, y un rojo
    # permanente se arregla aflojando la puerta.
    assert lint(ancla + "El andamiaje lo hace `modulo_vivo.py`.") == []


def test_falta_seccion_process_es_error():
    resultado = skill_lint.lint_skill("skill-mala", FIXTURES, {"skill-mala"})
    assert any("## Process" in e for e in resultado.errors)


def test_description_demasiado_larga_es_error():
    campos = {"name": "x", "description": "Use when " + "a" * 1030}
    errores = skill_lint.validar_description(campos["description"])
    assert any("1024" in e for e in errores)


def test_description_sin_disparador_es_error():
    errores = skill_lint.validar_description("Hace cosas con plugins de Appian.")
    assert any("Use when" in e for e in errores)


def test_name_debe_coincidir_con_directorio():
    resultado = skill_lint.lint_skill("skill-mala", FIXTURES, {"skill-mala"})
    assert any("name" in e and "directorio" in e for e in resultado.errors)


# --- El prefijo de despacho de los agentes, atado ---------------------------
#
# `SKILL.md` cita a los tres agentes como `appian-plugin-forge:<agente>`, y ese
# prefijo es el campo `name` de `.claude-plugin/plugin.json` (regla observada
# por el gate del ciclo 5 sobre dos plugins reales y un control negativo).
# Estaba acoplado SIN NADA QUE LO ATARA: renombrar el plugin --o un agente--
# rompia las cuatro citas en silencio, y ni `skill_lint` ni ningun test lo
# veian. Las dos lentes del ciclo 5 coincidieron en señalarlo.

def test_las_citas_a_agentes_casan_con_el_plugin_y_con_su_frontmatter():
    nombre_plugin = json.loads(
        (RAIZ / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )["name"]

    reales = set()
    for md in sorted((RAIZ / "agents").glob("*.md")):
        m = re.search(r"^name:\s*(\S+)", md.read_text(encoding="utf-8"), re.M)
        assert m, f"{md.name} no declara `name:` en su frontmatter"
        assert m.group(1) == md.stem, f"{md.name}: `name:` no casa con el fichero"
        reales.add(m.group(1))
    assert reales, "el barrido no encontro ningun agente: seria un verde vacuo"

    # La gramatica del nombre de despacho es la de PRODUCCION
    # (`skill_lint.citas_de_despacho`), no un regex copiado aqui: desde el ciclo
    # 10 el linter juzga esas mismas citas, y con dos gramaticas se podia
    # estrechar la suya --dejando de ver una cita rota-- con este test en verde.
    # Este test es ademas el suelo antivacuidad de esa gramatica: exige que vea
    # las citas reales de la SKILL y del README, en las dos direcciones.
    def citados_en(fichero):
        texto = (RAIZ / fichero).read_text(encoding="utf-8")
        return texto, {
            sufijo
            for prefijo, sufijo in skill_lint.citas_de_despacho(texto)
            if prefijo == nombre_plugin
        }

    skill, citados = citados_en(pathlib.Path("skills") / "crear-plugin-appian" / "SKILL.md")
    assert citados, "la skill no cita ningun agente por nombre de despacho"

    # LAS DOS DIRECCIONES. La primera version solo exigia `citados <= reales`,
    # asi que un agente que nadie cita --una capa sin llamador, que es lo que
    # este proyecto persigue en todas sus formas-- entraba sin ponerse rojo:
    # comprobado en el ciclo 6 anadiendo un `agents/fantasma.md` y viendo la
    # suite en verde.
    assert citados == reales, (
        f"agentes citados que no existen: {sorted(citados - reales)}; "
        f"agentes que existen y no cita nadie: {sorted(reales - citados)}"
    )

    # Y que no quede ninguna cita por RUTA, que es lo que invita a leer el
    # prompt del agente en vez de lanzarlo con `Agent`.
    assert "agents/" not in skill, "la skill vuelve a citar un agente por su ruta"

    # El README queda DENTRO del perimetro: un renombrado hecho bien en la
    # skill lo dejaba desfasado sin que nada fallara (M6 del ciclo 6), y es de
    # donde alguien copiaria el nombre para lanzar el agente.
    readme, citados_readme = citados_en("README.md")
    # LA MISMA dosis que el lado skill, no media. El ciclo 7 midio los tres
    # agujeros que dejaba `citados_readme <= reales`, y los tres salen de que
    # una inclusion se satisface VACUAMENTE:
    #   M7 renombrar el plugin en `plugin.json` deja el README citando tres
    #      nombres de despacho muertos, y `∅ <= reales` pasa: suite en verde.
    #   M8 el README puede volver al defecto que el ciclo 6 arreglo a mano
    #      --nombre pelado y cita por ruta-- porque el nombre pelado no casa el
    #      regex y por tanto desaparece del conjunto.
    #   M9 un agente que el README no lista deja incompleta la tabla que se
    #      titula «El equipo de runtime».
    # El coste se acepta a sabiendas: anadir un agente OBLIGA a editar el
    # README. Es la decision, no un efecto colateral.
    assert citados_readme, "el README no cita ningun agente por nombre de despacho"
    assert citados_readme == reales, (
        f"el README cita agentes que no existen: {sorted(citados_readme - reales)}; "
        f"agentes que existen y el README no lista: {sorted(reales - citados_readme)}"
    )
    assert "agents/" not in readme, "el README vuelve a citar un agente por su ruta"


# --- El perimetro de prosa, cerrado por los dos lados -----------------------
#
# Lo levanto el gate del ciclo 9 (Mayor): el barrido de mas abajo recorria SOLO
# `README.md` y `SKILL.md`, y solo buscaba `scripts/` y `assets/`. Todo lo demas
# no fallaba: DESAPARECIA del conjunto auditado. La lente midio la consecuencia
# --renombrar `referencias/entrevista.md` deja a la SKILL citando la nada con la
# suite en verde y `skill_lint` en OK--, que es el mismo mecanismo del nombre
# pelado de agente y del `run_evals2.py` que ya estan anotados aqui abajo.
#
# La lista va como LITERAL PROPIO y no como glob sobre `referencias/`: un glob
# encoge cuando se borra lo que vigila, asi que el aserto se cumpliria solo. El
# literal es `REFERENCIAS`, aqui abajo; `PROSA` deriva de el, que no es lo
# mismo que derivar de lo que vigila --sigue sin mirar el disco--.
NOMBRE_SKILL = "crear-plugin-appian"
DIR_SKILL = f"skills/{NOMBRE_SKILL}"
SKILL_REL = f"{DIR_SKILL}/SKILL.md"

# Las referencias que existen. LITERAL PROPIO, y clavado a disco por el aserto
# `en_disco == set(REFERENCIAS)` de
# `test_el_perimetro_cubre_TODAS_las_referencias_y_sus_citas`: por eso puede
# hacer de ancla del perimetro entero.
REFERENCIAS = (
    "entrevista.md",
    "tipos-de-plugin.md",
    "certificado.md",
    "entorno-windows.md",
    "secsp-servlet.md",
)

# La cola de `PROSA` SE DERIVA de `REFERENCIAS`, no se copia. Con las dos
# listas escritas a mano el perimetro tenia un agujero del tamano de cada
# referencia nueva, y estaba medido: anadir `referencias/nueva.md` al disco
# citando un `scripts/no_existe.py`, meterlo en `REFERENCIAS` y citarlo entero
# desde la SKILL --sin tocar `PROSA`-- dejaba la suite en verde y `skill_lint`
# en OK, porque el barrido de scripts y assets solo recorre `PROSA` y la
# referencia nueva no estaba ahi.
PROSA = (
    "README.md",
    SKILL_REL,
    *(f"{DIR_SKILL}/referencias/{r}" for r in REFERENCIAS),
)

# De los cuatro, los dos que DEBEN nombrar algun script. Los de `referencias/`
# no: `tipos-de-plugin.md` no nombra ninguno hoy y no tiene por que, asi que
# exigirselo seria un rojo del primer dia --y un rojo del primer dia se arregla
# aflojando el aserto, que es peor que no tenerlo--.
PROSA_CON_SCRIPTS = ("README.md", SKILL_REL)

# Los dos patrones del barrido de prosa son los de PRODUCCION, importados y no
# copiados. Hasta el ciclo 10 vivian aqui como literales propios y el linter
# tenia los suyos: dos gramaticas para el mismo convenio de cita, y este fichero
# argumentaba un nivel mas arriba que un guardian no debe ejercer *una copia*
# del regex mientras hacia justo eso respecto de `skill_lint`. Estrechar el de
# produccion --el que corre para quien usa el plugin sin la suite-- dejaba estos
# tests en verde.
#
# `test_los_patrones_de_ruta_VEN_los_nombres_con_mayuscula` ejerce ESTOS MISMOS
# objetos; el porque de sus clases de caracteres vive ahora en `skill_lint`,
# junto al regex.
PATRON_SCRIPT = skill_lint.PATRON_SCRIPT
PATRON_ASSET = skill_lint.PATRON_ASSET

# Un asset del repo cuyo nombre lleva mayuscula, para armar el guardian del
# ensanchado contra un fichero que existe de verdad. Literal propio y no un
# glob, por lo mismo que `PROSA`: un glob encoge cuando se borra lo que vigila.
ASSET_CON_MAYUSCULA = "plantillas/function/Clase.java.tmpl"

# Las DOS formas de cita admitidas, y ninguna mas. La completa --con o sin el
# prefijo de la variable-- resuelve desde la raiz del plugin; la corta
# `referencias/x.md` resuelve desde el directorio de la skill, y solo vale
# dentro de ese directorio: en el README, que vive en la raiz, `referencias/`
# no lleva a ninguna parte para quien lo lea, aunque el fichero exista.
# El Overview de la SKILL declara ese convenio --entera la primera vez, corta
# despues-- asi que exigirlo aqui no inventa una regla.
#
# El prefijo y el token de ruta son los de PRODUCCION, por lo mismo que los dos
# patrones de arriba: desde el ciclo 10 `skill_lint._referencias_rotas`
# clasifica la cita sobre ESE token, asi que aqui se importa en vez de
# aproximarlo. Lo que se queda en este fichero es el juicio de FORMA y de ORDEN
# --que la primera cita de la SKILL sea la entera--, porque ese convenio lo
# declara el Overview de ESTA skill y no toda skill futura; el linter solo
# juzga si el fichero citado existe.
PREFIJO_PLUGIN = skill_lint.PREFIJO_PLUGIN
_ANTES_DE_REFERENCIAS = skill_lint.TOKEN_ANTES_DE_REFERENCIAS

# Los cinco contratos canonicos que la SKILL §1 manda mirar «antes que el
# fuente». Ahi se citan por NOMBRE PELADO (`function-minimo.md`), nunca por
# ruta, asi que ningun patron de ruta los ve: van como literal propio.
CONTRATOS_CANONICOS = (
    "function-minimo.md",
    "writer-function-minimo.md",
    "smart-service-minimo.md",
    "smart-service-completo.md",
    "servlet-minimo.md",
)

# Lo que este perimetro NO barre, a proposito, para que el proximo gate no lo
# lea como olvido -- y por que `docs/como-funciona.md` NO esta en `PROSA`
# aunque sea la cosa mas natural del mundo (ciclo 11): ese documento habla de
# TRES arboles --este plugin, el proyecto generado y el repo de desarrollo-- y
# su convenio de rutas lo declara en su propia seccion «Convencion de rutas».
# La gramatica de `PROSA` esta anclada en prefijos (`scripts/`, `assets/`), asi
# que sobre el mapa no daria ni un falso positivo... y tampoco veria sus citas
# a `skills/`, `agents/`, `evals/` ni `tests/`: 17 rutas que DESAPARECERIAN del
# conjunto auditado, que es el defecto que este fichero persigue. Peor aun: una
# familia nueva entraria en silencio. Por eso el mapa tiene barrido propio
# --`test_el_mapa_del_repositorio_no_cita_rutas_que_no_existen`, al final-- que
# CLASIFICA cada cita en vez de filtrarla, y donde un primer segmento
# desconocido es rojo.
#
# Y las citas a `docs/superpowers/specs/...` y a
# `docs/AI Plugin Generator skill Support Guide.md` apuntan al REPO DE
# DESARROLLO, no al plugin --la propia SKILL lo dice al citarlas--, asi que
# comprobar su existencia desde la raiz del plugin seria un rojo permanente
# sobre ficheros que no viajan con el.
#
# Y el reparto con el linter, desde el ciclo 10: `skill_lint` juzga las cuatro
# familias de citas --referencias, rutas a `scripts/`y `assets/`, nombres de
# despacho y simbolos de script-- sobre el corpus de la SKILL y sus
# referencias, que es lo que una skill es. El README NO entra ahi: el linter
# lintea skills, no la prosa del repositorio. Por eso `PROSA` lo sigue
# incluyendo y el bucle de mas abajo sigue existiendo aunque el linter cubra ya
# los otros cuatro ficheros.


def _texto(relativo):
    return (RAIZ / relativo).read_text(encoding="utf-8")


def _prosa():
    return [(f, _texto(f)) for f in PROSA]


def test_el_README_no_puede_nombrar_scripts_NI_VERSIONES_que_ya_no_existen():
    """El resto del perímetro del README, que era una sola línea.

    El ciclo 7 lo dejó como comprobación pendiente: el guardián de agentes es
    lo único que mira el README, así que renombrar cualquiera de los cinco
    scripts que documenta lo dejaba mintiendo en verde — y el snippet de
    `marketplace.json` fija la versión a mano, la misma que gobierna
    `/plugin update`, sin nada que la ate a `plugin.json`.
    """
    readme = _texto("README.md")

    # LOS DOS FICHEROS, no solo el que lee un humano. El ciclo 8 midio el
    # agujero: renombrar `scripts/verificar_jar.py` dejaba 462 en verde y
    # `skill_lint` en OK, porque el perimetro cubria las cinco rutas del README
    # y no las DIEZ que la SKILL invoca como `${CLAUDE_PLUGIN_ROOT}/scripts/x.py`.
    # Es el mismo argumento del arreglo anterior aplicado donde vale mas: el
    # README se lee, la SKILL se ejecuta.
    #
    # LOS CUATRO desde el ciclo 9 (`PROSA`): `referencias/entrevista.md` invoca
    # `scripts/contrato.py` igual que la SKILL, y nadie lo miraba.
    #
    # Los dos patrones y el porque de sus clases de caracteres viven arriba,
    # en `PATRON_SCRIPT` y `PATRON_ASSET`; quien los ejerce es
    # `test_los_patrones_de_ruta_VEN_los_nombres_con_mayuscula`. Este bucle NO
    # los guarda: sobre la prosa de hoy, la version estrecha y la ancha producen
    # el mismo conjunto en los cinco ficheros, porque ninguno cita todavia un
    # asset con mayuscula. Medido, no supuesto (revision posterior al ciclo 9).
    assets_vistos = set()
    for fichero, texto in _prosa():
        nombrados = set(re.findall(PATRON_SCRIPT, texto))
        if fichero in PROSA_CON_SCRIPTS:
            assert nombrados, f"{fichero} ya no nombra ningun script: seria un verde vacuo"
        for script in sorted(nombrados):
            assert (RAIZ / "scripts" / script).is_file(), (
                f"{fichero} nombra `scripts/{script}`, que no existe"
            )
        # Y los assets, por el mismo motivo: `generar_indice_tipos.py` escribe
        # `indice-tipos-{version}.json`, asi que un salto de SDK renombra el
        # fichero. Los consumidores en codigo se ponen rojos y se arreglan en
        # esa misma edicion; estas dos lineas de prosa se quedarian en verde
        # para siempre nombrando un asset que ya no existe.
        assets = set(re.findall(PATRON_ASSET, texto))
        assets_vistos |= assets
        for asset in sorted(assets):
            assert (RAIZ / "assets" / asset).is_file(), (
                f"{fichero} nombra `assets/{asset}`, que no existe"
            )
    # El bucle de assets no tenia guarda de vacuidad --el de scripts si-- y con
    # ella no se habria podido llegar al ciclo 9 con un patron que devuelve `[]`
    # sin que nada se quejara. Va en el agregado y no por fichero porque
    # `tipos-de-plugin.md` no cita ningun asset y no tiene por que.
    assert assets_vistos, "ningun fichero de PROSA nombra ya un asset: seria un verde vacuo"

    # Desde el 21-sep-2026 `.claude-plugin/marketplace.json` VIAJA con el plugin
    # (antes el README ensenaba a escribirlo a mano). Su entrada copia campos de
    # `plugin.json`, y `claude plugin validate` no cruza los dos manifiestos:
    # valida el que encuentra. Lo que se ata aqui es que los dos digan lo mismo
    # --`version` gobierna `/plugin update`; `name` es el nombre de despacho--
    # y que el README instale con el par `<plugin>@<marketplace>` real.
    manifiesto = json.loads((RAIZ / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    marketplace = json.loads(
        (RAIZ / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
    )
    entradas = [p for p in marketplace["plugins"] if p.get("name") == manifiesto["name"]]
    assert len(entradas) == 1, (
        f"marketplace.json deberia declarar exactamente una entrada llamada "
        f"«{manifiesto['name']}» y declara {len(entradas)}"
    )
    entrada = entradas[0]
    for campo in ("version", "description"):
        assert entrada.get(campo) == manifiesto[campo], (
            f"marketplace.json declara {campo}={entrada.get(campo)!r} y plugin.json "
            f"va por {manifiesto[campo]!r}: `/plugin update` mira el primero"
        )
    # `"./"` y NO `{"source": "github", "repo": ...}`: medido el 21-sep-2026,
    # la forma `github` hace que `claude plugin install` clone por SSH
    # (`git@github.com`), que en un equipo sin clave para GitHub --el de
    # cualquiera que llegue nuevo-- muere con «Host key verification failed».
    # `./` copia el plugin del propio clon del marketplace, que `marketplace
    # add` ya trajo por HTTPS: sin segundo clon y sin SSH.
    assert entrada["source"] == "./", (
        "la entrada del marketplace ya no es relativa al propio repo: la forma `github` "
        "clona por SSH y falla en un equipo sin clave"
    )
    # La orden de instalacion lleva los dos nombres (`plugin@marketplace`), y
    # los dos son datos, no prosa: el del plugin y el del marketplace.
    orden = f"/plugin install {manifiesto['name']}@{marketplace['name']}"
    assert orden in readme, f"el README no ensena la orden de instalacion real «{orden}»"
    repo = entrada["homepage"].removeprefix("https://github.com/")
    assert f"/plugin marketplace add {repo}" in readme, (
        "el README no ensena a anadir el marketplace desde el repo publico"
    )


def test_los_patrones_de_ruta_VEN_los_nombres_con_mayuscula():
    """El ensanchado de las clases de caracteres, con guardian propio.

    El ciclo 9 ensancho `[a-z...]` a `[A-Za-z...]` en los dos patrones y lo
    anoto como trampa armada. No lo estaba: la lente de la revision posterior al ciclo 9 corrio los dos
    regex, viejo y nuevo, contra el contenido real de los cinco ficheros de
    `PROSA` y obtuvo EXACTAMENTE el mismo conjunto en todos -- ningun fichero de
    prosa cita hoy `Clase.java.tmpl` ni ninguno de los otros dos assets con
    mayuscula. Es decir: revertir el ensanchado dejaba la suite en verde, que es
    un arreglo sin guardian.

    Este test es el guardian. Ejerce los patrones sobre texto sintetico, porque
    lo que se vigila es el PATRON y no lo que la prosa diga hoy; el fichero
    contra el que se arma la trampa si es real, para que el ensanchado siga
    justificado por algo que existe y no por una hipotesis.
    """
    # Si este asset se renombra a minusculas, el test se pone rojo y toca elegir
    # otro fichero real, no aflojar el patron.
    assert (RAIZ / "assets" / ASSET_CON_MAYUSCULA).is_file(), (
        f"`assets/{ASSET_CON_MAYUSCULA}` ya no existe: el guardian del ensanchado se "
        f"quedaria sin fichero real que lo justifique"
    )
    texto = f"La plantilla de la clase vive en `assets/{ASSET_CON_MAYUSCULA}` y se copia."
    assert set(re.findall(PATRON_ASSET, texto)) == {ASSET_CON_MAYUSCULA}, (
        f"`PATRON_ASSET` no ve `assets/{ASSET_CON_MAYUSCULA}`: una cita a un asset con "
        f"mayuscula no fallaria, desapareceria del conjunto auditado"
    )

    # El lado de los scripts va con nombre sintetico y SIN comprobar disco: hoy
    # no existe ningun `scripts/Foo.py`, asi que aqui se guarda el patron por
    # simetria con el de assets --el mecanismo es el mismo-- y no la existencia
    # de un fichero. Sin esto, estrechar solo el patron de scripts pasaria.
    texto_script = "El validador se invoca como `scripts/Foo.py` desde la raiz."
    assert set(re.findall(PATRON_SCRIPT, texto_script)) == {"Foo.py"}, (
        "`PATRON_SCRIPT` no ve `scripts/Foo.py`: un script con mayuscula desapareceria "
        "del conjunto auditado en vez de fallar"
    )


def test_el_perimetro_cubre_TODAS_las_referencias_y_sus_citas():
    """Las dos familias de citas que el ciclo 9 encontro sin vigilante.

    El barrido de arriba solo conocia `scripts/` y `assets/`. La SKILL cita
    ademas sus dos referencias por ruta y sus cinco contratos canonicos por
    nombre pelado, y las propias referencias se citan entre si. Nada de eso
    tenia guardian: renombrar `entrevista.md` dejaba a la SKILL apuntando a la
    nada con la suite en verde y `skill_lint` en OK (medido por la lente del
    ciclo 9).
    """
    skill = _texto(SKILL_REL)
    dir_referencias = RAIZ / DIR_SKILL / "referencias"

    # LAS DOS DIRECCIONES, como en el guardian de agentes. `REFERENCIAS` es un
    # literal, asi que por si solo no ve una referencia NUEVA que nadie barre ni
    # nadie cita; este aserto la obliga a entrar en el perimetro. El coste se
    # acepta a sabiendas, igual que con el README y los agentes: anadir una
    # referencia OBLIGA a editar `REFERENCIAS`. Es la decision. `PROSA` YA NO:
    # deriva de `REFERENCIAS`, asi que la referencia nueva entra sola en el
    # barrido de scripts y assets --que es donde estaba el agujero--.
    en_disco = {p.name for p in sorted(dir_referencias.glob("*.md"))}
    assert en_disco == set(REFERENCIAS), (
        f"referencias en disco que el perimetro no barre: {sorted(en_disco - set(REFERENCIAS))}; "
        f"referencias que el perimetro declara y no existen: {sorted(set(REFERENCIAS) - en_disco)}"
    )
    # Y la cita ENTERA ANTES QUE NINGUNA CORTA, que es lo que hace legible la
    # forma corta del resto: sin una cita completa previa, `referencias/x.md`
    # solo se resuelve si ya sabes donde vive la skill. El convenio del Overview
    # es literalmente "enteras la primera vez y como `referencias/<fichero>.md`
    # a partir de ahi", o sea una regla de ORDEN.
    #
    # La version anterior solo exigia que la entera existiera EN ALGUN SITIO, y
    # eso NO es el convenio: reordenar el documento --una cita corta primero y la
    # entera mas abajo-- lo dejaba en verde violando justo lo que el comentario
    # decia comprobar. Medido por la lente de la revision posterior al ciclo 9.
    #
    # Se juzga la SKILL y solo la SKILL: la frase del Overview habla de como cita
    # este documento, y ese es el alcance que se promete aqui.
    for nombre in REFERENCIAS:
        apariciones = [
            m.group(0)
            for m in re.finditer(_ANTES_DE_REFERENCIAS + re.escape(nombre), skill)
        ]
        assert apariciones, (
            f"la SKILL ya no cita `referencias/{nombre}` de ninguna forma: "
            f"una referencia sin llamador"
        )
        primera = apariciones[0]
        cola = primera[len(PREFIJO_PLUGIN):] if primera.startswith(PREFIJO_PLUGIN) else primera
        assert cola.startswith(f"{DIR_SKILL}/referencias/"), (
            f"la PRIMERA cita de `referencias/{nombre}` en la SKILL es `{primera}`, que no es "
            f"la ruta entera: una cita corta que nada ancla todavia"
        )

    # La cita se comprueba ENTERA, no solo su nombre de fichero: se captura el
    # token de ruta COMPLETO --prefijo `${CLAUDE_PLUGIN_ROOT}/` incluido-- y se
    # exige que sea una de las dos formas admitidas. Capturar solo la cola
    # dejaria pasar un prefijo equivocado (`${CLAUDE_PLUGIN_ROOT}/referencias/x.md`,
    # sin `skills/crear-plugin-appian/` en medio): se leeria como forma corta y
    # resolveria por casualidad al fichero correcto, que es exactamente el
    # agujero que este bloque existe para cerrar.
    #
    # El token se toma hasta el primer espacio, backtick, parentesis o coma, asi
    # que una cita partida en dos lineas se escapa del barrido: las citas van
    # SIEMPRE en una sola linea.
    citadas = set()
    for fichero, texto in _prosa():
        for token in re.findall(skill_lint.PATRON_CITA_REFERENCIA, texto):
            cola = token[len(PREFIJO_PLUGIN):] if token.startswith(PREFIJO_PLUGIN) else token
            if cola.startswith("referencias/") and not token.startswith(PREFIJO_PLUGIN):
                # Forma corta: solo desde dentro del propio directorio de la skill.
                assert fichero.startswith(DIR_SKILL + "/"), (
                    f"{fichero} cita `{token}` en forma corta desde fuera de {DIR_SKILL}/"
                )
                destino = RAIZ / DIR_SKILL / cola
            else:
                assert cola.startswith(f"{DIR_SKILL}/referencias/"), (
                    f"{fichero} cita `{token}`, que no es ni la ruta completa desde la raiz "
                    f"del plugin ni la corta desde la skill"
                )
                destino = RAIZ / cola
            citadas.add(cola)
            assert destino.is_file(), f"{fichero} cita `{token}`, que no existe"
    # Suelo antivacuidad con literal propio: un patron que deja de casar nada
    # satisface el bucle de arriba sin mirar nada, que es justo el defecto que
    # este test cierra.
    assert {pathlib.PurePosixPath(r).name for r in citadas} == set(REFERENCIAS), (
        f"el perimetro solo vio citas a {sorted(citadas)}: falta alguna referencia por citar"
    )

    # Los contratos canonicos de la SKILL §1. Se citan por NOMBRE PELADO entre
    # comillas invertidas, no por ruta, asi que van como literal propio y se
    # comprueban por los dos lados: que la SKILL los siga citando y que existan.
    #
    # Deliberadamente NO se barren todos los `.md` pelados de la SKILL, que
    # seria lo generico: hoy incluiria `DOSSIER.md`, que es un fichero del
    # proyecto GENERADO y no existe aqui, y en las referencias `SKILL.md`. Un
    # barrido asi seria rojo permanente por falso positivo, y un rojo permanente
    # acaba desactivandose.
    dir_contratos = RAIZ / "tests" / "fixtures" / "contratos"
    assert "tests/fixtures/contratos/" in skill, (
        "la SKILL ya no manda mirar `tests/fixtures/contratos/` antes que el fuente"
    )
    for nombre in CONTRATOS_CANONICOS:
        assert f"`{nombre}`" in skill, f"la SKILL ya no cita el contrato canonico `{nombre}`"
        assert (dir_contratos / nombre).is_file(), (
            f"la SKILL cita `tests/fixtures/contratos/{nombre}`, que no existe"
        )


def test_el_linter_pasa_SOBRE_LA_SKILL_REAL():
    """El linter, contra el arbol de verdad y no contra fixtures.

    Hallazgo de altitud: NADA de la suite corria `lint_skill` sobre la skill
    real. Los tres tests de arriba usan `fixtures/skills/skill-buena` y
    `skill-mala`, y los dos de referencias rotas montan una skill sintetica en
    `tmp_path`; `run_evals.py` si lo hace, pero ningun test invoca su `main()`.
    Consecuencia: sobre los ficheros reales el perimetro efectivo era solo el
    de los tests de este fichero, y la gramatica de PRODUCCION --los dos regex
    de `skill_lint._referencias_rotas`-- no se ejercia nunca contra la prosa
    real. Que `python scripts/skill_lint.py` diga OK a mano no es lo mismo:
    quien rompa la skill sin lanzarlo no se entera.

    `known_skills` se deriva como lo hace `main()`, no se escribe a mano, para
    que este test ejerza la MISMA llamada que corre en produccion.

    Lo que este test NO puede garantizar por si solo es que el barrido de
    referencias tenga algo que barrer; eso lo sujeta
    `test_el_perimetro_cubre_TODAS_las_referencias_y_sus_citas`, que obliga a
    la SKILL a citar cada `REFERENCIAS` por su ruta entera -- justo la forma
    que el primer regex de produccion tiene que ver.
    """
    skills = RAIZ / "skills"
    conocidas = {d.name for d in skills.iterdir() if d.is_dir()}
    assert NOMBRE_SKILL in conocidas, (
        f"`skills/{NOMBRE_SKILL}` ya no existe: este guardian se quedaria sin skill que mirar"
    )
    resultado = skill_lint.lint_skill(NOMBRE_SKILL, skills, conocidas, raiz=RAIZ)
    assert resultado.errors == []


# El suelo antivacuidad de las tres familias nuevas. Los tres literales salen
# del acta del ciclo 10 (Mayor 3), que los nombra uno a uno; no se derivan de la
# prosa ni del disco, que es lo que vigilan. Van como SUELO (`<=`, `in`) y no
# como igualdad: la otra direccion --una cita nueva que se escape del barrido--
# no puede darse, porque el linter recorre la prosa entera y juzga todo lo que
# casa; y una igualdad se pondria roja cuando alguien anada una cita legitima.
#
# La familia de los agentes no repite suelo aqui: lo pone
# `test_las_citas_a_agentes_casan_con_el_plugin_y_con_su_frontmatter`, que ya
# ejerce `skill_lint.citas_de_despacho` sobre la SKILL real en las dos
# direcciones.
SIMBOLOS_DE_SCRIPT = (
    "contrato.ANOTACION_POR_PALETA",
    "contrato.SUBPAQUETE_DOMINIO",
    "contrato.insumo_vacio",
    "contrato.linea_no_aplica",
    "verificar_todo.estado_de_sumision",
)
SCRIPT_ANCLA = "verificar_bundles.py"
ASSET_ANCLA = "reglas-de-validacion.md"
# El ancla de la forma que entro en el ciclo 11. Es el directorio del hallazgo:
# la familia de citas que ninguna puerta vigilaba. Va aqui y no en un test
# aparte porque el suelo es el mismo -- que el OK del linter sobre la skill real
# no sea vacuo.
DIRECTORIO_ANCLA = "tests/fixtures/contratos/"


def test_el_linter_VE_las_tres_familias_en_la_skill_real():
    """Que el OK del linter sobre la skill real no sea vacuo.

    `test_el_linter_pasa_SOBRE_LA_SKILL_REAL` dice que no hay errores; eso lo
    cumple igual de bien un barrido que no mira nada. Estrechar cualquiera de
    las tres gramaticas nuevas --o romper el ancla de los simbolos, que se
    deriva de las citas por ruta del propio corpus-- lo dejaria en OK sin haber
    comprobado ni una ruta. Esto es lo que se pone rojo si eso pasa.

    `verificar_bundles.py` es el ejemplo literal del acta: era la rotura que
    dejaba el linter en OK y la skill mandando ejecutar un fichero inexistente.
    """
    _, cuerpo = skill_lint.parse_frontmatter(_texto(SKILL_REL))
    fuentes, ilegibles = skill_lint.fuentes_de_la_skill(RAIZ / DIR_SKILL, cuerpo)
    assert ilegibles == [], ilegibles
    # El corpus es `SKILL.md` MAS las referencias: si se quedara en una sola
    # fuente, las familias de las referencias dejarian de auditarse.
    assert len(fuentes) == 1 + len(REFERENCIAS), [f for f, _ in fuentes]

    scripts, assets, directorios = set(), set(), set()
    for _, texto in fuentes:
        scripts |= set(re.findall(skill_lint.PATRON_SCRIPT, texto))
        assets |= set(re.findall(skill_lint.PATRON_ASSET, texto))
        directorios |= set(re.findall(skill_lint.PATRON_DIRECTORIO_CITADO, texto))
    assert SCRIPT_ANCLA in scripts, (
        f"el barrido de rutas ya no ve `scripts/{SCRIPT_ANCLA}` en la skill: {sorted(scripts)}"
    )
    assert ASSET_ANCLA in assets, (
        f"el barrido de rutas ya no ve `assets/{ASSET_ANCLA}` en la skill: {sorted(assets)}"
    )
    # La forma del ciclo 11. Sin este suelo, estrechar `PATRON_DIRECTORIO_CITADO`
    # --o quitarlo-- dejaria la familia de `tests/` otra vez sin puerta y el
    # linter en OK, que es exactamente como llego el hallazgo.
    assert DIRECTORIO_ANCLA in directorios, (
        f"el barrido de directorios ya no ve `{DIRECTORIO_ANCLA}` en la skill: "
        f"{sorted(directorios)}"
    )

    vistos = {f"{modulo}.{simbolo}" for _, modulo, simbolo in skill_lint.citas_de_simbolo(fuentes)}
    assert set(SIMBOLOS_DE_SCRIPT) <= vistos, (
        f"el barrido de simbolos ya no ve {sorted(set(SIMBOLOS_DE_SCRIPT) - vistos)}: "
        f"o la prosa dejo de citarlos, o el ancla por ruta del modulo se rompio"
    )


# --- El mapa del repositorio, dentro de un perimetro ------------------------
#
# `docs/como-funciona.md` son 553 lineas con mas de cien citas de ruta y hasta
# el ciclo 11 NINGUN barrido automatico lo alcanzaba: `skill_lint` solo abre
# `skills/**`, el barrido de plantillas de `tests/test_lo_que_viaja.py` solo
# `assets/plantillas/**`, y `PROSA` no lo incluye. Sus citas estaban vivas
# porque una lente las comprobo a mano, que es la definicion de lo que este
# proyecto no acepta como guardian.
#
# El barrido CLASIFICA en vez de filtrar, y esa es la diferencia que importa:
# un primer segmento que no este ni en `FAMILIAS_DEL_MAPA` ni en
# `AJENOS_DEL_MAPA` es ROJO. Un `if` que se limitara a saltarse lo que no
# reconoce dejaria entrar una familia nueva sin puerta -- exactamente el
# agujero que este test cierra.
MAPA = "docs/como-funciona.md"

# La cita de ruta del mapa: un token entre comillas invertidas con al menos una
# barra. Entre comillas y no suelto porque asi es como el documento las escribe,
# y porque un barrido sin ancla leeria `95 / 85` o `_en_US`/`_es_ES` como rutas.
# Limitacion declarada: las etiquetas de los diagramas mermaid
# (`I[/"assets/indice-tipos-26.3.json"/]`) no llevan comillas invertidas y no se
# barren; todas las que aparecen ahi se citan ademas en la prosa, que si entra.
PATRON_RUTA_CITADA = r"`([A-Za-z0-9_.<>*-]+(?:/[A-Za-z0-9_.<>*-]*)+)`"

# Los primeros segmentos que SON de este plugin: su ruta se resuelve desde la
# raiz y tiene que existir. Literal propio y no `RAIZ.iterdir()`: derivarlo del
# disco haria que borrar `agents/` encogiera el conjunto auditado en vez de
# ponerlo rojo.
FAMILIAS_DEL_MAPA = (
    "scripts", "assets", "skills", "agents", "evals", "tests", ".claude-plugin",
)

# Y los que NO, que es la excepcion explicita y estrecha. No es un `if` que
# apague la comprobacion: es la lista cerrada de los OTROS DOS arboles de los
# que habla el documento, declarada por el propio documento en su seccion
# «Convencion de rutas» -- el proyecto generado (con prefijo o por nombre
# suelto: `build/`, `config/`, `src/`) y el repo de desarrollo (`docs/`). Ojo a
# `docs/`: es ambiguo a proposito --los tres arboles tienen uno-- y por eso no
# puede ir en la lista de arriba aunque exista en este plugin: el mapa cita
# `docs/retrospectiva-fase1.md` (repo de desarrollo) y `docs/contrato.md`
# (proyecto generado), y ninguno de los dos vive aqui.
AJENOS_DEL_MAPA = ("<proyecto-generado>", "docs", "build", "config", "src")

# Suelo antivacuidad. Las anclas son una por familia --si una deja de citarse,
# el barrido adelgaza sin fallar-- y el numero es el conjunto de rutas
# comprobadas, hoy 50.
ANCLAS_DEL_MAPA = (
    "scripts/verificar_todo.py",
    "assets/plantillas/comun/build.gradle.tmpl",
    "skills/crear-plugin-appian/SKILL.md",
    "agents/plugin-contract-reviewer.md",
    "evals/cases/disparo.json",
    "tests/fixtures/contratos/",
)
SUELO_DEL_MAPA = 45


def test_el_mapa_del_repositorio_no_cita_rutas_que_no_existen():
    """El mapa entra en un perimetro, y el README deja de no enlazarlo.

    Dos hallazgos del ciclo 11 en un solo guardian, porque su modo de fallo es
    el mismo --una ruta que ya no lleva a ninguna parte--:

    - El mapa no lo alcanzaba ningun barrido (hallazgo de fondo). Aqui se
      clasifica cada cita: familia del plugin, arbol ajeno declarado, o ROJO.
    - Nadie lo enlazaba: `grep -rn "como-funciona"` daba cero coincidencias
      fuera del propio fichero, asi que viajaba con el plugin y era
      inalcanzable desde dentro. El aserto del README ata las dos direcciones:
      renombrar el mapa o quitar el enlace ponen rojo lo mismo.
    """
    assert (RAIZ / MAPA).is_file(), f"`{MAPA}` ya no existe: este guardian se queda sin mapa"
    assert MAPA in _texto("README.md"), (
        f"el README ya no enlaza `{MAPA}`: el mapa viaja con el plugin y vuelve a ser "
        f"inalcanzable desde dentro"
    )

    texto = _texto(MAPA)
    comprobadas, ajenas, sin_clasificar = set(), set(), set()
    for token in re.findall(PATRON_RUTA_CITADA, texto):
        primero = token.split("/")[0]
        if primero in FAMILIAS_DEL_MAPA:
            comprobadas.add(token)
        elif primero in AJENOS_DEL_MAPA:
            ajenas.add(token)
        else:
            sin_clasificar.add(token)

    # Una familia nueva no se salta: se declara. Es lo que impide que este
    # barrido se quede ciego por crecimiento del documento.
    assert sin_clasificar == set(), (
        f"{MAPA} cita rutas cuyo primer segmento no esta clasificado: "
        f"{sorted(sin_clasificar)}. Si son de este plugin, van en FAMILIAS_DEL_MAPA; "
        f"si son del proyecto generado o del repo de desarrollo, en AJENOS_DEL_MAPA"
    )

    for ancla in ANCLAS_DEL_MAPA:
        assert ancla in comprobadas, (
            f"el barrido del mapa ya no ve `{ancla}`: una familia entera puede haber "
            f"dejado de auditarse sin que nada falle"
        )
    assert len(comprobadas) >= SUELO_DEL_MAPA, (
        f"solo se comprobaron {len(comprobadas)} rutas del mapa; un barrido que adelgaza "
        f"se pone verde solo"
    )
    # Y que la lista de ajenos siga teniendo trabajo: si el mapa dejara de citar
    # los otros dos arboles, la excepcion habria dejado de estar justificada.
    assert ajenas, (
        f"{MAPA} ya no cita ninguna ruta del proyecto generado ni del repo de desarrollo: "
        f"AJENOS_DEL_MAPA se quedo sin razon de ser"
    )

    rotas = sorted(t for t in comprobadas if not (RAIZ / t).exists())
    assert rotas == [], f"{MAPA} cita rutas de este plugin que no existen: {rotas}"


# --- La coletilla de lo que no viaja con el plugin --------------------------
#
# Aviso del ciclo 11 sobre `assets/reglas-de-validacion.md:3`, generalizado: ese
# fichero citaba `docs/auditoria-guia-vs-documentacion-appian.md` SIN la
# coletilla «repo de desarrollo» que llevan las otras cinco citas cruzadas.
# Importa porque el fichero VIAJA --`/plugin install` copia el directorio
# entero-- y su proposito es responder «por que me rechazas esto» con una
# fuente oficial: quien tenga el plugin instalado sigue la cita y no encuentra
# nada. El mismo defecto tenia el README en dos sitios mas, que el aviso no
# nombraba y este barrido si encuentra.
#
# La lista es de DOCUMENTOS DEL REPO DE DESARROLLO, no de `docs/` a secas: la
# prosa cita ademas `docs/contrato.md`, `docs/CERTIFICADO.md` y otros cuatro que
# son del PROYECTO GENERADO y donde la coletilla seria falsa. Va por prefijo
# para que `docs/superpowers/specs/` cubra las dos specs sin listarlas.
DOCS_DEL_REPO_DE_DESARROLLO = (
    "docs/superpowers/specs/",
    "docs/validaciones/",
    "docs/auditoria-guia-vs-documentacion-appian.md",
    "docs/retrospectiva-fase1.md",
    "docs/AI Plugin Generator skill Support Guide.md",
)

# Lo que se exige es la parte PORTANTE de la coletilla --la que le dice al
# lector que eso no esta en su copia--, no la frase entera: dos de las citas
# vivas la escriben como prosa corriente («§1, repo de desarrollo»), y exigir el
# literal completo obligaria a retorcerlas. La forma canonica y completa es
# «(repo de desarrollo; no viaja con el plugin)», y es la que se escribe al
# arreglar una.
COLETILLA_DE_DESARROLLO = "repo de desarrollo"

# La coletilla va DETRAS de la cita en todas las apariciones vivas, a veces
# partida en dos lineas. La ventana es de caracteres y no de lineas por eso.
VENTANA_COLETILLA = 200

# Toda la prosa que viaja: `PROSA` mas el mapa y los dos assets de texto. Deriva
# de `PROSA`, que a su vez deriva de `REFERENCIAS`: una referencia nueva entra
# sola en este barrido.
PROSA_QUE_VIAJA = (
    *PROSA, MAPA, "CHANGELOG.md", "assets/reglas-de-validacion.md", "assets/dossier.md",
)

# El suelo, con la cita del hallazgo como ancla literal.
CITA_ANCLA_DE_DESARROLLO = (
    "assets/reglas-de-validacion.md",
    "docs/auditoria-guia-vs-documentacion-appian.md",
)
SUELO_CITAS_DE_DESARROLLO = 8

PATRON_CITA_DOCS = r"`(docs/[^`]+)`"


def test_lo_que_no_viaja_con_el_plugin_se_cita_diciendolo():
    """Una cita a la spec o a la auditoria, desde dentro del plugin instalado.

    Quien tiene el plugin instalado no tiene el repo de desarrollo: la spec, la
    auditoria, la retrospectiva y los informes del gate no viajan. Citarlos sin
    decirlo manda al lector a una ruta que en su copia no existe, y el sitio
    donde mas duele es `assets/reglas-de-validacion.md`, cuyo trabajo es
    responder con una fuente oficial por que una regla rechaza algo.

    No se comprueba la EXISTENCIA de esos ficheros --no estan aqui, y exigirla
    seria un rojo permanente--: se comprueba que la cita se declare.
    """
    vistas = []
    sin_coletilla = []
    for fichero in PROSA_QUE_VIAJA:
        texto = _texto(fichero)
        for m in re.finditer(PATRON_CITA_DOCS, texto):
            citado = m.group(1)
            if not citado.startswith(DOCS_DEL_REPO_DE_DESARROLLO):
                continue
            vistas.append((fichero, citado))
            # El blanco se normaliza antes de buscar: la coletilla se parte por
            # el salto de linea en dos de las citas vivas («del repo\nde
            # desarrollo»), y sin esto serian dos falsos positivos. Medido.
            ventana = re.sub(r"\s+", " ", texto[m.end() : m.end() + VENTANA_COLETILLA])
            if COLETILLA_DE_DESARROLLO not in ventana:
                linea = texto[: m.start()].count("\n") + 1
                sin_coletilla.append(f"{fichero}:{linea} cita `{citado}`")

    assert CITA_ANCLA_DE_DESARROLLO in vistas, (
        f"el barrido ya no ve la cita del hallazgo {CITA_ANCLA_DE_DESARROLLO}: vio {vistas}"
    )
    assert len(vistas) >= SUELO_CITAS_DE_DESARROLLO, (
        f"solo se vieron {len(vistas)} citas al repo de desarrollo; un barrido que "
        f"adelgaza se pone verde solo"
    )
    assert sin_coletilla == [], (
        "prosa que viaja con el plugin y cita material que NO viaja, sin decirlo:\n  "
        + "\n  ".join(sin_coletilla)
    )


# ---------------------------------------------------------------------------
# LOS DOS RESIDUOS SIN GUARDIAN QUE DEJO EL CICLO 12
#
# El auditor de verdes los dejo anotados sin escalarlos, porque ninguna de las
# dos afirmaciones era falsa: el «cuatro familias» del mapa cuadra con los
# cuatro comprobadores, y el anclaje de `PATRON_TEST` es correcto. Lo que no
# habia era quien lo notara al dejar de serlo — desanclado el patron en una
# copia, este modulo seguia 20/20 verde y el linter seguia en OK.
# ---------------------------------------------------------------------------


def test_el_mapa_cuenta_bien_las_familias_de_citas_que_vigila_el_linter():
    """El numeral de `docs/como-funciona.md`, contado sobre el fuente.

    Es el mismo patron que ancla los dos numeros de la SKILL, aplicado al
    tercer sitio donde el ciclo 12 escribio una cuenta a mano. La expectativa
    sale de `skill_lint.py` --cuantos comprobadores de citas rotas alimentan la
    lista de errores-- y lo vigilado es la prosa del mapa. Dos fuentes.
    """
    numerales = {
        "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
    }
    mapa = _texto(MAPA)
    escritos = re.findall(r"\*\*(\w+) familias de citas rotas\*\*", mapa)
    assert escritos, (
        f"`{MAPA}` ya no dice cuantas familias de citas rotas vigila el linter: el numero "
        f"que este test ancla desaparecio de la prosa"
    )

    fuente = (RAIZ / "scripts" / "skill_lint.py").read_text(encoding="utf-8")
    # `\s*` para que un `extend(` con el argumento en la linea siguiente cuente
    # igual: `skill_lint` ya escribe varios `errores.extend(` partidos asi, y
    # una quinta familia anadida en ese estilo dejaba el recuento en cuatro
    # --con la prosa diciendo «cuatro» y el linter vigilando cinco--, que es
    # justo la deriva que este test existe para ver. /code-review del ciclo 12.
    comprobadores = set(re.findall(r"errores\.extend\(\s*(_\w+)\(", fuente))
    assert comprobadores, (
        "no se detecto ningun comprobador en `skill_lint.py`: el patron dejo de leer el "
        "fuente y este guardian se habria quedado ciego"
    )
    # Segunda lectura INDEPENDIENTE del mismo fichero: las funciones definidas
    # con el convenio de nombre de la familia. Que las dos coincidan es lo que
    # convierte «no vacio» en «no se me escapa ninguna»: un comprobador
    # definido y no enganchado, o enganchado de una forma que el patron de
    # arriba no lee, rompe la igualdad.
    definidas = set(re.findall(r"^def (_\w*rot[ao]s)\(", fuente, re.M))
    assert comprobadores == definidas, (
        f"los comprobadores enganchados y los definidos no coinciden: enganchados "
        f"{sorted(comprobadores)}, definidos {sorted(definidas)}. O hay uno sin llamador, "
        f"o el patron de enganche dejo de leerlo"
    )
    for palabra in escritos:
        assert numerales.get(palabra.lower()) == len(comprobadores), (
            f"`{MAPA}` dice «{palabra}» familias de citas rotas y `skill_lint.py` engancha "
            f"{len(comprobadores)}: {sorted(comprobadores)}"
        )


def test_el_patron_de_tests_solo_casa_citas_del_plugin():
    """El anclaje que el ciclo 12 puso y nadie vigilaba.

    Sin el prefijo `${CLAUDE_PLUGIN_ROOT}/`, `PATRON_TEST` casaba cualquier
    `tests/...` de la prosa. La cita realista que lo rompe es la del informe de
    JUnit del proyecto GENERADO --`build/reports/tests/test/index.html`--: se
    resolveria contra la raiz de ESTE plugin, no existiria, y el linter daria
    un rojo falso sobre una cita correcta. Un rojo falso se arregla aflojando
    la puerta, que es como mueren las puertas.
    """
    ajena = "el informe queda en `build/reports/tests/test/index.html` del proyecto generado"
    assert not re.findall(skill_lint.PATRON_TEST, ajena), (
        f"`PATRON_TEST` volvio a casar una ruta `tests/` que NO es del plugin: "
        f"{re.findall(skill_lint.PATRON_TEST, ajena)}"
    )

    # Y sigue casando lo suyo: desanclarlo no puede ser la forma de pasar este test.
    propia = "mira `${CLAUDE_PLUGIN_ROOT}/tests/fixtures/contratos/function-minimo.md` antes"
    assert re.findall(skill_lint.PATRON_TEST, propia) == ["fixtures/contratos/function-minimo.md"], (
        f"`PATRON_TEST` dejo de casar una cita legitima del plugin: "
        f"{re.findall(skill_lint.PATRON_TEST, propia)}"
    )


# Las tres exigencias de la politica de AppMarket que NINGUN script mecaniza y
# que por tanto solo existen si el revisor las lleva escritas. Cada pareja es
# (marca en el fichero, por que no la puede cubrir un script).
#
# Por que este guardian: hasta el 21-sep-2026 dos de ellas se daban por
# «delegadas al revisor» y NO estaban en su fichero. Una delegacion que nadie
# escribio es la misma vacuidad que este repositorio persigue en otras capas:
# parece cubierta y no la mira nadie.
DELEGACIONES_DE_POLITICA = (
    ("Closeable", "SpotBugs no reporta el patron que lo veria: es experimental"),
    ("doGet", "R-A01 esta exento en servlets, asi que el contexto de un usuario "
              "concreto pasa todas las capas mecanicas"),
    ("seguridad de Appian", "«no dar acceso a contenido que el usuario no tendria» "
                            "es un juicio, no un patron de bytecode"),
)


def test_el_revisor_lleva_escritas_las_politicas_que_ningun_script_comprueba():
    revisor = _texto("agents/plugin-contract-reviewer.md")
    for marca, porque in DELEGACIONES_DE_POLITICA:
        assert marca in revisor, (
            f"`agents/plugin-contract-reviewer.md` ya no menciona «{marca}». {porque}. "
            f"Si se quita de ahi, deja de mirarlo NADIE — y "
            f"`docs/auditoria-politicas-appmarket-vs-forge.md` la sigue contando como delegada."
        )
