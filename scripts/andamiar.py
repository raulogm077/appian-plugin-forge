"""Andamiaje: sustitucion de variables sobre las plantillas.

Sin modelo de por medio (spec S5.2): sale bien siempre, y son justo los
ficheros donde un error cuesta un ciclo de aprobacion entero.
"""

from __future__ import annotations

import datetime
import pathlib
import re

import contrato

PATRON_MARCADOR = re.compile(r"\{\{(\w+)\}\}")

# Anotaciones de conveniencia: fijan categoria y paleta a la vez y hacen
# imposible por construccion el error de R-F01 (auditoria S2.5). Aqui se
# previene; en R-F01b (verificar_framework.py) se detecta.
#
# El mapa vive en `contrato` porque tiene DOS lados: `contrato.validar` rechaza
# la paleta que no este en el, y esto la traduce. Cuando era privado de aqui,
# una paleta desconocida caia al repuesto sin aviso.
ANOTACION_POR_PALETA = contrato.ANOTACION_POR_PALETA
ANOTACION_POR_DEFECTO = contrato.ANOTACION_POR_DEFECTO

VERSION_MINIMA_USE_KEYWORDS = (26, 1)

# Que fichero se escapa lo decide `contrato.es_bundle`, no una copia de aqui: el
# que escapa y el que juzga (R-B05) tienen que estar de acuerdo sobre QUE
# ficheros, no solo sobre que cuenta como acento. Es de EXTENSION y no de
# locale: `en_US` entra --de ahi saca Appian los textos de display-- y no entra
# nada que no sea un `.properties`.

# El comentario de las dos salidas horneadas CUANDO el contrato no las declara.
# Si las declara, gana su descripcion: el plug-in aprobado del AppMarket las
# documenta mucho mejor que cualquier texto generico que pudieramos poner aqui.
COMENTARIO_POR_DEFECTO_HORNEADO = {
    "ErrorOccurred": "True if the execution failed",
    "ErrorMessage": "Description of the error, if any",
}
# El mismo texto que traia la plantilla antes de que estas claves pasaran a
# emitirse desde aqui. Se escribe en español legible: el escapado a `\uXXXX`
# que exige R-B05 --en TODO bundle, sin exencion de locale: `en_US` es
# justamente el que Appian lee para los textos de display-- lo pone
# `contrato.escapar_no_ascii` al emitir, igual que al resto del bundle
# traducido. Pre-escaparlo aqui a mano era el
# unico sitio del repositorio donde el mismo convenio se aplicaba dos veces por
# vias distintas — y mientras fue la unica via, tapaba que a lo demas no se le
# aplicaba ninguna.
COMENTARIO_POR_DEFECTO_HORNEADO_ES = {
    "ErrorOccurred": "Cierto si la ejecución falló",
    "ErrorMessage": "Descripción del error, si lo hubo",
}

# El subpaquete donde vive la clase de cada tipo. Vivia duplicado entre
# generar() y el nombre cualificado que necesita el filtro de SpotBugs.
SUBPAQUETE_POR_TIPO = {"smart-service": "smartservice", "servlet": "servlet"}
SUBPAQUETE_POR_DEFECTO = "function"

# Exclusiones de SpotBugs por tipo, cada una acotada a la clase y al patron, y
# con su porque al lado — el formato del plug-in de referencia, que pasa esta
# misma cadena y esta aprobado. Sin esto, `spotbugsMain` fallaba sobre codigo
# que escribe la PROPIA plantilla y `./gradlew build` no podia terminar en
# BUILD SUCCESSFUL, que es el criterio de salida del paso BUILD.
EXCLUSION_CRLF = """  <!-- El unico dato que esta clase concatena en un log es un UUID recien
       generado (`UUID.randomUUID().toString()`): no puede contener CR ni LF.
       El detalle del error va al log via el Throwable, nunca por la cadena.
       Si se anaden datos de entrada al mensaje, ESTA EXCLUSION DEJA DE VALER. -->
  <Match>
    <Class name="{clase}"/>
    <Bug pattern="CRLF_INJECTION_LOGS"/>
  </Match>"""

# SECSP (SERVLET_PARAMETER) se deja SIN excluir, y comentado en vez de activo:
# dispara en todo servlet que lea un parametro —que es su oficio— pero la
# plantilla no puede afirmar que el valor se trate con seguridad, porque quien
# escribe `ejecutar()` es el desarrollador. Afirmarlo aqui seria justo lo que
# este sistema existe para impedir. Se le deja la decision, con el argumento.
NOTA_SECSP = """  <!-- ABIERTO, a proposito. FindSecBugs marca `SERVLET_PARAMETER` en
       `request.getParameter(...)`: todo parametro de peticion es dato
       controlado por el cliente. No se excluye de fabrica porque la plantilla
       NO puede saber que haras con ese valor — lo recibe y te lo pasa.
       Antes de activar el bloque de abajo, comprueba que el valor no llega a
       una consulta, una ruta de fichero ni un comando sin validar, y escribe
       aqui por que es seguro. Mientras siga comentado, `./gradlew build`
       fallara en spotbugsMain, y eso es informacion, no una averia.

  <Match>
    <Class name="{clase}"/>
    <Bug pattern="SERVLET_PARAMETER"/>
  </Match>
  -->"""

# docs/decisiones.md nace con el andamiaje. Es la pieza 2 del dossier y lo que
# R-F14 lee para saber si una exclusion de SpotBugs esta firmada; y el
# andamiaje de smart-service deja UNA exclusion activa (EXCLUSION_CRLF, arriba,
# con su porque), asi que firmarla es del andamiaje, no de quien implementa.
# Sin esto, al generalizar R-F14 a los cuatro tipos (21-sep-2026) todo smart
# service recien generado nacia NOT_READY por una exclusion que no habia
# escrito nadie. Solo se escribe si no existe: regenerar sobre un proyecto en
# marcha no puede pisar decisiones ya tomadas.
DECISIONES_INICIALES = """# Decisiones de diseño

Cada decisión que se aparta del andamiaje, o que una puerta exige firmar, con su porqué. Es la
pieza 2 del dossier y lo que la regla `R-F14` lee para saber si una exclusión de SpotBugs está
firmada: una exclusión activa en `config/spotbugs/exclude.xml` que no se mencione aquí pone la
verificación en rojo.
"""

DECISION_CRLF = """
## Exclusión de SpotBugs: `CRLF_INJECTION_LOGS` en `{clase}`

Viene del andamiaje, no de quien implementa. El único dato que la clase generada concatena en un
log es un UUID recién generado (`UUID.randomUUID().toString()`), que no puede contener CR ni LF;
el detalle del error va al log vía el `Throwable`, nunca por la cadena. **Deja de valer si se
añaden datos de entrada al mensaje**: entonces se retira la exclusión de
`config/spotbugs/exclude.xml`, o se reescribe esta decisión con el argumento nuevo.
"""

# Va al plug-in generado, no a este repositorio. Sin el, `core.autocrlf=true`
# convierte gradlew a CRLF en el siguiente checkout y el script deja de
# arrancar en Unix -- el mismo tipo de fallo que ya rompio el parseo del
# contrato en la tarea 2, esta vez previsto de antemano.
GITATTRIBUTES_GENERADO = """# Finales de linea fijados: gradlew es un script de shell y se rompe con CRLF.
gradlew text eol=lf
*.bat text eol=crlf
*.jar -text
*.properties text eol=lf
*.java text eol=lf
*.gradle text eol=lf
"""


def _version_tupla(texto: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", texto)[:2]) or (0,)


def sustituir(plantilla: str, variables: dict[str, str]) -> str:
    resultado = PATRON_MARCADOR.sub(lambda m: variables.get(m.group(1), m.group(0)), plantilla)
    pendientes = sorted(set(PATRON_MARCADOR.findall(resultado)))
    if pendientes:
        raise ValueError(f"marcadores sin resolver: {pendientes}")
    return resultado


def construir_variables(datos: dict) -> dict[str, str]:
    plugin = datos["plugin"]
    tipo = plugin["tipo"]
    entradas = datos.get("entradas", [])
    salidas = datos.get("salidas", [])
    riguroso = plugin.get("perfil") == "riguroso"

    v: dict[str, str] = {
        "PAQUETE": plugin["paquete"],
        "PAQUETE_RAIZ": plugin["paquete"],
        "GRUPO": plugin["paquete"].rsplit(".", 1)[0],
        "KEY": plugin["key"],
        "NOMBRE": plugin["nombre"],
        "VERSION": plugin["version"],
        "DESCRIPCION": plugin.get("descripcion", plugin["nombre"]),
        "APPLICATION_VERSION_MIN": plugin["application_version_min"],
        "NOMBRE_ARTEFACTO": plugin["key"].rsplit(".", 1)[-1],
        "CLASE": contrato.seccion(datos, "clase").get("nombre", ""),
        "BUNDLE": contrato.seccion(datos, "bundle").get("nombre", ""),
        "VENDOR": plugin.get("vendor", "Raul Gomez Moya"),
        "VENDOR_URL": plugin.get("vendor_url", "https://example.invalid"),
        "PALETA": contrato.seccion(datos, "clase").get("paleta", ""),
        "PLUGINS_PERFIL": "",
        "BLOQUE_PERFIL": "",
        "DEPENDENCIAS_IMPLEMENTATION": "\n".join(
            f"    implementation '{d}'" for d in datos.get("dependencias", [])
        ),
        "ANO": str(datetime.date.today().year),
    }

    subpaquete = SUBPAQUETE_POR_TIPO.get(tipo, SUBPAQUETE_POR_DEFECTO)
    clase_cualificada = f"{plugin['paquete']}.{subpaquete}.{v['CLASE']}"
    if tipo == "smart-service":
        v["EXCLUSIONES_SPOTBUGS"] = EXCLUSION_CRLF.format(clase=clase_cualificada)
    elif tipo == "servlet":
        v["EXCLUSIONES_SPOTBUGS"] = NOTA_SECSP.format(clase=clase_cualificada)
    else:
        # Una function no registra nada ni recibe peticiones: excluirle un
        # fallo que no puede cometer ensena a coleccionar exclusiones por si
        # acaso, que es como una exclusion acotada se convierte en una global.
        v["EXCLUSIONES_SPOTBUGS"] = (
            "  <!-- Sin exclusiones: este tipo no incurre en ninguno de los "
            "patrones que\n       las plantillas necesitan justificar. -->"
        )

    # R-J07 exige LICENSE y THIRD_PARTY_NOTICES.md dentro del JAR, y
    # build.gradle los copia de la raiz del proyecto a META-INF: sin que el
    # andamiaje los escriba, TODO plug-in recien generado incumplia una regla
    # del propio sistema. El contenido de partida sale del contrato; cerrarlo
    # —licencia real de cada dependencia— es trabajo humano, y la plantilla lo
    # dice con todas las letras.
    dependencias = datos.get("dependencias", [])
    v["NOTICIAS_DEPENDENCIAS"] = (
        "\n".join(f"- `{d}` — licencia: **PENDIENTE DE COMPLETAR**" for d in dependencias)
        if dependencias
        else "_El contrato no declara ninguna dependencia de terceros._"
    )

    # @Order lleva SOLO nombres de entrada, nunca salidas (auditoria S2.1).
    v["ORDEN_ENTRADAS"] = ", ".join(f'"{e["nombre"]}"' for e in entradas)

    # RUIDOSO si la paleta no se conoce, igual que `placeholder_no_nulo` mas
    # abajo. `contrato.validar` ya la rechaza, asi que por el CLI esto no se
    # alcanza; pero un llamador de biblioteca que se saltara la puerta seguia
    # obteniendo la traduccion al repuesto EN SILENCIO, que es exactamente el
    # defecto que la puerta cerro un nivel mas arriba. Productor estricto y
    # consumidor indulgente es como se reabren las cosas.
    #
    # El repuesto se conserva para el unico caso legitimo: los tipos que no son
    # smart-service no declaran paleta, y su `{{ANOTACION_PALETA}}` no lo
    # consume ninguna plantilla.
    if v["PALETA"] and v["PALETA"] not in ANOTACION_POR_PALETA:
        raise ValueError(
            f"paleta desconocida «{v['PALETA']}»: no esta en contrato.ANOTACION_POR_PALETA. "
            f"{contrato._pista_de_paleta(v['PALETA'])} Traducirla al repuesto pondria el "
            f"plug-in en una paleta que nadie pidio, sin decirlo."
        )
    v["ANOTACION_PALETA"] = ANOTACION_POR_PALETA.get(v["PALETA"], ANOTACION_POR_DEFECTO)

    # El tipo se EMITE resuelto, no verbatim: la plantilla no lleva imports,
    # asi que `Timestamp` a secas producia un `.java` que no compila. Es lo que
    # le pasaba al oraculo del propio repositorio, el plug-in del AppMarket,
    # con sus nueve salidas de fecha.
    def tipo_emitido(campo: dict) -> str:
        return contrato.tipo_java_emitible(campo["tipo_java"]) or campo["tipo_java"]

    # Las salidas que la plantilla ya hornea (`ErrorOccurred`, `ErrorMessage`)
    # no se declaran otra vez: se mapean sobre el miembro existente. Emitirlas
    # daba «method getErrorOccurred() is already defined».
    salidas_propias = [s for s in salidas if not contrato.salida_horneada(s)]

    # El identificador del CAMPO no es el nombre que ve Appian. Los nombres de
    # input/output son PascalCase y usarlos verbatim como campo hacia saltar
    # `Nm` de SpotBugs en cada uno. El plug-in aprobado separa las dos cosas:
    # campo en lowerCamelCase, y Appian leyendo el nombre por el ACCESOR.
    def campo(x: dict) -> str:
        return contrato.identificador_java(x["nombre"])

    v["CAMPOS_ENTRADA"] = "\n".join(
        f"    private {tipo_emitido(e)} {campo(e)};" for e in entradas
    )
    v["CAMPOS_SALIDA"] = "\n".join(
        f"    private {tipo_emitido(s)} {campo(s)};" for s in salidas_propias
    )

    # SETTERS y GETTERS son EXCLUSIVOS del smart service: solo
    # smart-service/Clase.java.tmpl los usa, y solo el smart service declara
    # `required` en sus entradas —la puerta determinista no lo exige a los
    # demas tipos, con razon: `@Input`/`Required` no existen fuera del
    # framework de proceso—. Construirlos siempre indexaba `e['required']` a
    # ciegas y mataba a los otros TRES tipos con KeyError sobre un contrato
    # que la puerta acababa de aprobar.
    v["SETTERS"] = ""
    v["GETTERS"] = ""
    v["CUERPO_EJECUTAR"] = ""

    # Convenio de claves SEGUN EL TIPO: confundirlos es el error de la guia
    # (auditoria S7.11).
    if tipo == "smart-service":
        setters = []
        for e in entradas:
            mayuscula = e["nombre"][0].upper() + e["nombre"][1:]
            setters.append(
                f"    @Input(required = Required.{e['required']})\n"
                f"    public void set{mayuscula}({tipo_emitido(e)} {campo(e)}) {{\n"
                f"        this.{campo(e)} = {campo(e)};\n"
                f"    }}"
            )
        v["SETTERS"] = "\n\n".join(setters)

        getters = []
        for s in salidas_propias:
            mayuscula = s["nombre"][0].upper() + s["nombre"][1:]
            getters.append(
                f"    public {tipo_emitido(s)} get{mayuscula}() {{\n"
                f"        return {campo(s)};\n"
                f"    }}"
            )
        v["GETTERS"] = "\n\n".join(getters)

        # El cuerpo de ejecutar() (Critico 1 del gate de ciclo 1): sin esto
        # ninguna entrada se lee ni ninguna salida se escribe, y SpotBugs
        # marca UwF/UrF sobre TODO smart-service recien andamiado con al
        # menos una entrada y una salida propia (obligatorio por contrato,
        # ver validar()). El `throw` que hace el fallo ruidoso vive FIJO en
        # la plantilla, no aqui: que esta generacion cambie de forma nunca
        # puede silenciar el aviso de "sin implementar".
        # Una entrada OPTIONAL puede llegar nula por contrato: exigirla con
        # `requireNonNull` convertia el andamiaje en un NullPointerException en
        # tiempo de ejecucion --dentro de Appian, no aqui-- en vez de alcanzar
        # el `throw` de "sin implementar" que la plantilla tiene puesto. Se
        # sigue LEYENDO, que es lo que SpotBugs necesita para no marcar UrF,
        # pero sin exigirla.
        #
        # La lectura de una OPTIONAL no puede ser `LOG.debug(valor)`: esta
        # clase evita a proposito que ningun dato del usuario llegue al log
        # (ver el manejo de errores de la plantilla), y el contrato puede
        # declarar `datos_personales`. Se registra el NOMBRE del campo, nunca
        # su valor. Tampoco vale una expresion cuyo retorno se ignore: el
        # perfil de SpotBugs es `effort=MAX` con `reportLevel=LOW`, y ahi
        # `RV_RETURN_VALUE_IGNORED_NO_SIDE_EFFECT` si se reporta.
        lineas_cuerpo = []
        for e in entradas:
            nombre = campo(e)
            if e.get("required") == "OPTIONAL":
                lineas_cuerpo.append(
                    f"        if ({nombre} == null) {{\n"
                    f'            LOG.debug("entrada opcional sin valor: {nombre}");\n'
                    f"        }}"
                )
            else:
                lineas_cuerpo.append(
                    f'        java.util.Objects.requireNonNull({nombre}, "{nombre}");'
                )
        for s in salidas_propias:
            tipo_s = tipo_emitido(s)
            placeholder = contrato.placeholder_no_nulo(tipo_s)
            if placeholder is None:
                raise ValueError(
                    f"sin placeholder no nulo para el tipo «{tipo_s}» de la salida "
                    f"«{s['nombre']}»: la puerta determinista acepta cualquier tipo "
                    f"cualificado con un punto, pero este andamiador solo sabe dar "
                    f"placeholder a los de java.lang y a los alias de java.sql "
                    f"(contrato.PLACEHOLDER_POR_TIPO) -- documenta el tipo que falta "
                    f"y decide el placeholder antes de seguir; no se inventa aqui"
                )
            lineas_cuerpo.append(f"        this.{campo(s)} = {placeholder};")
        v["CUERPO_EJECUTAR"] = "\n".join(lineas_cuerpo)

        v["CLAVES_ENTRADAS"] = "\n".join(
            contrato.lineas_de_entrada(e["nombre"], e["descripcion"]) for e in entradas
        )
        # Las etiquetas de TODAS las salidas salen de aqui, incluidas las dos
        # horneadas. Se salta el miembro Java (`salidas_propias`), nunca la
        # etiqueta: Appian expone los dos outputs de error y necesita su
        # displayName y su comment.
        #
        # Antes las horneaba la plantilla del bundle, y con la caja equivocada
        # --`output.errorOccurred`-- mientras la clase declara
        # `getErrorOccurred()`. Appian lee el nombre del ACCESOR, asi que esas
        # dos etiquetas no etiquetaban nada. Emitirlas desde aqui arregla las
        # dos mitades a la vez: la caja sale del nombre real de la salida, y un
        # contrato que las declare --el del plug-in aprobado las declara-- gana
        # su propia descripcion en vez de la generica, sin duplicar la clave.
        def bloque_de_salidas(por_defecto: dict[str, str]) -> str:
            declaradas = {s["nombre"] for s in salidas}
            con_etiqueta = list(salidas) + [
                {"nombre": nombre, "descripcion": por_defecto[nombre]}
                for nombre in contrato.SALIDAS_HORNEADAS
                if nombre not in declaradas
            ]
            return "\n".join(
                contrato.lineas_de_salida(s["nombre"], s["descripcion"])
                for s in con_etiqueta
            )

        v["CLAVES_SALIDAS"] = bloque_de_salidas(COMENTARIO_POR_DEFECTO_HORNEADO)
        # Las declaradas por el contrato se reutilizan tal cual --no hay modelo
        # que traduzca--, pero las dos horneadas SI tienen texto propio: es el
        # que traia la plantilla, y perderlo al moverlas aqui habria sido una
        # regresion silenciosa en el unico locale que las llevaba traducidas.
        #
        # El escapado a `\\uXXXX` que exige R-B05 NO se hace aqui: se hace en
        # `generar()`, sobre el fichero ya renderizado y segun su destino. Ver
        # alli por que.
        v["CLAVES_ENTRADAS_ES"] = v["CLAVES_ENTRADAS"]
        v["CLAVES_SALIDAS_ES"] = bloque_de_salidas(COMENTARIO_POR_DEFECTO_HORNEADO_ES)
    else:
        # Un solo fallback para todo el sistema: verificar_bundles deriva de
        # aqui las claves que exige R-B03. Cuando cada lado tenia el suyo,
        # R-B03 pedia `function..description` —con doble punto— que ninguna
        # plantilla puede emitir.
        funcion = contrato.nombre_funcion(datos)
        v["FUNCION"] = funcion
        v["CATEGORIA"] = contrato.seccion(datos, "funcion").get("categoria", "category.name.TextFunctions")
        v["TIPO_RETORNO"] = tipo_emitido(salidas[0]) if salidas else "String"
        v["PARAMETROS"] = ",\n            ".join(
            f"@Parameter {tipo_emitido(e)} {e['nombre']}" for e in entradas
        )
        v["CLAVES_PARAMETROS"] = "\n".join(
            f"{contrato.clave_de_parametro(funcion, e['nombre'])}={e['descripcion']}"
            for e in entradas
        )
        # Igual que CLAVES_ENTRADAS_ES en smart-service: sin traduccion real
        # (no hay modelo de por medio), se reutiliza el mismo texto que ya
        # escribio el autor del contrato. function/bundle_es_ES.properties.tmpl
        # (tarea 11) exige estas dos claves; sin ellas sustituir() rechaza
        # CUALQUIER function o writer-function con marcadores sin resolver.
        v["DESCRIPCION_ES"] = v["DESCRIPCION"]
        v["CLAVES_PARAMETROS_ES"] = v["CLAVES_PARAMETROS"]
        # useKeywords solo surte efecto desde 26.1; emitirlo con un
        # application-version menor es la incoherencia que detecta R-F05.
        if _version_tupla(plugin["application_version_min"]) >= VERSION_MINIMA_USE_KEYWORDS:
            v["ANOTACION_FUNCTION"] = "@Function(useKeywords = true)"
        else:
            v["ANOTACION_FUNCTION"] = "@Function"

    if tipo == "servlet":
        # Del contrato, con valores por defecto seguros. Sin estas dos, el
        # 100 % de los servlets abortaba el andamiado por marcadores sin
        # variable. La tarea 2 no reservo campos para esto (no es su alcance
        # tocarlo aqui): seccion [servlet] opcional, mismo patron
        # datos.get(..., defecto) que ya usan VENDOR/DEPENDENCIAS/FUNCION.
        servlet = datos.get("servlet", {})
        v["URL_PATTERN"] = servlet.get("url_pattern", "/" + v["NOMBRE_ARTEFACTO"])
        v["PARAMETRO"] = servlet.get("parametro", "valor")

    if riguroso:
        raiz = pathlib.Path(__file__).resolve().parents[1] / "assets" / "plantillas"
        texto = (raiz / "perfil-riguroso.gradle.tmpl").read_text(encoding="utf-8")
        # El fragmento trae su propio {{PAQUETE_RAIZ}} (targetClasses/
        # targetTests). sustituir() es de una sola pasada -- re.sub no
        # reescanea el texto de reemplazo --, asi que sin esto el marcador
        # queda literal DENTRO de BLOQUE_PERFIL y sustituir() lo rechaza al
        # insertarlo en build.gradle.tmpl, aunque PAQUETE_RAIZ si este en v.
        texto = sustituir(texto, v)
        marca_inicio = "// ---8<--- PLUGINS_PERFIL"
        marca_fin = "// --->8---"
        if marca_inicio in texto:
            inicio = texto.index(marca_inicio) + len(marca_inicio)
            fin = texto.index(marca_fin)
            v["PLUGINS_PERFIL"] = texto[inicio:fin].strip("\n")
            texto = texto[:texto.index(marca_inicio)] + texto[fin + len(marca_fin):]
        v["BLOQUE_PERFIL"] = texto

    return v


def generar(
    datos: dict,
    dir_plantillas: pathlib.Path,
    destino: pathlib.Path,
    contrato_origen: pathlib.Path | str,
) -> list[pathlib.Path]:
    """Andamia el proyecto y escribe `docs/contrato.md` (Critico 2 del gate de
    ciclo 1).

    `contrato_origen` es OBLIGATORIO a proposito -- opcional habria recreado
    el mismo hueco en silencio para quien lo omitiera. Acepta la RUTA al
    contrato.md real (se copia LITERAL, byte a byte, con `shutil.copy2`) o el
    TEXTO ya leido como `str` (para quien construye `datos` a mano, sin
    fichero en disco, como varios tests). `docs/contrato.md` en el proyecto
    generado es el insumo que exigen sin condicion `verificar_framework.py`,
    `verificar_appmarket.py`, `verificar_bundles.py` y `verificar_jar.py`
    (los cuatro invocados por `verificar_todo.py` sin comprobar que el
    fichero exista) y `generar_dossier.py` -- cinco consumidores reales,
    ninguno con try/except, todos con `FileNotFoundError` sobre un proyecto
    recien andamiado (informe del ciclo 1, hallazgo CRITICO 2; ampliado de
    tres a cinco consumidores por `evidencia/13-revisor-de-costuras.md`).
    """
    variables = construir_variables(datos)
    tipo = datos["plugin"]["tipo"]
    escritos: list[pathlib.Path] = []

    ruta_paquete = datos["plugin"]["paquete"].replace(".", "/")
    ruta_key = datos["plugin"]["key"].replace(".", "/")
    nombre_bundle = contrato.seccion(datos, "bundle").get("nombre", "")
    subdir = SUBPAQUETE_POR_TIPO.get(tipo, SUBPAQUETE_POR_DEFECTO)

    # writer-function (tarea 11, Step 4) solo tiene Clase.java.tmpl propia:
    # su manifiesto y sus bundles son los de function, con los que es
    # compatible -- mismo paquete `.function`, y una writer function se
    # declara en el XML con el mismo <function key=.../> que una de lectura,
    # solo cambia el tipo de retorno en Java. Sin este alias, el mapa de
    # abajo apunta a ficheros que no existen, is_file() los salta en
    # silencio, y el plug-in generado sale sin manifiesto ni bundles.
    tipo_recursos = "function" if tipo == "writer-function" else tipo

    mapa = {
        "comun/build.gradle.tmpl": "build.gradle",
        "comun/settings.gradle.tmpl": "settings.gradle",
        "comun/gitignore.tmpl": ".gitignore",
        # A la RAIZ del proyecto, que es de donde el bloque `into('META-INF')`
        # de build.gradle los copia al JAR: R-J07 los busca en META-INF.
        "comun/LICENSE.tmpl": "LICENSE",
        "comun/THIRD_PARTY_NOTICES.md.tmpl": "THIRD_PARTY_NOTICES.md",
        # Donde lo tiene el plug-in de referencia, y donde lo busca el
        # `excludeFilter` de build.gradle.
        "comun/spotbugs-exclude.xml.tmpl": "config/spotbugs/exclude.xml",
        f"{tipo}/Clase.java.tmpl": f"src/main/java/{ruta_paquete}/{subdir}/{variables['CLASE']}.java",
        f"{tipo_recursos}/appian-plugin.xml.tmpl": "src/main/resources/appian-plugin.xml",
    }
    if tipo != "servlet":
        mapa[f"{tipo_recursos}/bundle_en_US.properties.tmpl"] = (
            f"src/main/resources/{ruta_key}/{nombre_bundle}_en_US.properties"
        )
        mapa[f"{tipo_recursos}/bundle_es_ES.properties.tmpl"] = (
            f"src/main/resources/{ruta_key}/{nombre_bundle}_es_ES.properties"
        )

    for origen, salida in mapa.items():
        ruta_origen = dir_plantillas / origen
        # Una plantilla que falta NO se salta en silencio: eso es justo lo que
        # producia un plug-in incompleto sin avisar (el Fallo B de la ronda 1:
        # writer-function salia sin manifiesto ni bundles y generar() no lo
        # senalaba).
        if not ruta_origen.is_file():
            raise FileNotFoundError(f"falta la plantilla {origen} para el tipo «{tipo}»")
        contenido = sustituir(ruta_origen.read_text(encoding="utf-8"), variables)
        ruta_salida = destino / salida
        # R-B05 se cumple AQUI, donde se conoce el destino, y no variable a
        # variable en `construir_variables`. El primer intento escapaba las
        # cuatro variables `*_ES` y dejaba pasar `{{NOMBRE}}`, que la plantilla
        # `bundle_es_ES` tambien escribe: el fichero seguia saliendo con
        # `anexión` crudo al lado de `ejecución` escapado, que era
        # exactamente el defecto que se creia corregido. Escapar por variable
        # obliga a acertar con la lista; escapar por destino cubre tambien el
        # texto literal de la plantilla y la variable que alguien anada manana.
        #
        # Es un no-op sobre lo que ya esta escapado (la funcion es idempotente).
        #
        # Se aplica a TODOS los bundles, `en_US` incluido. Antes se le eximia
        # «porque ese si se lee», y el razonamiento estaba del reves: es
        # precisamente por leerse. `en_US` es el locale del que Appian saca los
        # textos de display, o sea el unico fichero cuyo mojibake veria un
        # usuario, y salia con la tilde en UTF-8 crudo mientras su hermano
        # `_es_ES` la escapaba. El plug-in de referencia aprobado en AppMarket
        # no tiene un solo no-ASCII en su `en_US`. Escapar es seguro lea quien
        # lea --`Properties.load` (ISO-8859-1) o `ResourceBundle` (UTF-8 desde
        # Java 9)-- y quita la dependencia del lector. Levantado por el gate del
        # ciclo 16: emisor y juez compartian la MISMA exencion, asi que la
        # cadena entera era ciega.
        if contrato.es_bundle(ruta_salida.name):
            contenido = contrato.escapar_no_ascii(contenido)
        ruta_salida.parent.mkdir(parents=True, exist_ok=True)
        ruta_salida.write_text(contenido, encoding="utf-8")
        escritos.append(ruta_salida)

    import shutil

    # docs/contrato.md (Critico 2): copia LITERAL del contrato de origen, no
    # una reserializacion de `datos` -- eso perderia la prosa para el humano
    # y cualquier comentario del TOML. Un Path se copia en BINARIO
    # (`copy2`), igual que el wrapper de Gradle mas abajo: "literal" es byte
    # a byte, y un roundtrip `read_text`/`write_text` en Windows convertiria
    # los `\n` a CRLF al escribir. Un `str` ya es el texto final -- se
    # escribe tal cual, en UTF-8.
    ruta_contrato_destino = destino / "docs" / "contrato.md"
    ruta_contrato_destino.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(contrato_origen, pathlib.Path):
        try:
            shutil.copy2(contrato_origen, ruta_contrato_destino)
        except shutil.SameFileError:
            # El contrato YA es `docs/contrato.md` del destino. Pasa en el caso
            # mas normal que hay: volver a andamiar sobre un proyecto existente
            # apuntando a su propio contrato -- que es exactamente lo que hace
            # quien corrige el contrato y regenera. `copy2` sobre un fichero y
            # si mismo lanza, y lanzaba AQUI, con los ~14 ficheros de arriba ya
            # escritos: un proyecto a medias y una traza en vez de un fallo que
            # se entienda.
            #
            # Se ATRAPA en vez de compararse antes con `samefile`: la
            # comparacion previa es una carrera --el fichero puede moverse
            # entre la comprobacion y la copia-- y ademas `samefile` exige que
            # los dos existan, asi que habria que envolverlo igual. La
            # excepcion la levanta el propio `copy2` sobre el estado real.
            #
            # Y no se copia nada, que es lo correcto y no un apaño: el destino
            # ya ES el origen, byte a byte. La ruta sigue viajando en
            # `escritos` porque la promesa del andamiador es que ese fichero
            # esta ahi --de eso va el Critico 2--, no que lo haya escrito el.
            pass
    else:
        ruta_contrato_destino.write_text(contrato_origen, encoding="utf-8")
    escritos.append(ruta_contrato_destino)

    # El wrapper se copia tal cual: es el comando que ejecutara quien reciba el
    # plug-in, y fija la version dentro del proyecto (spec S5.4).
    # copy2 es binario: NO transforma finales de linea. Es imprescindible para
    # gradle-wrapper.jar, y tambien para gradlew, que es un script de shell y
    # se rompe con CRLF.
    for relativo in ("gradlew", "gradlew.bat", "gradle/wrapper/gradle-wrapper.jar",
                     "gradle/wrapper/gradle-wrapper.properties"):
        origen = dir_plantillas / "comun" / relativo
        if origen.is_file():
            salida = destino / relativo
            salida.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origen, salida)
            escritos.append(salida)
    # gradlew necesita el bit de ejecucion para quien reciba el plug-in en Unix.
    ruta_gradlew = destino / "gradlew"
    if ruta_gradlew.is_file():
        ruta_gradlew.chmod(ruta_gradlew.stat().st_mode | 0o111)

    # El plug-in GENERADO necesita su propio .gitattributes: copiar bien los
    # ficheros no basta si luego git los convierte al hacer checkout en Windows.
    # Sin esto, `core.autocrlf=true` deja gradlew en CRLF y deja de arrancar en
    # cualquier consumidor Unix. Contenido fijo, no plantilla: no depende del
    # contrato.
    ruta_atributos = destino / ".gitattributes"
    ruta_atributos.write_text(GITATTRIBUTES_GENERADO, encoding="utf-8")
    escritos.append(ruta_atributos)

    # Ver DECISIONES_INICIALES: la firma de la exclusion que el propio
    # andamiaje activa, y solo si nadie ha escrito ya el fichero.
    ruta_decisiones = destino / "docs" / "decisiones.md"
    if not ruta_decisiones.exists():
        texto_decisiones = DECISIONES_INICIALES
        if tipo == "smart-service":
            clase_cualificada = f"{datos['plugin']['paquete']}.{subdir}.{variables['CLASE']}"
            texto_decisiones += DECISION_CRLF.format(clase=clase_cualificada)
        ruta_decisiones.write_text(texto_decisiones, encoding="utf-8")
        escritos.append(ruta_decisiones)

    return escritos


def main() -> int:
    import sys

    if len(sys.argv) != 3:
        print("uso: andamiar.py <contrato.md> <directorio-destino>")
        return 2
    try:
        datos = contrato.cargar(pathlib.Path(sys.argv[1]))
    except contrato.ContratoIlegible as error:
        print(f"ERROR contrato: {error}")
        return 2
    faltantes = contrato.validar(datos)
    if faltantes:
        print("El contrato esta incompleto; no se genera nada:")
        for f in faltantes:
            print(f"  FALTA {f}")
        return 1
    plantillas = pathlib.Path(__file__).resolve().parents[1] / "assets" / "plantillas"
    escritos = generar(datos, plantillas, pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[1]))
    for ruta in escritos:
        print(f"escrito {ruta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
