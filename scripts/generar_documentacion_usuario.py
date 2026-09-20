"""Genera documentacion de usuario a partir del contrato ya congelado: GUIA_INTEGRACION.md
para el desarrollador Appian que integra el plugin, y FICHA_APPMARKET.md para quien lo
encuentra en el Marketplace (spec 2026-09-18, capacidad C). No pregunta nada nuevo: todo sale
de lo que la entrevista ya recogio.
"""

import pathlib
import re
import xml.etree.ElementTree as ET

import contrato

# Una frase por tipo, con `{key}`, `{params}` y `{paleta}` como huecos -- no
# valores de ejemplo (spec E4): describe COMO se invoca, no con que datos.
INVOCACION_POR_TIPO = {
    "function": "Se invoca desde una expresion SAIL: `{key}({params})`.",
    "writer-function": (
        "Se invoca como `Writer` desde el `saveInto` de un componente de interfaz: "
        "`{key}({params})`."
    ),
    "smart-service": (
        "Se añade como paso de un modelo de proceso, en la subpaleta **{paleta}**."
    ),
    "servlet": (
        "Expone un endpoint HTTP dentro de Appian; metodo y ruta segun lo declarado en "
        "`appian-plugin.xml`."
    ),
}


# Los metodos que un `HttpServlet` puede atender. Se busca la DECLARACION
# (`void doGet(`) y no la mencion: una llamada a `super.doPost(...)` no hace que
# el servlet atienda POST, y anunciarlo seria peor que no decir nada.
DECLARACION_DE_METODO = re.compile(
    r"void\s+do(Get|Post|Put|Delete|Head|Options|Patch)\s*\(", re.MULTILINE
)


def _ruta_declarada(raiz: pathlib.Path) -> str | None:
    """El `<url-pattern>` del manifiesto GENERADO, que es el hecho.

    Se lee del fichero y no se re-deriva del contrato a proposito: `andamiar.py`
    lo saca de `[servlet].url_pattern` con un relleno por defecto cuando falta,
    y quien implementa el servlet puede haberlo cambiado despues. Re-derivarlo
    abriria una segunda costura que diria algo distinto del XML que se entrega.
    """
    manifiesto = raiz / "src" / "main" / "resources" / "appian-plugin.xml"
    if not manifiesto.is_file():
        return None
    try:
        arbol = ET.fromstring(manifiesto.read_text(encoding="utf-8"))
    except ET.ParseError:
        return None
    for elemento in arbol.iter("url-pattern"):
        if elemento.text and elemento.text.strip():
            return elemento.text.strip()
    return None


def _metodos_atendidos(raiz: pathlib.Path, datos: dict) -> list:
    """Los `doXxx` que la clase del servlet declara, en orden de aparicion."""
    plugin = contrato.seccion(datos, "plugin")
    nombre_clase = contrato.seccion(datos, "clase").get("nombre", "")
    paquete = plugin.get("paquete", "")
    if not nombre_clase or not paquete:
        return []
    fuente = (
        raiz / "src" / "main" / "java"
        / pathlib.Path(*paquete.split("."))
        / "servlet"
        / f"{nombre_clase}.java"
    )
    if not fuente.is_file():
        return []
    vistos = []
    for verbo in DECLARACION_DE_METODO.findall(fuente.read_text(encoding="utf-8")):
        metodo = verbo.upper()
        if metodo not in vistos:
            vistos.append(metodo)
    return vistos


def _invocacion_servlet(raiz, datos: dict) -> str | None:
    """La frase del servlet con ruta y metodos, o None si no consta ninguna.

    Sin proyecto en disco --o sin manifiesto-- devuelve None y la frase generica
    se queda: decir «ruta `/algo`» sin haberla leido seria inventarsela.
    """
    if raiz is None:
        return None
    ruta = _ruta_declarada(pathlib.Path(raiz))
    if not ruta:
        return None
    frase = (
        f"Expone un endpoint HTTP dentro de Appian, en la ruta `{ruta}` que declara "
        f"`appian-plugin.xml`."
    )
    metodos = _metodos_atendidos(pathlib.Path(raiz), datos)
    if metodos:
        frase += " Metodos HTTP atendidos: " + ", ".join(f"`{m}`" for m in metodos) + "."
    return frase


def _parametros(datos: dict) -> str:
    return ", ".join(
        e.get("nombre", "?") for e in datos.get("entradas", []) if isinstance(e, dict)
    )


def _tabla_campos(campos: list, con_required: bool) -> str:
    if not any(isinstance(c, dict) for c in campos):
        return "_Ninguna._"
    if con_required:
        filas = ["| Nombre | Tipo | Obligatorio | Descripcion |", "|---|---|---|---|"]
    else:
        filas = ["| Nombre | Tipo | Descripcion |", "|---|---|---|"]
    for campo in campos:
        if not isinstance(campo, dict):
            continue
        nombre = campo.get("nombre", "?")
        tipo = campo.get("tipo_java", "?")
        descripcion = campo.get("descripcion", "")
        if con_required:
            obligatorio = "si" if campo.get("required") == "ALWAYS" else "no"
            filas.append(f"| `{nombre}` | `{tipo}` | {obligatorio} | {descripcion} |")
        else:
            filas.append(f"| `{nombre}` | `{tipo}` | {descripcion} |")
    return "\n".join(filas)


# Orden fijo: es el orden en que se preguntan en la entrevista (referencias/entrevista.md).
NOTAS_DE_CAPACIDAD = (
    ("parsea_formatos_ajenos", "El formato de entrada no lo controla Appian: valida el "
                                "documento antes de pasarlo si tu proceso puede recibir datos "
                                "corruptos o ajenos."),
    ("sale_a_la_red", "Puede fallar por timeout o por caida del servicio remoto: preve reintentos "
                       "en tu proceso si lo invocas de forma sincrona."),
    ("toca_credenciales", "Espera que la credencial ya este en el Secure Credentials Store de "
                           "Appian; no la pases como texto plano."),
    ("datos_personales", "Maneja datos personales: revisa la politica de retencion de tu "
                          "organizacion antes de registrar su salida en logs propios."),
)


def render_guia_integracion(datos: dict, raiz=None) -> str:
    plugin = contrato.seccion(datos, "plugin")
    clase = contrato.seccion(datos, "clase")
    capacidades = contrato.seccion(datos, "capacidades")
    tipo = plugin.get("tipo", "")

    invocacion = INVOCACION_POR_TIPO.get(tipo, "Tipo de plugin no reconocido.").format(
        key=contrato.nombre_funcion(datos), params=_parametros(datos), paleta=clase.get("paleta", "")
    )
    # El servlet es el unico tipo cuya invocacion no se deduce entera del
    # contrato: su ruta vive en el manifiesto. Con el proyecto delante se dice;
    # sin el, se mantiene la frase generica, que es menos util pero cierta.
    if tipo == "servlet":
        invocacion = _invocacion_servlet(raiz, datos) or invocacion

    lineas = [
        f"# Guia de integracion — {plugin.get('nombre', '')}",
        "",
        plugin.get("descripcion") or "_Sin descripcion declarada en el contrato._",
        "",
        "## Como invocarlo",
        "",
        invocacion,
        "",
        "## Entradas",
        "",
        _tabla_campos(datos.get("entradas", []), con_required=(tipo == "smart-service")),
        "",
        "## Salidas",
        "",
        _tabla_campos(datos.get("salidas", []), con_required=False),
        "",
        "## Version minima de Appian requerida",
        "",
        f"`{plugin.get('application_version_min', '?')}`",
    ]

    notas = [texto for clave, texto in NOTAS_DE_CAPACIDAD if capacidades.get(clave)]
    if notas:
        lineas += ["", "## Notas de seguridad", ""]
        lineas += [f"- {n}" for n in notas]

    return "\n".join(lineas) + "\n"


ETIQUETA_DE_CAPACIDAD = (
    ("sale_a_la_red", "sale a la red"),
    ("toca_credenciales", "usa credenciales del Secure Credentials Store"),
    ("datos_personales", "maneja datos personales"),
)


def render_ficha_appmarket(datos: dict) -> str:
    plugin = contrato.seccion(datos, "plugin")
    clase = contrato.seccion(datos, "clase")
    capacidades = contrato.seccion(datos, "capacidades")

    lineas = [
        f"# {plugin.get('nombre', '')}",
        "",
        plugin.get("descripcion") or "_Sin descripcion declarada en el contrato._",
    ]

    # `clase.paleta` es especifica de smart-service (la subpaleta del paso de
    # proceso, referencias/entrevista.md): function, writer-function y
    # servlet nunca la piden en la entrevista, asi que su ficha prometia una
    # subcategoria que ese tipo de plugin no puede tener. Se omite la linea
    # entera en vez de imprimir un `_sin declarar_` que 3 de 4 tipos verian
    # siempre.
    paleta = clase.get("paleta")
    if paleta:
        lineas += ["", f"**Subcategoria:** {paleta}"]

    etiquetas = [t for clave, t in ETIQUETA_DE_CAPACIDAD if capacidades.get(clave)]
    if etiquetas:
        lineas += ["", f"**Transparencia:** este plugin {', '.join(etiquetas)}."]

    return "\n".join(lineas) + "\n"


def main_con_raiz(raiz: pathlib.Path) -> int:
    datos = contrato.cargar(raiz / "docs" / "contrato.md")
    (raiz / "docs" / "GUIA_INTEGRACION.md").write_text(
        render_guia_integracion(datos, raiz=raiz), encoding="utf-8"
    )
    (raiz / "docs" / "FICHA_APPMARKET.md").write_text(
        render_ficha_appmarket(datos), encoding="utf-8"
    )
    print(f"escrito {raiz / 'docs' / 'GUIA_INTEGRACION.md'}")
    print(f"escrito {raiz / 'docs' / 'FICHA_APPMARKET.md'}")
    return 0


def main() -> int:
    import sys

    if len(sys.argv) != 2:
        print("uso: generar_documentacion_usuario.py <raiz-proyecto-generado>")
        return 2
    return main_con_raiz(pathlib.Path(sys.argv[1]))


if __name__ == "__main__":
    raise SystemExit(main())
