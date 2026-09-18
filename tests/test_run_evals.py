import pathlib

import run_evals

SKILLS = {
    "crear-plugin-appian": (
        "Genera un plugin de Appian de tipo Function, Smart Service o Servlet a partir "
        "de una entrevista al usuario, y lo verifica en cuatro capas. Use when el usuario "
        "pide crear un plugin de Appian, una funcion de expresion personalizada, un smart "
        "service propio o un servlet de Appian."
    ),
    "appian-sail-generator": (
        "Genera expresiones SAIL de interfaz de Appian a partir de requisitos en lenguaje "
        "natural. Use when el usuario quiere construir una interfaz, formulario, dashboard o pantalla."
    ),
}


def test_la_skill_correcta_gana_en_un_caso_positivo():
    ranking = run_evals.puntuar("necesito un smart service propio para mi proceso", SKILLS)
    assert ranking[0][0] == "crear-plugin-appian"


def test_un_negativo_no_dispara_la_skill():
    ranking = run_evals.puntuar("hazme una pantalla de alta de clientes en Appian", SKILLS)
    assert ranking[0][0] == "appian-sail-generator"


def test_ejecutar_casos_reporta_fallos():
    casos = [
        {"prompt": "necesito un smart service propio", "esperada": "crear-plugin-appian"},
        {"prompt": "hazme una pantalla", "esperada": "crear-plugin-appian"},
    ]
    resultados = run_evals.ejecutar_casos(casos, SKILLS)
    assert resultados[0]["acierto"] is True
    assert resultados[1]["acierto"] is False


def test_prompt_que_copia_la_descripcion_se_marca_como_trampa():
    caso = {"prompt": SKILLS["crear-plugin-appian"][:60], "esperada": "crear-plugin-appian"}
    assert run_evals.es_trampa(caso, SKILLS) is True


# --- un caso no puede ganar por los pelos y constar como acierto ----------
# El caso 3 («endpoint http dentro de appian») ganaba con un margen de 0.0242
# cuando todos los demas pasan de 0.4458. Demostrado por mutacion: borrando
# TODA mencion a «servlet» de la descripcion, la puntuacion no se movia ni una
# milesima. Su unica palanca era repetir «appian», que es la optimizacion
# equivocada para el mecanismo real de disparo: no medía lo que decía medir.
#
# Misma forma que la propiedad del insumo: no se parchea el caso, se hace que
# el eval VEA la diferencia entre ganar por el contenido y ganar por un pelo.

def test_el_margen_separa_ganar_por_contenido_de_ganar_por_un_pelo():
    skills = {
        "a": "documentos plugin smart service de appian para procesos",
        "b": "interfaces y formularios de appian",
    }
    ranking = run_evals.puntuar("quiero un smart service que mueva documentos", skills)
    assert run_evals.margen(ranking) == round(ranking[0][1] - ranking[1][1], 4)


def test_un_caso_con_margen_ridiculo_no_cuenta_como_acierto():
    casos = [{"prompt": "algo de appian", "esperada": "a"}]
    skills = {"a": "cosas de appian", "b": "otras cosas de appian tambien"}
    resultados = run_evals.ejecutar_casos(casos, skills)
    r = resultados[0]
    if r["margen"] < run_evals.MARGEN_MINIMO:
        assert not r["acierto_limpio"], (
            "gana por un pelo y aun asi cuenta como acierto limpio"
        )


def test_los_casos_reales_son_todos_discriminantes():
    """La condicion que el caso 3 incumplia. Si vuelve a incumplirla —o si
    alguien anade uno nuevo que gane por un token generico—, cae aqui.
    """
    import json
    import pathlib
    import re

    raiz = pathlib.Path(__file__).resolve().parents[1]
    datos = json.loads((raiz / "evals" / "cases" / "disparo.json").read_text(encoding="utf-8"))
    descripcion = re.search(
        r"^description: (.+)$",
        (raiz / "skills" / "crear-plugin-appian" / "SKILL.md").read_text(encoding="utf-8"),
        re.M,
    ).group(1)
    skills = dict(datos["skills_competidoras"])
    skills["crear-plugin-appian"] = descripcion

    resultados = run_evals.ejecutar_casos(datos["casos"], skills)
    flojos = [
        (r["prompt"], r["margen"]) for r in resultados if r["margen"] < run_evals.MARGEN_MINIMO
    ]
    assert flojos == [], f"casos que ganan por un pelo y no miden lo que dicen medir: {flojos}"


def test_la_frontera_sin_competidora_NO_se_la_lleva_la_skill():
    """La tercera frontera declarada, que no se puede escribir como caso.

    `disparo.json` la aparta en `fronteras_que_el_ranking_no_decide` con su
    motivo medido: ninguna skill de las que existen cubre EDITAR un plug-in ya
    hecho, asi que las cuatro competidoras puntuan 0.0 y ganaria la primera por
    orden alfabetico con margen 0.0 -- un caso no discriminante, justo lo que
    `MARGEN_MINIMO` existe para rechazar. Inventar una competidora que lo
    ganase seria un verde vacuo: no probaria nada del disparo de hoy.

    Lo que SI es comprobable, y es lo que este test sujeta, es el efecto
    contraintuitivo de nombrar lo excluido en un ranking lexico: la frase de
    exclusion que la `description` anadio --«ni para modificar, auditar o
    migrar de version un plugin que ya existe»-- mete las palabras del caso
    excluido en el texto que puntua, asi que podria ATRAER el prompt que
    pretende repeler. Se exige que no gane por contenido.

    La nota de `disparo.json` nombra este test. Sin el, esa nota prometia un
    guardian que no existia.
    """
    import json
    import re

    raiz = pathlib.Path(__file__).resolve().parents[1]
    datos = json.loads((raiz / "evals" / "cases" / "disparo.json").read_text(encoding="utf-8"))
    frontera = datos["fronteras_que_el_ranking_no_decide"]
    assert frontera["prompts"], "la frontera se declaro sin ningun prompt: no vigila nada"
    assert "test_la_frontera_sin_competidora_NO_se_la_lleva_la_skill" in frontera["nota"], (
        "la nota dejo de nombrar a su guardian"
    )

    descripcion = re.search(
        r"^description: (.+)$",
        (raiz / "skills" / "crear-plugin-appian" / "SKILL.md").read_text(encoding="utf-8"),
        re.M,
    ).group(1)
    # El literal va escrito AQUI: leerlo de la `description` seria derivar la
    # expectativa de lo que se vigila, y el aserto encogeria con ella.
    assert "modificar, auditar o migrar" in descripcion, (
        "la `description` dejo de declarar la tercera frontera, y este test dejo de "
        "medir el riesgo que existe para medir"
    )

    skills = dict(datos["skills_competidoras"])
    skills["crear-plugin-appian"] = descripcion
    for prompt in frontera["prompts"]:
        ranking = run_evals.puntuar(prompt, skills)
        ganadora, punto = ranking[0]
        margen = run_evals.margen(ranking)
        assert not (ganadora == "crear-plugin-appian" and margen >= run_evals.MARGEN_MINIMO), (
            f"«{prompt}» se lo lleva la skill POR CONTENIDO (margen {margen}): la frase de "
            f"exclusion esta atrayendo lo que pretende repeler"
        )


# --- El nivel 1 declara SOBRE QUE dio su verde ------------------------------
# «Nivel 1: 0 errores» se imprimia igual con la skill movida fuera: la unica
# linea del pipeline que reportaba exito sin decir el tamano de su insumo, en
# un sistema cuya regla es que un verde sobre cero unidades no cuenta como
# verde. Levantado por el gate del ciclo 13 (OBS-1 del auditor).


def _salida(capsys) -> str:
    run_evals.main()
    return capsys.readouterr().out


def test_el_nivel_1_declara_el_TAMANO_del_corpus_que_linto(capsys):
    salida = _salida(capsys)
    linea = next(l for l in salida.splitlines() if l.startswith("Nivel 1:"))
    assert "skill(s)" in linea and "ficheros" in linea and "lineas" in linea, (
        f"el nivel 1 volvio a reportar su resultado sin decir sobre que lo dio: «{linea}»"
    )
    # Y las cuentas son las de verdad, no un adorno: SKILL.md mas sus
    # referencias, contadas aqui aparte.
    raiz = pathlib.Path(run_evals.__file__).resolve().parents[1]
    skills = sorted(d for d in (raiz / "skills").iterdir() if d.is_dir())
    ficheros = [
        f for d in skills
        for f in [d / "SKILL.md", *sorted((d / "referencias").glob("*.md"))] if f.is_file()
    ]
    # Los TRES numeros a la vez y CON SUS DELIMITADORES. Comprobarlos por
    # separado con `in` los dejaba pasar por subcadena: publicar «1827 lineas»
    # satisfacia un aserto que buscaba «827 lineas», e igual «14 ficheros»
    # contra «4 ficheros». Un guardian de recuentos que no ve un digito de mas
    # por delante ancla contra la deriva pequena y no contra la grande.
    # Levantado por el gate del ciclo 15.
    lineas_de_corpus = sum(
        len(f.read_text(encoding="utf-8").splitlines()) for f in ficheros
    )
    esperado = f" {len(skills)} skill(s), {len(ficheros)} ficheros, {lineas_de_corpus} lineas"
    assert esperado in linea, (
        f"la linea de insumo no cuadra con el re-conteo propio «{esperado.strip()}»: «{linea}»"
    )


def test_un_corpus_VACIO_no_sale_con_cero_errores_y_exito(tmp_path, monkeypatch, capsys):
    """La direccion que faltaba: sin skills que lintar, «0 errores» es cierto y
    no significa nada. Tiene que salir distinto de 0.
    """
    raiz_real = pathlib.Path(run_evals.__file__).resolve().parents[1]
    vacio = tmp_path / "raiz"
    (vacio / "skills").mkdir(parents=True)
    (vacio / "evals" / "cases").mkdir(parents=True)
    (vacio / "evals" / "cases" / "disparo.json").write_text(
        (raiz_real / "evals" / "cases" / "disparo.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.setattr(run_evals, "__file__", str(vacio / "scripts" / "run_evals.py"))
    assert run_evals.main() != 0
    # El codigo de salida NO basta como aserto: sin skills, el nivel 2 tampoco
    # encuentra a su ganadora y devolveria 1 por su cuenta, asi que este test
    # pasaria con el insumo vacio pasando desapercibido. Lo que se mira es que
    # el nivel 1 lo DIGA.
    salida = capsys.readouterr().out
    assert "insumo vacio" in salida, (
        "con cero skills en el corpus nadie declara el insumo vacio: el rojo llega por el "
        "nivel 2 y el nivel 1 sigue afirmando «0 errores» sin decir sobre que"
    )
    assert "0 skill(s), 0 ficheros" in salida, salida
