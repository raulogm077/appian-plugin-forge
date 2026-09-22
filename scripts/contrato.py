"""Esquema del contrato y puerta determinista de la entrevista (spec §6.2).

El contrato es un Markdown con un bloque ```toml. Markdown porque lo lee una
persona; TOML porque tomllib esta en la biblioteca estandar desde Python 3.11
y la restriccion global prohibe dependencias externas.
"""

from __future__ import annotations

import dataclasses
import pathlib
import re
import tomllib
import xml.etree.ElementTree as ET

TIPOS_VALIDOS = {"function", "writer-function", "smart-service", "servlet"}
REQUIRED_VALIDOS = {"ALWAYS", "OPTIONAL"}
PERFILES = {"estandar", "riguroso"}

# Los tipos que cargan un bundle de recursos. `bundle.nombre` alimenta DOS
# cosas a la vez —la key del modulo en el manifiesto y el nombre base del
# `.properties`—, asi que dejarlo pasar vacio producia `<smart-service key=""
# …/>` y un fichero llamado `_en_US.properties`, y las cuatro puertas decian
# que si: `verificar_bundles` derivaba la ruta esperada del MISMO dato vacio.
# El oraculo lo zanja: el plug-in publicado en el AppMarket declara
# `key="readEmailFile"`.
#
# El servlet queda fuera: su name/description van como atributos del
# manifiesto, no en un `.properties` (nota de alcance de la capa 1C en
# assets/reglas-de-validacion.md), y su key de modulo sale del artefacto.
TIPOS_CON_BUNDLE = {"function", "writer-function", "smart-service"}

# EL SUBPAQUETE DEL DOMINIO, por convenio y en un solo sitio.
#
# D19 (spec §5.6) dice que el dominio no conoce el SDK, y eso es lo que permite
# que los tests JUnit --lo mas parecido a una ejecucion real de que se dispone--
# corran sin cargar el SDK. `verificar_superficie.comprobar_dominio_sin_sdk` lo
# comprueba desde el principio... y hasta el ciclo 6 NO TENIA LLAMADOR VIVO: el
# orquestador invocaba el script sin pasarle ningun paquete de dominio, asi que
# el bucle hacia `continue` en toda clase y la funcion devolvia `[]` SIEMPRE.
# Tenia tests unitarios y ninguna ejecucion real que la disparara.
#
# El convenio vive aqui porque tiene dos lados: la SKILL manda poner la logica
# en este subpaquete (paso 4) y el escaner comprueba ahi que no se cuele el SDK.
# Sin un nombre acordado, el que escribe y el que juzga no pueden encontrarse.
#
# ALCANCE, dicho para que la celda del certificado no se lea de mas: es el
# convenio de los plug-ins que ESTE forge genera. Un plug-in construido a mano
# con otros nombres --el oraculo EML reparte su dominio en `parser`, `service`,
# `model` y `util`-- declarara `0 clases de dominio`, y eso es cierto: por este
# convenio no tiene ninguna. No se define el dominio como «todo lo que no es el
# adaptador» porque el propio EML lo desmiente: su paquete `appian` toca el SDK
# a proposito, y esa definicion lo acusaria en falso.
SUBPAQUETE_DOMINIO = "dominio"


def paquete_de_dominio(datos: dict) -> str:
    """`com.raul.appian.ejemplo` -> `com.raul.appian.ejemplo.dominio`.

    Cadena vacia si el contrato no declara paquete, y el llamador tiene que
    filtrarla. Antes devolvia `.dominio` a secas, un prefijo que ninguna clase
    casa nunca: la comprobacion D19 recorria las clases, no encontraba dominio
    y aprobaba: cero, mudo e indistinguible de «este proyecto no usa el
    convenio». Un contrato sin paquete ya sale rojo por la capa 1; lo que no
    puede es ademas apagar una regla en silencio.
    """
    paquete = seccion(datos, "plugin").get("paquete", "")
    return f"{paquete}.{SUBPAQUETE_DOMINIO}" if paquete else ""


def seccion(datos: dict, nombre: str) -> dict:
    """La seccion `[nombre]` del contrato, o `{}` si no es una tabla.

    Existe porque el `datos.get(<nombre>, {})` que habia antes repone el
    defecto SOLO cuando la clave falta: con `plugin = "smart-service"` --o con
    `[[plugin]]`, que TOML
    convierte en lista-- el `.get` encadenado de detras estalla sobre un `str`
    y se lleva por delante a quien lo llamo. El gate del ciclo 11 lo midio en
    el peor sitio posible: `verificar_todo.ejecutar()` moria en
    `paquete_de_dominio` UNA LINEA DESPUES de la guarda que `_resolver_perfil`
    acababa de poner para ese mismo caso, y no emitia certificado -- que es
    peor que cualquier fila roja, porque no queda documento que leer.

    La guarda vive AQUI, en el modulo que posee la forma del contrato, y no en
    cada llamador: eran veinte accesos encadenados con el mismo modo de fallo,
    y ponerla en uno solo era arreglar la instancia y dejar la clase.

    Que un contrato mal formado se lea como vacio NO lo esconde: la puerta
    determinista (`validar`) lo rechaza con su propia linea `FALTA`, y las
    filas que dependan de la seccion saldran en rojo por falta de dato. Lo que
    esto evita no es el rojo, es la traza sin certificado.
    """
    valor = datos.get(nombre)
    return valor if isinstance(valor, dict) else {}


# Tipos que se pueden escribir SUELTOS en el contrato. El `tipo_java` se emite
# al `.java` tal cual, y la plantilla no lleva imports: todo lo que no sea de
# `java.lang` necesitaba venir cualificado, y nadie lo comprobaba — el fallo
# aparecia en `javac`, no en la puerta. Le paso al oraculo del propio
# repositorio: las nueve salidas `Timestamp` del EML salian sin import.
TIPOS_JAVA_LANG = frozenset({
    "byte", "short", "int", "long", "float", "double", "boolean", "char",
    "String", "Boolean", "Long", "Integer", "Double", "Float", "Short", "Byte",
    "Character", "Number", "Object",
})

# Un nombre de tipo Java: identificadores separados por puntos. Sin parentesis,
# sin espacios, sin comas y sin `<>` —los genericos no los infiere Appian, y
# ningun contrato canonico los usa—. Lo que esto ataja no es un tipo raro: es
# una CADENA QUE NO ES UN TIPO colandose hasta el `.java` (ver
# `tipo_java_emitible`).
PATRON_NOMBRE_TIPO_JAVA = re.compile(
    r"[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*"
)

# Los dos alias que la auditoria bendice expresamente para fechas: R-F04
# rechaza `java.util.Date` y manda usar `java.sql.Date`/`Time`/`Timestamp`.
# Se resuelven aqui para que el contrato pueda escribir `Timestamp` a secas,
# que es como lo escribe cualquiera, sin que el `.java` salga roto.
ALIAS_JAVA_SQL = {"Timestamp": "java.sql.Timestamp", "Time": "java.sql.Time"}

# Las dos salidas que la plantilla de smart service ya hornea: campo, getter y
# el manejo de errores que las rellena. Declararlas en el contrato NO es un
# error —el plug-in aprobado del AppMarket las declara— pero el andamiador no
# debe emitirlas dos veces: se mapean sobre las horneadas, y para eso el tipo
# tiene que coincidir. Con otro tipo si es una colision, y la detecta R-F03.
SALIDAS_HORNEADAS = {"ErrorOccurred": "Boolean", "ErrorMessage": "String"}

# La marca que TODAS las plantillas dejan en el cuerpo sin implementar. Vive
# aqui, y no en cada plantilla por su cuenta, porque plantilla y validador se
# tienen que mirar en el mismo espejo: si divergen, R-F13 deja de disparar y
# nadie se entera. Es la costura de la que nacen los defectos de este proyecto.
#
# Cada plantilla la escribe dentro de un `UnsupportedOperationException`, asi
# que la cadena llega al *constant pool* y el escaner de bytecode la ve.
#
# NO hay una constante «Pendiente» suelta al lado, y se quito a proposito: la
# habia, sin un solo uso, y era peor que muerta. Parecia la canonica y es
# subcadena de dos de las tres marcas reales, asi que quien la usara creeria
# estar comprobando lo mismo que R-F13 comprobando bastante menos.
MARCAS_SIN_IMPLEMENTAR = (
    "sin implementar: ver docs/contrato.md",   # smart-service
    "Pendiente: delegar en el dominio",        # function y servlet
    "Pendiente: devolver el Writer del dominio",  # writer-function
)


# El tamano del insumo que una puerta analizo, declarado junto a su resultado.
#
# La familia del «verde vacuo» lleva cinco instancias, y las guardas se habian
# ido anadiendo UNA A UNA segun se descubrian. Cero clases, cero tipos, cero
# claves esperadas y cero dependencias son EL MISMO SINTOMA: un exito sobre
# nada. Esto lo convierte de guarda reactiva en propiedad exigida a toda pieza
# que pueda reportar exito — el certificado ya tenia donde ponerlo.
PREFIJO_INSUMO = "INSUMO"

# Una capa que no aplica a este tipo de plug-in no es un aprobado. Sin esto,
# la capa 1C salia VERDE en todos los servlets habiendo mirado cero bundles y
# cero claves: verde vacuo legitimo, pero verde vacuo.
MARCA_NO_APLICA = "NO APLICA"

# LA REGLA, y esta escrita aqui porque este es el unico sitio por el que se
# puede emitir el estado:
#
#     «NO APLICA» SE DERIVA DE UN HECHO DECLARADO EN EL CONTRATO,
#     NUNCA DE UNA AUSENCIA DE INSUMO.
#
# Toda la diferencia esta ahi. `plugin.tipo == "servlet"` es un hecho: los
# servlets declaran name/description como atributos del manifiesto y no cargan
# ningun `.properties`, asi que no hay nada que comprobar. «No encontre ningun
# bundle», en cambio, es una ausencia de insumo, y un `no aplica` derivado de
# una ausencia seria otra instancia del verde vacuo con nombre nuevo —
# `estado_de_sumision`, que es quien decide, acepta `no-aplica` como
# equivalente a pasado.
#
# Por eso la marca lleva el hecho DENTRO, y el orquestador lo comprueba contra
# el contrato real antes de aceptarla. Declarar un hecho falso no cuela: es
# justo la forma que tendria la excusa escrita desde dentro de un `if not
# bundles:`.
SEPARADOR_NO_APLICA = " -- "
PATRON_NO_APLICA = re.compile(
    rf"^{MARCA_NO_APLICA} porque ([\w.]+) = (\S+){SEPARADOR_NO_APLICA}(.+)$"
)


@dataclasses.dataclass(frozen=True)
class ReclamoNoAplica:
    """Un validador diciendo de que hecho del contrato deriva su `no aplica`."""

    clave: str
    valor: str
    motivo: str


def linea_no_aplica(clave: str, valor: str, motivo: str) -> str:
    """`NO APLICA porque plugin.tipo = servlet -- los servlets no cargan bundle`.

    La unica via sancionada para emitir el estado. Si al escribir esto no
    sabes que par clave/valor del contrato poner, la respuesta no es inventar
    uno: es que esta capa SI aplica y lo que tienes es un insumo vacio.
    """
    return f"{MARCA_NO_APLICA} porque {clave} = {valor}{SEPARADOR_NO_APLICA}{motivo}"


def buscar_no_aplica(stdout: str) -> tuple[ReclamoNoAplica | None, str]:
    """`(reclamo, motivo_de_rechazo)` sobre la salida de un validador.

    `(None, "")` es el caso corriente: no se reclamo nada. Ausencia y
    malformacion son cosas distintas, y solo la segunda es un error.
    """
    for linea in (stdout or "").splitlines():
        if not linea.startswith(MARCA_NO_APLICA):
            continue
        m = PATRON_NO_APLICA.match(linea.strip())
        if not m:
            return None, (
                f"declara «{MARCA_NO_APLICA}» sin decir de que hecho del contrato lo "
                f"deriva; un «no aplica» sale de un hecho declarado, nunca de una "
                f"ausencia de insumo: {linea.strip()}"
            )
        return ReclamoNoAplica(m.group(1), m.group(2), m.group(3)), ""
    return None, ""


def hecho_del_contrato(datos: dict, clave: str) -> str | None:
    """El valor de una clave con puntos —`plugin.tipo`— sobre el contrato."""
    actual: object = datos
    for parte in clave.split("."):
        if not isinstance(actual, dict) or parte not in actual:
            return None
        actual = actual[parte]
    return None if isinstance(actual, (dict, list)) else str(actual)


# La unidad PORTANTE: la que a cero significa «no se verifico nada».
#
# La regla de «todas las unidades a cero» caza 2 de las 6 instancias conocidas
# y falla en la mas cara --el escaner ciego a las anotaciones-- porque alli
# habia una clase. La forma real del fallo nunca fue «todo a cero»: fue CERO EN
# LA DIMENSION QUE IMPORTABA, con las demas sanas. `30 clases, 0 tipos de
# appian` es un escaner roto y la regla vieja lo daba por bueno.
#
# Se declara solo donde la portante es clara y defendible. Donde cero es
# legitimo --dependencias de terceros, entradas y salidas de un contrato-- NO
# se marca ninguna: inventar una portante crearia una alarma que salta siempre,
# y una alarma que salta siempre ensena a ignorarla.
SUFIJO_PORTANTE = " · portante: "


def linea_de_insumo(portante: str | None = None, **unidades: int) -> str:
    """`INSUMO 30 clases, 19 tipos de appian`, para que la lea el orquestador.

    `portante` nombra la unidad cuyo cero basta para marcar el insumo. Se
    valida al emitir: una portante mal escrita degradaria en silencio a la
    regla vieja, y la puerta se creeria protegida sin estarlo.
    """
    if portante is not None and portante not in unidades:
        raise ValueError(
            f"la unidad portante «{portante}» no esta entre las declaradas: "
            f"{sorted(unidades)}"
        )
    partes = ", ".join(f"{n} {nombre.replace('_', ' ')}" for nombre, n in unidades.items())
    sufijo = f"{SUFIJO_PORTANTE}{portante.replace('_', ' ')}" if portante else ""
    return f"{PREFIJO_INSUMO} {partes}{sufijo}"


def insumo_vacio(linea: str) -> bool:
    """Si no se analizo nada, medido en la unidad que lo decide.

    Con portante declarada manda ella sola. Sin portante, la regla de siempre:
    todas las unidades a cero. Basta con que una sea distinta de cero para que
    la puerta haya mirado algo real —un contrato sin salidas es legitimo, un
    proyecto sin clases no—.
    """
    if not linea:
        return False
    cuerpo, _, portante = linea.partition(SUFIJO_PORTANTE)
    cuentas = _cuentas_declaradas(cuerpo)
    if portante:
        # Una portante que no figura entre las cuentas es una linea corrupta, y
        # no poder medirlo se resuelve en contra, no a favor.
        return cuentas.get(portante.strip(), 0) == 0
    return bool(cuentas) and all(n == 0 for n in cuentas.values())


def _cuentas_declaradas(cuerpo: str) -> dict[str, int]:
    """`INSUMO 30 clases, 0 tipos de appian` -> `{'clases': 30, ...}`."""
    cuentas: dict[str, int] = {}
    for parte in cuerpo[len(PREFIJO_INSUMO):].split(","):
        m = re.match(r"\s*(\d+)\s+(.+?)\s*$", parte)
        if m:
            cuentas[m.group(2)] = int(m.group(1))
    return cuentas


def identificador_java(nombre: str) -> str:
    """El nombre del CAMPO Java para un input/output del contrato.

    Los nombres de input y output de Appian son PascalCase —asi los declara el
    plug-in aprobado del AppMarket— y usarlos verbatim como nombre de campo
    hacia que SpotBugs marcara `Nm` en cada uno («should be lowerCamelCase») y
    `./gradlew build` no llegara a BUILD SUCCESSFUL.

    Son dos cosas distintas, y el plug-in aprobado las separa: Appian ve el
    nombre a traves del ACCESOR (`getSourceDocument()` -> output
    `SourceDocument`), nunca del campo. Comprobado en su
    `ReadEmailFileSmartService.java`: `private Long sourceDocument;` con
    `setSourceDocument(...)`, y `@Order({"SourceDocument", …})`.

    Asi que el campo se pone en lowerCamelCase y el accesor, `@Order` y las
    claves de bundle conservan el nombre del contrato — que es el unico que
    Appian lee.
    """
    if not nombre:
        return nombre
    return nombre[0].lower() + nombre[1:]


# Que cuenta como «no ASCII», definido UNA vez para los dos lados. `andamiar`
# escapa lo que casa esto; `verificar_bundles` levanta R-B05 sobre lo que casa
# esto. Cuando cada lado traia su propia definicion, el espejo que el comentario
# de abajo invoca no existia: eran dos piezas que coincidian por suerte.
# LAS PALETAS QUE EXISTEN, y por que la lista vive aqui y no en el andamiador.
#
# `clase.paleta` NO es `paletteCategory`. Son dos niveles distintos y
# confundirlos costo un hallazgo [alta] del gate del ciclo 3: los cuatro valores
# de R-F01 (`Workflow`, `Automation Smart Services`, `Deprecated Services`,
# `Hidden`) son categorias de paleta, mientras que esto son SUBPALETAS, y de
# aquellos cuatro solo `Workflow` es ademas una subpaleta real.
#
# El mapa es CERRADO y solo emite anotaciones de la familia segura: quince de
# las treinta y dos anotaciones de conveniencia del SDK hornean una categoria
# que Appian remapea en silencio (ver R-F01b en verificar_framework.py).
#
# Vive en `contrato` porque hay dos lados: `validar` RECHAZA lo que no este
# aqui, y `andamiar` TRADUCE lo que si esta. Mientras la lista fue privada del
# andamiador, un valor desconocido caia al repuesto SIN AVISO y el plug-in
# certificaba READY en una paleta distinta de la pedida — el fallo silencioso
# que R-F01 existe para impedir, entrando por otra puerta.
# LA TABLA SALE DE `javap -v` SOBRE EL JAR DEL SDK 26.3, no de ningun mapa
# preexistente. La primera version de esta lista se construyo copiando el mapa
# que ya vivia en `andamiar.py`, y ese mapa estaba mal por dos sitios: metia
# `Workflow` --que es una CATEGORIA, no una subpaleta-- y se dejaba fuera cinco
# subpaletas reales. Un contrato con `paleta = "Workflow"` pasaba la puerta y
# aterrizaba en `Activities`, que es la traduccion silenciosa que esta pieza
# existe para impedir; y `Human Tasks`, el smart service mas corriente que hay,
# se rechazaba con el mensaje «no es una subpaleta de Appian», que es falso.
# El CLAUDE.md del proyecto lo dice y aqui costo dos gates aprenderlo: para un
# nombre admitido, `javap` o la documentacion, nunca una fuente de segunda mano
# --y el mapa del propio repositorio es de segunda mano--.
#
# Son las 17 anotaciones de `com.appiancorp.suiteapi.process.palette` cuya
# `paletteCategory` es una de las cuatro validas en 26.x. Las otras 15 hornean
# una categoria que Appian remapea en silencio (R-F01b), y por eso NO estan.
#
# OJO, la traduccion NO es derivable del nombre: para casi cada subpaleta
# existen DOS anotaciones, una segura y otra que hornea una categoria
# remapeada. `Analytics` es el caso mas claro --`AutomationSmartServicesAnalitycs`
# (con la errata del SDK en el nombre de la clase) es la buena; la escueta
# `Analytics` hornea «Appian Smart Services» y ademas esta `@Deprecated`--.
# Por eso el mapa es explicito y no un `"Automation" + nombre`.
ANOTACION_POR_PALETA = {
    # paletteCategory = "Automation Smart Services" (12)
    "Analytics": "AutomationSmartServicesAnalitycs",
    "Business Rules": "AutomationSmartServicesBusinessRules",
    "Communication": "AutomationSmartServicesCommunication",
    "Data Services": "AutomationSmartServicesDataServices",
    "Document Generation": "AutomationSmartServicesDocumentGeneration",
    "Document Management": "AutomationSmartServicesDocumentManagement",
    "Identity Management": "AutomationSmartServicesIdentityManagement",
    "Integration & APIs": "AutomationSmartServicesIntegrationAPIs",
    "Process Management": "AutomationSmartServicesProcessManagement",
    "Robotic Processes": "AutomationSmartServicesRoboticProcesses",
    "Social": "AutomationSmartServicesSocial",
    "Test Management": "AutomationSmartServicesTestManagement",
    # paletteCategory = "Workflow" (4). `Workflow` NO es una clave: es la
    # categoria de estas cuatro, y la subpaleta de `WorkflowActivities` se
    # llama `Activities`.
    "Activities": "WorkflowActivities",
    "Events": "WorkflowEvents",
    "Gateways": "WorkflowGateways",
    "Human Tasks": "WorkflowHumanTasks",
    # paletteCategory = "Deprecated Services" (1). Valida para Appian, asi que
    # la puerta la acepta; la entrevista no la propone, que es otra cosa.
    "Forum Management": "ForumManagement",
}
# Solo para el caso en que no haya paleta que traducir --los tipos que no son
# smart-service, donde el campo no pinta nada y el valor se calcula y se tira--.
# Con `validar` delante, una paleta desconocida ya no llega hasta aqui.
ANOTACION_POR_DEFECTO = "AutomationSmartServicesIntegrationAPIs"

# Las cuatro CATEGORIAS validas en 26.x (R-F01). No se escriben en el contrato:
# estan aqui para poder decirle a quien confunda los dos niveles --que es el
# error que costo dos gates-- en cual se ha equivocado, en vez de soltarle la
# lista de 17 y que lo adivine.
CATEGORIAS_DE_PALETA = {
    "Workflow": ("Activities", "Events", "Gateways", "Human Tasks"),
    "Automation Smart Services": (),
    "Deprecated Services": ("Forum Management",),
    "Hidden": (),
}


def _pista_de_paleta(valor: str) -> str:
    """Por que ese valor no vale, dicho en los terminos de quien lo escribio."""
    if valor in CATEGORIAS_DE_PALETA:
        subpaletas = CATEGORIAS_DE_PALETA[valor]
        dentro = (
            f" Las subpaletas de esa categoria son {list(subpaletas)}."
            if subpaletas else
            " Sus subpaletas se nombran una a una; ninguna se llama como ella."
        )
        return (
            f"«{valor}» es una CATEGORIA de paleta (`paletteCategory`, el nivel de R-F01), "
            f"no una subpaleta, y en el contrato va la subpaleta.{dentro}"
        )
    return f"«{valor}» no es ninguna subpaleta de Appian 26.3."

PATRON_NO_ASCII = re.compile(r"[^\x00-\x7F]")

# Y QUE FICHERO cae bajo R-B05, que es la otra mitad de la misma regla. Estaba
# duplicada en dos formulaciones que no son equivalentes: el andamiador miraba
# el sufijo del nombre; el validador, que la ruta no fuera la del `_en_US`
# esperado. Coincidian solo sobre los ficheros que el forge emite -- un segundo
# `_en_US.properties` en otra ruta lo juzgaba el validador y el andamiador no lo
# escapaba nunca. Compartir el patron de no-ASCII y dejar el alcance duplicado
# arregla la mitad visible y deja creer que estan las dos.
#
# Hoy los dos lados miran TODOS los `.properties`, `en_US` incluido. Y conviene
# decir como se llego, porque el atajo cuesta: se cambio este predicado creyendo
# que ahi vivia la exencion, y se escribio que emisor y juez ya eran simetricos.
# Era falso. En el juez este predicado es SIEMPRE cierto --los bundles le llegan
# de un `rglob("*.properties")`-- y el alcance de verdad lo fijaba un `continue`
# treinta lineas mas arriba, que descartaba el `en_US` canonico. Un predicado
# compartido no hace simetrica una comprobacion si cada lado la evalua sobre un
# conjunto distinto: la simetria se comprueba con un caso, no con un nombre.


def es_bundle(ruta_o_nombre: str) -> bool:
    """Un `.properties` de locale, EL QUE SEA, incluido `en_US`.

    Este es el alcance del escapado, y es de EXTENSION, no de locale. Dos
    ciclos seguidos se equivoco aqui en direcciones opuestas: primero se eximia
    a `en_US` --que es justo el fichero cuyo mojibake ve un usuario, porque es
    de donde Appian saca los textos de display--, y al quitar aquella guarda se
    quito la condicion ENTERA, con lo que el escapado cayo sobre
    `appian-plugin.xml`, `THIRD_PARTY_NOTICES.md`, los `.java` y el
    `exclude.xml`. `\\uXXXX` solo significa algo en un `.properties`: en un XML
    o en un Markdown es texto literal, o sea el mismo mojibake por el otro
    extremo. Levantado por el /code-review posterior al ciclo 16.
    """
    return ruta_o_nombre.endswith(".properties")


# `es_bundle_traducido` vivia aqui y se ha ido: al pasar el escapado a mirar la
# extension se quedo sin un solo llamador en todo el repositorio, tests
# incluidos. Su docstring alegaba que «hay reglas que si dependen del locale»,
# y es cierto —R-B01 y R-B04— pero esas usan las constantes locales de
# `verificar_bundles`, no este predicado. Un predicado publico sin llamador en
# el vocabulario que comparten emisor y juez no es codigo muerto inocuo: invita
# a creer que alguien lo aplica. Levantado por el gate del ciclo 17.


# EL CONVENIO DE CLAVES DEL BUNDLE, en un solo sitio para sus dos lados.
#
# Appian usa dos convenios distintos --`input.<N>.displayName`/`.comment` y
# `output.<N>.…` en smart services; `function.<f>.description` y
# `function.<f>.param.<p>.description` en functions-- y confundirlos es el error
# de la guia que R-B02 existe para atrapar. Aqui no se juzga cual toca: aqui se
# CONSTRUYE la cadena, para que el que emite el bundle (`andamiar`) y el que lo
# juzga (`verificar_bundles`, R-B03/R-B06) no puedan escribirla distinta.
#
# Estaba a mano en tres sitios, y esta familia ya se cobro dos piezas: el
# `function..description` con doble punto que nacio de dos fallbacks (ver
# `nombre_funcion`) y el `output.errorOccurred` en minuscula que hizo falta
# inventar R-B06 para ver. Un literal repetido no es un detalle de estilo
# cuando el que lo escribe y el que lo lee tienen que coincidir exactamente.
#
# Con una excepcion declarada: `clave_de_funcion` tiene UN solo lado, el juez.
# En functions la clave la escribe la propia plantilla como literal
# (`function.{{FUNCION}}.description` en los dos `bundle_*.properties.tmpl`),
# no el andamiador, asi que no hay emisor que enganchar aqui sin pasar tambien
# esa clave a variable. Se deja dicho para que no se lea como un olvido.
def nombre_de_acp(nombre: str) -> str:
    """El nombre con el que Appian publica una entrada o salida de smart service.

    NO es el nombre del campo Java: es el del ACCESOR sin su `set`/`get`, y por
    eso empieza en mayuscula aunque el campo sea `documentoOrigen`. Un `String
    documentoOrigen` genera `setDocumentoOrigen`, y Appian lo publica como
    `DocumentoOrigen`.

    Tres fuentes lo sostienen. *Smart Service Plug-ins > Internationalization*:
    «`InputName` and `OutputName` are the camelCase names (or `@Name` annotated
    names) of the targets of the getter and setter methods (after removing the
    prepended `get-` or `set-`)». La misma pagina, al describir el nombre que
    Appian se inventa cuando la clave no esta: «For example: `MySmartServiceInput`
    is rendered as **My Smart Service Input**» --su propio ejemplo de nombre ACP
    empieza en mayuscula--. Y el plug-in de referencia, aprobado y desplegado,
    escribe `input.SourceDocument.displayName` para su `setSourceDocument`.

    Capitalizar aqui y no pedirselo al contrato es deliberado: `documentoOrigen`
    es lo que un programador escribe sin pensar, y antes de esto el bundle salia
    con `input.documentoOrigen` --una clave que Appian no resuelve nunca--. No
    rompe el despliegue: la misma pagina dice que entonces el display name «is
    rendered automatically», asi que lo que se pierde en silencio es la
    descripcion que la entrevista se molesto en redactar y el tooltip entero.

    `capitalize()` no vale: pone en minuscula todo lo demas y `CsvContent` se
    volveria `Csvcontent`.
    """
    return nombre[:1].upper() + nombre[1:]


def claves_de_entrada(nombre: str) -> tuple[str, str]:
    acp = nombre_de_acp(nombre)
    return f"input.{acp}.displayName", f"input.{acp}.comment"


def claves_de_salida(nombre: str) -> tuple[str, str]:
    acp = nombre_de_acp(nombre)
    return f"output.{acp}.displayName", f"output.{acp}.comment"


def clave_de_funcion(funcion: str) -> str:
    return f"function.{funcion}.description"


def clave_de_parametro(funcion: str, parametro: str) -> str:
    return f"function.{funcion}.param.{parametro}.description"


# EL OTRO CONVENIO QUE COMPARTEN EMISOR Y JUEZ: donde vive el bundle de un
# MODULO, y como se llama.
#
# Appian resuelve el bundle de cada modulo como `<key del plug-in>.<key del
# modulo>`, asi que el fichero se llama como la key del MODULO --no como el
# plug-in, ni como la funcion-- y vive en la carpeta que sale de cambiar los
# puntos de la key del plug-in por separadores. Sin el `_en_US`, el plug-in
# NO DESPLIEGA, y el mensaje del servidor nombra el modulo culpable:
#
#   The Plug-in <key> Module <key del modulo> is missing the following
#   internationalization bundle(s) for Locale en_US: [<key>.<key del modulo>]
#   (APNX-1-4200-000)
#
# Que son DOS cosas ligadas y no una sola ya estaba escrito arriba, en
# TIPOS_CON_BUNDLE --«bundle.nombre alimenta DOS cosas a la vez: la key del
# modulo en el manifiesto y el nombre base del .properties»--; lo que faltaba
# era que alguien lo comprobara sobre el manifiesto de verdad. Un manifiesto
# con varios modulos necesita un bundle por modulo, y eso el contrato no puede
# decirlo: solo el XML sabe cuantos modulos hay.
# `function-category` esta aqui porque la documentacion le aplica la MISMA regla
# que a los demas modulos, con el mismo ejemplo: *"The category key will also be
# the name of the internationalization bundle… if the plugin-key is `com.example`
# and the category name is `ExampleCategory`, the name of the file … will be
# `ExampleCategory_en_US.properties` and will be located in the `/com/example`
# folder. It will only contain one key—the category key itself."* Y la misma
# pagina lo llama modulo al hablar del orden de despliegue: *"the category module
# definition"*.
#
# `datatype` NO esta, y no por olvido: es el unico elemento del que consta que
# carga SIN bundle propio --un plug-in con `<datatype>` y sin
# `<key>_en_US.properties` para el desplego sus modulos anteriores sin quejarse
# y murio en el primer `<function>`--. Sus `<class>` tampoco son modulos.
ETIQUETAS_DE_MODULO_CON_BUNDLE = ("function", "smart-service", "function-category")

# Solo una de las tres se ha visto fallar de verdad (`<function>`, con el mensaje
# APNX-1-4200-000 de un Appian real). Las otras dos salen de la documentacion, que
# describe un mecanismo unico para todos los modulos. Quien informe un hallazgo
# puede decir cual es cual en vez de dar todo por igual de comprobado.
ETIQUETAS_CON_FALLO_OBSERVADO = ("function",)


def modulos_con_bundle(xml_manifiesto: str) -> list[tuple[str, str]]:
    """`[(etiqueta, key)]` de los modulos del manifiesto que cargan bundle.

    Solo mira los hijos DIRECTOS de `<appian-plugin>`: `<class>` dentro de un
    `<datatype>` no es un modulo, y un `<function>` anidado en cualquier otro
    sitio no existe en el esquema. Un modulo sin `key` sale con cadena vacia y
    lo juzga quien llame, no este constructor.
    """
    raiz = ET.fromstring(xml_manifiesto)
    return [
        (hijo.tag, hijo.get("key", ""))
        for hijo in raiz
        if hijo.tag in ETIQUETAS_DE_MODULO_CON_BUNDLE
    ]


def clases_declaradas(xml_manifiesto: str) -> list[tuple[str, str]]:
    """`[(donde, nombre_cualificado)]` de TODA clase que el manifiesto nombra.

    Appian las carga por nombre al desplegar, una por una: el atributo `class`
    de cada modulo --`<function>`, `<smart-service>`, `<servlet>`-- y cada
    `<class>` de un `<datatype>`. Una que no este en el JAR es un fallo de carga
    al desplegar, no un error de compilacion: `javac` nunca ve el XML, asi que
    un nombre mal escrito ahi llega intacto hasta el servidor.

    `donde` es la etiqueta del elemento, para que el hallazgo pueda decir de
    cual de ellos habla cuando hay varios.
    """
    raiz = ET.fromstring(xml_manifiesto)
    encontradas: list[tuple[str, str]] = []
    for elemento in raiz.iter():
        atributo = (elemento.get("class") or "").strip()
        if atributo:
            encontradas.append((elemento.tag, atributo))
        if elemento.tag == "class" and (elemento.text or "").strip():
            encontradas.append(("datatype", elemento.text.strip()))
    return encontradas


def claves_de_modulo_repetidas(xml_manifiesto: str) -> list[str]:
    """Las `key` que aparecen mas de una vez entre los modulos del manifiesto.

    Cada modulo es una entrada distinta en el registro de plug-ins de Appian y
    su key la identifica; dos iguales dejan una de las dos sin alcanzar, y cual
    de ellas no esta definido.
    """
    raiz = ET.fromstring(xml_manifiesto)
    vistas: list[str] = []
    for hijo in raiz:
        key = hijo.get("key", "")
        if key and hijo.tag in ETIQUETAS_DE_MODULO_CON_BUNDLE + ("servlet", "datatype"):
            vistas.append(key)
    return sorted({k for k in vistas if vistas.count(k) > 1})


def procedencia_de_modulo(etiqueta: str) -> str:
    """La frase con la que un hallazgo dice CUANTO se sabe de su propio caso.

    Dar por igual de comprobado lo observado y lo deducido es como se colo la
    afirmacion --escrita, razonada y falsa-- de que el nombre del bundle de una
    funcion era libre. Quien lea el hallazgo merece saber si detras hay un
    servidor que se nego a cargar el plug-in o una pagina de documentacion.
    """
    if etiqueta in ETIQUETAS_CON_FALLO_OBSERVADO:
        return ("Sin el, el plug-in NO DESPLIEGA: es el caso observado en un Appian real "
                "(APNX-1-4200-000).")
    return ("Appian aplica a este modulo la misma regla de bundle que a los demas, segun su "
            "documentacion; el fallo de despliegue esta observado para <function>, no para "
            "este elemento.")


def ruta_de_bundle(key_plugin: str, key_modulo: str, locale: str) -> str:
    """`com.x.y` + `miModulo` + `en_US` -> `com/x/y/miModulo_en_US.properties`."""
    return f"{key_plugin.replace('.', '/')}/{key_modulo}_{locale}.properties"


def titulo_humano(nombre: str) -> str:
    """El VALOR del `displayName`: el nombre partido por sus mayusculas.

    `documentoOrigen` da «Documento Origen», que es exactamente lo que Appian
    se inventa cuando no encuentra la clave --«the display name is rendered
    automatically using the node input (ACP) name, with spaces separating the
    camel cased name»--. Poner el identificador crudo dejaba al disenador algo
    PEOR que no poner nada: la etiqueta decia `documentoOrigen` en vez de
    «Documento Origen». Escribirlo asi es el suelo, no el techo: el texto se
    puede mejorar a mano, y el plug-in de referencia lo hace.
    """
    partido = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", nombre_de_acp(nombre))
    return re.sub(r"\s+", " ", partido).strip()


def _lineas_de_etiqueta(claves: tuple[str, str], nombre: str, descripcion: str) -> str:
    display, comment = claves
    return f"{display}={titulo_humano(nombre)}\n{comment}={descripcion}"


# UN argumento por cosa. La primera version recibia la tupla de claves Y el
# nombre por separado, y nada obligaba a que hablaran del mismo campo: un
# `claves_de_entrada("A")` con `nombre="B"` producia `input.A.displayName=B`,
# una clave bien formada y mal apuntada. Es la clase exacta de defecto que hizo
# falta inventar R-B06 para ver, invitada por la firma de la pieza que existe
# para impedirla.
def lineas_de_entrada(nombre: str, descripcion: str) -> str:
    """Las dos lineas `clave=valor` que etiquetan una entrada.

    Appian lee el nombre por el ACCESOR, no por el campo: la CLAVE la compone
    `nombre_de_acp`, que es donde vive esa regla y sus tres fuentes. El VALOR
    del `displayName` es distinto --es texto para el diseñador, no un
    identificador-- y va el nombre del contrato tal cual.
    """
    return _lineas_de_etiqueta(claves_de_entrada(nombre), nombre, descripcion)


def lineas_de_salida(nombre: str, descripcion: str) -> str:
    """Las dos lineas `clave=valor` que etiquetan una salida."""
    return _lineas_de_etiqueta(claves_de_salida(nombre), nombre, descripcion)


# EL VOCABULARIO con el que todo validador le habla al orquestador, en el mismo
# sitio que `PREFIJO_INSUMO` y `MARCA_NO_APLICA` y por el mismo motivo.
#
# `verificar_todo._evidencia` decide QUE linea representa a una puerta casando
# estos prefijos: con la puerta en rojo se queda con la primera que empiece por
# ERROR o FALTA, y un AVISO viaja siempre, aunque la puerta salga verde.
#
# Son SIETE piezas las que tienen que coincidir, y ninguna lo hacia por
# construccion: los cinco validadores con `Hallazgo` los derivaban cada uno de
# su `h.severidad.upper()`; `verificar_superficie` --que no usa `Hallazgo`-- los
# escribia literales, y es justo el que imprime el AVISO de modo degradado que
# motivo toda esta regla; y el consumidor, `_evidencia`, casaba sus propios
# literales. Con siete copias, un `Hallazgo` con severidad «advertencia» habria
# impreso una linea que el consumidor no reconoce, y el aviso habria dejado de
# llegar al certificado EN SILENCIO: exactamente la averia que la regla del
# AVISO acababa de corregir. Ahora las siete leen de aqui.
PREFIJO_ERROR = "ERROR"
PREFIJO_FALTA = "FALTA"
PREFIJO_AVISO = "AVISO"
PREFIJOS_DE_FALLO = (PREFIJO_ERROR, PREFIJO_FALTA)
PREFIJO_POR_SEVERIDAD = {"error": PREFIJO_ERROR, "aviso": PREFIJO_AVISO}


def prefijo_de(severidad: str) -> str:
    """El prefijo de una severidad, o ruidosamente nada.

    Falla en vez de improvisar un `severidad.upper()`: una severidad que el
    orquestador no sabe leer tiene que romper aqui, donde se ve, y no
    convertirse en una linea que el certificado ignora sin decirlo.
    """
    if severidad not in PREFIJO_POR_SEVERIDAD:
        raise ValueError(
            f"severidad «{severidad}» desconocida: el orquestador solo sabe leer "
            f"{sorted(PREFIJO_POR_SEVERIDAD)} (verificar_todo._evidencia)"
        )
    return PREFIJO_POR_SEVERIDAD[severidad]


def informar(hallazgos, insumo: str = "", detalle: str = "") -> int:
    """El epilogo comun de los validadores, y su codigo de salida.

    Los cinco lo tenian copiado, en el mismo orden y con las mismas cadenas:
    insumo, una linea por hallazgo, recuento, `return 1 if errores`. Y la
    quinta copia ya habia divergido —`verificar_licencias` cerraba «… sobre N
    dependencias de terceros» y las otras cuatro no—, que es lo que pasa
    siempre: no es decoracion, es el contrato de costura que `verificar_todo`
    parsea. `detalle` deja esa cola como parametro deliberado en vez de como
    accidente.
    """
    if insumo:
        print(insumo)
    for h in hallazgos:
        print(f"{prefijo_de(h.severidad)} {h.regla}: {h.mensaje}")
    errores = [h for h in hallazgos if h.severidad == "error"]
    print(f"{len(hallazgos)} hallazgos ({len(errores)} errores){detalle}")
    return 1 if errores else 0


def escapar_no_ascii(texto: str) -> str:
    """Acentos a `\\uXXXX`, que es como los quiere un `.properties` fuera de en_US.

    Vive aqui, y no dentro del andamiador, por la misma razon que
    `MARCAS_SIN_IMPLEMENTAR`: hay dos lados que se tienen que mirar en el mismo
    espejo. Uno EMITE el bundle traducido (`andamiar`) y otro lo JUZGA
    (`verificar_bundles`, R-B05, sobre el `PATRON_NO_ASCII` de aqui arriba).
    Cuando solo el emisor sabia escapar, sabia a medias: las dos cadenas
    horneadas a mano salian con `\\u00f3` y todo lo que venia del contrato salia
    con la tilde cruda, en el MISMO fichero. Ningun test lo vio porque ningun
    fixture de contrato lleva una sola tilde, y la unica prueba que habria
    fallado --andamiar un contrato en español y pasarle su propio validador--
    no existia.

    Se aplica al CONTENIDO YA RENDERIZADO del fichero, no variable a variable:
    el primer intento escapaba las cuatro variables `*_ES` y dejaba pasar
    `{{NOMBRE}}`, que la plantilla `bundle_es_ES` tambien escribe. Escapar por
    variable obliga a acertar con la lista; escapar por destino no puede
    olvidarse de ninguna, ni de la que alguien anada manana.

    Ya escapado es idempotente: `\\u00f3` son seis caracteres ASCII.

    Fuera del BMP se emite el par subrogado, que es lo que entiende Java; por
    eso se codifica a UTF-16 en vez de usar `ord()` directamente, que para un
    emoji daria un `\\u1f600` de cinco digitos que ningun cargador acepta.
    """
    salida: list[str] = []
    for caracter in texto:
        if caracter.isascii():
            salida.append(caracter)
            continue
        crudo = caracter.encode("utf-16-be")
        for i in range(0, len(crudo), 2):
            salida.append(f"\\u{(crudo[i] << 8) | crudo[i + 1]:04x}")
    return "".join(salida)


def horneada_equivalente(nombre: str) -> str | None:
    """La salida horneada que PRODUCE EL MISMO MIEMBRO JAVA que `nombre`, si la hay.

    Se compara por el identificador del campo, no por el nombre del contrato:
    `errorOccurred` y `ErrorOccurred` son dos nombres distintos para Appian y
    **el mismo campo** para javac, porque los dos dan `private … errorOccurred`
    y `getErrorOccurred()`. Comparar por nombre exacto --que es lo que se hacia--
    dejaba pasar la caja cambiada, y entonces el `.java` salia con el campo y el
    getter DUPLICADOS: «variable errorOccurred is already defined». No es un
    fallo de despliegue sino de compilacion, y aun asi se escapaba de la puerta.
    """
    objetivo = identificador_java(nombre).lower()
    for reservada in SALIDAS_HORNEADAS:
        if identificador_java(reservada).lower() == objetivo:
            return reservada
    return None


def salida_horneada(salida: dict) -> bool:
    """La salida se mapea sobre un miembro que la plantilla ya declara.

    Exige el nombre EXACTO ademas del tipo: con la caja cambiada no se mapea,
    porque el output que Appian acabaria publicando es el del accesor horneado
    (`ErrorOccurred`) y no el que el autor escribio. Ese caso lo rechaza
    `colision_con_horneada` en vez de resolverlo en silencio.
    """
    return SALIDAS_HORNEADAS.get(salida.get("nombre", "")) == salida.get("tipo_java")


def colision_con_horneada(salida: dict) -> str | None:
    """El motivo por el que esta salida chocaria con un miembro horneado, o None.

    Dos casos, y los dos acaban en un `.java` que no compila:
      - mismo nombre reservado y tipo distinto;
      - el mismo miembro Java con otra caja (`errorOccurred`).
    """
    nombre = salida.get("nombre", "")
    equivalente = horneada_equivalente(nombre)
    if equivalente is None:
        return None
    esperado = SALIDAS_HORNEADAS[equivalente]
    if nombre != equivalente:
        return (f"se escribe «{equivalente}», no «{nombre}»: los dos dan el mismo campo y el "
                f"mismo getter, asi que el .java saldria duplicado, y el nombre que Appian "
                f"publica es el del accesor")
    if esperado != salida.get("tipo_java"):
        return (f"el miembro que la plantilla ya declara es de tipo {esperado} y no "
                f"{salida.get('tipo_java')}: el .java saldria con el getter duplicado. "
                f"Usar {esperado}, o renombrar la salida")
    return None


def tipo_java_emitible(tipo: str) -> str | None:
    """El tipo tal como debe escribirse en el `.java`, o None si no se puede.

    Devuelve None cuando el tipo no es de `java.lang`, no es uno de los alias
    de `java.sql` y tampoco viene cualificado: eso no compilaria, y es mejor
    decirlo en la puerta que en `javac`.

    «Cualificado» exige ser un NOMBRE DE TIPO, no solo llevar un punto. Mientras
    basto con el punto, la puerta dejo pasar
    `com.appiancorp.suiteapi.expression.annotations.ParameterizedType(com.appiancorp.suiteapi.type.TypedValue)`
    --una anotacion escrita como si fuera un tipo-- y el andamiador la emitio
    tal cual, como manda su contrato: el fallo no aparecio hasta `javac`, con la
    causa a dos pasos de distancia, en un fichero que nadie escribio a mano.
    Visto en una prueba E2E real el 19-sep-2026.
    """
    if not isinstance(tipo, str) or not tipo.strip():
        return None
    base, sufijo = tipo.strip(), ""
    while base.endswith("[]"):
        base, sufijo = base[:-2], sufijo + "[]"
    if not PATRON_NOMBRE_TIPO_JAVA.fullmatch(base):
        return None
    if base in ALIAS_JAVA_SQL:
        return ALIAS_JAVA_SQL[base] + sufijo
    if base in TIPOS_JAVA_LANG:
        return base + sufijo
    if "." in base:  # ya viene cualificado: se emite tal cual
        return base + sufijo
    return None


# Un literal Java NO NULO para cada tipo BASE que `tipo_java_emitible` puede
# devolver -- indexado por la forma YA RESUELTA (`java.sql.Timestamp`, no el
# alias `Timestamp` del contrato), o las nueve salidas Timestamp del oraculo
# EML no encontrarian su placeholder.
#
# Por que hace falta y por que ninguno es `null`: SpotBugs marca UwF (campo
# nunca escrito) sobre toda salida que el stub de `ejecutar()` no toca, pero
# tiene TAMBIEN un patron para el arreglo ingenuo -- UWF_NULL_FIELD, «campo
# solo escrito a null» -- asi que la escritura tiene que ser un valor real del
# tipo. Cada entrada de aqui es ese valor.
PLACEHOLDER_POR_TIPO = {
    "byte": "(byte) 0", "short": "(short) 0", "int": "0", "long": "0L",
    "float": "0f", "double": "0d", "boolean": "false", "char": "'\\0'",
    "String": '""',
    "Boolean": "Boolean.FALSE", "Long": "0L", "Integer": "0", "Double": "0d",
    "Float": "0f", "Short": "(short) 0", "Byte": "(byte) 0",
    "Character": "'\\0'", "Number": "0", "Object": "new Object()",
    "java.sql.Timestamp": "new java.sql.Timestamp(0L)",
    "java.sql.Time": "new java.sql.Time(0L)",
}


def placeholder_no_nulo(tipo_emitido: str) -> str | None:
    """Un literal Java no nulo del tipo YA RESUELTO (la salida de
    `tipo_java_emitible`, no lo que escribe el contrato), o None si el tipo
    no tiene uno evidente.

    Los arrays se resuelven por nivel: `String[]` -> `new String[0]`,
    `String[][]` -> `new String[0][]` (arrays multidimensionales no
    aparecen hoy en ningun fixture, pero la regla es general).

    None es la senal para NO INVENTAR: `validar()` acepta cualquier tipo
    cualificado con un punto (R-F04 y hermanas viven en las capas de
    verificacion, no aqui), asi que un smart-service con una salida de tipo
    `com.acme.Cdt` pasa la puerta determinista sin que este modulo sepa
    construir un valor de ese tipo -- un vacio real del sistema, no un
    tipo que "se resista": no hay constructor conocido que forzar sin
    inventar. Quien llame a esta funcion con None debe fallar RUIDOSO
    (ValueError), nunca escribir `null` ni adivinar un constructor.
    """
    base, nivel = tipo_emitido, 0
    while base.endswith("[]"):
        base, nivel = base[:-2], nivel + 1
    if nivel:
        return f"new {base}[0]" + "[]" * (nivel - 1)
    return PLACEHOLDER_POR_TIPO.get(base)


# Las cuatro preguntas que proponen RIGUROSO (spec §2.3 y §6.4). La lista es
# corta a proposito: si casi todo dispara RIGUROSO, el perfil no distingue nada.
CAPACIDADES_QUE_PROPONEN_RIGUROSO = (
    "parsea_formatos_ajenos",
    "sale_a_la_red",
    "toca_credenciales",
    "datos_personales",
)

# Un identificador Java y un nombre cualificado por puntos. `$` es legal en el
# lenguaje pero lo reservan los compiladores para clases internas y sinteticas:
# admitirlo aqui produciria nombres que compilan y confunden al escaner de
# bytecode, que normaliza `$` a punto. Se deja fuera a proposito.
PATRON_IDENTIFICADOR = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
PATRON_CUALIFICADO = re.compile(
    rf"{PATRON_IDENTIFICADOR.pattern}(\.{PATRON_IDENTIFICADOR.pattern})*"
)

# Palabras que el compilador no admite como segmento de paquete ni como nombre
# de clase. `var`, `record`, `sealed` y companía son *contextuales*: legales
# como identificador, asi que no entran.
RESERVADAS_JAVA = frozenset("""
abstract assert boolean break byte case catch char class const continue default do double else
enum extends final finally float for goto if implements import instanceof int interface long
native new package private protected public return short static strictfp super switch
synchronized this throw throws transient try void volatile while true false null _
""".split())


def _error_de_identificador(valor: str, cualificado: bool) -> str | None:
    """Por que este valor no puede ir en el `.java`, o None si puede.

    Se comprueba en la PUERTA DETERMINISTA y no mas tarde a proposito: un
    paquete con un espacio, un guion o una palabra reservada produce un
    proyecto que no compila, y sin esto el fallo no aparecia al validar el
    contrato --instantaneo-- sino dentro de `./gradlew build`, minutos despues
    y con un error del compilador que no menciona el contrato.
    """
    patron = PATRON_CUALIFICADO if cualificado else PATRON_IDENTIFICADOR
    if not patron.fullmatch(valor):
        forma = "segmentos separados por puntos" if cualificado else "un identificador"
        return (
            f"«{valor}» no es {forma} valido de Java: solo letras, digitos y guion bajo, "
            f"sin empezar por digito"
        )
    reservadas = sorted({s for s in valor.split(".") if s in RESERVADAS_JAVA})
    if reservadas:
        return f"«{valor}» usa palabras reservadas de Java: {reservadas}"
    return None


PATRON_BLOQUE_TOML = re.compile(r"```toml\s*\n(.*?)\n```", re.DOTALL)

# Lo que `validar` exige que sea CADENA, seccion a seccion. Las listas
# (`entradas`, `salidas`) se comprueban campo a campo en su propio bucle.
CAMPOS_QUE_SON_CADENA = (
    ("plugin", ("key", "nombre", "version", "paquete", "tipo", "perfil",
                "application_version_min", "descripcion", "vendor")),
    ("clase", ("nombre", "paleta")),
    ("bundle", ("nombre",)),
    ("funcion", ("nombre",)),
)

# `26.3`, `24.1`, `26.3.1`: digitos separados por puntos, al menos un punto.
PATRON_VERSION_APPIAN = re.compile(r"\d+(\.\d+)+")


def extraer_toml(texto_md: str) -> dict:
    # Se normalizan los finales de linea antes de casar: el repositorio esta en
    # Windows y git convierte a CRLF al hacer checkout. Sin esto, el \r que
    # queda antes de la valla de cierre entra en el bloque capturado y tomllib
    # lo rechaza con TOMLDecodeError. Comprobado, no supuesto.
    normalizado = texto_md.replace("\r\n", "\n").replace("\r", "\n")
    coincidencia = PATRON_BLOQUE_TOML.search(normalizado)
    if not coincidencia:
        raise ValueError("el contrato no contiene ningun bloque ```toml")
    return tomllib.loads(coincidencia.group(1))


class TextoIlegible(ValueError):
    """Un fichero de texto que no se puede leer como UTF-8, dicho en castellano.

    Nace el 21-sep-2026 de una prueba adversaria: un `contrato.md`, un
    `exclude.xml` o un `.properties` guardados desde PowerShell 5.1 con `>`
    salen en UTF-16, y cada script moria con `UnicodeDecodeError: 'utf-8'
    codec can't decode byte 0xff`, que no le dice a nadie que hacer.
    """


class ContratoIlegible(TextoIlegible):
    """El contrato no se pudo ni abrir: no existe, no es UTF-8, esta vacio, no
    trae bloque toml o el TOML no parsea. Distinto de `validar()`, que juzga un
    contrato que SI se leyo."""


def leer_utf8(ruta: pathlib.Path) -> str:
    """`read_text(encoding="utf-8")` con diagnostico. NO quita el BOM UTF-8:
    quien lo necesite ver (R-F14 sobre `exclude.xml`) lo ve."""
    ruta = pathlib.Path(ruta)
    if ruta.is_dir():
        raise TextoIlegible(f"{ruta} es un directorio, no un fichero")
    if not ruta.is_file():
        raise TextoIlegible(f"no existe {ruta}")
    crudo = ruta.read_bytes()
    if crudo[:2] in (b"\xff\xfe", b"\xfe\xff"):
        raise TextoIlegible(
            f"{ruta} esta guardado en UTF-16 --es lo que escribe `>` en PowerShell 5.1--: "
            f"reescribelo en UTF-8 (desde el editor, o con `Out-File -Encoding utf8`)"
        )
    try:
        return crudo.decode("utf-8")
    except UnicodeDecodeError as error:
        raise TextoIlegible(
            f"{ruta} no esta en UTF-8 (byte {error.start} no valido): reescribelo en UTF-8"
        ) from None


def cargar(ruta: pathlib.Path) -> dict:
    ruta = pathlib.Path(ruta)
    try:
        texto = leer_utf8(ruta)
    except TextoIlegible as error:
        raise ContratoIlegible(str(error)) from None
    if not texto.strip():
        raise ContratoIlegible(f"{ruta} esta vacio")
    try:
        return extraer_toml(texto)
    except tomllib.TOMLDecodeError as error:
        # `TOMLDecodeError` es un `ValueError`: va antes que la rama generica.
        raise ContratoIlegible(
            f"el bloque toml de {ruta} no es TOML valido: {error}"
        ) from None
    except ValueError as error:
        raise ContratoIlegible(
            f"{ruta}: {error}; el contrato lleva su TOML en un bloque que empieza por "
            f"```toml y termina por ```"
        ) from None


def capacidades_exigentes(capacidades: dict) -> list[str]:
    """Cuales de las declaradas piden RIGUROSO, por su nombre.

    Los NOMBRES, y no solo el perfil, porque `verificar_todo` los necesita para
    la nota del certificado: «tus capacidades lo piden» sin decir cual manda a
    leerse el contrato entero. Y en una sola funcion porque la regla se aplica
    en dos modulos --el AVISO de `main()` promete lo que hara `verificar_todo`,
    y esa promesa solo es cierta mientras los dos apliquen el mismo criterio--.
    Con dos copias del bucle, un cambio de criterio las separa en silencio.
    """
    return [clave for clave in CAPACIDADES_QUE_PROPONEN_RIGUROSO if capacidades.get(clave)]


def perfil_propuesto(capacidades: dict) -> str:
    return "riguroso" if capacidades_exigentes(capacidades) else "estandar"


def nombre_funcion(datos: dict) -> str:
    """Nombre de la funcion, con UN SOLO fallback para todo el sistema.

    La seccion `[funcion]` es opcional. Cuando falta, el nombre se deriva del
    de la clase — y esa derivacion tiene que vivir en un unico sitio: el
    andamiador caia a `CLASE.lower()` y `verificar_bundles` caia a `""`, asi
    que R-B03 acababa exigiendo `function..description`, con doble punto, que
    ninguna plantilla puede emitir. Dos fallbacks distintos para el mismo dato
    es una puerta que se contradice con el artefacto que juzga.
    """
    declarado = seccion(datos, "funcion").get("nombre")
    if declarado:
        return declarado
    return seccion(datos, "clase").get("nombre", "").lower()


def validar(datos: dict) -> list[str]:
    """Puerta determinista: campos obligatorios que faltan o son invalidos.

    No juzga la intencion —eso es la puerta de confianza de la entrevista—,
    solo que no falte nada sin lo cual el andamiaje no puede generarse.

    El contrato que esta puerta acepta y lo que el andamiador sabe procesar
    son la MISMA forma, y esa simetria es justo su razon de ser: un contrato
    de function pasaba esta funcion y mataba a `andamiar.py` con
    `KeyError: 'required'`, que es el peor sitio posible para fallar.
    Cualquier campo que `andamiar.py` indexe con subindice duro tiene que
    exigirse aqui, para el mismo conjunto de tipos.
    """
    faltantes: list[str] = []

    # LA FORMA DE CADA SECCION, ANTES QUE SU CONTENIDO, y para todas por igual.
    # `datos.get("x", {})` solo repone el defecto cuando la clave FALTA, asi
    # que una seccion del tipo equivocado llegaba entera al bucle de abajo:
    # `plugin = "x"` reventaba con `AttributeError` en el primer `.get`, y
    # `[entradas]` escrito como tabla en vez de `[[entradas]]` reventaba al
    # iterar sus claves-`str`. En los dos casos la puerta determinista del
    # paso 1 MORIA CON TRAZA en vez de imprimir `FALTA`, que es lo unico que
    # su lector sabe leer. La guarda existia solo para `capacidades`; esto es
    # la misma regla aplicada a sus hermanas, que es donde debio nacer.
    # Levantada por la revision de codigo posterior al ciclo 10.
    # LAS NUEVE: las OCHO que consume el andamiador mas `[capacidades]`, que
    # leen `perfil_propuesto` y `verificar_todo._resolver_perfil`. La guarda es
    # a proposito un SUPERCONJUNTO de lo que toca `andamiar`; lo que no puede
    # es quedarse corta por ese lado.
    # El gate del ciclo 12 midio el hueco: la tupla traia siete y el andamiador
    # ya consumia ocho, asi que `[servlet]` y `[dependencias]` entraban sin
    # mirar. `dependencias` era la silenciosa de las dos --con una cadena, los
    # tres consumidores la iteran CARACTER A CARACTER y el `build.gradle`
    # generado sale con un `implementation 'c'` por letra, con la puerta en
    # verde--. Quien anada una seccion al esquema tiene que anadirla aqui: lo
    # vigila `test_contrato.test_la_guarda_cubre_TODAS_las_secciones_que_el_
    # andamiador_consume`, que las cuenta sobre `andamiar.py`, no sobre esta
    # tupla ni sobre los fixtures --ningun fixture declara estas dos, que es
    # justo por lo que el hueco sobrevivio al guardian anterior--.
    # La tercera columna es la forma de los ELEMENTOS, y no es adorno:
    # `entradas`/`salidas` son listas de TABLAS y `dependencias` una lista de
    # CADENAS (`implementation '<coordenada>'`, andamiar.py:141-143). Con una
    # sola forma de elemento para las tres, la guarda habria rechazado
    # `dependencias = ["com.example:lib:1.0"]`, que es justo la forma buena.
    datos = dict(datos)
    for nombre, forma, forma_elemento in (
        ("plugin", dict, None), ("clase", dict, None), ("bundle", dict, None),
        ("funcion", dict, None), ("capacidades", dict, None), ("servlet", dict, None),
        ("entradas", list, dict), ("salidas", list, dict), ("dependencias", list, str),
    ):
        valor = datos.get(nombre)
        if valor is not None and not isinstance(valor, forma):
            # El «como se escribe» sale de la forma del ELEMENTO, no de la de
            # la seccion, y no es un matiz: `[[x]]` es la sintaxis TOML de una
            # lista de TABLAS. Decirselo a quien tecleo `dependencias =
            # "com.example:lib:1.0"` lo mandaba en circulo -- obedecia,
            # escribia `[[dependencias]]`, y la guarda de elementos lo
            # rechazaba entonces por traerle un dict donde espera una cadena.
            # En una puerta cuya salida entera son lineas accionables, un
            # mensaje que da la vuelta es peor que no decir nada.
            # Levantado por el /code-review del ciclo 12.
            if forma is dict:
                comose = f"una seccion `[{nombre}]`"
            elif forma_elemento is dict:
                comose = f"una lista de tablas `[[{nombre}]]`"
            else:
                # Los puntos suspensivos, en ASCII: esto es sintaxis para
                # copiar y la consola de Windows (cp1252) convierte el `…` en
                # un rombo. En prosa da igual; dentro de un ejemplo tecleable
                # no.
                comose = f'una lista de cadenas (`{nombre} = ["..."]`)'
            faltantes.append(
                f"{nombre}: tiene que ser {comose}, y viene como {type(valor).__name__}"
            )
            datos[nombre] = forma()
            continue
        # Y los ELEMENTOS de las listas, que es la mitad que faltaba: la guarda
        # comprobaba que `entradas` fuera una lista y no que sus elementos
        # fueran tablas, asi que `entradas = ["nombre"]` --TOML valido-- llegaba
        # al `.get(campo)` del bucle de abajo y mataba a la puerta con
        # `AttributeError` en vez de imprimir `FALTA`. Levantado por el gate
        # del ciclo 11.
        if forma_elemento is not None and valor:
            # El indice que se imprime es SIEMPRE el del contrato que el lector
            # tiene delante, y por eso los elementos sanos viajan emparejados
            # con el suyo. Filtrar y volver a enumerar renumeraba lo que queda:
            # con `entradas = ["basura", {...}]`, el bloque malo salia como
            # `entradas[0]` y el segundo bloque --incompleto-- tambien, dos
            # `[[entradas]]` distintos con la misma etiqueta. En una puerta
            # cuya salida entera son lineas `FALTA` accionables, el indice ES
            # el dato. Levantado por la revision de codigo del ciclo 11.
            # La lista NO se filtra: se deja entera y los bucles de contenido
            # saltan lo que no sea tabla. Asi `enumerate` sigue contando sobre
            # el contrato real y no sobre un residuo renumerado.
            comose_elemento = (
                f"una tabla `[[{nombre}]]` con sus campos" if forma_elemento is dict
                else "una cadena"
            )
            for i, elemento in enumerate(valor):
                if not isinstance(elemento, forma_elemento):
                    faltantes.append(
                        f"{nombre}[{i}]: cada entrada es {comose_elemento}, "
                        f"y esta viene como {type(elemento).__name__}"
                    )

    plugin = seccion(datos, "plugin")
    for campo in ("key", "nombre", "version", "paquete", "tipo", "perfil", "application_version_min"):
        if not plugin.get(campo):
            faltantes.append(f"plugin.{campo}")

    tipo = plugin.get("tipo")
    if tipo and tipo not in TIPOS_VALIDOS:
        faltantes.append(f"plugin.tipo: «{tipo}» no es uno de {sorted(TIPOS_VALIDOS)}")
    if plugin.get("perfil") and plugin["perfil"] not in PERFILES:
        faltantes.append(f"plugin.perfil: «{plugin['perfil']}» no es uno de {sorted(PERFILES)}")

    faltantes += _validar_confirmacion(datos)

    # CADENAS, no solo presentes. `application_version_min = 26` sin comillas
    # es un entero para TOML: pasaba esta puerta y mataba a `andamiar.py` con
    # un `TypeError` en `sustituir`; `key = 123` mataba aqui mismo, en el
    # `fullmatch` de abajo. Y `sale_a_la_red = "no"` es una cadena no vacia,
    # o sea VERDADERO: proponia RIGUROSO por un «no». Prueba adversaria del
    # 21-sep-2026, casos 05 y 18d.
    for nombre_seccion, campos in CAMPOS_QUE_SON_CADENA:
        for campo in campos:
            valor = seccion(datos, nombre_seccion).get(campo)
            if valor is not None and not isinstance(valor, str):
                faltantes.append(
                    f"{nombre_seccion}.{campo}: debe ir entre comillas; sin ellas TOML lo lee "
                    f"como {type(valor).__name__} y el andamiador no puede escribirlo"
                )
    # `dependencias` es clave de RAIZ del TOML. Escrita despues de `[[salidas]]`
    # --o de cualquier otra tabla--, TOML la cuelga en silencio de la ultima
    # tabla abierta: el contrato daba «OK contrato completo», `build.gradle`
    # salia sin ningun `implementation` y el fallo aparecia en `compileJava`,
    # lejos de la causa. Lo encontro el primer ensayo con una dependencia real
    # (libphonenumber, 21-sep-2026).
    extraviadas = [
        f"{nombre}[{i}]" for nombre in ("entradas", "salidas")
        for i, campo in enumerate(datos.get(nombre, []))
        if isinstance(campo, dict) and "dependencias" in campo
    ] + [
        nombre for nombre, valor in datos.items()
        if isinstance(valor, dict) and "dependencias" in valor
    ]
    if extraviadas:
        faltantes.append(
            f"dependencias: aparece dentro de {', '.join(extraviadas)} y tiene que ir en la RAIZ "
            f"del bloque toml, ANTES de `[plugin]`; escrita despues de una tabla, TOML la cuelga "
            f"de esa tabla y el andamiador no la ve"
        )

    for clave, valor in seccion(datos, "capacidades").items():
        if not isinstance(valor, bool):
            faltantes.append(
                f"capacidades.{clave}: debe ser true o false sin comillas; "
                f"«{valor}» cuenta como verdadero y sube el perfil"
            )
    avm = plugin.get("application_version_min")
    if isinstance(avm, str) and not PATRON_VERSION_APPIAN.fullmatch(avm):
        faltantes.append(
            f"plugin.application_version_min: «{avm}» no tiene forma de version de Appian "
            f"(p. ej. 26.3): va tal cual al manifiesto y Appian no lo aceptaria"
        )

    # Bien formados, no solo presentes. Los tres viajan al `.java`, al
    # manifiesto y a la RUTA de los ficheros generados: `paquete` se convierte
    # en directorios y `key` en la ruta del bundle (`key.replace('.', '/')`).
    # Y desde el 21-sep-2026, tambien los nombres de entradas, salidas y de la
    # funcion: `andamiar.py` los escribe VERBATIM en `@Parameter String <nombre>`,
    # en `<function key>` y en las claves del bundle, y `nom bre` o
    # `nombre;System.exit(0);String x` pasaban la puerta y fallaban en javac o
    # en SAIL, justo lo que esta puerta existe para adelantar.
    identificadores = [
        ("plugin.paquete", plugin.get("paquete"), True),
        ("plugin.key", plugin.get("key"), True),
        ("clase.nombre", seccion(datos, "clase").get("nombre"), False),
        ("bundle.nombre", seccion(datos, "bundle").get("nombre"), False),
        ("funcion.nombre", seccion(datos, "funcion").get("nombre"), False),
    ]
    for lista in ("entradas", "salidas"):
        for i, campo in enumerate(datos.get(lista, [])):
            if isinstance(campo, dict):
                identificadores.append((f"{lista}[{i}].nombre", campo.get("nombre"), False))
    for ruta_campo, valor, cualificado in identificadores:
        if not valor or not isinstance(valor, str):
            continue  # la ausencia y el tipo ya los reporta su propia comprobacion
        problema = _error_de_identificador(valor, cualificado)
        if problema:
            faltantes.append(f"{ruta_campo}: {problema}")

    if not seccion(datos, "clase").get("nombre"):
        faltantes.append("clase.nombre")
    paleta = seccion(datos, "clase").get("paleta")
    if tipo == "smart-service" and not paleta:
        faltantes.append("clase.paleta")
    elif paleta and paleta not in ANOTACION_POR_PALETA:
        # RECHAZO, no repuesto. Antes el andamiador traducia lo que conocia y
        # todo lo demas caia a `ANOTACION_POR_DEFECTO` sin decir nada: el
        # plug-in compilaba, desplegaba y certificaba READY, y aparecia en una
        # paleta que nadie habia pedido. Ninguna de las trece puertas lo veia
        # --R-F01 y R-F01b miran el valor efectivo, y la anotacion de repuesto
        # es de la familia segura--, asi que el unico sitio donde se puede
        # atrapar es aqui, antes de generar nada.
        faltantes.append(
            f"clase.paleta: {_pista_de_paleta(paleta)} Las validas son "
            f"{sorted(ANOTACION_POR_PALETA)}"
        )

    if tipo in TIPOS_CON_BUNDLE and not seccion(datos, "bundle").get("nombre"):
        faltantes.append(
            "bundle.nombre: alimenta la key del manifiesto y el nombre del .properties; "
            "sin el salen «key=\"\"» y un fichero «_en_US.properties»"
        )

    entradas = datos.get("entradas", [])
    if not entradas:
        faltantes.append("entradas: el contrato no declara ninguna")
    for i, entrada in enumerate(entradas):
        # Lo que no es tabla ya lo reporto la guarda de forma de arriba, con su
        # indice real; aqui se salta para no volver a contarlo ni reventar.
        if not isinstance(entrada, dict):
            continue
        for campo in ("nombre", "tipo_java", "descripcion"):
            if not entrada.get(campo):
                faltantes.append(f"entradas[{i}].{campo}")
            elif not isinstance(entrada[campo], str):
                faltantes.append(
                    f"entradas[{i}].{campo}: debe ir entre comillas; sin ellas TOML lo lee "
                    f"como {type(entrada[campo]).__name__}"
                )
        if isinstance(entrada.get("tipo_java"), str) and tipo_java_emitible(entrada["tipo_java"]) is None:
            faltantes.append(
                f"entradas[{i}].tipo_java: «{entrada['tipo_java']}» no es un nombre de tipo Java "
                f"de java.lang ni viene cualificado; el .java no compilaria. Un tipo es "
                f"`Paquete.Clase`, sin parentesis ni genericos: si dudas del tipo exacto, "
                f"`javap` sobre el JAR del SDK o el agente appian-docs-researcher"
            )
        if tipo == "smart-service":
            valor = entrada.get("required")
            if not valor:
                faltantes.append(f"entradas[{i}].required")
            elif valor not in REQUIRED_VALIDOS:
                faltantes.append(f"entradas[{i}].required: «{valor}» no es ALWAYS ni OPTIONAL")

    # EN FUNCTIONS la salida decide el TIPO DE RETORNO del metodo Java, asi que
    # no declararla no es «no hay salida»: es que el andamiador elige uno por su
    # cuenta. Elegia `String` en silencio (`andamiar.py:352`), y ninguna puerta
    # posterior podia atraparlo --no hay salida declarada contra la que
    # comparar--. Es la misma familia que la paleta, alcanzable por el CLI, y la
    # levanto el gate del ciclo 5 como preexistente.
    #
    # Solo `function`. Los otros dos tipos con clase quedan fuera Y POR MOTIVOS
    # DISTINTOS, que conviene no mezclar:
    #   - `writer-function` hornea su tipo de retorno en la plantilla (`public
    #     Writer …`), no lo deriva de la salida, asi que no hay nada que elegir
    #     en silencio. La primera version de esta regla lo incluia y rompio su
    #     fixture: el fixture tenia razon.
    #   - `smart-service` no devuelve nada; sus salidas son campos con accesor,
    #     y el propio proyecto declara legitimo un contrato sin ellas (ver
    #     `insumo_vacio`).
    salidas_declaradas = datos.get("salidas") or []
    if tipo == "function" and not salidas_declaradas:
        faltantes.append(
            "salidas: una function DEBE declarar la suya — de su `tipo_java` sale el tipo de "
            "retorno del metodo Java, y sin ella el andamiador elegiria uno que el contrato "
            "no dice"
        )
    # Y EXACTAMENTE UNA. Un metodo Java devuelve un valor: con dos declaradas,
    # `andamiar` tomaba `salidas[0]` y la segunda no aparecia ni en el `.java`
    # ni en el bundle -- y si se invertia el orden en el TOML, cambiaba el tipo
    # de retorno sin que nada lo dijera. Ninguna puerta posterior podia verlo.
    elif tipo == "function" and len(salidas_declaradas) > 1:
        faltantes.append(
            f"salidas: una function declara UNA, y aqui hay {len(salidas_declaradas)} "
            f"({[s.get('nombre') for s in salidas_declaradas]}). Un metodo Java devuelve un "
            f"valor: el andamiador emitiria solo la primera y las demas no llegarian al "
            f"artefacto"
        )
    # La writer-function NO declara ninguna: su plantilla hornea `public Writer`
    # y no deriva nada de la salida. Declarar `resultado: String` producia un
    # contrato que decia String sobre un artefacto que devuelve Writer.
    elif tipo == "writer-function" and salidas_declaradas:
        faltantes.append(
            "salidas: una writer-function no declara ninguna — su metodo devuelve siempre "
            "`Writer` (lo hornea la plantilla), asi que una salida declarada aqui describiria "
            "un artefacto que no existe"
        )
    # El servlet, por el mismo argumento y por la misma prueba: su plantilla no
    # consume NINGUNA salida --escribe en el `HttpServletResponse`, y el
    # `TIPO_RETORNO` que el andamiador calcula no lo lee nadie--. Declararlas
    # salia exit 0, y de ahi viajaban: `generar_dossier` las publica en la
    # firma y R-F08 las compara, asi que el DOSSIER de un servlet afirmaba unas
    # salidas que el artefacto no tiene. Levantado por el gate del ciclo 7.
    elif tipo == "servlet" and salidas_declaradas:
        faltantes.append(
            "salidas: un servlet no declara ninguna — escribe su respuesta en el "
            "`HttpServletResponse` y la plantilla no consume ninguna salida, asi que lo "
            "declarado aqui solo llegaria al DOSSIER, a describir algo que no existe"
        )

    for i, salida in enumerate(datos.get("salidas", [])):
        # Lo que no es tabla ya lo reporto la guarda de forma de arriba, con su
        # indice real; aqui se salta para no volver a contarlo ni reventar.
        if not isinstance(salida, dict):
            continue
        for campo in ("nombre", "tipo_java", "descripcion"):
            if not salida.get(campo):
                faltantes.append(f"salidas[{i}].{campo}")
            elif not isinstance(salida[campo], str):
                faltantes.append(
                    f"salidas[{i}].{campo}: debe ir entre comillas; sin ellas TOML lo lee "
                    f"como {type(salida[campo]).__name__}"
                )
        if isinstance(salida.get("tipo_java"), str) and tipo_java_emitible(salida["tipo_java"]) is None:
            faltantes.append(
                f"salidas[{i}].tipo_java: «{salida['tipo_java']}» no es un nombre de tipo Java "
                f"de java.lang ni viene cualificado; el .java no compilaria. Un tipo es "
                f"`Paquete.Clase`, sin parentesis ni genericos: si dudas del tipo exacto, "
                f"`javap` sobre el JAR del SDK o el agente appian-docs-researcher"
            )

    # La FORMA antes que el contenido: sin esto, `capacidades = 5` hacia
    # `5 not in 5` --`TypeError`, la puerta determinista muriendo con traza en
    # vez de imprimir `FALTA`-- y `capacidades = "sale_a_la_red ..."` pasaba
    # limpio por la semantica de subcadena del `in` sobre un `str`, para
    # reventar dos lineas despues en `perfil_propuesto`. La puerta que POSEE la
    # forma del contrato tiene que ser la que la comprueba. Levantado por el
    # /simplify del ciclo 9, que lo encontro al mirar la asimetria con
    # `verificar_todo._resolver_perfil`, donde si estaba.
    # La forma ya la comprobo la guarda del principio, para esta seccion y para
    # todas sus hermanas; aqui solo queda el contenido. Sin numero: eran seis
    # cuando se escribio y son ocho desde el ciclo 12, y una cuenta repetida en
    # prosa es justo lo que este repositorio se pasa el dia desincronizando.
    capacidades = seccion(datos, "capacidades")
    for clave in CAPACIDADES_QUE_PROPONEN_RIGUROSO:
        if clave not in capacidades:
            faltantes.append(f"capacidades.{clave}")

    faltantes += _validar_version_anterior(datos.get("version_anterior"))

    return faltantes


def _validar_confirmacion(datos: dict) -> list[str]:
    """Puerta de confianza de la entrevista (spec de Fase 1 §6.2), hecha comprobable
    (spec 2026-09-18, capacidad B, decision E1-E2). `seccion()` ya devuelve `{}`
    sobre un valor mal formado, asi que un `confirmacion = "si"` cae aqui igual
    que un bloque ausente -- una sola linea cubre las dos formas de faltar. Con
    validador propio (como `version_anterior`) porque su mensaje es de CAMPO
    (`confirmacion.usuario_confirmo: ...`), no de SECCION -- no encaja en la
    guarda generica de arriba, que solo sabe emitir `confirmacion: ...`.
    """
    confirmacion = seccion(datos, "confirmacion")
    if confirmacion.get("usuario_confirmo") is not True:
        return [
            "confirmacion.usuario_confirmo: tiene que ser `true` -- el usuario no ha "
            "confirmado el contrato con un \"si\" explicito; no se genera nada sin el "
            "(referencias/entrevista.md)"
        ]
    return []


def _validar_version_anterior(anterior) -> list[str]:
    """La linea base de R-F08, cuando el contrato la declara.

    Opcional a proposito: un plug-in que se estrena no tiene version anterior.
    Pero un bloque A MEDIAS es peor que ninguno — parece que hay contra que
    comparar y no lo hay, y la regla cuya factura paga produccion se queda
    callada creyendo que comparo. Se exige la forma exacta que lee R-F08:
    `key` hermana de `firma`, y `firma` con sus dos listas.
    """
    if anterior is None:
        return []
    if not isinstance(anterior, dict):
        return ["version_anterior: debe ser una seccion [version_anterior]"]

    faltantes: list[str] = []
    if not anterior.get("key"):
        faltantes.append(
            "version_anterior.key: la key de la version desplegada, HERMANA de la firma "
            "(es lo que R-F08 compara con plugin.key)"
        )
    firma = anterior.get("firma")
    if not isinstance(firma, dict):
        faltantes.append("version_anterior.firma: la seccion [version_anterior.firma] del dossier")
        return faltantes
    for lista in ("entradas", "salidas"):
        if not isinstance(firma.get(lista), list):
            faltantes.append(
                f"version_anterior.firma.{lista}: lista de «nombre:tipo», tal como la "
                f"congelo el dossier de la version anterior"
            )
    return faltantes


def main() -> int:
    import sys

    if len(sys.argv) != 2:
        print("uso: contrato.py <ruta-al-contrato.md>")
        return 2
    try:
        datos = cargar(pathlib.Path(sys.argv[1]))
    except ContratoIlegible as error:
        # Codigo 2, como el uso incorrecto: no hubo contrato que juzgar. El 1
        # queda para «se leyo y le falta algo».
        print(f"ERROR contrato: {error}")
        return 2
    faltantes = validar(datos)
    if faltantes:
        for f in faltantes:
            print(f"FALTA {f}")
        return 1
    propuesto = perfil_propuesto(seccion(datos, "capacidades"))
    declarado = datos["plugin"]["perfil"]
    print(f"OK contrato completo. Perfil declarado: {declarado}; propuesto por capacidades: {propuesto}")
    if propuesto == "riguroso" and declarado == "estandar":
        # El aviso dice ademas QUE VA A PASAR. Mientras solo «proponia», podia
        # leerse como opcional y el criterio de salida de la skill lo daba por
        # bueno: el contrato seguia declarando `estandar`, la verificacion lo
        # obedecia y las cuatro filas rigurosas no fallaban, DESAPARECIAN. Hoy
        # las sube `verificar_todo._resolver_perfil`, asi que ignorarlo no
        # abarata nada -- solo lo aparta de la vista de quien lee el contrato.
        print(
            "AVISO: las capacidades declaradas proponen perfil RIGUROSO (spec §2.3); "
            "la verificacion lo subira por su cuenta y el certificado dira por que"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
