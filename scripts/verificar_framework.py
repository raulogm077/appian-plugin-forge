"""Capa 1A: reglas del framework de Appian.

Cada regla sale de un error CONFIRMADO en docs/auditoria-guia-vs-documentacion-appian.md.
El identificador R-Fnn se cita en el certificado y en assets/reglas-de-validacion.md,
donde cada regla lleva su fuente oficial.
"""

from __future__ import annotations

import dataclasses
import re
import xml.etree.ElementTree as ET

import contrato

# Solo cuatro valores son validos en 26.x; el SDK expone siete y tres se
# remapean en silencio (auditoria §2.5). «Hidden» y «#Deprecated#» se admiten
# las dos: la documentacion nombra la primera y su unico ejemplo usa la
# segunda, y rechazar la buena por adivinar mal seria peor que aceptar una de
# mas —el efecto de acertar es cosmetico y el de fallar es un rechazo en falso—.
PALETAS_VALIDAS = frozenset(
    {"Workflow", "Automation Smart Services", "Deprecated Services", "Hidden", "#Deprecated#"}
)
PALETAS_REMAPEADAS = frozenset({"Appian Smart Services", "Standard Nodes", "Integration Services"})

# Las anotaciones de conveniencia hacen imposible por construccion el error de
# la categoria... PERO SOLO 17 DE LAS 32. Comprobado con `javap -v` sobre el
# SDK 26.3, anotacion por anotacion: cada una lleva su par (categoria, paleta)
# horneado en una meta-anotacion @PaletteInfo propia, y quince de ellas hornean
# justo uno de los tres valores que Appian remapea en silencio. Ejemplos reales:
#   @DocumentManagement -> paletteCategory="Appian Smart Services"  (invalida)
#   @Activities         -> paletteCategory="Standard Nodes"         (invalida)
#   @DataServices       -> paletteCategory="Integration Services"   (invalida)
# frente a
#   @AutomationSmartServicesDocumentManagement -> "Automation Smart Services"
#
# Y ESTA REGLA NO PODIA VERLO: la cadena de la categoria vive dentro del .class
# de la anotacion, en el SDK, que es `compileOnly` y el escaner nunca lee. En el
# bytecode del plug-in solo aparece el NOMBRE de la anotacion. Por eso se
# comprueba el nombre.
#
# El criterio es por prefijo, no una lista enumerada, y cubre exactamente las 17
# seguras sin dejar pasar ninguna de las 15 inseguras. Ademas falla del lado
# seguro: una anotacion nueva en un SDK futuro se marcaria en vez de colarse.
PREFIJOS_PALETA_SEGUROS = ("AutomationSmartServices", "Workflow")
PALETAS_SEGURAS_SUELTAS = frozenset({"ForumManagement"})  # -> "Deprecated Services", valida
PATRON_ANOTACION_PALETA = re.compile(
    r"com/appiancorp/suiteapi/process/palette/(\w+)"
)

PRIMITIVOS = frozenset({"byte", "short", "int", "long", "float", "double", "boolean", "char"})
TIPOS_NO_INFERIBLES = frozenset(
    {"byte", "char", "short", "float", "Currency", "java.util.Date", "Date"}
)

VERSION_MINIMA_USE_KEYWORDS = (26, 1)


@dataclasses.dataclass
class Hallazgo:
    regla: str
    severidad: str
    mensaje: str


# R-F14 · los dos ajustes que el andamiaje fija para que SpotBugs pueda decir
# que no. No son preferencias de estilo: son el interruptor de la puerta.
# `ignoreFailures = true` la apaga entera, y subir `reportLevel` la deja
# encendida pero ciega, las dos SIN tocar una sola linea de codigo del plug-in
# y con cara de configuracion legitima.
AJUSTES_SPOTBUGS = (
    ("ignoreFailures", re.compile(r"ignoreFailures\s*=\s*(\w+)"), "false"),
    ("reportLevel", re.compile(r"reportLevel\s*=\s*Confidence\.valueOf\(\s*'(\w+)'\s*\)"), "LOW"),
)

# Los dos patrones de FindSecBugs que un servlet recien andamiado dispara por
# oficio y que `andamiar.py` deja COMENTADOS a proposito: la plantilla no puede
# afirmar que el valor se trate con seguridad, porque eso solo lo sabe quien
# escriba `ejecutar()`.
PATRONES_ABIERTOS_EN_SERVLET = frozenset({"SERVLET_PARAMETER", "SECSP"})


def _version_tupla(texto: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", texto)[:2]) or (0,)


def comprobar_guardarrailes(tipo: str, gradle: str, exclusiones: str,
                            decisiones: str) -> list[Hallazgo]:
    """R-F14 · la cadena de verificacion no se debilita para que el build pase.

    Las demas reglas miran el plug-in. Esta mira LA PUERTA, porque el resto del
    sistema descansa en que siga encendida y hasta ahora nadie lo comprobaba:
    `SKILL.md` lo prohibe por escrito --«ni relajar reportLevel ni
    ignoreFailures»-- y el andamiaje deja la exclusion de `SECSP` comentada,
    pero ninguna de las cuatro capas volvia a mirar esos tres sitios. En dos
    pruebas E2E independientes del 19-sep-2026, con dos tipos de plug-in
    distintos, el ejecutor acabo haciendo justo eso para sacar un
    `BUILD SUCCESSFUL`: uno subio `reportLevel` a MEDIUM y otro descomento
    `SECSP` con un motivo inventado, antes de escribir `ejecutar()`.

    Activar la exclusion NO se prohibe --es una decision legitima una vez
    escrito `ejecutar()`-- pero deja de ser gratis: hay que firmarla en
    `docs/decisiones.md`, que es la pieza 2 del dossier y el sitio donde el
    paso 6 la va a leer. Lo que esta regla impide es hacerlo en silencio.
    """
    hallazgos: list[Hallazgo] = []
    for nombre, patron, esperado in AJUSTES_SPOTBUGS:
        # TODAS las apariciones, no la primera: el bloque original puede
        # quedarse intacto y anadirse otro debajo que lo pise --que es como se
        # relaja una configuracion sin que el diff parezca que la relaja--.
        valores = patron.findall(gradle)
        if not valores:
            hallazgos.append(
                Hallazgo("R-F14", "error",
                         f"{nombre} no aparece en build.gradle: el andamiaje lo fija en "
                         f"«{esperado}» y sin el la puerta de SpotBugs no puede fallar")
            )
        elif any(v != esperado for v in valores):
            malos = ", ".join(sorted({v for v in valores if v != esperado}))
            hallazgos.append(
                Hallazgo("R-F14", "error",
                         f"{nombre} = {malos} en build.gradle, y el andamiaje lo "
                         f"fija en «{esperado}»: relajarlo apaga la puerta de SpotBugs sin tocar "
                         f"el codigo. Si un patron concreto sobra, se excluye ESE patron en "
                         f"config/spotbugs/exclude.xml con su motivo al lado")
            )
    if tipo != "servlet" or not exclusiones.strip():
        return hallazgos
    try:
        # Los `<Match>` COMENTADOS no sobreviven al parseo, que es justo lo que
        # hace falta: el andamiaje deja el de SECSP dentro de un comentario.
        raiz = ET.fromstring(exclusiones)
    except ET.ParseError as error:
        hallazgos.append(
            Hallazgo("R-F14", "error",
                     f"config/spotbugs/exclude.xml no es XML valido ({error}): SpotBugs no "
                     f"aplicaria ninguna exclusion y nadie lo diria")
        )
        return hallazgos
    activos = {
        bug.get("pattern", "")
        for bug in raiz.iter("Bug")
    } & PATRONES_ABIERTOS_EN_SERVLET
    if activos and not any(p in decisiones for p in activos):
        hallazgos.append(
            Hallazgo("R-F14", "error",
                     f"exclude.xml activa {', '.join(sorted(activos))} y docs/decisiones.md no "
                     f"lo menciona. El andamiaje la deja comentada a proposito: solo quien "
                     f"escribio `ejecutar()` sabe si el valor se trata con seguridad. Si ya lo "
                     f"decidiste, escribe la decision --es la pieza 2 del dossier--; si aun no, "
                     f"vuelve a comentarla y deja la puerta en rojo, que es la verdad")
        )
    return hallazgos


def comprobar(datos_contrato: dict, xml_manifiesto: str, clases: list, *,
              gradle: str | None = None, exclusiones: str = "",
              decisiones: str = "") -> list[Hallazgo]:
    """`gradle=None` significa «no me han dado el fichero» y salta R-F14; un
    `build.gradle` vacio o sin los ajustes SI es un hallazgo. Son cosas
    distintas y confundirlas tenia un lado barato y otro caro: las llamadas
    unitarias que solo ejercen otras reglas no tienen que fabricar un
    `build.gradle`, y un proyecto real al que le falte no se escapa --`main()`
    siempre pasa una cadena, aunque el fichero no exista--.
    """
    hallazgos: list[Hallazgo] = []
    plugin = datos_contrato.get("plugin", {})
    tipo = plugin.get("tipo", "")
    entradas = datos_contrato.get("entradas", [])
    salidas = datos_contrato.get("salidas", [])
    cadenas = set()
    for c in clases:
        cadenas |= c.cadenas

    # R-F13 · el andamiaje sin implementar NO puede certificarse.
    #
    # Es el agujero mas caro que ha tenido este sistema, y no hacia falta mala
    # fe para caer en el: un proyecto recien andamiado mas UN test trivial
    # --que es exactamente el paso siguiente que pide la SKILL-- construia con
    # BUILD SUCCESSFUL y sacaba STATUS: READY_FOR_APPIAN_SUBMISSION, con cero
    # motivos que lo impidieran. El `ejecutar()` que ese certificado declaraba
    # listo para enviar a Appian no hacia nada: lanzaba
    # UnsupportedOperationException.
    #
    # Ninguna de las doce puertas anteriores miraba si el plug-in HACE algo.
    # Medían el tamano del insumo, no que el trabajo existiera, y sobre un
    # andamiaje la unica puerta que lo frenaba era «0 tests»: un test de una
    # linea la volcaba a verde.
    #
    # La marca vive en `contrato.MARCAS_SIN_IMPLEMENTAR`, compartida con las
    # plantillas que la escriben: si divergieran, esta regla dejaria de
    # disparar y nadie se enteraria.
    for marca in contrato.MARCAS_SIN_IMPLEMENTAR:
        if any(marca in c for c in cadenas):
            hallazgos.append(
                Hallazgo("R-F13", "error",
                         f"el cuerpo sigue siendo el del andamiaje: el bytecode contiene "
                         f"«{marca}», asi que el metodo lanza UnsupportedOperationException en "
                         f"vez de hacer lo que dice el contrato. Un plug-in que no puede "
                         f"ejecutarse no es un plug-in, y enviarlo cuesta un ciclo de aprobacion")
            )
            break

    # R-F01 · paleta remapeada en silencio. Se mira el VALOR EFECTIVO, no que
    # venga de una constante del SDK: escribir PaletteCategoryConstants.
    # APPIAN_SMART_SERVICES produce exactamente el mismo error.
    for remapeada in PALETAS_REMAPEADAS:
        if remapeada in cadenas:
            hallazgos.append(
                Hallazgo("R-F01", "error",
                         f"paletteCategory «{remapeada}» se remapea en silencio a "
                         f"«Automation Smart Services» en 26.x (auditoria §2.5). "
                         f"Validos: {sorted(PALETAS_VALIDAS)}")
            )

    # R-F01b · la anotacion de conveniencia, por NOMBRE. Ver el bloque de
    # constantes: quince de las treinta y dos hornean una categoria invalida, y
    # la cadena horneada no llega al bytecode del plug-in, asi que la
    # comprobacion de arriba no puede verlas.
    for s in sorted(cadenas):
        for nombre in PATRON_ANOTACION_PALETA.findall(s):
            if nombre.startswith(PREFIJOS_PALETA_SEGUROS) or nombre in PALETAS_SEGURAS_SUELTAS:
                continue
            if nombre in ("PaletteInfo", "PaletteCategoryConstants", "PaletteConstants"):
                continue
            hallazgos.append(
                Hallazgo("R-F01", "error",
                         f"la anotacion de paleta @{nombre} lleva horneada una categoria que "
                         f"Appian remapea en silencio en 26.x. Usar una de la familia "
                         f"@AutomationSmartServices… o @Workflow…, que son las que fijan una "
                         f"categoria valida (comprobado con javap sobre el SDK 26.3)")
            )

    # R-F02 · un primitivo no admite null: para opcional, wrapper.
    #
    # SOLO en smart services: `Required` es del framework de proceso y no
    # existe en una function, cuyos parametros no lo declaran en absoluto. Sin
    # acotar, la regla disparaba sobre todo contrato de function con un
    # parametro primitivo y le exigia un `ALWAYS` que su plantilla no puede
    # emitir — reprochandole no cumplir algo que no le aplica.
    for e in entradas if tipo == "smart-service" else ():
        if e.get("tipo_java") in PRIMITIVOS and e.get("required") != "ALWAYS":
            hallazgos.append(
                Hallazgo("R-F02", "error",
                         f"la entrada «{e['nombre']}» es primitiva ({e['tipo_java']}) y no es "
                         f"Required.ALWAYS; un primitivo no admite null (auditoria §2.8)")
            )

    # R-F03 · unicidad de nombres, o falla el despliegue.
    nombres = [e.get("nombre") for e in entradas] + [s.get("nombre") for s in salidas]
    repetidos = {n for n in nombres if nombres.count(n) > 1}
    for n in sorted(repetidos):
        hallazgos.append(
            Hallazgo("R-F03", "error",
                     f"el nombre «{n}» se repite entre entradas y salidas; deben ser unicos "
                     f"o falla el despliegue (auditoria §2.8)")
        )

    # R-F03 (segunda mitad) · unicidad TAMBIEN contra los nombres que la
    # plantilla hornea. La regla comparaba los nombres del contrato entre si y
    # nunca contra los reservados, asi que `ErrorOccurred: String` producia un
    # `getErrorOccurred()` duplicado y el fallo salia en `javac`, no aqui.
    # Con el tipo correcto NO es colision: se mapea sobre el miembro horneado,
    # y asi lo declara el plug-in aprobado del AppMarket.
    if tipo == "smart-service":
        for s in salidas:
            if contrato.colision_con_horneada(s):
                esperado = contrato.SALIDAS_HORNEADAS[s["nombre"]]
                hallazgos.append(
                    Hallazgo("R-F03", "error",
                             f"la salida «{s['nombre']}» choca con el miembro que la plantilla "
                             f"ya declara, que es de tipo {esperado} y no {s.get('tipo_java')}: "
                             f"el .java saldria con el getter duplicado. Usar {esperado}, o "
                             f"renombrar la salida")
                )

    # R-F04 · tipos no soportados para inferencia.
    for campo in (*entradas, *salidas):
        if campo.get("tipo_java") in TIPOS_NO_INFERIBLES:
            hallazgos.append(
                Hallazgo("R-F04", "error",
                         f"«{campo['nombre']}» usa {campo['tipo_java']}, que Appian no infiere; "
                         f"para fechas usar java.sql.Date/Time/Timestamp (auditoria §2.8)")
            )

    # R-F05 · useKeywords solo surte efecto desde 26.1.
    if "useKeywords" in cadenas:
        if _version_tupla(plugin.get("application_version_min", "0")) < VERSION_MINIMA_USE_KEYWORDS:
            hallazgos.append(
                Hallazgo("R-F05", "error",
                         f"useKeywords = true solo surte efecto desde Appian 26.1, pero "
                         f"application-version min es {plugin.get('application_version_min')} "
                         f"(auditoria §1.2)")
            )

    # R-F06 · metodos sobrecargados: solo cuenta el primero.
    if tipo in ("function", "writer-function"):
        for c in clases:
            # El punto final delimita el segmento: sin el, el paquete hermano
            # `com.raul.appianhelper` casaria con `com.raul.appian`.
            if not c.nombre_clase.startswith(plugin.get("paquete", "\0") + "."):
                continue
            vistos: set[str] = set()
            for m in c.metodos:
                if m.nombre in ("<init>", "<clinit>"):
                    continue
                if m.nombre in vistos:
                    hallazgos.append(
                        Hallazgo("R-F06", "error",
                                 f"{c.nombre_clase}.{m.nombre} esta sobrecargado; Appian solo "
                                 f"tiene en cuenta el primero (auditoria §2.8)")
                    )
                vistos.add(m.nombre)

    # R-F07 · new InitialContext() siempre falla contra fuentes del Admin Console.
    if any("InitialContext" in s for s in cadenas):
        hallazgos.append(
            Hallazgo("R-F07", "error",
                     "new InitialContext() falla contra las fuentes de datos del Admin Console; "
                     "javax.naming.Context se inyecta por constructor (auditoria §2.8)")
        )

    # R-F08 · LA REGLA CON PEOR CONSECUENCIA: cambiar inputs u outputs sin clave
    # nueva rompe procesos VIVOS en produccion (auditoria §7.4).
    anterior = datos_contrato.get("version_anterior") or {}
    if anterior.get("firma"):
        # La firma compara nombre Y TIPO, no solo el nombre: cambiar
        # `doc: Long` por `doc: String` es un cambio de input a todos los
        # efectos y rompe igual los procesos vivos. Comparar solo nombres
        # dejaba un falso negativo justo en la regla mas cara del sistema.
        antes_e = list(anterior["firma"].get("entradas", []))
        antes_s = list(anterior["firma"].get("salidas", []))
        ahora_e = [f"{e.get('nombre')}:{e.get('tipo_java')}" for e in entradas]
        ahora_s = [f"{s.get('nombre')}:{s.get('tipo_java')}" for s in salidas]
        if (antes_e != ahora_e or antes_s != ahora_s) and anterior.get("key") == plugin.get("key"):
            hallazgos.append(
                Hallazgo("R-F08", "error",
                         "cambian inputs u outputs respecto de la version desplegada y se "
                         "reutiliza la misma key: hace falta clave nueva y clase o paquete "
                         "distintos, y deprecar la anterior. Sobrescribir puede ROMPER "
                         "procesos vivos (auditoria §7.4)")
            )

    if xml_manifiesto:
        # R-F09 · ningun ejemplo oficial declara xmlns (auditoria §3.3).
        if "xmlns" in xml_manifiesto:
            hallazgos.append(
                Hallazgo("R-F09", "aviso",
                         "el manifiesto declara xmlns; ningun appian-plugin.xml oficial lo usa "
                         "y no se localizo XSD publicado (auditoria §3.3)")
            )
        raiz = ET.fromstring(xml_manifiesto)
        # R-F10 · el paquete no puede ser de Appian (politica de AppMarket, se
        # comprueba aqui porque el dato esta en el contrato).
        if plugin.get("paquete", "").startswith(("com.appiancorp.", "com.appian.")):
            hallazgos.append(
                Hallazgo("R-F10", "error",
                         f"el paquete «{plugin['paquete']}» no puede empezar por com.appiancorp. "
                         f"ni com.appian. (auditoria §3.5)")
            )
        # R-F11 · la key del manifiesto debe ser la del contrato.
        if raiz.get("key") != plugin.get("key"):
            hallazgos.append(
                Hallazgo("R-F11", "error",
                         f"la key del manifiesto «{raiz.get('key')}» no coincide con la del "
                         f"contrato «{plugin.get('key')}»")
            )
        # R-F12 · coherencia cruzada contrato <-> manifiesto: la clase declarada.
        clase_esperada = datos_contrato.get("clase", {}).get("nombre")
        clases_xml = [el.get("class", "") for el in raiz.iter() if el.get("class")]
        if clase_esperada and not any(c.endswith("." + clase_esperada) for c in clases_xml):
            hallazgos.append(
                Hallazgo("R-F12", "error",
                         f"el manifiesto no declara la clase «{clase_esperada}» del contrato; "
                         f"declara {clases_xml}")
            )

    if gradle is not None:
        hallazgos += comprobar_guardarrailes(tipo, gradle, exclusiones, decisiones)

    return hallazgos


def main() -> int:
    import pathlib
    import sys

    import contrato
    import verificar_superficie

    # La raiz es OBLIGATORIA, y no por comodidad: de ella salen los tres
    # ficheros de R-F14. Si fuera opcional, un orquestador que dejara de
    # pasarla apagaria la regla sin que nadie lo notara --exactamente el modo
    # de fallo que R-F14 existe para impedir--.
    if len(sys.argv) < 5:
        print("uso: verificar_framework.py <contrato.md> <appian-plugin.xml> <dir-clases> "
              "<raiz-proyecto>")
        return 2
    datos = contrato.cargar(pathlib.Path(sys.argv[1]))
    xml = pathlib.Path(sys.argv[2]).read_text(encoding="utf-8")
    clases = verificar_superficie.cargar_clases(pathlib.Path(sys.argv[3]))
    # Mismo verde vacuo que se corrigio en verificar_superficie: analizar CERO
    # clases no es verificar. Sin esto, las reglas que dependen del bytecode no
    # encuentran nada que reportar y la puerta sale verde sobre un proyecto sin
    # compilar. La guarda va aqui ademas de en verificar_superficie porque este
    # main() llama a cargar_clases() directamente, saltandose aquella.
    if not clases:
        print(f"ERROR no hay ninguna clase que analizar en {sys.argv[3]}: "
              f"¿se ha compilado el proyecto? Analizar cero clases NO es verificar.")
        return 1
    raiz = pathlib.Path(sys.argv[4])

    def _texto(ruta: pathlib.Path) -> str:
        return ruta.read_text(encoding="utf-8") if ruta.is_file() else ""

    hallazgos = comprobar(
        datos, xml, clases,
        gradle=_texto(raiz / "build.gradle"),
        exclusiones=_texto(raiz / "config" / "spotbugs" / "exclude.xml"),
        decisiones=_texto(raiz / "docs" / "decisiones.md"),
    )
    # PORTANTE `clases`, y no la regla de «todas las unidades a cero»: esta
    # puerta declara tres unidades, asi que `0 clases, 1 entradas, 1 salidas`
    # --cero en la dimension que importa, las demas sanas-- daba un insumo
    # LLENO. Es la forma canonica del fallo que la portante existe para cazar, y
    # estaba justo aqui. La guarda de `if not clases` de arriba lo tapaba: la
    # honestidad de la puerta descansaba en un `if` copiado en tres validadores
    # en vez de en la propiedad que el sistema anuncia como general.
    return contrato.informar(hallazgos, insumo=contrato.linea_de_insumo(
        portante="clases",
        clases=len(clases),
        entradas=len(datos.get('entradas', [])),
        salidas=len(datos.get('salidas', [])),
    ))


if __name__ == "__main__":
    raise SystemExit(main())
