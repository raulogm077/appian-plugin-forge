"""Orquesta las cuatro capas y emite el certificado de verificacion.

El marco del que tomamos las demas disciplinas define «terminado» de forma
binaria y exigiendo runtime, y no contempla el caso de NO PODER EJECUTAR
(spec §8.2). Aplicado tal cual, este sistema nunca podria declarar nada
terminado. El certificado sustituye ese binario por un libro mayor.

Regla que no se negocia: una puerta que no se ejecuto NUNCA se marca como
pasada. Las dos ultimas filas van siempre en rojo, y decirlo es la funcion.
"""

from __future__ import annotations

import argparse
import ast
import concurrent.futures
import dataclasses
import json
import pathlib
import re
import subprocess
import sys

# Hermanos en `scripts/`, que es `sys.path[0]` como script y lo que los tests
# insertan. Estuvieron importados DENTRO de las funciones --siete veces
# `contrato`-- y no habia razon: `contrato` y `salida_build` solo importan
# biblioteca estandar, asi que no hay ciclo, y ninguna ruta de ejecucion
# termina sin tocar los dos. En un fichero donde todo lo demas lleva su
# porque, un import local sin explicacion se lee como si tuviera una.
import contrato
import salida_build as sb

PUERTAS_AMBOS_PERFILES = [
    "Reglas del framework de Appian",
    "Politicas AppMarket",
    "Bundles y locales",
    "Compilacion · SDK 26.3 / release 17",
    "Superficie documentada · indice 26.3",
    "Deriva contra la version del entorno",
    "Tests unitarios",
    "SpotBugs + FindSecBugs",
    "Licencias de terceros",
    "Empaquetado y cierre de dependencias",
    "Bytecode del artefacto · major 61",
]
PUERTAS_RIGUROSO = [
    "Cobertura JaCoCo 95 / 85",
    "Mutacion PIT >= 85 %",
    "Property tests y fuzz sembrado",
    "Build reproducible",
]
PUERTAS_NUNCA_VERIFICABLES = [
    ("Resolucion OSGi en la plataforma", "R13 — no hay contenedor equivalente en local"),
    ("Ejecucion en Appian real", "imposible sin despliegue aprobado"),
]
PUERTA_INFORMATIVA = "Deriva contra la version del entorno"
PUERTA_EMPAQUETADO = "Empaquetado y cierre de dependencias"
PUERTA_LICENCIAS = "Licencias de terceros"
PUERTA_PROPERTY_TESTS = "Property tests y fuzz sembrado"

# El perfil que ANADE puertas. Nombrado una sola vez y comprobado contra la
# lista del contrato: escrito a mano en cada `==`, un dia uno de ellos no casa
# y su rama deja de ejecutarse sin que nada falle.
PERFIL_ESTRICTO = "riguroso"
PERFIL_POR_DEFECTO = "estandar"
if PERFIL_ESTRICTO not in contrato.PERFILES:
    raise AssertionError(
        f"«{PERFIL_ESTRICTO}» no es uno de los perfiles del contrato ({contrato.PERFILES}): "
        f"las puertas rigurosas no se anadirian nunca"
    )

# Toda constante que NOMBRE una puerta tiene que nombrar una que exista. Es la
# misma costura que ya sujeta `SCRIPT_POR_PUERTA` --un nombre mal escrito alli
# revienta con KeyError-- pero estas se comparaban con `==` contra el nombre de
# una fila, y una comparacion que nunca casa no falla: se salta la rama en
# silencio. Medido en el ciclo 7 sobre `PUERTA_PROPERTY_TESTS`: mutar la
# constante dejaba la suite entera en verde y devolvia su fila al verde vacuo
# que el ciclo 6 acababa de quitarle. Aqui revienta al importar, y desde el
# gate del ciclo 9 revienta este donde este la constante en el fichero.
_TODAS_LAS_PUERTAS = frozenset(
    PUERTAS_AMBOS_PERFILES + PUERTAS_RIGUROSO + [n for n, _ in PUERTAS_NUNCA_VERIFICABLES]
)

# Marca de un `PUERTA_* = <algo que no es un literal de cadena>`. No se resuelve
# ejecutando nada: se declara ilegible y cae como huerfana, que es el mismo
# criterio que el parser de exclusiones de PIT aplica en el test --toda entrada
# se reconoce o se rechaza, ninguna se cuela sin clasificar--.
_VALOR_NO_LITERAL = "<valor que no es un literal de cadena>"


def _constantes_de_puerta(ruta: pathlib.Path) -> list[tuple[str, str]]:
    """Los `PUERTA_* = "..."` del fichero, leidos de su CODIGO FUENTE.

    Se leen del arbol sintactico y NO de `globals()`, y esa es la correccion
    que pide el gate del ciclo 9. `globals()` en tiempo de modulo solo ve los
    nombres YA ligados: la version anterior se evaluaba justo aqui, en la linea
    de la propia guarda, y no veia un quinto `PUERTA_*` declarado mas abajo
    --el sitio natural seria junto a `SCRIPT_POR_PUERTA`--, asi que el
    comentario prometia una cobertura que no tenia. El gate lo midio en las dos
    direcciones con el mismo fantasma: arriba reventaba el import, abajo dejaba
    la suite en verde.

    Bajar la guarda al final del modulo era la via facil y NO se tomo: deja el
    mismo agujero una linea mas abajo --lo declarado despues de la llamada
    sigue escapando-- y obliga a su propio test a inyectar el fantasma ANTES de
    la llamada, que es medir por donde es comodo. Leer el fuente no depende de
    donde este la guarda: un `PUERTA_*` en cualquier linea del fichero entra,
    incluso despues del bloque `__main__`.

    No poder leerse a si mismo NO se resuelve a favor: si el fuente no esta o
    no parsea, esto propaga el error en vez de devolver un conjunto vacio que
    se leeria como "ninguna huerfana".
    """
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    encontradas: list[tuple[str, str]] = []
    for nodo in ast.walk(arbol):
        # `x = ...`, `x: str = ...` y el desempaquetado `a, b = ...`. Las tres
        # formas ligan un nombre, y contemplar solo la primera seria el mismo
        # punto ciego de siempre con otra cara.
        if isinstance(nodo, ast.Assign):
            destinos, valor = nodo.targets, nodo.value
        elif isinstance(nodo, ast.AnnAssign) and nodo.value is not None:
            destinos, valor = [nodo.target], nodo.value
        else:
            continue
        for destino in destinos:
            literal = (
                valor.value
                if isinstance(destino, ast.Name)
                and isinstance(valor, ast.Constant)
                and isinstance(valor.value, str)
                else _VALOR_NO_LITERAL
            )
            for nombre in _nombres_ligados(destino):
                if nombre.startswith("PUERTA_"):
                    encontradas.append((nombre, literal))
    return encontradas


def _tablas_indexadas_por_puerta(ruta: pathlib.Path) -> dict[str, list[str]]:
    """Las tablas del fichero cuyas claves son nombres de puerta, y esas claves.

    Del FUENTE, por el mismo motivo que `_constantes_de_puerta`: la primera
    version filtraba `list(globals().items())` en la linea de la propia guarda,
    o sea que reintroducia el punto ciego de posicion que la funcion de arriba
    acababa de quitar --una tabla declarada mas abajo no entraba, medido--.
    Leer el fuente no depende de donde este la guarda.

    Lo que este barrido SI ve: todo `dict` o `set` literal de nivel de modulo
    cuyas claves sean todas cadenas y del que AL MENOS UNA nombre una puerta
    real. Lo que NO ve, y conviene no prometerlo: una tabla nueva cuyas claves
    esten TODAS mal escritas, que no tiene marca sintactica que la distinga de
    cualquier otro diccionario del fichero. Contra eso, y solo contra eso, esta
    el suelo de nombres esperados de la guarda.
    """
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    tablas: dict[str, list[str]] = {}
    for nodo in arbol.body:
        destinos, valor = (
            (nodo.targets, nodo.value) if isinstance(nodo, ast.Assign)
            else ([nodo.target], nodo.value)
            if isinstance(nodo, ast.AnnAssign) and nodo.value is not None
            else ([], None)
        )
        if isinstance(valor, ast.Dict):
            claves = valor.keys
        elif isinstance(valor, ast.Set):
            claves = valor.elts
        else:
            continue
        # Las claves que son literales de cadena se recogen; las que son un
        # `PUERTA_*` --`SCRIPT_POR_PUERTA` mezcla las dos formas-- se dejan
        # pasar sin recoger, porque a esas ya las vigila la guarda de
        # constantes de arriba. Cualquier otra forma de clave significa que
        # esto no es una tabla de puertas, y se salta entera: recoger solo la
        # mitad legible seria juzgar sobre un insumo recortado en silencio.
        literales = [c.value for c in claves if isinstance(c, ast.Constant) and isinstance(c.value, str)]
        ya_vigiladas = [c for c in claves if isinstance(c, ast.Name) and c.id.startswith("PUERTA_")]
        if len(literales) + len(ya_vigiladas) != len(claves) or not claves:
            continue
        for destino in destinos:
            for nombre in _nombres_ligados(destino):
                tablas[nombre] = literales
    return tablas


def _nombres_ligados(destino: ast.expr) -> list[str]:
    if isinstance(destino, ast.Name):
        return [destino.id]
    if isinstance(destino, (ast.Tuple, ast.List)):
        return [n for e in destino.elts for n in _nombres_ligados(e)]
    return []


_HUERFANAS = sorted(
    f"{nombre} = {valor!r}"
    for nombre, valor in _constantes_de_puerta(pathlib.Path(__file__))
    if valor not in _TODAS_LAS_PUERTAS
)
if _HUERFANAS:
    raise AssertionError(
        f"constantes que nombran una puerta inexistente: {_HUERFANAS}. "
        f"La rama que dependa de ellas no se ejecutaria nunca, sin fallar."
    )

# Las puertas que este orquestador NO ejecuta, cada una con quien si lo hace.
#
# No es un tecnicismo: sin esta tabla, siete de las once puertas se quedaban en
# «pendiente» para siempre y el criterio de salida de la SKILL —«ninguna puerta
# en pendiente»— era insatisfacible tal como se entregaba. La alternativa
# tentadora, inventar una invocacion que las pusiera en verde, es exactamente
# el verde vacuo que este sistema existe para impedir.
#
# «Delegada» NO cuenta como verde en `estado_de_sumision`, que es quien decide.
# Delegar es decir quien mira, no decir que esta bien.
PUERTAS_DELEGADAS = {
    "Compilacion · SDK 26.3 / release 17":
        "la ejecuta `./gradlew build` (paso 4 · BUILD); este orquestador no invoca Gradle",
    "Tests unitarios":
        "los ejecuta `./gradlew build` (paso 4 · BUILD) con JUnit 5 + Mockito",
    "SpotBugs + FindSecBugs":
        "los ejecuta `./gradlew build` via `check.dependsOn spotbugsMain`",
    "Bytecode del artefacto · major 61":
        "R-A09 (capa 1B) ya comprueba major 61 sobre build/classes; sobre las copias DENTRO "
        "del JAR no hay regla documentada — las nueve de la capa 4 no lo cubren",
    "Cobertura JaCoCo 95 / 85":
        "la ejecuta `./gradlew jacocoTestCoverageVerification` (perfil RIGUROSO)",
    "Mutacion PIT >= 85 %":
        "la ejecuta `./gradlew mutationTest` (perfil RIGUROSO)",
    "Property tests y fuzz sembrado":
        "van dentro de la bateria JUnit que ejecuta `./gradlew build` (perfil RIGUROSO)",
    "Build reproducible":
        "la plantilla la CONFIGURA (`preserveFileTimestamps = false`, "
        "`reproducibleFileOrder = true`) pero ninguna tarea la COMPRUEBA: "
        "`releaseCheck` no construye dos veces ni compara el hash del JAR",
}

# Que tarea de Gradle resuelve cada puerta delegada. Delegar es nombrar a quien
# mira; esto es lo que va a buscar lo que ese alguien VIO. Sin esta tabla, las
# filas delegadas declaraban su comando y nadie leia jamas su resultado:
# un servlet con `spotbugsMain FAILED` certificaba igual que un `function` que
# pasaba (RESERVA 1, sexta instancia del verde vacuo).
TAREAS_POR_PUERTA = {
    "Compilacion · SDK 26.3 / release 17": ":compileJava",
    "Tests unitarios": ":test",
    "SpotBugs + FindSecBugs": ":spotbugsMain",
    "Cobertura JaCoCo 95 / 85": ":jacocoTestCoverageVerification",
    "Mutacion PIT >= 85 %": ":mutationTest",
    "Property tests y fuzz sembrado": ":test",
    # Sigue aqui para poder distinguir «nadie ejecuto el perfil riguroso»
    # (ROJO) de «se ejecuto, pero esa tarea no comprueba la reproducibilidad»
    # (delegada). Esta ademas en PUERTAS_QUE_EL_BUILD_NO_APRUEBA, y el orden de
    # las ramas de `_resolver_delegadas` es lo que separa los dos casos.
    "Build reproducible": ":releaseCheck",
}

# Las que un BUILD SUCCESSFUL NO puede aprobar, por mucho que se ejecute.
# El build no mira el bytecode de las copias DENTRO del JAR. Ponerla en verde
# seria cambiar un verde vacuo por otro; dejarla eternamente en rojo seria una
# alarma que salta siempre, que es el mismo dano. Se queda delegada, con su
# matiz intacto, pero ROJA si el build fallo: entonces no consta ni el minimo.
#
# «Licencias de terceros» SALIO de esta lista: el juicio sobre copyleft ya no
# esta sin mecanizar. Lo hace `verificar_licencias.py` leyendo el SBOM que
# genera el propio build, asi que la puerta paso de «delegada» a ejecutada.
PUERTAS_QUE_EL_BUILD_NO_APRUEBA = {
    "Bytecode del artefacto · major 61",
    # ENTRO en el ciclo 5. Estaba mapeada a `:releaseCheck` y salia VERDE en
    # cuanto esa tarea pasaba, pero `releaseCheck` es `dependsOn check,
    # mutationTest, jacocoTestCoverageVerification, verificarRevisionGit`:
    # NADA ahi compara dos builds byte a byte. La reproducibilidad esta
    # CONFIGURADA en la plantilla (`preserveFileTimestamps = false`,
    # `reproducibleFileOrder = true`) y nunca comprobada, asi que el verde
    # descansaba sobre trabajo que no se hacia -- la familia exacta que este
    # sistema persigue. Verificarla de verdad exige construir dos veces y
    # comparar el hash del JAR, y ninguna tarea del proyecto generado lo hace.
    "Build reproducible",
}

# Las que miden su insumo en tests y no en clases. Un BUILD SUCCESSFUL sobre
# `> Task :test NO-SOURCE` --lo que imprime de verdad un proyecto recien
# andamiado-- es un verde sobre cero tests, y la columna de insumo ya sabe
# marcarlo sin necesidad de una guarda nueva.
PUERTAS_MEDIDAS_EN_TESTS = {
    "Tests unitarios",
    "Property tests y fuzz sembrado",
    "Cobertura JaCoCo 95 / 85",
    "Mutacion PIT >= 85 %",
}

# Las que si ejecuta este script, y CON QUE. Fuera de esta tabla y de
# PUERTAS_DELEGADAS no deberia quedar ninguna puerta muda.
#
# La lista de nombres se DERIVA de aqui en vez de escribirse aparte, y no es
# cosmetica: `PUERTAS_CON_INVOCACION` es el allowlist con el que
# `test_ninguna_puerta_se_queda_sin_explicacion` excusa a una puerta de tener
# motivo --«puede quedarse en pendiente porque alguien la ejecuta»--. Mientras
# fue una tupla escrita a mano, una puerta podia perder su invocacion y seguir
# figurando ahi: el test que existe para delatar a una puerta muda la habria
# absuelto. De las ocho tablas indexadas por nombre de puerta, esta era la unica
# cuyo desajuste fallaba en silencio; las demas fallan en rojo.
SCRIPT_POR_PUERTA = {
    "Reglas del framework de Appian": "verificar_framework.py",
    "Politicas AppMarket": "verificar_appmarket.py",
    "Bundles y locales": "verificar_bundles.py",
    "Superficie documentada · indice 26.3": "verificar_superficie.py",
    PUERTA_LICENCIAS: "verificar_licencias.py",
    PUERTA_EMPAQUETADO: "verificar_jar.py",
}
PUERTAS_CON_INVOCACION = tuple(SCRIPT_POR_PUERTA)


# Y las TABLAS indexadas por nombre de puerta, por el mismo motivo que las
# constantes de arriba y sobre mas superficie: aquella guarda vigila cuatro
# escalares, y aqui hay cinco tablas cuyas claves son nombres de puerta. Una
# clave mal escrita no casa con ninguna fila y su rama no se ejecuta, sin
# fallar.
#
# Tres de las cinco fallarian en ruidoso por su cuenta --la fila se queda
# pendiente o sin aprobar y `estado_de_sumision` bloquea el READY--, pero
# `PUERTAS_MEDIDAS_EN_TESTS` falla EN FAVOR y en silencio: `_insumo_delegado`
# cae a `linea_de_insumo(clases=...)`, asi que la fila mide clases compiladas
# en vez de tests, `7 clases` no es insumo vacio, y un `> Task :test NO-SOURCE`
# dentro de un BUILD SUCCESSFUL sale verde. Es la familia [ALTA] del ciclo 6
# que motivo justamente esa tabla. Levantado por el /simplify del ciclo 9.
#
# Las tablas se descubren leyendo el FUENTE, no `globals()`: filtrar el espacio
# de nombres en esta misma linea reintroducia el punto ciego de posicion que
# `_constantes_de_puerta` acababa de quitarle a los escalares --una tabla
# declarada mas abajo no entraba, y eso se midio--. El barrido ve toda tabla de
# nivel de modulo con claves de cadena de la que al menos una nombre una puerta
# real; lo que NO ve, y no se promete, es una tabla nueva con TODAS las claves
# mal escritas: contra eso esta el suelo de nombres de aqui abajo, que obliga a
# que las cinco conocidas sigan reconociendose.
# Levantado por la revision de codigo posterior al ciclo 10.
_TABLAS_DE_PUERTA = {
    nombre: claves
    for nombre, claves in _tablas_indexadas_por_puerta(pathlib.Path(__file__)).items()
    if nombre != "_TODAS_LAS_PUERTAS" and set(claves) & _TODAS_LAS_PUERTAS
}
_ESPERADAS = {
    "PUERTAS_DELEGADAS", "TAREAS_POR_PUERTA", "PUERTAS_QUE_EL_BUILD_NO_APRUEBA",
    "PUERTAS_MEDIDAS_EN_TESTS", "SCRIPT_POR_PUERTA",
}
if not _ESPERADAS <= set(_TABLAS_DE_PUERTA):
    raise AssertionError(
        f"la deteccion de tablas indexadas por puerta dejo de ver "
        f"{sorted(_ESPERADAS - set(_TABLAS_DE_PUERTA))}: sin ellas esta guarda no vigila nada"
    )
_CLAVES_HUERFANAS = {
    nombre: sorted(set(tabla) - _TODAS_LAS_PUERTAS)
    for nombre, tabla in _TABLAS_DE_PUERTA.items()
    if set(tabla) - _TODAS_LAS_PUERTAS
}
if _CLAVES_HUERFANAS:
    raise AssertionError(
        f"tablas con claves que no nombran ninguna puerta: {_CLAVES_HUERFANAS}. "
        f"Su rama no se ejecutaria nunca, y la de PUERTAS_MEDIDAS_EN_TESTS ademas "
        f"mediria clases en vez de tests, que es un verde sobre cero tests."
    )


AVISO_INSUMO_VACIO = "AVISO: insumo vacio"


@dataclasses.dataclass
class Puerta:
    nombre: str
    perfil: str
    estado: str
    evidencia: str
    # El TAMANO de lo que la puerta analizo, no solo su resultado. Cero
    # clases, cero tipos, cero claves y cero dependencias son el mismo
    # sintoma, y hasta ahora se atrapaba con una guarda distinta cada vez,
    # anadida despues de que alguien descubriera la instancia por accidente.
    insumo: str = ""


@dataclasses.dataclass
class Certificado:
    perfil: str
    puertas: list[Puerta]
    # El nombre dice lo que el campo GUARDA. Se llamaba `todo_verde` y desde
    # que pasó a guardar `estado_de_sumision` mentia: «todas las puertas
    # verdes» es provablemente falso en TODO certificado real --dos filas van
    # siempre en rojo por diseño-- y este es el fichero cuyo unico cometido es
    # no mentir. No se guarda ademas la lista de motivos: `render_markdown` la
    # recalcula por ser puro, asi que el campo era estado de solo escritura y
    # quien lo leyera se habria encontrado `[]` sobre un certificado emitido.
    listo_para_sumision: bool
    # Si `./gradlew build` se ejecuto y COMO termino, en la cabecera. Es el
    # minimo irrenunciable: antes el certificado no guardaba ni una huella de
    # un build fallido.
    build: str = ""
    # Contra QUE superficie se valido y sobre QUE fuente. La SKILL ya prometia
    # los dos en la cabecera y el certificado no los llevaba: sin el hash, un
    # dossier de hace dos semanas y uno de hoy son indistinguibles.
    indice: str = ""
    revision: str = ""
    # Por que el perfil es el que es, cuando no es el que se pidio. Va en el
    # certificado y no en un `print` porque el sitio donde importa es el
    # documento que alguien lee semanas despues, no la consola de quien lanzo
    # la orden.
    nota_perfil: str = ""


def _resolver_perfil(pedido: str, datos_contrato) -> tuple[str, str]:
    """Que perfil describe este certificado, y por que.

    Manda EL MAS ESTRICTO de los dos, nunca el mas comodo. RIGUROSO es un
    superconjunto de ESTANDAR --anade cuatro filas y no quita ninguna-- asi que
    la asimetria es real y no una convencion:

    - **Bajar no se puede.** Un contrato que promete RIGUROSO verificado como
      estandar perdia sus cuatro filas; no fallaban, DESAPARECIAN, y el
      certificado quedaba mas limpio por haber mirado menos. Y `estandar` es el
      defecto del CLI, asi que bastaba olvidarse del argumento.
    - **Subir si.** Pedir RIGUROSO sobre un contrato estandar es comprobar con
      el liston alto: nadie sale enganado de ahi.

    Nada que no se pueda leer se resuelve a favor: un perfil --declarado O
    PEDIDO-- que no existe, y una seccion `[plugin]` o `[capacidades]` que no
    es una tabla, llevan todos al liston alto, con la nota diciendo QUE fue.
    Se recogen todas las averias antes de decidir, para que la primera no tape
    a las siguientes.

    Y hay un TERCER reclamante, que es el que cierra la puerta de atras: las
    `[capacidades]`. Describen lo que el plug-in HACE --sale a la red, toca
    credenciales, parsea formatos ajenos, trata datos personales-- y son el
    unico reclamante que nadie puede olvidarse de escribir, porque el esquema
    las exige. Un contrato que las declara y aun asi pide `estandar` perdia
    exactamente las mismas cuatro filas por la otra puerta: `contrato.py` lo
    veia, lo decia como `AVISO` y devolvia 0, y aqui no se miraba. La
    vigilancia NO vive en `contrato.validar` --que solo comprueba que las
    claves esten presentes--: vive aqui, que es donde se decide que filas
    aparecen. Levantado por el gate del ciclo 9.
    """
    # `None` = nadie pidio nada; el defecto se aplica AQUI y no en argparse,
    # para que la nota no afirme una peticion que no existio. Es el fichero
    # cuyo unico cometido es no mentir: «se lanzo como ESTANDAR» sobre alguien
    # que no escribio el argumento es una afirmacion falsa, pequena y gratuita.
    pedido_de_verdad = pedido
    pedido = pedido or PERFIL_POR_DEFECTO
    datos = datos_contrato or {}

    # TODO lo que puede venir mal se recoge ANTES de decidir, y todo lo que
    # venga mal se dice. Encadenar `return`s hacia que el primero tapara a los
    # demas: con `perfil = "RIGUROSO"` en mayusculas Y ADEMAS `capacidades =
    # "pendiente"`, la nota hablaba solo de las capacidades y el «perfil que no
    # existe» desaparecia, que es el mismo defecto que el reordenado anterior
    # se escribio para cerrar. Revision de codigo posterior al ciclo 10.
    averias: list[str] = []

    # `[plugin]` que no es tabla. AQUI no se usa `contrato.seccion`, y es
    # deliberado: ese helper devuelve `{}` para lo que no sea tabla, que es
    # lo correcto para un consumidor que solo quiere leer, y ESTE es el
    # unico sitio que tiene que DISTINGUIR «no es una tabla» de «no esta»
    # para poder decirlo en la nota. Con el helper, la averia desaparecia de
    # la nota sin dejar rastro. `datos.get(nombre, {})` solo repone el
    # defecto cuando la clave FALTA: con `plugin = "smart-service"` --o con
    # `[[plugin]]`, que TOML convierte en lista-- el `.get` de dentro estallaba
    # sobre un `str` y se llevaba por delante al orquestador entero, sin
    # certificado, que es peor que cualquier fila roja. Es la guarda que
    # `[capacidades]` ya tenia una linea mas abajo y sus hermanas no.
    seccion_plugin = datos.get("plugin", {})
    if not isinstance(seccion_plugin, dict):
        averias.append("la seccion `[plugin]` del contrato no es una tabla")
        seccion_plugin = {}
    declarado = seccion_plugin.get("perfil")

    capacidades = datos.get("capacidades", {})
    if not isinstance(capacidades, dict):
        averias.append(
            f"la seccion `[capacidades]` del contrato no es una tabla, asi que no se "
            f"puede saber si piden {PERFIL_ESTRICTO.upper()}"
        )
        capacidades = {}

    if declarado is not None and declarado not in contrato.PERFILES:
        averias.append(f"el contrato declara un perfil que no existe (`{declarado}`)")
        declarado = None

    # Y el perfil PEDIDO tambien se valida, que era el agujero mas caro de los
    # tres: `argparse` no llevaba `choices` y aqui solo se miraba el declarado,
    # asi que una errata de una letra --`rigoroso`-- devolvia ese valor tal
    # cual, `certificado_base` lo comparaba con PERFIL_ESTRICTO, salia falso, y
    # las cuatro filas rigurosas NO FALLABAN: DESAPARECIAN, mientras la
    # cabecera imprimia «Perfil: RIGOROSO», que a ojo se lee como correcto.
    if pedido not in contrato.PERFILES:
        averias.append(f"se pidio verificar con un perfil que no existe (`{pedido}`)")

    if averias:
        # Cualquier averia se resuelve EN CONTRA. No se sabe que se quiso
        # verificar, y el liston alto no engana a nadie: las cuatro filas
        # rigurosas apareceran y saldran NO VERIFICADO, que es justo lo que hay
        # que ver. Resolverlo a favor las hacia desaparecer.
        return PERFIL_ESTRICTO, (
            "; ".join(averias)
            + f". No se puede saber que se quiso verificar, asi que se usa el liston alto "
              f"({PERFIL_ESTRICTO.upper()}): corrigelo en el contrato o en la orden. "
              f"Ninguna fila de este certificado lo comprueba por su cuenta"
        )

    # La regla de QUE capacidades piden RIGUROSO vive en `contrato`, no aqui:
    # el AVISO de `contrato.main` promete lo que hara este fichero, y esa
    # promesa solo es cierta mientras los dos apliquen el mismo criterio. Los
    # nombres, y no solo el perfil, porque «tus capacidades lo piden» sin decir
    # cual manda a leerse el contrato entero.
    exigentes = contrato.capacidades_exigentes(capacidades)

    if exigentes and PERFIL_ESTRICTO not in (declarado, pedido):
        return PERFIL_ESTRICTO, (
            f"lo piden las capacidades declaradas ({', '.join(exigentes)}); el contrato "
            f"declara {(declarado or 'ninguno').upper()} y subir el liston no engana a nadie"
        )

    if not declarado or declarado == pedido:
        return pedido, ""
    if declarado == PERFIL_ESTRICTO:
        como = (
            f"se lanzo como {pedido.upper()}" if pedido_de_verdad
            else f"no se pidio ninguno y el defecto es {PERFIL_POR_DEFECTO.upper()}"
        )
        return declarado, (
            f"lo pide el contrato, que declara {declarado.upper()}; {como}, y un "
            f"certificado describe el plug-in, no la orden con que se verifico"
        )
    return pedido, (
        f"lo pide quien lanzo la verificacion; el contrato declara {declarado.upper()}. "
        f"Subir el liston no engana a nadie, asi que se respeta"
    )


def certificado_base(perfil: str, nota_perfil: str = "") -> Certificado:
    puertas = [
        Puerta(n, "ambos", "no-ejecutada", "") for n in PUERTAS_AMBOS_PERFILES
    ]
    if perfil == PERFIL_ESTRICTO:
        puertas += [
            Puerta(n, PERFIL_ESTRICTO, "no-ejecutada", "") for n in PUERTAS_RIGUROSO
        ]
    puertas += [
        Puerta(n, "ambos", "rojo", motivo) for n, motivo in PUERTAS_NUNCA_VERIFICABLES
    ]
    for p in puertas:
        if p.nombre == PUERTA_INFORMATIVA:
            p.estado = "informativa"
            p.evidencia = "no bloquea — insumo de la Fase 3"
        elif p.nombre in PUERTAS_DELEGADAS:
            p.estado = "delegada"
            p.evidencia = PUERTAS_DELEGADAS[p.nombre]
    return Certificado(
        perfil=perfil, puertas=puertas, listo_para_sumision=False,
        nota_perfil=nota_perfil,
    )


def calcular_todo_verde(puertas: list[Puerta]) -> bool:
    # SIN LLAMADOR DE PRODUCCION, y se dice para que nadie lo descubra tarde:
    # quien decide es `estado_de_sumision`, que ademas excluye las dos filas
    # estructuralmente rojas. Esta se conserva porque es un predicado distinto
    # --«TODAS verdes», sin exclusiones-- y sus tests fijan el fundamento que
    # los comentarios de este fichero citan. Si algun dia hay que elegir, la
    # que manda es la otra.
    # «delegada» NO entra: delegar es nombrar a quien mira, no afirmar que
    # miro y salio bien. Si colara como verde, declarar motivos se convertiria
    # en la via limpia para blanquear una puerta sin ejecutarla.
    #
    # Y un verde sobre CERO unidades tampoco entra: es la forma exacta que
    # tienen las cinco instancias del verde vacuo. Antes hacia falta una
    # guarda nueva en cada validador segun se descubrian; aqui es una sola
    # propiedad que las cubre a todas, incluidas las que nadie ha encontrado.
    return all(
        p.estado in ("verde", "informativa", "no-aplica")
        and not (p.estado == "verde" and contrato.insumo_vacio(p.insumo))
        for p in puertas
    )


LISTO = "READY_FOR_APPIAN_SUBMISSION"
NO_LISTO = "NOT_READY"


def estado_de_sumision(puertas: list[Puerta]) -> tuple[bool, list[str]]:
    """El criterio de salida de la SKILL (paso 5), hecho comprobable.

    Por que no vale `calcular_todo_verde` para esto: aquella exige que TODAS
    las puertas esten verdes, y las dos ultimas van SIEMPRE en rojo por diseno
    --resolucion OSGi y ejecucion en Appian real no son verificables en local--.
    En un certificado real nunca podia dar cierto, asi que publicarla habria
    sido una alarma que salta siempre, que es el mismo dano que este proyecto ya
    evito dos veces. Aqui esas dos filas se excluyen EXPRESAMENTE: son el limite
    honesto de la verificacion local, no un defecto del plug-in.

    Las tres partes del criterio, mas la propiedad del insumo:
      1. ninguna puerta en «pendiente» — nadie la miro y nadie dijo por que;
      2. ninguna en rojo, salvo las dos estructurales;
      3. ninguna «delegada» salvo las que un BUILD SUCCESSFUL no puede
         aprobar por mucho que se ejecute — delegar no es aprobar;
      4. ningun verde sobre un insumo vacio: un exito sobre cero unidades no
         es un exito, y hasta ahora eso solo se marcaba en una celda que nadie
         estaba obligado a leer.

    La pregunta que hay que hacerle a todo mecanismo que pueda reportar exito
    --«¿que trabajo respalda este verde, y como se veria si no se hubiera
    hecho?»-- aplicada a esta funcion: de los estados que NO bloquean, `verde`
    solo lo asigna una invocacion real con codigo 0 o la salida del build que
    confirma la tarea; `no-aplica` solo `_aplicar_no_aplica`, tras confirmar el
    hecho contra el contrato; y `delegada` solo sobrevive en las que un
    BUILD SUCCESSFUL no puede aprobar (hoy dos: el bytecode dentro del JAR y
    la reproducibilidad del build). El unico que se asigna AL NACER y nunca
    se gana es `informativa`, y lo lleva una sola puerta --la deriva contra la
    version del entorno-- que es no bloqueante POR DISENO, no por haber pasado:
    su mecanizacion es insumo de la Fase 3. `test_solo_una_puerta_puede_ser_informativa`
    fija que siga siendo una y solo una.
    """
    nunca = {n for n, _ in PUERTAS_NUNCA_VERIFICABLES}
    motivos: list[str] = []
    for p in puertas:
        if p.nombre in nunca:
            continue
        if p.estado == "no-ejecutada":
            motivos.append(f"«{p.nombre}»: no la ejecuto nadie")
        elif p.estado == "rojo":
            motivos.append(f"«{p.nombre}»: en rojo — {p.evidencia}")
        elif p.estado == "delegada" and p.nombre not in PUERTAS_QUE_EL_BUILD_NO_APRUEBA:
            motivos.append(
                f"«{p.nombre}»: sigue delegada, sin la salida real de quien la ejecuta"
            )
        elif p.estado == "verde" and contrato.insumo_vacio(p.insumo):
            unidades = p.insumo[len(contrato.PREFIJO_INSUMO):].strip() or "sin declarar"
            motivos.append(f"«{p.nombre}»: verde sobre un insumo vacio ({unidades})")
    return (not motivos), motivos


SIMBOLO = {
    "verde": "OK",
    "rojo": "NO VERIFICADO",
    "informativa": "info",
    "no-ejecutada": "pendiente",
    "delegada": "delegada",
    # Una capa que no aplica a este tipo de plug-in. No es un aprobado —no se
    # comprobo nada— pero tampoco un pendiente: no hay nada que comprobar.
    "no-aplica": "no aplica",
}


def render_markdown(cert: Certificado) -> str:
    listo, motivos = estado_de_sumision(cert.puertas)
    lineas = [
        "# Certificado de verificacion",
        "",
        # El estado va PRIMERO y con todas las letras. Es lo unico que un
        # lector con prisa va a leer, y hasta ahora habia que deducirlo
        # interpretando una tabla de trece a diecisiete filas.
        f"**STATUS: {LISTO if listo else NO_LISTO}**",
        "",
        f"**Perfil:** {cert.perfil.upper()}"
        + (f" — {cert.nota_perfil}" if cert.nota_perfil else ""),
        "**SDK:** com.appian:appian-plug-in-sdk:26.3 · **Java:** release 17 (major 61)",
    ]
    if cert.indice:
        lineas.append(f"**Indice de tipos:** {cert.indice}")
    if cert.revision:
        lineas.append(f"**Revision del fuente:** {cert.revision}")
    if cert.build:
        lineas.append(f"**`./gradlew build`:** {cert.build}")
    if not listo:
        lineas += ["", f"### Que impide enviarlo ({len(motivos)})", ""]
        lineas += [f"- {m}" for m in motivos]
    lineas += [
        "",
        "| Puerta | Perfil | Estado | Insumo analizado | Evidencia |",
        "|---|---|---|---|---|",
    ]
    for p in cert.puertas:
        insumo = p.insumo[len(contrato.PREFIJO_INSUMO):].strip() if p.insumo else "—"
        if p.estado == "verde" and contrato.insumo_vacio(p.insumo):
            insumo = f"{insumo} · **{AVISO_INSUMO_VACIO}**"
        lineas.append(
            f"| {p.nombre} | {p.perfil} | {SIMBOLO[p.estado]} | {insumo} | {p.evidencia or '—'} |"
        )
    lineas += [
        "",
        f"**{LISTO}** exige las tres partes del criterio —ninguna puerta pendiente,",
        "ninguna en rojo salvo las dos estructurales, y ninguna delegada sin la salida",
        "real de quien la ejecuta— mas que ningun verde lo sea sobre un insumo vacio.",
        "Las dos filas estructurales NO cuentan en contra: son el limite honesto de la",
        "verificacion local, y decirlo es la funcion de este documento.",
        "",
        "Las dos ultimas filas van siempre en rojo. Una puerta que no se ejecuto",
        "nunca se marca como pasada.",
        "",
        "«delegada» significa que la puerta la ejecuta otro —Gradle, en el paso BUILD—,",
        "y la columna de evidencia dice cual. No es un aprobado: para darla por cumplida",
        "hace falta la salida real de ese ejecutor, no esta tabla.",
    ]
    return "\n".join(lineas)


def ejecutar(
    raiz_proyecto: pathlib.Path,
    perfil: str,
    salida_build: pathlib.Path | None = None,
    codigo_build: int | None = None,
) -> Certificado:
    """Ejecuta cada validador y anota su resultado como evidencia.

    Cada bloque invoca el script correspondiente sobre los artefactos reales del
    proyecto generado. Si un validador falla —por lo que sea, incluido no poder
    arrancar—, su puerta queda en ROJO con la salida real como evidencia; jamas
    en verde. Las puertas sin invocacion enganchada se quedan en «no-ejecutada»,
    que tampoco es verde. La regla no negociable es la misma en los dos casos:
    una puerta que no se ejecuto NUNCA se marca como pasada.

    Las que ejecuta Gradle no se invocan desde aqui —no se puede— pero SI se
    leen: `salida_build.ingerir` va a buscar la salida real de `./gradlew build`
    y cada fila delegada se resuelve con ella.
    """
    # `sys.executable`, NUNCA la cadena "python". En un sistema donde `python`
    # no esta en el PATH --POSIX moderno instala `python3`-- o bajo un venv que
    # el orquestador no herede, `subprocess.run` lanza FileNotFoundError, y
    # aqui no hay nada que lo capture: el orquestador muere justo al emitir el
    # certificado, que es el peor momento posible para caerse (el mismo
    # argumento que ya defiende `_evidencia`). El humo E2E no podia cazarlo
    # porque el SI invoca este script con `sys.executable`: llamaba bien al
    # padre, que llamaba mal a los hijos.
    piton = sys.executable

    scripts = pathlib.Path(__file__).resolve().parent
    contrato_md = raiz_proyecto / "docs" / "contrato.md"
    clases = raiz_proyecto / "build" / "classes" / "java" / "main"
    recursos = raiz_proyecto / "src" / "main" / "resources"
    indice = scripts.parent / "assets" / "indice-tipos-26.3.json"
    inventario = raiz_proyecto / "build" / "reports" / "inventario-api.json"

    # Capa 4: solo se puede mirar el JAR ya construido. Nueve reglas
    # documentadas que hasta ahora no tenian ningun llamador en el repositorio.
    # Por FECHA descendente, no alfabeticamente. `build` no limpia, asi que
    # tras subir la version conviven `x-0.1.0.jar` y `x-0.2.0.jar`, y el orden
    # alfabetico elegia el de version MENOR: las nueve reglas de esta capa
    # certificaban el artefacto que ya no se entrega, con el log fresco y la
    # red de rancidez sin nada que decir. Levantado por el gate del ciclo 16.
    jars = sorted(
        (j for j in (raiz_proyecto / "build" / "libs").glob("*.jar")
         if not j.stem.endswith(("-sources", "-javadoc"))),
        key=lambda j: j.stat().st_mtime,
        reverse=True,
    )

    # Solo los ARGUMENTOS: el script de cada puerta sale de `SCRIPT_POR_PUERTA`,
    # que es tambien de donde se deriva `PUERTAS_CON_INVOCACION`. Asi un nombre
    # que se escriba mal aqui revienta con KeyError en vez de dejar una puerta
    # muda que el allowlist absuelve.
    # El contrato se lee UNA vez, no una por puerta verde: es invariante del
    # bucle, `cargar` reparsea el TOML en cada llamada, y ademas de el sale el
    # paquete de dominio que necesita la puerta de superficie.
    datos_contrato = _contrato_leido(contrato_md)

    # Y de el sale tambien EL PERFIL. Hasta el ciclo 7 el perfil venia solo del
    # argumento de linea de ordenes, con `estandar` por defecto, y nadie lo
    # cruzaba con el contrato: un plug-in cuyo contrato declara RIGUROSO
    # verificado sin argumento emitia `**Perfil:** ESTANDAR` y las cuatro filas
    # rigurosas --cobertura, mutacion, property tests, build reproducible-- no
    # aparecian siquiera. No es que fallaran: desaparecian, y el certificado
    # quedaba mas limpio por haber mirado menos. El defecto era el debil.
    cert = certificado_base(*_resolver_perfil(perfil, datos_contrato))
    paquete_dominio = contrato.paquete_de_dominio(datos_contrato) if datos_contrato else ""

    argumentos = {
        # La raiz va al final porque de ella salen los tres ficheros de R-F14
        # --`build.gradle`, `config/spotbugs/exclude.xml` y `docs/decisiones.md`--:
        # la unica regla que mira la PUERTA en vez del plug-in.
        "Reglas del framework de Appian": [
            str(contrato_md), str(recursos / "appian-plugin.xml"), str(clases),
            str(raiz_proyecto),
        ],
        "Politicas AppMarket": [str(contrato_md), str(clases)],
        "Bundles y locales": [str(contrato_md), str(recursos)],
        # El inventario se pide POR RUTA ABSOLUTA dentro del proyecto: antes se
        # escribia relativo al cwd del orquestador y el dossier lo leia relativo
        # a la raiz del proyecto, asi que su pieza 3 salia siempre «pendiente»
        # —y un inventario rancio de otro plug-in podia acabar publicado bajo un
        # encabezado que afirma su procedencia—.
        # El paquete de dominio va al FINAL, que es donde `verificar_superficie`
        # espera los suyos. Sin el, D19 --«el dominio no conoce el SDK»-- tenia
        # el bucle vacio y devolvia `[]` siempre: declarado, con tests
        # unitarios, y sin una sola ejecucion real que lo disparara. Lo levanto
        # el gate del ciclo 6.
        "Superficie documentada · indice 26.3": [
            str(clases), str(indice), "--inventario", str(inventario),
            *([paquete_dominio] if paquete_dominio else []),
        ],
        # Lee el SBOM que genero `./gradlew cyclonedxDirectBom`. Si no hay
        # SBOM, el script sale en rojo diciendolo: no poder mirar no es «ya lo
        # miraremos», el mismo criterio que rige para el JAR ausente.
        PUERTA_LICENCIAS: [str(raiz_proyecto)],
        # La UNICA condicional, y por eso va con su valor aunque no haya JAR:
        # sin JAR la puerta se resuelve en rojo antes de llegar a buscar aqui.
        PUERTA_EMPAQUETADO: [str(jars[0]), str(contrato_md)] if jars else [],
    }
    # El otro sentido de la costura: que no sobre ni falte ninguna. Sin esto,
    # una puerta podia figurar en `SCRIPT_POR_PUERTA` --y por tanto en el
    # allowlist-- sin que nadie le pasara argumentos.
    if set(argumentos) != set(SCRIPT_POR_PUERTA):
        raise AssertionError(
            f"puertas con script pero sin argumentos (o al reves): "
            f"{set(argumentos) ^ set(SCRIPT_POR_PUERTA)}"
        )
    invocaciones = {
        nombre: [piton, str(scripts / SCRIPT_POR_PUERTA[nombre]), *args]
        for nombre, args in argumentos.items()
    }

    pendientes: list[tuple[Puerta, list[str]]] = []
    for puerta in cert.puertas:
        if puerta.nombre == PUERTA_EMPAQUETADO and not jars:
            # No poder mirar el artefacto NO es «ya lo miraremos»: es lo mismo
            # que analizar cero clases, y alli tambien es rojo.
            puerta.estado = "rojo"
            puerta.evidencia = (
                f"no hay ningun JAR en {raiz_proyecto / 'build' / 'libs'}; la capa 4 solo se "
                f"puede ejecutar sobre el artefacto ya construido (`./gradlew jar`)"
            )
            continue
        comando = invocaciones.get(puerta.nombre)
        if comando:
            pendientes.append((puerta, comando))

    # En PARALELO, y no por elegancia: en Windows cada `subprocess.run` cuesta
    # ~0,5 s de puro arranque, asi que seis en serie son ~3 s de espera pura
    # sobre ~0,2 s de trabajo real. Medido sobre el proyecto de referencia:
    # 2,15 s en serie frente a 0,88 s en paralelo.
    #
    # Son independientes y se puede afirmar por que: cinco solo LEEN, y el
    # unico que escribe --`verificar_superficie`, que deja el inventario-- no
    # tiene ningun lector dentro del bucle; `_indice_usado` lo abre despues.
    # Cada proceso captura su propio stdout, asi que tampoco hay salida
    # entrelazada, y el orden de las filas del certificado lo fija
    # `cert.puertas`, no el orden en que terminen.
    #
    # Hilos y no procesos: aqui se espera a un proceso hijo, no se calcula.
    if pendientes:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(pendientes)) as pool:
            lanzados = {
                pool.submit(subprocess.run, comando, capture_output=True, text=True): puerta
                for puerta, comando in pendientes
            }
            for futuro in concurrent.futures.as_completed(lanzados):
                puerta = lanzados[futuro]
                proceso = futuro.result()
                puerta.estado = "verde" if proceso.returncode == 0 else "rojo"
                puerta.evidencia = _evidencia(proceso.stdout, proceso.stderr, puerta.estado)
                puerta.insumo = _insumo(proceso.stdout)
                # Un validador que declara que su capa no aplica a este tipo no
                # ha aprobado nada: aprobarlo seria un verde sobre cero
                # unidades, que es justo lo que la columna de insumo existe
                # para no dejar pasar.
                if puerta.estado == "verde":
                    _aplicar_no_aplica(puerta, proceso.stdout, datos_contrato)

    cert.build = _resolver_delegadas(cert, raiz_proyecto, salida_build, codigo_build)
    cert.indice = _indice_usado(inventario)
    cert.revision = _revision_git(raiz_proyecto)
    # El campo pasa a significar LISTO PARA SUMISION, que es lo que un lector
    # necesita saber, en vez de «todas las puertas verdes» — condicion que las
    # dos filas estructuralmente rojas hacian inalcanzable en un certificado
    # real. `calcular_todo_verde` sigue existiendo como predicado puro.
    cert.listo_para_sumision = estado_de_sumision(cert.puertas)[0]
    return cert


def _indice_usado(inventario: pathlib.Path) -> str:
    """Contra QUE superficie se valido, con su hash.

    El dato ya lo escribe `verificar_superficie` en el inventario; lo unico que
    faltaba era subirlo a la cabecera. Sin el, dos dossieres de superficies
    distintas son indistinguibles — y el modo degradado del escaner (sin
    indice) se lee igual que una validacion completa.
    """
    if not inventario.is_file():
        # No hay inventario porque el escaner no llego a correr; su propia
        # puerta ya lo dice, y esta cabecera no tiene nada que anadir.
        return ""
    try:
        datos = json.loads(inventario.read_text(encoding="utf-8"))
    except Exception as e:
        # Un inventario que EXISTE y no se puede leer no es lo mismo que no
        # tenerlo, y hasta el ciclo 7 se publicaban igual: cadena vacia, linea
        # ausente, cabecera indistinguible de la de un certificado sano. La
        # regla del fichero --no resolver a favor lo que no se pudo mirar-- ya
        # la aplican `_revision_git` y `_contrato_leido`.
        return f"ILEGIBLE — `{inventario.name}` existe y no se pudo leer ({type(e).__name__})"
    version, hash_ = datos.get("version_indice"), datos.get("hash_indice")
    if not version:
        return "SIN INDICE — el escaner corrio en modo degradado (filtro por paquete)"
    return f"{version} · sha256 {hash_[:16]}" if hash_ else str(version)


def _revision_git(raiz: pathlib.Path) -> str:
    """La revision del fuente que este certificado describe.

    No se resuelve a favor: si no hay repositorio, se dice, en vez de callar y
    dejar creer que el certificado esta atado a un commit.
    """

    # UN solo proceso para los dos datos. `--porcelain=v2 --branch` trae el OID
    # en `# branch.oid` y, en las lineas sin `#`, el estado del arbol: antes
    # eran `rev-parse` mas `status`, ~0,87 s en esta maquina frente a ~0,33 s.
    #
    # Y NO se usa `git describe --always --dirty`, que tambien seria un proceso:
    # `--dirty` mira `diff-index` e ignora los ficheros sin seguimiento, asi que
    # un arbol con un fichero nuevo sin anadir se declararia limpio. En un
    # documento cuya funcion es la honestidad, esa diferencia no es un detalle.
    try:
        proceso = subprocess.run(
            ["git", "-C", str(raiz), "status", "--porcelain=v2", "--branch"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "sin determinar (no se pudo ejecutar git)"
    if proceso.returncode != 0:
        return "sin repositorio git — el certificado no queda atado a ningun commit"

    oid, sucio = "", False
    for linea in proceso.stdout.splitlines():
        if linea.startswith("# branch.oid "):
            oid = linea[len("# branch.oid "):].strip()
        elif linea.strip() and not linea.startswith("#"):
            sucio = True
    # Un repositorio recien creado y sin ningun commit responde `(initial)`. No
    # se resuelve a favor: tampoco ahi hay commit al que atar el certificado.
    if not oid or oid == "(initial)":
        return "repositorio git sin ningun commit — el certificado no queda atado a ninguno"
    marca = " (arbol con cambios sin commitear)" if sucio else ""
    return oid[:7] + marca


def _resolver_delegadas(
    cert: Certificado,
    raiz: pathlib.Path,
    ruta: pathlib.Path | None,
    codigo: int | None,
) -> str:
    """Cada fila delegada, resuelta con la salida REAL de `./gradlew build`.

    Devuelve el resumen que va a la cabecera del certificado. La regla es la
    misma que ya rige para el JAR ausente: no poder mirar no es «ya lo
    miraremos». Un log ausente, rancio, truncado o contradictorio vale lo mismo
    que uno que dice BUILD FAILED — rojo.
    """
    resultado = sb.ingerir(raiz, ruta, codigo)

    for p in cert.puertas:
        if p.nombre not in PUERTAS_DELEGADAS:
            continue
        matiz = PUERTAS_DELEGADAS[p.nombre]
        tarea = TAREAS_POR_PUERTA.get(p.nombre)

        if not resultado.consta:
            p.estado = "rojo"
            p.evidencia = resultado.motivo
        elif resultado.desenlace == sb.FALLIDO:
            # Ninguna puerta delegada se certifica dentro de un build fallido,
            # ni siquiera una cuya tarea llego a pasar antes del fallo: Gradle
            # se detiene en el primer error y lo de despues no consta. Aprobar
            # una por dentro seria la via limpia para escoger a mano.
            p.estado = "rojo"
            p.evidencia = (
                resultado.motivo
                if tarea and resultado.tareas.get(tarea) == "FAILED"
                else f"{resultado.motivo}; dentro de un build fallido no se certifica "
                     f"ninguna puerta delegada"
            )
        elif tarea and resultado.tareas.get(tarea) is None:
            # `mutationTest`, `jacocoTestCoverageVerification` y `releaseCheck`
            # no forman parte de `build`: si el log no las menciona, nadie las
            # ejecuto, y eso es exactamente lo que hay que decir.
            #
            # VA ANTES que la rama de PUERTAS_QUE_EL_BUILD_NO_APRUEBA, y el
            # orden importa: «Build reproducible» esta en las DOS tablas, y son
            # dos cosas distintas que no se pueden confundir --«nadie lo
            # ejecuto» es ROJO; «se ejecuto pero esa tarea no comprueba esto»
            # es delegada--. El `tarea and` es lo que deja pasar de largo a la
            # puerta del bytecode del JAR, que no tiene tarea asociada.
            p.estado = "rojo"
            # Y se dice CON QUE se arregla. Decir solo «no se ejecuto» deja al
            # lector buscando el comando: medido el 19-sep-2026, dos pruebas
            # E2E con contrato RIGUROSO capturaron el log con un `./gradlew
            # build` a secas, leyeron estas tres filas en rojo y ninguna de las
            # dos dio con el comando que faltaba --una lo dio por normal y
            # siguio hasta el dossier--. El comando sale de `salida_build`, que
            # es de donde sale tambien el de la captura corriente.
            p.evidencia = (
                f"`{tarea}` no aparece en la salida del build: ese comando no se "
                f"ejecuto — {matiz}. Se capturan las tres de una vez con "
                f"`{sb.COMANDO_DE_CAPTURA_RIGUROSO}`, sobre un worktree ya commiteado"
            )
        elif p.nombre in PUERTAS_QUE_EL_BUILD_NO_APRUEBA:
            p.evidencia = f"{resultado.motivo}, que NO la comprueba: {matiz}"
        else:
            p.estado = "verde"
            p.evidencia = f"{resultado.motivo} (`{tarea}` {resultado.tareas[tarea]})"
            p.insumo = _insumo_delegado(raiz, p.nombre, resultado)

    origen = f" · `{pathlib.Path(resultado.origen).name}`" if resultado.origen else ""
    return f"{resultado.motivo}{origen}"


# El convenio de nombre con el que se reconoce un property/fuzz test. ESTA es
# la fuente: la plantilla del perfil riguroso lo consume para excluirlos de PIT
# (`perfil-riguroso.gradle.tmpl`, `excludedTestClasses`) y un test lo sujeta en
# esa direccion. El ciclo 7 encontro los dos lados divergidos --la puerta
# contaba `*PropertyTest` y la plantilla no lo excluia, asi que PIT lo ATACABA,
# con `mutationThreshold = 85` y `failWhenNoMutations = true` esperando-- y por
# eso el convenio ya no se escribe dos veces a mano.
#
# `*PerformanceTest` lo excluye la plantilla y NO cuenta aqui a proposito: un
# test de rendimiento tampoco debe mutarse, pero no es un property test.
SUFIJOS_PROPERTY_TEST = ("FuzzTest", "PropertyTest")


def _insumo_delegado(raiz: pathlib.Path, nombre: str, resultado) -> str:
    # La puerta de property tests se mide en PROPERTY TESTS, no en tests a
    # secas. Medirla en el total era un verde vacuo de manual: `5 tests, 0
    # property tests` es la forma canonica --cero en la dimension que importa,
    # las demas sanas-- y la fila salia VERDE con una bateria de tests
    # corrientes y ni un solo property test, porque su tarea es `:test`, que SI
    # forma parte de `build`. Lo levanto el gate del ciclo 6 como [ALTA], y es
    # la misma familia que el «Build reproducible» del ciclo 5.
    #
    # La portante se declara: cero property tests marca el insumo y bloquea el
    # READY, en vez de esconderse detras del recuento total.
    if nombre == PUERTA_PROPERTY_TESTS:
        return contrato.linea_de_insumo(
            portante="property_tests",
            property_tests=_tests_ejecutados(raiz, resultado, solo_property=True),
            tests=_tests_ejecutados(raiz, resultado),
        )
    if nombre in PUERTAS_MEDIDAS_EN_TESTS:
        return contrato.linea_de_insumo(tests=_tests_ejecutados(raiz, resultado))
    return contrato.linea_de_insumo(clases=_clases_compiladas(raiz))


def _clases_compiladas(raiz: pathlib.Path) -> int:
    destino = raiz / "build" / "classes" / "java" / "main"
    return sum(1 for _ in destino.rglob("*.class")) if destino.is_dir() else 0


def _tests_ejecutados(raiz, resultado, solo_property: bool = False) -> int:
    """Cuantos casos corrio de verdad la bateria, no cuantos hay escritos.

    `NO-SOURCE` manda sobre cualquier XML que quedara de una corrida anterior:
    si esta vez no habia tests, fueron cero.

    Con `solo_property`, cuenta unicamente los ficheros de resultados cuya
    clase sigue el convenio `*FuzzTest` / `*PropertyTest`. Gradle escribe un
    `TEST-<clase>.xml` por clase, asi que el nombre del fichero basta y no hay
    que abrir el XML para saber de quien es.
    """
    if resultado.tareas.get(":test") in ("NO-SOURCE", "SKIPPED"):
        return 0
    destino = raiz / "build" / "test-results" / "test"
    if not destino.is_dir():
        return 0
    total = 0
    for xml in sorted(destino.glob("TEST-*.xml")):
        if solo_property and not xml.stem.endswith(SUFIJOS_PROPERTY_TEST):
            continue
        m = re.search(r'\btests="(\d+)"', xml.read_text(encoding="utf-8", errors="replace"))
        if m:
            total += int(m.group(1))
    return total


def _contrato_leido(contrato_md: pathlib.Path):
    """El contrato ya parseado, o None si no se pudo leer.

    None no se resuelve a favor: un `no aplica` que no se puede confirmar
    contra el contrato se rechaza igual que uno mal declarado.
    """
    try:
        return contrato.cargar(contrato_md)
    except Exception:
        return None


def _aplicar_no_aplica(puerta: Puerta, stdout: str, datos_contrato) -> None:
    """Acepta `no aplica` solo si sale de un hecho del contrato, y es cierto.

    `estado_de_sumision` --y `calcular_todo_verde` con ella-- trata `no-aplica`
    como equivalente a pasado, asi que el dia que un validador lo emitiera por
    ausencia de insumo en vez de por un hecho del contrato seria un pase libre.
    Hasta ahora lo unico que lo impedia era el buen criterio de la unica linea
    que lo emite.

    Comprobar el hecho contra el contrato --y no solo exigir que se declare--
    es lo que atrapa la forma peligrosa: la excusa bien escrita y FALSA,
    impresa desde dentro de un `if not bundles:`.
    """
    reclamo, rechazo = contrato.buscar_no_aplica(stdout)
    if rechazo:
        puerta.estado, puerta.evidencia = "rojo", rechazo
        return
    if reclamo is None:
        return
    if datos_contrato is None:
        puerta.estado = "rojo"
        puerta.evidencia = (
            f"declara NO APLICA por `{reclamo.clave} = {reclamo.valor}` y no se pudo leer "
            f"el contrato para confirmarlo"
        )
        return
    real = contrato.hecho_del_contrato(datos_contrato, reclamo.clave)
    if real != reclamo.valor:
        puerta.estado = "rojo"
        puerta.evidencia = (
            f"declara NO APLICA por `{reclamo.clave} = {reclamo.valor}`, pero el contrato "
            f"dice `{real}`: un «no aplica» se deriva de un hecho del contrato, nunca de "
            f"una ausencia de insumo"
        )
        return
    puerta.estado = "no-aplica"
    # Y la fila publica EL MOTIVO DECLARADO, no la ultima linea de la salida.
    # Los tres caminos de rechazo de aqui arriba si escriben su porque; el de
    # aceptacion se quedaba con la evidencia generica que `_evidencia` habia
    # puesto --«0 hallazgos (0 errores)»--, que es indistinguible de la de una
    # puerta que SI verifico. El unico estado que equivale a pasado sin haber
    # mirado nada era, ademas, el unico que no decia por que.
    # Los AVISOS que `_evidencia` ya habia recogido viajan igual: la regla de
    # este fichero es «un AVISO viaja SIEMPRE, aunque la puerta salga verde», y
    # sobrescribir sin condicion la rompia para el unico estado que equivale a
    # pasado sin haber mirado. Hoy no es alcanzable --el unico emisor de
    # `linea_no_aplica` corta antes de poder emitir un aviso-- pero R-B05 esta a
    # un `return` de coexistir, y la corrección no cuesta nada.
    previos = [t for t in (puerta.evidencia or "").split(" · ") if contrato.PREFIJO_AVISO in t]
    puerta.evidencia = " · ".join(
        [f"no aplica: `{reclamo.clave} = {reclamo.valor}` — {reclamo.motivo}", *previos]
    )


def _insumo(stdout: str) -> str:
    """La linea `INSUMO …` que declara cuantas unidades analizo la puerta.

    Un validador que no la emita deja la celda vacia, y eso tambien se ve: la
    propiedad se exige a toda pieza que pueda reportar exito.
    """
    for linea in (stdout or "").splitlines():
        if linea.startswith(contrato.PREFIJO_INSUMO):
            return linea.strip()
    return ""


def _evidencia(stdout: str, stderr: str, estado: str) -> str:
    """La linea que representa el resultado, no la ultima que se imprimio.

    Una puerta roja se certificaba con una evidencia que parecia un exito:
    `verificar_superficie` imprime «Inventario escrito…» DESPUES de sus lineas
    ERROR, y la evidencia era la ultima linea de stdout. Cuando la puerta esta
    en rojo, la evidencia tiene que ser el motivo del rojo.

    `[-1:][0]` sobre una lista vacia lanza IndexError: una salida de solo
    espacios en blanco tumbaria el orquestador entero al emitir el certificado,
    que es el peor momento posible para caerse.
    """
    lineas = (stdout or stderr or "").strip().splitlines()
    if not lineas:
        return "sin salida"
    if estado == "rojo":
        motivos = [
            l for l in lineas if l.lstrip().startswith(contrato.PREFIJOS_DE_FALLO)
        ]
        if motivos:
            sufijo = f" (+{len(motivos) - 1} más)" if len(motivos) > 1 else ""
            return motivos[0].strip() + sufijo
    # Un AVISO viaja SIEMPRE, aunque la puerta salga verde. El caso que lo
    # motiva: sin el indice de tipos, `verificar_superficie` conmuta a una red
    # gruesa de seis prefijos de paquete --que por diseno «deja pasar clases no
    # documentadas»-- e imprime su aviso. Pero lo imprime ANTES del resumen, y
    # como la evidencia de una puerta verde era la ultima linea, el certificado
    # mostraba «Inventario de API escrito...» y nada mas: una validacion mucho
    # mas laxa, indistinguible de una completa. El codigo creia declararlo
    # («eso se DECLARA en el certificado», decia su comentario) y no llegaba.
    avisos = [l.strip() for l in lineas if l.lstrip().startswith(contrato.PREFIJO_AVISO)]
    if avisos:
        return " · ".join(avisos + [lineas[-1].strip()])
    return lineas[-1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raiz", nargs="?", default=".")
    # Sin `default`: el defecto lo aplica `_resolver_perfil`, que es quien
    # escribe la nota y necesita distinguir «se pidio estandar» de «no se
    # pidio nada». Argparse rellenandolo borraba esa diferencia.
    # `choices` para que una errata muera aqui, con el mensaje de argparse
    # nombrando los dos validos, en vez de llegar a `_resolver_perfil`. Alli
    # tambien se comprueba --hay llamadores que no pasan por esta CLI-- pero
    # fallar pronto y claro ahorra leer un certificado entero para descubrir
    # que se escribio `rigoroso`.
    parser.add_argument(
        "perfil", nargs="?", default=None, choices=sorted(contrato.PERFILES)
    )
    parser.add_argument(
        "--salida-build", dest="salida_build", default=None,
        help=f"log de `./gradlew build`; por defecto {sb.RUTA_POR_DEFECTO.as_posix()} "
             f"dentro del proyecto",
    )
    parser.add_argument(
        "--codigo-build", dest="codigo_build", type=int, default=None,
        help="codigo de salida de `./gradlew build`; si contradice al log, la evidencia "
             "se declara corrupta y no se resuelve a favor",
    )
    args = parser.parse_args()

    raiz = pathlib.Path(args.raiz)

    # LA RAIZ SE COMPRUEBA ANTES DE ESCRIBIR NADA.
    #
    # Hasta el ciclo 12, una raiz inexistente --una errata en la ruta, lo mas
    # facil que hay de teclear-- producia esto: `destino.parent.mkdir(parents=
    # True)` mas abajo CREABA `<raiz>/docs/` y dejaba dentro un certificado
    # entero, ocho mil caracteres, sobre un proyecto que no existe. Las diez
    # filas salian rojas, asi que no era un verde vacuo; era peor de leer: un
    # documento con la forma de un veredicto cuyo verdadero contenido es «te
    # equivocaste de ruta», dicho en diez FileNotFoundError distintos. Y de
    # regalo, un directorio nuevo en el sitio equivocado.
    #
    # Codigo 2, no 1: `1` significa «hay filas rojas», que es un desenlace
    # legitimo de una verificacion que SI ocurrio. Aqui no ocurrio ninguna.
    # Confundirlos haria que un guion que reintenta ante el 1 reintentase
    # eternamente sobre una ruta que nunca va a existir.
    #
    # Se comprueba en `main` y no en `ejecutar`. NO porque `ejecutar` no
    # escriba --si escribe: la capa 2 deja el inventario del dossier en
    # `build/reports/`, con su `mkdir`, dentro de la raiz
    # (`verificar_superficie.py:161-162`)-- sino por lo que hace cada una.
    # `ejecutar` VERIFICA un proyecto y devuelve el certificado; escribe donde
    # el proyecto ya esta, y tiene llamadores legitimos sobre arboles a medio
    # montar. `main` recibe la ORDEN DEL USUARIO, y una orden que apunta a
    # ninguna parte se rechaza entera antes de empezar: es el unico sitio donde
    # «esta ruta no es un proyecto» se puede decir sin haber tocado nada.
    if not raiz.is_dir():
        que = "no existe" if not raiz.exists() else "no es un directorio"
        print(
            f"verificar_todo: la raiz del proyecto {que}: {raiz}\n"
            f"No se ha escrito ningun certificado ni creado ningun directorio. "
            f"Comprueba la ruta y vuelve a ejecutar.",
            file=sys.stderr,
        )
        return 2

    perfil = args.perfil
    cert = ejecutar(
        raiz,
        perfil,
        pathlib.Path(args.salida_build) if args.salida_build else None,
        args.codigo_build,
    )
    destino = raiz / "docs" / "CERTIFICADO.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    # Se renderiza UNA vez: el fichero que se escribe y lo que se imprime tienen
    # que ser byte a byte lo mismo, y con dos llamadas eso era una coincidencia
    # que nadie sostenia --`render_markdown` recalcula `estado_de_sumision` en
    # cada invocacion--.
    markdown = render_markdown(cert)
    destino.write_text(markdown, encoding="utf-8")
    print(markdown)
    hay_rojas = any(
        p.estado == "rojo" and p.nombre not in {n for n, _ in PUERTAS_NUNCA_VERIFICABLES}
        for p in cert.puertas
    )
    return 1 if hay_rojas else 0


if __name__ == "__main__":
    raise SystemExit(main())
