"""Capa 1C: bundles de recursos, locales y paridad de claves.

Es el bloqueante numero uno de la auditoria (§2.6): «Plug-ins without a
required resource bundle fail to deploy».

Dos convenios DISTINTOS segun el tipo, y confundirlos es facil —es justo el
error que cometio la guia (§7.11), que generalizo a los smart services el
convenio valido en las funciones—:

  Smart Service : name= , input.<Name>.displayName , input.<Name>.comment ,
                  output.<Name>.displayName , output.<Name>.comment
  Function      : function.<nombre>.description ,
                  function.<nombre>.param.<Param>.description

Y fuera de en_US solo se leen los mensajes de error (§7.10): un displayName
traducido NO se muestra.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import contrato
from verificar_framework import Hallazgo

LOCALE_POR_DEFECTO = "en_US"
PATRON_LOCALE = re.compile(r"_([a-z]{2}_[A-Z]{2})\.properties$")
# La MISMA definicion que usa el andamiador para escapar. Se importa en vez de
# repetirse: emisor y juez de R-B05 tienen que medir con la misma regla, o la
# puerta aprueba lo que el forge escribe mal, o reprueba escribiendolo bien.
PATRON_NO_ASCII = contrato.PATRON_NO_ASCII
PREFIJOS_QUE_VIAJAN_ENTRE_LOCALES = ("error.", "validation.")


def ruta_esperada(key: str, nombre_bundle: str, locale: str) -> str:
    # Delega en `contrato` a proposito: la MISMA cadena la construyen R-J06
    # sobre el JAR y `andamiar` al escribir. Tres copias de esta expresion es
    # justo como se coló la 1.0.0 de un plug-in real que no desplegaba.
    return contrato.ruta_de_bundle(key, nombre_bundle, locale)


def parsear_properties(texto: str) -> dict[str, str]:
    pares: dict[str, str] = {}
    for linea in texto.splitlines():
        limpia = linea.strip()
        if not limpia or limpia.startswith(("#", "!")):
            continue
        clave, sep, valor = limpia.partition("=")
        if sep:
            pares[clave.strip()] = valor.strip()
    return pares


def claves_de_salidas_horneadas() -> set[str]:
    """Las claves de las dos salidas que la plantilla de smart service declara
    siempre, las enumere o no el contrato.

    No entran en `claves_esperadas` --R-B03 no puede exigirselas a un bundle
    escrito a mano por un tercero-- pero tampoco son sobrantes: el `.java`
    genera `getErrorOccurred()`/`getErrorMessage()`, asi que Appian expone esos
    dos outputs y sus etiquetas son legitimas.
    """
    return {
        clave
        for nombre in contrato.SALIDAS_HORNEADAS
        for clave in contrato.claves_de_salida(nombre)
    }


def claves_esperadas(datos_contrato: dict) -> set[str]:
    tipo = datos_contrato["plugin"]["tipo"]
    esperadas: set[str] = set()
    if tipo == "smart-service":
        esperadas.add("name")
        for e in datos_contrato.get("entradas", []):
            esperadas.update(contrato.claves_de_entrada(e["nombre"]))
        for s in datos_contrato.get("salidas", []):
            esperadas.update(contrato.claves_de_salida(s["nombre"]))
    elif tipo in ("function", "writer-function"):
        # El MISMO fallback que usa el andamiador, no uno propio. Cuando cada
        # lado tenia el suyo —aqui `""`, alli `CLASE.lower()`—, R-B03 exigia
        # `function..description`, con doble punto, que ninguna plantilla
        # puede emitir: la puerta reprobaba el unico artefacto correcto.
        nombre = contrato.nombre_funcion(datos_contrato)
        esperadas.add(contrato.clave_de_funcion(nombre))
        for e in datos_contrato.get("entradas", []):
            esperadas.add(contrato.clave_de_parametro(nombre, e["nombre"]))
    return esperadas


def _con_sugerencia(clave: str, admitidas: set[str]) -> str:
    """`output.errorOccurred.displayName -> output.ErrorOccurred.displayName`.

    Casi siempre la clave sobrante es una admitida con otra caja, y decirlo
    ahorra la busqueda: el error se comete una letra a la vez.
    """
    por_minusculas = {a.lower(): a for a in admitidas}
    correcta = por_minusculas.get(clave.lower())
    return f"{clave} (¿{correcta}?)" if correcta and correcta != clave else clave


def _modulos_del_manifiesto(plugin: dict, bundles: dict[str, str],
                            manifiesto: str | None) -> list[Hallazgo]:
    """R-B07 · UN BUNDLE `_en_US` POR MODULO DEL MANIFIESTO, llamado como su key.

    Es la unica regla de esta capa que lee el MANIFIESTO y no el contrato, y por
    eso ve lo que ninguna otra puede ver. Appian resuelve el bundle de cada
    modulo como `<key del plug-in>.<key del modulo>`; con dos modulos hacen falta
    dos bundles, y el contrato --que describe UNO-- no tiene como saberlo. R-B01
    deriva su ruta de `bundle.nombre`, asi que sus dos lados salen del mismo dato
    y coinciden aunque el manifiesto diga otra cosa: el hueco exacto por el que un
    plug-in certificado READY_FOR_APPIAN_SUBMISSION murio al desplegar con
    «Module <k> is missing the following internationalization bundle(s) for Locale
    en_US: [<key>.<k>] (APNX-1-4200-000)».

    Vive en su propia funcion para que su POSICION no dependa de donde este
    escrita: la llama `comprobar` antes de cualquier `return`, incluido el de la
    exencion de los servlets. Los dos cortes de este fichero --el de servlet, por
    el tipo del contrato, y el de R-B01, por el bundle que falta-- se han llevado
    por delante a otras reglas cuatro veces ya.
    """
    hallazgos: list[Hallazgo] = []
    if manifiesto is None:
        return hallazgos
    modulos: list[tuple[str, str]] = []
    if not manifiesto.strip():
        # Fichero ausente o vacio. Se dice UNA vez y con el motivo real: parsear
        # la cadena vacia daria ademas un ParseError que se lee como «XML
        # corrupto» y manda a arreglar lo que no esta roto.
        hallazgos.append(
            Hallazgo("R-B07", "error",
                     "no hay appian-plugin.xml junto a los recursos; sin manifiesto no se "
                     "sabe que modulos declara el plug-in ni cuantos bundles hacen falta")
        )
        return hallazgos
    try:
        modulos = contrato.modulos_con_bundle(manifiesto)
    except ET.ParseError as error:
        hallazgos.append(
            Hallazgo("R-B07", "error",
                     f"no se puede leer appian-plugin.xml para saber que modulos declara "
                     f"({error})")
        )
        return hallazgos
    for etiqueta, key_modulo in modulos:
        if not key_modulo:
            hallazgos.append(
                Hallazgo("R-B07", "error",
                         f"el manifiesto declara un <{etiqueta}> sin atributo key; Appian "
                         f"busca su bundle por esa key")
            )
            continue
        ruta_modulo = contrato.ruta_de_bundle(plugin["key"], key_modulo, LOCALE_POR_DEFECTO)
        if ruta_modulo not in bundles:
            hallazgos.append(
                Hallazgo("R-B07", "error",
                         f"el modulo <{etiqueta} key=\"{key_modulo}\"> no tiene su bundle "
                         f"{ruta_modulo}; Appian lo busca como "
                         f"«{plugin['key']}.{key_modulo}». El bundle se llama como la key "
                         f"del MODULO, no como la funcion ni como el plug-in. "
                         f"{contrato.procedencia_de_modulo(etiqueta)}")
            )
    return hallazgos


def comprobar(datos_contrato: dict, bundles: dict[str, str],
              manifiesto: str | None = None) -> list[Hallazgo]:
    """`manifiesto=None` sigue el convenio de `verificar_framework.comprobar`:
    es «no me han dado el fichero» y salta R-B07, para que una llamada unitaria
    que solo ejerce otra regla no tenga que fabricar un XML. Desde `main()`
    llega SIEMPRE una cadena, aunque el fichero no exista --y entonces R-B07
    dice que no ha podido mirar, que no es lo mismo que aprobar--.
    """
    hallazgos: list[Hallazgo] = []
    plugin = datos_contrato["plugin"]
    tipo = plugin["tipo"]
    nombre_bundle = datos_contrato.get("bundle", {}).get("nombre", "")

    # OJO CON EL ORDEN: este `return` sale del TIPO DECLARADO EN EL CONTRATO, y
    # R-B07 pregunta por los modulos que declara el MANIFIESTO. Un contrato
    # `servlet` cuyo XML declare ademas un `<function>` o un `<function-category>`
    # se llevaba la capa entera sin mirar nada. El tipo del contrato no manda
    # sobre lo que el manifiesto dice.
    hallazgos += _modulos_del_manifiesto(plugin, bundles, manifiesto)

    if tipo == "servlet":
        # La exencion sigue valiendo para SU modulo: el name y la description de
        # un servlet son atributos de `<servlet>`, no claves de un `.properties`.
        return hallazgos

    ruta_en_us = ruta_esperada(plugin["key"], nombre_bundle, LOCALE_POR_DEFECTO)

    # R-B05 · acentos en Unicode escapado, como exige la documentacion.
    #
    # LO PRIMERO, y esa posicion es la regla. Vivia dentro del bucle de R-B04,
    # que empieza con `continue` sobre el `en_US` canonico —porque R-B04 solo
    # habla de los OTROS locales—, asi que el unico fichero del que Appian saca
    # los textos de display, y el unico cuyo mojibake ve un usuario, no llegaba
    # nunca a esta regla. El ciclo 17 lo midio por tres vias independientes.
    #
    # Sacarlo de aquel bucle no bastaba: quedaba por debajo del `return` de
    # R-B01, asi que un `[bundle].nombre` renombrado sin renombrar el fichero
    # --o cualquier otra ruta que no case-- volvia antes de mirar la
    # codificacion de NINGUN bundle, y los `_es_ES` escritos a mano con la tilde
    # cruda no recibian aviso hasta que se arreglara R-B01. Mismo defecto por
    # tercera vez: el alcance de la regla fijado por un control de flujo ajeno.
    # No necesita nada de lo que se calcula debajo, asi que va delante de todo.
    #
    # Leccion, porque costo dos ciclos: la exencion no estaba donde ponia. Se
    # cambio el predicado (`es_bundle_traducido` -> `es_bundle`) creyendo que
    # ahi vivia, y se escribio en tres sitios que emisor y juez ya compartian
    # alcance. Era falso: en el juez el predicado es SIEMPRE cierto —los
    # bundles llegan de un `rglob("*.properties")`— y quien fijaba el alcance
    # de verdad era el `continue`. Un predicado compartido no hace simetrica una
    # comprobacion si cada lado la evalua sobre un conjunto distinto.
    for ruta, contenido in sorted(bundles.items()):
        if PATRON_NO_ASCII.search(contenido):
            hallazgos.append(
                Hallazgo("R-B05", "aviso",
                         f"{ruta} contiene caracteres no ASCII sin escapar; los acentos van en "
                         f"Unicode escapado (\\u00ed)")
            )

    # R-B01, primera mitad · sufijo de locale. AQUI ARRIBA por la misma razon
    # que R-B05, y es la CUARTA vez que esta funcion se cobra la misma pieza.
    #
    # Vivia dentro del bucle de R-B04, o sea por debajo del `return` de la OTRA
    # mitad de R-B01 --la que exige el `_en_US`--, asi que un proyecto sin
    # `_en_US` canonico se llevaba «falta el bundle obligatorio» y nunca se
    # enteraba de que ademas tiene ficheros sin sufijo de locale. Los descubria
    # despues, al arreglar lo primero. R-B01 se cegaba a si misma.
    #
    # Y su test estaba VERDE POR LA RAMA EQUIVOCADA: montaba un caso SIN
    # `_en_US` canonico y asertaba sobre el identificador `R-B01`, que las dos
    # mitades emiten. Pasaba por «falta el bundle obligatorio» y la
    # comprobacion que le da nombre no se ejecutaba nunca. Medido: desactivando
    # el predicado de sufijo, el test seguia pasando.
    #
    # El criterio que emerge, y que vale para la regla que se anada manana: el
    # `return` de R-B01 va DESPUES de todo lo que no dependa de lo que ese
    # return guarda. Arriba, lo que solo mira el CONJUNTO DE FICHEROS --R-B05
    # (contenido crudo) y esto (la ruta)--; abajo, lo que necesita las claves
    # parseadas del `_en_US`. La posicion deja de ser un accidente y pasa a ser
    # esa particion. Lo levanto la lente de altitud del ciclo 18.
    for ruta in sorted(bundles):
        if ruta != ruta_en_us and not PATRON_LOCALE.search(ruta):
            hallazgos.append(
                Hallazgo("R-B01", "error",
                         f"{ruta} no lleva sufijo de locale (<clave>_<locale>.properties)")
            )

    # R-B01, segunda mitad · el bundle _en_US es OBLIGATORIO y va en la ruta que sale de la key.
    if ruta_en_us not in bundles:
        hallazgos.append(
            Hallazgo("R-B01", "error",
                     f"falta el bundle obligatorio {ruta_en_us}; sin el, el plug-in NO despliega "
                     f"(auditoria §2.6). Presentes: {sorted(bundles) or 'ninguno'}")
        )
        return hallazgos

    pares_en_us = parsear_properties(bundles[ruta_en_us])
    esperadas = claves_esperadas(datos_contrato)

    # R-B02 · convenio equivocado para el tipo.
    if tipo == "smart-service":
        # Se casa por PREFIJO, nunca por el sufijo «.description»: las claves
        # error.* y validation.* pueden acabar en «.description» de forma
        # perfectamente legitima (p.ej. `error.io.description`), y son justo
        # las que R-B04 exige. Casar por sufijo hacia que dos reglas del mismo
        # validador se contradijeran.
        # `smartservice.` es el prefijo erroneo de la guia; `function.` es el
        # convenio de las funciones colandose donde no toca.
        intrusas = [k for k in pares_en_us if k.startswith(("smartservice.", "function."))]
        if intrusas:
            hallazgos.append(
                Hallazgo("R-B02", "error",
                         f"{ruta_en_us} usa el convenio de Function en un smart service "
                         f"({sorted(intrusas)[:3]}…); lo correcto es input.<Name>.displayName y "
                         f".comment sin prefijo (auditoria §2.6 y §7.11)")
            )
    else:
        intrusas = [k for k in pares_en_us if k.startswith(("input.", "output.", "smartservice."))]
        if intrusas:
            hallazgos.append(
                Hallazgo("R-B02", "error",
                         f"{ruta_en_us} usa el convenio de Smart Service en una funcion "
                         f"({sorted(intrusas)[:3]}…); lo correcto es function.<n>.description "
                         f"(auditoria §7.11)")
            )

    # R-B03 · claves obligatorias del tipo, ausentes.
    faltan = sorted(esperadas - set(pares_en_us))
    if faltan:
        hallazgos.append(
            Hallazgo("R-B03", "error", f"{ruta_en_us} no declara las claves obligatorias: {faltan}")
        )

    # R-B06 · claves input./output. que no corresponden a NINGUN input u output
    # real. R-B03 compara `esperadas - presentes`: mira solo lo que falta.
    # Nada miraba lo que SOBRA, y por ese hueco se colo un defecto real de la
    # plantilla de smart service: horneaba `output.errorOccurred.displayName`
    # mientras la clase declara `getErrorOccurred()`, y Appian lee el nombre
    # del ACCESOR (contrato.identificador_java). Resultado: los dos outputs de
    # error se quedaban SIN ETIQUETA en el Process Modeler, y las cuatro capas
    # lo daban por bueno --no faltaba ninguna clave esperada, y la sobrante no
    # casa con ningun prefijo prohibido de R-B02--.
    # El plug-in aprobado por la revision real de Appian las escribe en
    # PascalCase (`output.ErrorOccurred.displayName`), que es la evidencia
    # externa que zanja cual de las dos cajas es la correcta.
    if tipo == "smart-service":
        admitidas = esperadas | claves_de_salidas_horneadas()
        sobrantes = sorted(
            k for k in pares_en_us
            if k.startswith(("input.", "output.")) and k not in admitidas
        )
        if sobrantes:
            hallazgos.append(
                Hallazgo("R-B06", "error",
                         f"{ruta_en_us} declara claves que no corresponden a ninguna entrada ni "
                         f"salida: {[_con_sugerencia(k, admitidas) for k in sobrantes[:3]]}"
                         f"{'…' if len(sobrantes) > 3 else ''}. Appian lee el nombre del accesor, "
                         f"asi que una clave que no case con el no etiqueta nada")
            )

    # R-B04 · paridad de error.* y validation.* en los demas locales: son las
    # UNICAS que Appian lee fuera de en_US (auditoria §7.10). Un locale sin
    # paridad muestra la clave literal al usuario (spec R18).
    claves_que_viajan = {
        k for k in pares_en_us if k.startswith(PREFIJOS_QUE_VIAJAN_ENTRE_LOCALES)
    }
    for ruta, contenido in sorted(bundles.items()):
        if ruta == ruta_en_us:
            continue
        # El sufijo ya lo juzgo el bucle de arriba; aqui solo se salta lo que no
        # lo tiene, sin volver a reportarlo.
        if not PATRON_LOCALE.search(ruta):
            continue
        pares = parsear_properties(contenido)
        faltan_aqui = sorted(claves_que_viajan - set(pares))
        if faltan_aqui:
            hallazgos.append(
                Hallazgo("R-B04", "error",
                         f"{ruta} no tiene paridad de claves error.*/validation.* con en_US; "
                         f"faltan {faltan_aqui}. Son las unicas que Appian lee fuera de en_US "
                         f"(auditoria §7.10)")
            )
    return hallazgos


def main() -> int:
    import pathlib
    import sys

    if len(sys.argv) < 3:
        print("uso: verificar_bundles.py <contrato.md> <dir-resources>")
        return 2
    datos = contrato.cargar(pathlib.Path(sys.argv[1]))
    raiz = pathlib.Path(sys.argv[2])
    # `leer_utf8`: un `.properties` guardado desde PowerShell con `>` sale en
    # UTF-16 y la traza no dice que hacer; el mensaje de `leer_utf8` si.
    bundles = {
        str(p.relative_to(raiz)).replace("\\", "/"): contrato.leer_utf8(p)
        for p in raiz.rglob("*.properties")
    }
    # Siempre una cadena, exista o no el fichero: «no he podido mirar» es un
    # hallazgo de R-B07, no un silencio.
    ruta_manifiesto = raiz / "appian-plugin.xml"
    manifiesto = contrato.leer_utf8(ruta_manifiesto) if ruta_manifiesto.is_file() else ""
    if datos["plugin"]["tipo"] == "servlet":
        # Su name/description van como atributos del manifiesto, no en un
        # .properties (nota de alcance de la capa 1C). Decirlo es mas honesto
        # que aprobar sin haber mirado nada.
        print(contrato.linea_no_aplica(
            "plugin.tipo", "servlet", "los servlets no cargan bundle de recursos"
        ))
    hallazgos = comprobar(datos, bundles, manifiesto)
    modulos_declarados = 0
    if manifiesto.strip():
        try:
            modulos_declarados = len(contrato.modulos_con_bundle(manifiesto))
        except ET.ParseError:
            modulos_declarados = 0
    print(contrato.linea_de_insumo(
        bundles=len(bundles), claves_esperadas=len(claves_esperadas(datos)),
        modulos_declarados=modulos_declarados,
        # La portante es `claves_esperadas`, no `bundles`: cero claves es el
        # validador comparando ficheros REALES contra cero expectativas y
        # dandose la razon a si mismo. Cero bundles, en cambio, ya lo
        # reprueban las reglas R-B por su cuenta.
        portante="claves_esperadas",
    ))
    return contrato.informar(hallazgos)


if __name__ == "__main__":
    raise SystemExit(main())
