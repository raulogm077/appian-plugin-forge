"""Capa 1B: politicas de AppMarket.

Son los criterios de aceptacion publicados por quien nos va a juzgar, asi que
cumplirlos SIEMPRE sale barato comparado con un ciclo de aprobacion de una
semana (spec D3).

Sobre bytecode, no sobre fuente: el proyecto de referencia hace la version de
fuente y tiene que partir los tokens ('Service' + 'Locator') para no delatarse
a si mismo — sintoma de que un escaner de fuente se evade con un nombre
cualificado o con reflexion.
"""

from __future__ import annotations

import re

from verificar_framework import Hallazgo

PREFIJO_APPIAN = "com.appiancorp."

TIPOS_SISTEMA_DE_FICHEROS = (
    "java.io.File",
    "java.io.FileInputStream",
    "java.io.FileOutputStream",
    "java.io.FileReader",
    "java.io.FileWriter",
    "java.io.RandomAccessFile",
    "java.nio.file.Files",
    "java.nio.file.Paths",
)
PREFIJOS_RED = ("java.net.", "javax.net.", "java.nio.channels.Socket")
TIPOS_RED_INOFENSIVOS = frozenset({"java.net.URLEncoder", "java.net.URLDecoder"})

PATRON_SECRETO = re.compile(
    r"(?i)(password|passwd|api[_-]?key|client[_-]?secret|token)\s*[:=]\s*\S{8,}"
)
MAJOR_ESPERADO = 61

# HEURISTICAS DECLARADAS. R-A02, R-A05 y R-A06 combinan «un tipo referenciado»
# con «una cadena del constant pool», y el analisis estatico a nivel de fichero
# no puede saber si las dos senales vienen de la MISMA llamada. Sus falsos
# positivos conocidos, para que nadie los descubra por sorpresa:
#   R-A02: una clase que use java.lang.System para algo inocuo (currentTimeMillis)
#          y ademas tenga un campo llamado «out» o «err».
#   R-A05: una clase que construya un java.util.Properties —con su setProperty—
#          y que ademas toque java.lang.System por otro motivo.
#   R-A06: java.lang.Class entra en el pool con cualquier getClass(), y el patron
#          de errores que la propia guia impone usa
#          `new SmartServiceException.Builder(getClass(), e)`. Basta entonces con
#          que exista una cadena literal «com.appiancorp.…» (por ejemplo en un
#          mensaje de log) para que salte sin haber reflexion.
# Se mantienen como error y no como aviso porque el coste de un falso negativo
# —un rechazo de AppMarket, una semana— supera al de un falso positivo, que el
# usuario resuelve renombrando o justificando. Pero la fragilidad se DECLARA
# aqui y en assets/reglas-de-validacion.md, en vez de quedar implicita.


def comprobar(clases: list, tipo_plugin: str, capacidades: dict) -> list[Hallazgo]:
    hallazgos: list[Hallazgo] = []

    for c in clases:
        tipos = c.tipos_referenciados
        cadenas = c.cadenas

        # R-A01 · ServiceLocator. En servlets SI es legitimo dentro de
        # doGet/doPost —el ejemplo oficial de Appian lo hace—; la regla es «no
        # en constructores» (auditoria §3.2). Como el analisis a nivel de
        # metodo queda fuera de alcance, en servlets se delega a la lente de
        # revision y aqui no se marca.
        # Se exige el prefijo de Appian: «Service Locator» es un nombre de
        # patron corriente en Java, y sin el prefijo una clase propia como
        # com.raul.util.DatabaseServiceLocator disparaba la regla en falso.
        if tipo_plugin != "servlet" and any(
            t.startswith(PREFIJO_APPIAN) and "ServiceLocator" in t for t in tipos
        ):
            hallazgos.append(
                Hallazgo("R-A01", "error",
                         f"{c.nombre_clase} usa ServiceLocator; en funciones y smart services los "
                         f"servicios se inyectan por constructor o parametro")
            )

        # R-A10 · el ServiceContext de Administrator esta prohibido por la
        # politica de AppMarket. Firma confirmada con javap sobre el JAR del
        # SDK 26.3: ServiceLocator.getAdministratorServiceContext() devuelve
        # com.appiancorp.services.ServiceContext. Los nombres de metodo si
        # llegan al constant pool, asi que la senal es fiable —a diferencia de
        # las heuristicas de R-A02/R-A05/R-A06, declaradas arriba—.
        for senal in ("getAdministratorServiceContext", "getAdministratorUser"):
            if any(senal in s for s in cadenas):
                hallazgos.append(
                    Hallazgo("R-A10", "error",
                             f"{c.nombre_clase} obtiene un contexto de Administrator ({senal}); "
                             f"AppMarket lo prohibe: el plug-in debe operar con el contexto del "
                             f"usuario que lo invoca")
                )

        # R-A02 y R-A03 · logging solo por Log4j.
        if "java.lang.System" in tipos and ("out" in cadenas or "err" in cadenas):
            hallazgos.append(
                Hallazgo("R-A02", "error",
                         f"{c.nombre_clase} parece usar System.out/System.err; el logging va por Log4j")
            )
        if any("printStackTrace" in s for s in cadenas):
            hallazgos.append(
                Hallazgo("R-A03", "error", f"{c.nombre_clase} usa printStackTrace(); el detalle va al log")
            )

        # R-A04 · el sistema de ficheros esta prohibido: ContentService y Document.
        for prohibido in TIPOS_SISTEMA_DE_FICHEROS:
            if prohibido in tipos:
                hallazgos.append(
                    Hallazgo("R-A04", "error",
                             f"{c.nombre_clase} accede al sistema de ficheros ({prohibido}); "
                             f"usar ContentService y Document")
                )

        # R-A05 · alterar configuracion global de la JVM.
        if "java.lang.System" in tipos and any("setProperty" in s for s in cadenas):
            hallazgos.append(
                Hallazgo("R-A05", "error",
                         f"{c.nombre_clase} usa System.setProperty(); prohibido alterar la JVM")
            )

        # R-A06 · reflexion sobre com.appiancorp: es el residuo que ningun
        # analisis estatico ve (spec R12), asi que se prohibe donde SI se puede
        # comprobar mecanicamente.
        if "java.lang.Class" in tipos and any(s.startswith("com.appiancorp.") for s in cadenas):
            hallazgos.append(
                Hallazgo("R-A06", "error",
                         f"{c.nombre_clase} parece cargar com.appiancorp.* por reflexion; "
                         f"prohibido: evade el escaner de superficie (spec R12)")
            )

        # R-A07 · la politica de red se deriva del CONTRATO, no esta fija en la
        # plantilla: java.net entero es correcto prohibirlo para un lector de
        # correo y falso para un plug-in que deba salir a la red (spec §3.7).
        if not capacidades.get("sale_a_la_red"):
            for t in sorted(tipos):
                if t.startswith(PREFIJOS_RED) and t not in TIPOS_RED_INOFENSIVOS:
                    hallazgos.append(
                        Hallazgo("R-A07", "error",
                                 f"{c.nombre_clase} usa {t} pero el contrato declara que el plug-in "
                                 f"no sale a la red")
                    )

        # R-A08 · sin credenciales embebidas -> Secure Credentials Store.
        for s in cadenas:
            if PATRON_SECRETO.search(s):
                hallazgos.append(
                    Hallazgo("R-A08", "error",
                             f"{c.nombre_clase} contiene un posible secreto embebido; las "
                             f"credenciales van al Secure Credentials Store")
                )
                break

        # R-A09 · bytecode verificado, no solo pedido (spec §5.3 capa 4).
        if c.major != MAJOR_ESPERADO:
            hallazgos.append(
                Hallazgo("R-A09", "error",
                         f"{c.nombre_clase} esta compilada a major {c.major}; se exige "
                         f"{MAJOR_ESPERADO} (Java 17, D12)")
            )

    return hallazgos


def main() -> int:
    import pathlib
    import sys

    import contrato
    import verificar_superficie

    if len(sys.argv) < 3:
        print("uso: verificar_appmarket.py <contrato.md> <dir-clases>")
        return 2
    datos = contrato.cargar(pathlib.Path(sys.argv[1]))
    clases = verificar_superficie.cargar_clases(pathlib.Path(sys.argv[2]))
    # Mismo verde vacuo que se corrigio en verificar_superficie: analizar CERO
    # clases no es verificar. Sin esto, las reglas que dependen del bytecode no
    # encuentran nada que reportar y la puerta sale verde sobre un proyecto sin
    # compilar. La guarda va aqui ademas de en verificar_superficie porque este
    # main() llama a cargar_clases() directamente, saltandose aquella.
    if not clases:
        print(f"ERROR no hay ninguna clase que analizar en {sys.argv[2]}: "
              f"¿se ha compilado el proyecto? Analizar cero clases NO es verificar.")
        return 1
    hallazgos = comprobar(clases, datos["plugin"]["tipo"], datos.get("capacidades", {}))
    # Se declara la portante aunque `clases` sea hoy la UNICA unidad y la regla
    # de «todas a cero» ya bastara: que baste es un accidente que se pierde en
    # silencio el dia que alguien anada una segunda unidad a esta linea. Las
    # diez reglas R-A son todas de bytecode; sin clases no puede disparar
    # ninguna, asi que cero aqui nunca es legitimo.
    return contrato.informar(
        hallazgos,
        insumo=contrato.linea_de_insumo(portante="clases", clases=len(clases)),
    )


if __name__ == "__main__":
    raise SystemExit(main())
