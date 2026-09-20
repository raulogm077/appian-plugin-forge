"""Toda puerta declara el TAMANO del insumo que analizo.

La familia del «verde vacuo» va por cinco instancias: el escaner ciego a las
anotaciones, el acuerdo de `verificar_bundles` consigo mismo con `[bundle]`
ausente, la lista de clases vacia en el oraculo del EML, un caso de eval que
ganaba por una razon trivial, y las tres guardas de «cero clases» que se
fueron anadiendo UNA A UNA, reactivamente, segun se descubrian.

Cero clases, cero tipos, cero claves esperadas y cero dependencias son EL
MISMO SINTOMA. Esto lo convierte de guarda reactiva en propiedad exigida a
toda pieza que pueda reportar exito: cada validador dice cuantas unidades
analizo, el orquestador lo lleva al certificado, y un verde sobre un insumo
vacio queda marcado a la vista en vez de esperar a que alguien lo descubra por
accidente.
"""

import pathlib
import subprocess
import sys

import pytest

import contrato
import verificar_todo as vt

RAIZ = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = RAIZ / "scripts"
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "contratos"
REFERENCIA = pathlib.Path(r"C:\Users\rgmoya\Documents\Plugin Read EML (Codex)")
CLASES_REFERENCIA = REFERENCIA / "build" / "classes" / "java" / "main"


# --- el formato ------------------------------------------------------------

def test_la_linea_de_insumo_enumera_las_unidades():
    linea = contrato.linea_de_insumo(clases=30, tipos_de_appian=19)
    assert linea.startswith(contrato.PREFIJO_INSUMO)
    assert "30 clases" in linea
    assert "19 tipos de appian" in linea


def test_la_linea_de_insumo_no_esconde_los_ceros():
    """Un cero es justo el dato que importa: es el sintoma comun de las cinco
    instancias del verde vacuo.
    """
    assert "0 clases" in contrato.linea_de_insumo(clases=0)
    assert contrato.insumo_vacio(contrato.linea_de_insumo(clases=0, tipos=0))
    assert not contrato.insumo_vacio(contrato.linea_de_insumo(clases=0, tipos=3))


# --- cada validador la emite ----------------------------------------------

@pytest.mark.skipif(not CLASES_REFERENCIA.is_dir(),
                    reason="el proyecto de referencia no esta compilado")
@pytest.mark.parametrize(
    "script,argumentos",
    [
        ("verificar_framework.py", ["{contrato}", "{xml}", "{clases}", "{raiz}"]),
        ("verificar_appmarket.py", ["{contrato}", "{clases}"]),
        ("verificar_bundles.py", ["{contrato}", "{recursos}"]),
        ("verificar_superficie.py", ["{clases}", "{indice}"]),
    ],
)
def test_cada_validador_declara_su_insumo(script, argumentos, tmp_path):
    sustituciones = {
        "contrato": str(FIXTURES / "eml-referencia.md"),
        "xml": str(REFERENCIA / "src" / "main" / "resources" / "appian-plugin.xml"),
        "clases": str(CLASES_REFERENCIA),
        "recursos": str(REFERENCIA / "src" / "main" / "resources"),
        "raiz": str(REFERENCIA),
        "indice": str(RAIZ / "assets" / "indice-tipos-26.3.json"),
    }
    comando = [sys.executable, str(SCRIPTS / script)] + [a.format(**sustituciones) for a in argumentos]
    if script == "verificar_superficie.py":
        comando += ["--inventario", str(tmp_path / "inv.json")]

    proceso = subprocess.run(comando, capture_output=True, text=True, cwd=str(tmp_path))
    lineas = [l for l in proceso.stdout.splitlines() if l.startswith(contrato.PREFIJO_INSUMO)]
    assert lineas, (
        f"{script} no declara cuantas unidades analizo:\n{proceso.stdout}{proceso.stderr}"
    )


# --- el orquestador lo lleva al certificado -------------------------------

def _proceso_falso(stdout, returncode=0):
    class ProcesoFalso:
        pass

    ProcesoFalso.returncode = returncode
    ProcesoFalso.stdout = stdout
    ProcesoFalso.stderr = ""
    return ProcesoFalso


def test_el_certificado_recoge_el_insumo_de_cada_puerta(monkeypatch, tmp_path):
    salida = f"{contrato.PREFIJO_INSUMO} 30 clases, 19 tipos de appian\n0 hallazgos (0 errores)"
    monkeypatch.setattr("subprocess.run", lambda *a, **k: _proceso_falso(salida))

    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / "docs" / "contrato.md").write_text(
        (FIXTURES / "smart-service-minimo.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    cert = vt.ejecutar(tmp_path, "estandar")

    ejecutadas = [p for p in cert.puertas if p.nombre in vt.PUERTAS_CON_INVOCACION and p.insumo]
    assert ejecutadas, "ninguna puerta recogio su insumo"
    for p in ejecutadas:
        assert "30 clases" in p.insumo

    md = vt.render_markdown(cert)
    assert "Insumo" in md, "el certificado no tiene columna de insumo"
    assert "30 clases" in md


def test_un_verde_sobre_insumo_vacio_queda_marcado(monkeypatch, tmp_path):
    """La propiedad, en una linea: un exito sobre cero unidades no puede
    parecerse a un exito sobre treinta.
    """
    salida = f"{contrato.PREFIJO_INSUMO} 0 clases, 0 tipos de appian\n0 hallazgos (0 errores)"
    monkeypatch.setattr("subprocess.run", lambda *a, **k: _proceso_falso(salida))

    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / "docs" / "contrato.md").write_text(
        (FIXTURES / "smart-service-minimo.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    cert = vt.ejecutar(tmp_path, "estandar")

    verdes_vacias = [
        p for p in cert.puertas if p.estado == "verde" and contrato.insumo_vacio(p.insumo)
    ]
    assert verdes_vacias, "el escenario no se reprodujo"
    md = vt.render_markdown(cert)
    assert vt.AVISO_INSUMO_VACIO in md, (
        "el certificado muestra un verde sobre cero unidades sin distinguirlo de uno real"
    )
    assert cert.listo_para_sumision is False, (
        "un verde sobre insumo vacio no puede dar listo para sumision"
    )


# --- la sexta instancia, encontrada por la propia propiedad ----------------
# En un servlet, `verificar_bundles` devuelve [] de inmediato --su capa excluye
# expresamente a los servlets, que declaran name/description como atributos del
# manifiesto-- y la puerta salia VERDE habiendo mirado cero bundles y cero
# claves. Es un verde vacuo legitimo, pero verde vacuo: la propiedad del insumo
# lo saco a la luz en la primera ejecucion, que es justo para lo que se puso.
#
# Dejarlo con el AVISO en cada servlet seria peor que no tenerlo: una alarma
# que salta siempre ensena a ignorarla, que es el mismo dano que hacia el
# Critical 2. Asi que la puerta pasa a decir lo que de verdad ocurre: NO
# APLICA, que no es un aprobado ni un suspenso.

def test_en_un_servlet_la_capa_de_bundles_no_aplica_en_vez_de_aprobar(tmp_path, monkeypatch):
    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / "docs" / "contrato.md").write_text(
        (FIXTURES / "servlet-minimo.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    # Reserva 3a: el `NO APLICA` ya no se acepta a secas. Tiene que decir de
    # que hecho del contrato sale, y el orquestador lo comprueba contra el
    # contrato real -- aqui `plugin.tipo = servlet`, que es cierto.
    salida = (
        f"{contrato.linea_no_aplica('plugin.tipo', 'servlet', 'los servlets no cargan bundle')}\n"
        f"{contrato.linea_de_insumo(bundles=0, claves_esperadas=0)}\n0 hallazgos (0 errores)"
    )
    monkeypatch.setattr("subprocess.run", lambda *a, **k: _proceso_falso(salida))

    cert = vt.ejecutar(tmp_path, "estandar")
    puerta = {p.nombre: p for p in cert.puertas}["Bundles y locales"]
    assert puerta.estado == "no-aplica", (
        "una capa que no aplica a este tipo no puede presentarse como aprobada"
    )
    md = vt.render_markdown(cert)
    assert vt.AVISO_INSUMO_VACIO not in md, (
        "un aviso que salta en todos los servlets ensena a ignorar el aviso"
    )
    # Y la fila PUBLICA el hecho del que sale. Se quedaba con la evidencia
    # generica --«0 hallazgos (0 errores)»--, indistinguible de la de una
    # puerta que si verifico: el unico estado que equivale a pasado sin haber
    # mirado nada era el unico que no decia por que. Los tres caminos de
    # rechazo si escribian el suyo.
    assert "plugin.tipo = servlet" in puerta.evidencia, (
        f"la fila no aplica no publica el hecho que la justifica: {puerta.evidencia!r}"
    )
    assert "los servlets no cargan bundle" in puerta.evidencia


def test_no_aplica_no_bloquea_pero_tampoco_es_verde():
    puertas = [
        vt.Puerta("A", "ambos", "verde", "ok", "INSUMO 3 clases"),
        vt.Puerta("B", "ambos", "no-aplica", "no cargan bundle", "INSUMO 0 bundles"),
    ]
    assert vt.calcular_todo_verde(puertas) is True
    assert vt.SIMBOLO["no-aplica"] != vt.SIMBOLO["verde"]


# ---------------------------------------------------------------------------
# RESERVA 3a · `NO APLICA` podia convertirse en un pase libre.
#
# El estado quedo ratificado por una razon concreta: se deriva de un HECHO
# declarado en el contrato --`plugin.tipo == "servlet"`--, no de haber
# encontrado cero ficheros. Esa es toda la diferencia. Un `no aplica` que
# saliera de «no encontre nada» seria otra instancia del verde vacuo con
# nombre nuevo.
#
# Pero `calcular_todo_verde` acepta `no-aplica` como equivalente a pasado, y
# hasta ahora lo unico que impedia el abuso era el buen criterio de una linea:
# el marcador se reconocia por `startswith("NO APLICA")` y nadie comprobaba de
# donde salia. La regla pasa a estar donde se puede hacer cumplir.
# ---------------------------------------------------------------------------


def test_la_marca_de_no_aplica_declara_el_hecho_del_que_sale():
    linea = contrato.linea_no_aplica("plugin.tipo", "servlet", "no cargan bundle")
    assert linea.startswith(contrato.MARCA_NO_APLICA)
    reclamo, rechazo = contrato.buscar_no_aplica(linea)
    assert rechazo == ""
    assert (reclamo.clave, reclamo.valor) == ("plugin.tipo", "servlet")


def test_un_no_aplica_a_secas_se_rechaza():
    """La forma historica, que es justo la que no se puede seguir aceptando."""
    _, rechazo = contrato.buscar_no_aplica("NO APLICA los servlets no cargan bundle")
    assert rechazo, "un NO APLICA sin hecho declarado se acepto"


def test_sin_marca_no_hay_ni_reclamo_ni_rechazo():
    """Ausencia y malformacion son cosas distintas: la inmensa mayoria de las
    salidas no reclaman nada, y eso no es un error.
    """
    assert contrato.buscar_no_aplica("0 hallazgos (0 errores)") == (None, "")


def _proyecto_con_contrato(tmp_path, fixture):
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "contrato.md").write_text(
        (FIXTURES / fixture).read_text(encoding="utf-8"), encoding="utf-8"
    )
    return tmp_path


def test_el_orquestador_rechaza_un_no_aplica_sin_hecho(tmp_path, monkeypatch):
    salida = f"{contrato.MARCA_NO_APLICA} no encontre ningun bundle\n0 hallazgos (0 errores)"
    monkeypatch.setattr("subprocess.run", lambda *a, **k: _proceso_falso(salida))
    cert = vt.ejecutar(_proyecto_con_contrato(tmp_path, "servlet-minimo.md"), "estandar")
    puerta = {p.nombre: p for p in cert.puertas}["Bundles y locales"]
    assert puerta.estado == "rojo", (
        "un NO APLICA sin hecho del contrato se acepto como equivalente a pasado"
    )


def test_el_orquestador_rechaza_un_hecho_que_el_contrato_DESMIENTE(tmp_path, monkeypatch):
    """La forma que el mero «declara un hecho» no atraparia: la excusa esta
    bien escrita y es FALSA. El contrato de este proyecto es un smart service.
    """
    salida = (
        f"{contrato.linea_no_aplica('plugin.tipo', 'servlet', 'no cargan bundle')}\n"
        f"0 hallazgos (0 errores)"
    )
    monkeypatch.setattr("subprocess.run", lambda *a, **k: _proceso_falso(salida))
    cert = vt.ejecutar(_proyecto_con_contrato(tmp_path, "smart-service-minimo.md"), "estandar")
    puerta = {p.nombre: p for p in cert.puertas}["Bundles y locales"]
    assert puerta.estado == "rojo"
    assert "servlet" in puerta.evidencia


def test_el_validador_real_de_bundles_emite_el_formato_nuevo(tmp_path):
    """Los dos extremos de la cadena: de nada sirve que el orquestador exija
    el hecho si el unico emisor real sigue imprimiendo la forma vieja.
    """
    recursos = tmp_path / "resources"
    recursos.mkdir()
    proceso = subprocess.run(
        [sys.executable, str(SCRIPTS / "verificar_bundles.py"),
         str(FIXTURES / "servlet-minimo.md"), str(recursos)],
        capture_output=True, text=True,
    )
    reclamo, rechazo = contrato.buscar_no_aplica(proceso.stdout)
    assert rechazo == "", f"{rechazo}\n{proceso.stdout}"
    assert reclamo and reclamo.clave == "plugin.tipo" and reclamo.valor == "servlet"


# ---------------------------------------------------------------------------
# RESERVA 3b · la UNIDAD PORTANTE del insumo.
#
# La propiedad del insumo declarado caza 2 de las 6 instancias conocidas, y
# falla en la mas cara --el escaner ciego a las anotaciones-- porque el aviso
# exige que TODAS las unidades sean cero, y alli habia una clase. La forma real
# del fallo no era «todo a cero»: era «cero en la dimension que importaba, con
# las demas sanas».
#
# Cada puerta marca cual es su unidad PORTANTE --la que a cero significa «no se
# verifico nada»-- y el aviso se dispara con esa, no con todas. Solo donde la
# portante es clara y defendible: inventar una donde no la hay crearia la
# alarma que salta siempre, que es el dano que este proyecto ya ha evitado dos
# veces.
# ---------------------------------------------------------------------------


def test_la_portante_a_cero_marca_el_insumo_aunque_las_demas_esten_sanas():
    """La forma exacta del escaner ciego a anotaciones: 30 clases analizadas
    y CERO tipos de Appian encontrados. Con la regla de «todas a cero» esto
    pasaba como insumo lleno, que es justo como se escapo.
    """
    con_portante = contrato.linea_de_insumo(
        clases=30, tipos_de_appian=0, portante="tipos_de_appian"
    )
    assert contrato.insumo_vacio(con_portante), "la portante a cero no marco el insumo"
    assert not contrato.insumo_vacio(
        contrato.linea_de_insumo(clases=30, tipos_de_appian=0)
    ), "sin portante declarada la regla vieja sigue sin verlo (y por eso hace falta)"


def test_la_portante_distinta_de_cero_no_marca_nada():
    linea = contrato.linea_de_insumo(clases=0, tipos_de_appian=19, portante="tipos_de_appian")
    assert not contrato.insumo_vacio(linea)


def test_sin_portante_declarada_manda_la_regla_de_todas_a_cero():
    """Compatibilidad: la mayoria de las puertas no tiene portante clara y no
    se les inventa una.
    """
    assert contrato.insumo_vacio(contrato.linea_de_insumo(clases=0, tipos=0))
    assert not contrato.insumo_vacio(contrato.linea_de_insumo(clases=0, tipos=3))


def test_declarar_una_portante_que_no_se_mide_es_un_error():
    """Falla al EMITIR, no degradando en silencio a la regla vieja: una
    portante mal escrita seria una puerta que cree estar protegida y no lo
    esta.
    """
    with pytest.raises(ValueError):
        contrato.linea_de_insumo(clases=3, portante="tipos_de_appian")


def test_la_portante_se_ve_en_la_linea():
    linea = contrato.linea_de_insumo(bundles=3, claves_esperadas=0, portante="claves_esperadas")
    assert "portante" in linea and "claves esperadas" in linea


# --- las tres puertas que SI tienen portante defendible --------------------


def test_el_escaner_de_superficie_declara_tipos_de_appian_como_portante(tmp_path):
    """Cero tipos SOLO puede significar escaner roto: toda clase de un plug-in
    referencia al menos sus anotaciones de Appian. Sobre clases REALES, con el
    mismo fixture compilado que usa `test_verificar_superficie`: con el
    directorio vacio el validador corta antes de llegar a la linea de insumo.
    """
    import shutil

    if shutil.which("javac") is None:
        pytest.skip("javac no esta en el PATH")
    clases = tmp_path / "clases"
    subprocess.run(
        ["javac", "--release", "17", "-d", str(clases),
         str(pathlib.Path(__file__).resolve().parent / "fixtures" / "java" / "Ejemplo.java")],
        check=True, capture_output=True,
    )
    proceso = subprocess.run(
        [sys.executable, str(SCRIPTS / "verificar_superficie.py"), str(clases),
         str(RAIZ / "assets" / "indice-tipos-26.3.json"),
         "--inventario", str(tmp_path / "inv.json")],
        capture_output=True, text=True,
    )
    linea = next(
        (l for l in proceso.stdout.splitlines() if l.startswith(contrato.PREFIJO_INSUMO)), ""
    )
    assert "portante: tipos de appian" in linea, f"{proceso.stdout}{proceso.stderr}"


def test_bundles_declara_claves_esperadas_como_portante():
    """La otra dimension, y la que de verdad importa aqui: `claves_esperadas`
    a cero es el validador comparando ficheros reales contra CERO expectativas
    y dandose la razon a si mismo. `bundles` a cero, en cambio, es un fallo que
    las reglas R-B ya reprueban por su cuenta.
    """
    proceso = subprocess.run(
        [sys.executable, str(SCRIPTS / "verificar_bundles.py"),
         str(FIXTURES / "smart-service-minimo.md"), str(RAIZ)],
        capture_output=True, text=True,
    )
    linea = next(
        (l for l in proceso.stdout.splitlines() if l.startswith(contrato.PREFIJO_INSUMO)), ""
    )
    assert "portante: claves esperadas" in linea, f"{proceso.stdout}{proceso.stderr}"


def test_un_acuerdo_consigo_mismo_sobre_cero_expectativas_queda_marcado():
    """La forma del defecto, en una linea: tres ficheros mirados, cero claves
    que exigirles, cero hallazgos. Con la regla de «todas a cero» pasaba.
    """
    linea = contrato.linea_de_insumo(bundles=3, claves_esperadas=0, portante="claves_esperadas")
    assert contrato.insumo_vacio(linea)


def test_el_jar_declara_sus_entradas_como_portante(tmp_path):
    """Un zip sin entradas es no haber analizado nada. `dependencias_esperadas`
    NO es portante: cero dependencias es legitimo, y R-J05 ya lo declara con
    todas las letras por su cuenta.
    """
    import zipfile

    jar = tmp_path / "x.jar"
    with zipfile.ZipFile(jar, "w") as z:
        z.writestr("appian-plugin.xml", "<appian-plugin/>")
    proceso = subprocess.run(
        [sys.executable, str(SCRIPTS / "verificar_jar.py"), str(jar),
         str(FIXTURES / "smart-service-minimo.md")],
        capture_output=True, text=True,
    )
    linea = next(
        (l for l in proceso.stdout.splitlines() if l.startswith(contrato.PREFIJO_INSUMO)), ""
    )
    assert "portante: entradas del jar" in linea, f"{proceso.stdout}{proceso.stderr}"


# --- La puerta de property tests, medida en la unidad que la sostiene -------
#
# [ALTA] del gate del ciclo 6. Su tarea es `:test`, que SI forma parte de
# `build`, asi que un `gradlew build` corriente la ponia VERDE. Y el insumo se
# declaraba en `tests` TOTALES, de modo que una bateria de tests normales sin
# un solo property test daba `INSUMO 5 tests` y no marcaba nada. Es la forma
# canonica del verde vacuo --cero en la dimension que importa, las demas
# sanas--, la misma de `30 clases, 0 tipos de appian`.

def _proyecto_con_tests(raiz, nombres_de_clase):
    """Un proyecto con resultados JUnit reales, uno por clase de test."""
    (raiz / "docs").mkdir(parents=True, exist_ok=True)
    (raiz / "docs" / "contrato.md").write_text(
        (FIXTURES / "function-minimo.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    resultados = raiz / "build" / "test-results" / "test"
    resultados.mkdir(parents=True, exist_ok=True)
    for clase in nombres_de_clase:
        (resultados / f"TEST-{clase}.xml").write_text(
            f'<testsuite name="{clase}" tests="3" failures="0" errors="0"/>', encoding="utf-8"
        )
    return raiz


def test_property_tests_se_mide_en_property_tests_no_en_tests(tmp_path):
    import verificar_todo as vt

    class _Resultado:
        tareas = {":test": "OK"}

    # Solo tests corrientes: la puerta NO puede darse por satisfecha.
    solo_corrientes = _proyecto_con_tests(tmp_path / "a", ["com.x.SaludoTest", "com.x.OtroTest"])
    linea = vt._insumo_delegado(solo_corrientes, vt.PUERTA_PROPERTY_TESTS, _Resultado())
    assert "0 property tests" in linea, linea
    assert contrato.insumo_vacio(linea), (
        f"6 tests corrientes y CERO property tests no puede contar como insumo lleno: {linea}"
    )

    # Con uno de verdad, deja de estar vacio.
    con_property = _proyecto_con_tests(
        tmp_path / "b", ["com.x.SaludoTest", "com.x.SaludoFuzzTest"]
    )
    linea = vt._insumo_delegado(con_property, vt.PUERTA_PROPERTY_TESTS, _Resultado())
    assert "3 property tests" in linea, linea
    assert not contrato.insumo_vacio(linea), linea

    # Y con el OTRO sufijo del convenio. Hasta el ciclo 8 ningun fixture del
    # repositorio llevaba `*PropertyTest`: la mitad publicada del convenio no
    # la ejercia nada, asi que borrarla de la constante no ponia nada rojo.
    # El literal va escrito aqui, no derivado de `SUFIJOS_PROPERTY_TEST`.
    con_el_otro = _proyecto_con_tests(
        tmp_path / "c", ["com.x.SaludoTest", "com.x.SaludoPropertyTest"]
    )
    linea = vt._insumo_delegado(con_el_otro, vt.PUERTA_PROPERTY_TESTS, _Resultado())
    assert "3 property tests" in linea, (
        f"`*PropertyTest` es la mitad del convenio que la SKILL publica y la puerta no lo "
        f"cuenta: {linea}"
    )
    assert not contrato.insumo_vacio(linea), linea


def test_las_demas_puertas_medidas_en_tests_siguen_contando_el_total(tmp_path):
    """La portante nueva es SOLO de la puerta de property tests: «Tests
    unitarios» sigue midiendose en tests totales, que es su unidad correcta."""
    import verificar_todo as vt

    class _Resultado:
        tareas = {":test": "OK"}

    proyecto = _proyecto_con_tests(tmp_path, ["com.x.SaludoTest", "com.x.OtroTest"])
    linea = vt._insumo_delegado(proyecto, "Tests unitarios", _Resultado())
    assert "6 tests" in linea and "property" not in linea, linea
