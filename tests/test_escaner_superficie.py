"""El escaner de superficie, contra bytecode REAL de los cuatro tipos.

Por que compilar de verdad y no fabricar un `.class` de laboratorio: las dos
averias que este modulo fija solo se ven sobre el bytecode que produce javac a
partir de lo que el andamiador escribe.

  C2 · `_normalizar` conservaba el `$` de las clases internas. El indice
       documentado guarda la forma con punto y no tiene ni una entrada con
       `$`, asi que `SmartServiceException$Builder` —una linea que escribe el
       propio andamiador— se reportaba como API no documentada en el 100 % de
       los smart services.

  C6 · el escaner era ciego a TODA anotacion de Appian: al fusionar los tipos
       de los miembros solo se usaba `miembro.descriptor`, nunca
       `miembro.anotaciones`, y las anotaciones a nivel de clase no se
       parseaban en absoluto. Sobre un `function` real y compilado que usa
       `@Category`, `@Function` y `@Parameter`, el escaner reportaba
       «0 tipos» y salia con 0. La guarda `if not clases` no lo veia: una
       clase SI se habia cargado. La vacuidad se habia mudado de «cero
       clases» a «cero tipos de una clase».

El SDK sale de la cache de Gradle. Si no esta, el modulo se salta entero en
vez de fingir que verifico algo.
"""

import json
import pathlib
import shutil
import subprocess

import pytest

import andamiar
import contrato
import verificar_superficie

RAIZ = pathlib.Path(__file__).resolve().parents[1]
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "contratos"
PLANTILLAS = RAIZ / "assets" / "plantillas"
INDICE = RAIZ / "assets" / "indice-tipos-26.3.json"

CACHE_SDK = pathlib.Path.home() / ".gradle" / "caches" / "modules-2" / "files-2.1"

MINIMOS = {
    "function": "function-minimo.md",
    "writer-function": "writer-function-minimo.md",
    "smart-service": "smart-service-minimo.md",
    "servlet": "servlet-minimo.md",
}
TIPOS = sorted(MINIMOS)


def _jar(grupo: str, artefacto: str) -> pathlib.Path | None:
    candidatos = sorted((CACHE_SDK / grupo / artefacto).rglob("*.jar")) if CACHE_SDK.is_dir() else []
    # Los `-sources`/`-javadoc` no sirven para compilar.
    reales = [j for j in candidatos if not j.stem.endswith(("-sources", "-javadoc"))]
    return reales[0] if reales else None


SDK = _jar("com.appian", "appian-plug-in-sdk")
LOG4J = _jar("log4j", "log4j")
SERVLET_API = _jar("javax.servlet", "javax.servlet-api")

pytestmark = pytest.mark.skipif(
    shutil.which("javac") is None or SDK is None,
    reason="hacen falta javac y el JAR del SDK en la cache de Gradle",
)


@pytest.fixture(scope="module")
def clases_por_tipo(tmp_path_factory):
    """Andamia y COMPILA los cuatro tipos. Devuelve {tipo: [ClaseLeida]}."""
    compiladas = {}
    classpath = [str(SDK)] + [str(j) for j in (LOG4J, SERVLET_API) if j is not None]
    for tipo, fixture in MINIMOS.items():
        base = tmp_path_factory.mktemp(tipo.replace("-", "_"))
        proyecto, salida = base / "proyecto", base / "clases"
        andamiar.generar(contrato.cargar(FIXTURES / fixture), PLANTILLAS, proyecto, FIXTURES / fixture)

        fuentes = [str(p) for p in (proyecto / "src" / "main" / "java").rglob("*.java")]
        assert fuentes, f"el andamiador no escribio ningun .java para {tipo}"
        proceso = subprocess.run(
            ["javac", "--release", "17", "-classpath", ";".join(classpath),
             "-d", str(salida), *fuentes],
            capture_output=True, text=True,
        )
        assert proceso.returncode == 0, (
            f"el .java andamiado para «{tipo}» no compila contra el SDK real:\n{proceso.stderr}"
        )
        compiladas[tipo] = verificar_superficie.cargar_clases(salida)
    return compiladas


@pytest.mark.parametrize("tipo", TIPOS)
def test_el_java_andamiado_compila_contra_el_SDK_real(clases_por_tipo, tipo):
    """Que compile es la premisa de todo lo demas: si no, el resto de este
    modulo estaria analizando bytecode que nunca existio.
    """
    assert clases_por_tipo[tipo], f"no se cargo ninguna clase compilada para {tipo}"


@pytest.mark.parametrize("tipo", TIPOS)
def test_el_escaner_ve_la_API_de_Appian_que_la_clase_usa(clases_por_tipo, tipo):
    """C6. Verificado en rojo: con el `classfile.py` sin corregir, el
    `function` compilado daba la lista VACIA aqui —«0 tipos», exit 0— pese a
    llevar `@Category`, `@Function` y `@Parameter`.
    """
    vistos = set()
    for clase in clases_por_tipo[tipo]:
        vistos |= {t for t in clase.tipos_referenciados if t.startswith("com.appiancorp.")}
    assert vistos, (
        f"el escaner no ve NINGUN tipo de Appian en un {tipo} compilado que si los usa; "
        f"un inventario vacio hace que el dossier afirme «extraido del constant pool» "
        f"sobre una seccion en blanco"
    )


ANOTACIONES_ESPERADAS = {
    "function": {
        "com.appiancorp.suiteapi.expression.annotations.Category",
        "com.appiancorp.suiteapi.expression.annotations.Function",
        "com.appiancorp.suiteapi.expression.annotations.Parameter",
    },
    "writer-function": {
        "com.appiancorp.suiteapi.expression.annotations.Category",
        "com.appiancorp.suiteapi.expression.annotations.Function",
        "com.appiancorp.suiteapi.expression.annotations.Parameter",
    },
    # La de paleta va a nivel de CLASE, que es justo la tabla de atributos que
    # el lector no parseaba; `@Input`/`@Order` son de miembro.
    "smart-service": {
        "com.appiancorp.suiteapi.process.palette.AutomationSmartServicesDocumentManagement",
        "com.appiancorp.suiteapi.process.framework.Input",
        "com.appiancorp.suiteapi.process.framework.Order",
    },
}


@pytest.mark.parametrize("tipo", sorted(ANOTACIONES_ESPERADAS))
def test_las_anotaciones_de_clase_de_parametro_y_de_miembro_llegan_al_inventario(
    clases_por_tipo, tipo
):
    vistos = set()
    for clase in clases_por_tipo[tipo]:
        vistos |= clase.tipos_referenciados
    faltan = ANOTACIONES_ESPERADAS[tipo] - vistos
    assert not faltan, f"el escaner no ve estas anotaciones en un {tipo} compilado: {sorted(faltan)}"


@pytest.mark.parametrize("tipo", TIPOS)
def test_ningun_tipo_del_inventario_conserva_el_dolar(clases_por_tipo, tipo):
    """C2, sobre el bytecode real: el `$` no puede sobrevivir a la
    normalizacion, porque el indice no lo contiene en ninguna de sus 906
    entradas.
    """
    con_dolar = sorted(
        t
        for clase in clases_por_tipo[tipo]
        for t in clase.tipos_referenciados
        if "$" in t
    )
    assert not con_dolar, f"quedan tipos con `$`, que el indice nunca podra casar: {con_dolar}"


@pytest.mark.parametrize("tipo", TIPOS)
def test_lo_que_el_andamiador_escribe_pasa_la_capa_2(clases_por_tipo, tipo):
    """La consecuencia que se paga. Verificado en rojo: sin la correccion de
    `_normalizar`, el smart service fallaba aqui con
    `SmartServiceException$Builder` — una linea que escribio el propio
    andamiador, reportada como API no documentada.
    """
    indice = json.loads(INDICE.read_text(encoding="utf-8"))
    informe = verificar_superficie.analizar(clases_por_tipo[tipo], indice)
    assert not informe.modo_degradado
    assert informe.no_documentados == [], (
        f"el andamiador genero codigo que su propia capa 2 rechaza: {informe.no_documentados}"
    )


def test_el_smart_service_referencia_la_clase_interna_normalizada(clases_por_tipo):
    """Que el caso concreto de C2 esta realmente presente: si un dia la
    plantilla dejara de emitir `SmartServiceException.Builder`, el test de
    arriba pasaria por vacuidad y nadie se enteraria.
    """
    vistos = set()
    for clase in clases_por_tipo["smart-service"]:
        vistos |= clase.tipos_referenciados
    assert "com.appiancorp.suiteapi.process.exceptions.SmartServiceException.Builder" in vistos
