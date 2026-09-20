"""Lector de ficheros .class: constant pool, major version y metodos.

Por que bytecode y no imports (spec D16): un nombre cualificado no genera
import, y la reflexion tampoco. El constant pool contiene toda referencia
real. Ademas, una sola pasada alimenta la puerta de verificacion (capa 2) y el
inventario de API del dossier (§8.1), asi que no pueden desincronizarse.

Formato: JVM Specification, capitulo 4.
"""

from __future__ import annotations

import dataclasses
import pathlib
import re
import struct

TAG_UTF8 = 1
TAG_INTEGER = 3
TAG_FLOAT = 4
TAG_LONG = 5
TAG_DOUBLE = 6
TAG_CLASS = 7
TAG_STRING = 8
TAG_FIELDREF = 9
TAG_METHODREF = 10
TAG_INTERFACE_METHODREF = 11
TAG_NAME_AND_TYPE = 12
TAG_METHOD_HANDLE = 15
TAG_METHOD_TYPE = 16
TAG_DYNAMIC = 17
TAG_INVOKE_DYNAMIC = 18
TAG_MODULE = 19
TAG_PACKAGE = 20

# Tamano en bytes de la parte fija de cada entrada, sin contar el tag.
TAMANOS_FIJOS = {
    TAG_INTEGER: 4,
    TAG_FLOAT: 4,
    TAG_LONG: 8,
    TAG_DOUBLE: 8,
    TAG_CLASS: 2,
    TAG_STRING: 2,
    TAG_FIELDREF: 4,
    TAG_METHODREF: 4,
    TAG_INTERFACE_METHODREF: 4,
    TAG_NAME_AND_TYPE: 4,
    TAG_METHOD_HANDLE: 3,
    TAG_METHOD_TYPE: 2,
    TAG_DYNAMIC: 4,
    TAG_INVOKE_DYNAMIC: 4,
    TAG_MODULE: 2,
    TAG_PACKAGE: 2,
}

PATRON_TIPO_EN_DESCRIPTOR = re.compile(r"L([a-zA-Z_$][\w$/]*(?:/[\w$]+)*);")

# Los cuatro atributos que llevan anotaciones y le importan a los validadores.
# Los de PARAMETRO son imprescindibles: `@Parameter` de una function vive solo
# ahi, y sin ellos el escaner no veia ni una de las tres anotaciones que usa
# el tipo mas comun de plug-in.
NOMBRES_ATRIBUTO_DE_ANOTACION = (
    "RuntimeVisibleAnnotations",
    "RuntimeInvisibleAnnotations",
    "RuntimeVisibleParameterAnnotations",
    "RuntimeInvisibleParameterAnnotations",
)


@dataclasses.dataclass
class MetodoLeido:
    nombre: str
    descriptor: str
    anotaciones: set[str]


@dataclasses.dataclass
class ClaseLeida:
    nombre_clase: str
    major: int
    tipos_referenciados: set[str]
    cadenas: set[str]
    metodos: list[MetodoLeido]
    anotaciones_de_clase: set[str] = dataclasses.field(default_factory=set)
    #: Pares `(tipo, nombre_de_miembro)` de lo que esta clase INVOCA o LEE:
    #: `("java.util.Locale", "setDefault")`. Sale de resolver cada `Methodref`,
    #: `InterfaceMethodref` y `Fieldref` contra su `CONSTANT_Class` y su
    #: `NameAndType`, enlace que antes se tiraba.
    #:
    #: Por que hace falta: `tipos_referenciados` y `cadenas` son dos conjuntos
    #: SUELTOS, asi que una regla que los cruce no puede saber si las dos
    #: senales vienen de la misma llamada — es la fragilidad que R-A02, R-A05 y
    #: R-A06 declaran por escrito. Con el par resuelto, una regla sobre un
    #: metodo concreto de un tipo concreto es EXACTA, como R-A10.
    miembros_invocados: set[tuple[str, str]] = dataclasses.field(default_factory=set)


def tipos_de_descriptor(descriptor: str) -> set[str]:
    return {_normalizar(m) for m in PATRON_TIPO_EN_DESCRIPTOR.findall(descriptor)}


def _normalizar(nombre_interno: str) -> str:
    """Convierte com/x/Y en com.x.Y y descarta descriptores de array.

    El `$` de las clases internas se traduce tambien a punto, y no es un
    detalle cosmetico: el indice de tipos documentado guarda
    `SmartServiceException.Builder` —con punto— y no tiene ni una sola de sus
    906 entradas con `$`. Conservarlo hacia que
    `SmartServiceException$Builder` no casara nunca y se reportara como API no
    documentada... sobre una linea que escribe el propio andamiador, en el
    100 % de los smart services. Es peor que un falso positivo cualquiera:
    entrena al usuario a ignorar la unica puerta de superficie que tiene.
    """
    limpio = nombre_interno.lstrip("[")
    if limpio.startswith("L") and limpio.endswith(";"):
        limpio = limpio[1:-1]
    return limpio.replace("/", ".").replace("$", ".")


def leer(ruta: pathlib.Path) -> ClaseLeida:
    datos = ruta.read_bytes()
    if datos[:4] != b"\xca\xfe\xba\xbe":
        raise ValueError(f"{ruta} no es un fichero .class (falta el magic CAFEBABE)")

    major = struct.unpack_from(">H", datos, 6)[0]
    contador = struct.unpack_from(">H", datos, 8)[0]

    utf8: dict[int, str] = {}
    indices_clase: list[int] = []
    indices_nombre_y_tipo: list[tuple[int, int]] = []
    # Los tres mapas que hacen falta para resolver `miembros_invocados`. Se
    # guardan por INDICE DE POOL —no solo el valor— porque una referencia a
    # miembro apunta a sus dos mitades por indice, y el pool admite referencias
    # hacia adelante: resolver dentro del bucle fallaria. Se resuelve al final.
    clase_por_indice: dict[int, int] = {}
    nombre_y_tipo_por_indice: dict[int, tuple[int, int]] = {}
    referencias_a_miembro: list[tuple[int, int]] = []

    pos = 10
    indice = 1
    while indice < contador:
        tag = datos[pos]
        pos += 1
        if tag == TAG_UTF8:
            longitud = struct.unpack_from(">H", datos, pos)[0]
            pos += 2
            utf8[indice] = datos[pos : pos + longitud].decode("utf-8", errors="replace")
            pos += longitud
        else:
            if tag == TAG_CLASS:
                idx_nombre_clase = struct.unpack_from(">H", datos, pos)[0]
                indices_clase.append(idx_nombre_clase)
                clase_por_indice[indice] = idx_nombre_clase
            elif tag == TAG_NAME_AND_TYPE:
                par = struct.unpack_from(">HH", datos, pos)
                indices_nombre_y_tipo.append(par)
                nombre_y_tipo_por_indice[indice] = par
            elif tag in (TAG_FIELDREF, TAG_METHODREF, TAG_INTERFACE_METHODREF):
                referencias_a_miembro.append(struct.unpack_from(">HH", datos, pos))
            tamano = TAMANOS_FIJOS.get(tag)
            if tamano is None:
                raise ValueError(f"tag desconocido {tag} en el constant pool de {ruta}")
            pos += tamano
        # LONG y DOUBLE ocupan DOS entradas del pool. Olvidarlo desalinea todo
        # lo que venga despues: es el error clasico al leer un .class.
        if tag in (TAG_LONG, TAG_DOUBLE):
            indice += 2
        else:
            indice += 1

    tipos: set[str] = set()
    for i in indices_clase:
        if i in utf8:
            tipos.add(_normalizar(utf8[i]))
    # Los descriptores aportan tipos que a veces no tienen entrada CONSTANT_Class
    # propia: se extraen tambien de ahi.
    for _, idx_desc in indices_nombre_y_tipo:
        if idx_desc in utf8:
            tipos |= tipos_de_descriptor(utf8[idx_desc])

    pos = _saltar_cabecera_clase(datos, pos)
    pos, campos = _leer_miembros(datos, pos, utf8)
    pos, metodos = _leer_miembros(datos, pos, utf8)
    # La tabla de atributos DE LA CLASE va justo despues de la de metodos, y
    # es donde vive `@Category` de una function y la anotacion de paleta de un
    # smart service. No se parseaba en absoluto.
    _, anotaciones_de_clase = _leer_atributos(datos, pos, utf8)

    # Los campos y metodos DECLARADOS por esta clase aportan sus propios tipos
    # aunque nadie los invoque: si no se llaman, el pool no genera para ellos
    # ninguna entrada NameAndType, y el bucle de arriba no los alcanzaria.
    #
    # Y sus ANOTACIONES son tipos de Appian tanto como cualquier otro: una
    # anotacion no genera entrada CONSTANT_Class ni descriptor NameAndType, asi
    # que ninguna de las dos vias de arriba la alcanza. Fusionarlas es lo que
    # separa «0 tipos, exit 0» sobre un function real de un inventario que
    # dice la verdad — la vacuidad se habia mudado de «cero clases» a «cero
    # tipos de una clase», y la guarda `if not clases` no puede verla.
    for miembro in (*campos, *metodos):
        tipos |= tipos_de_descriptor(miembro.descriptor)
        tipos |= miembro.anotaciones
    tipos |= anotaciones_de_clase

    nombre_clase = _nombre_de_esta_clase(datos, utf8, contador)
    cadenas = {v for v in utf8.values()}

    miembros_invocados: set[tuple[str, str]] = set()
    for idx_clase, idx_nombre_y_tipo in referencias_a_miembro:
        nombre_del_tipo = utf8.get(clase_por_indice.get(idx_clase, -1), "")
        par = nombre_y_tipo_por_indice.get(idx_nombre_y_tipo)
        if not nombre_del_tipo or par is None:
            continue
        nombre_del_miembro = utf8.get(par[0], "")
        if nombre_del_miembro:
            miembros_invocados.add((_normalizar(nombre_del_tipo), nombre_del_miembro))

    return ClaseLeida(
        nombre_clase=nombre_clase,
        major=major,
        tipos_referenciados=tipos,
        cadenas=cadenas,
        metodos=metodos,
        anotaciones_de_clase=anotaciones_de_clase,
        miembros_invocados=miembros_invocados,
    )


def _nombre_de_esta_clase(datos: bytes, utf8: dict[int, str], contador: int) -> str:
    # this_class va justo despues del pool: se relee el pool para localizar su
    # offset exacto sin duplicar la logica de tamanos.
    pos = 10
    indice = 1
    indices_clase: dict[int, int] = {}
    while indice < contador:
        tag = datos[pos]
        pos += 1
        if tag == TAG_UTF8:
            longitud = struct.unpack_from(">H", datos, pos)[0]
            pos += 2 + longitud
        else:
            if tag == TAG_CLASS:
                indices_clase[indice] = struct.unpack_from(">H", datos, pos)[0]
            pos += TAMANOS_FIJOS[tag]
        indice += 2 if tag in (TAG_LONG, TAG_DOUBLE) else 1
    this_class = struct.unpack_from(">H", datos, pos + 2)[0]
    return _normalizar(utf8.get(indices_clase.get(this_class, -1), ""))


def _saltar_cabecera_clase(datos: bytes, pos: int) -> int:
    # access_flags, this_class, super_class
    pos += 6
    interfaces = struct.unpack_from(">H", datos, pos)[0]
    pos += 2 + interfaces * 2
    return pos


def _leer_atributos(datos: bytes, pos: int, utf8: dict[int, str]) -> tuple[int, set[str]]:
    """Recorre una tabla de atributos y devuelve los tipos de anotacion.

    Es la MISMA tabla en los tres sitios donde aparece —campo, metodo y
    clase—, asi que la lee una sola funcion: cuando solo la leian los
    miembros, las anotaciones a nivel de clase no se parseaban en absoluto.
    """
    cantidad = struct.unpack_from(">H", datos, pos)[0]
    pos += 2
    anotaciones: set[str] = set()
    for _ in range(cantidad):
        idx_attr, longitud = struct.unpack_from(">HI", datos, pos)
        pos += 6
        if utf8.get(idx_attr, "") in NOMBRES_ATRIBUTO_DE_ANOTACION:
            anotaciones |= _tipos_en_bloque_de_anotaciones(datos[pos : pos + longitud], utf8)
        pos += longitud
    return pos, anotaciones


def _leer_miembros(datos: bytes, pos: int, utf8: dict[int, str]) -> tuple[int, list[MetodoLeido]]:
    cantidad = struct.unpack_from(">H", datos, pos)[0]
    pos += 2
    miembros: list[MetodoLeido] = []
    for _ in range(cantidad):
        _flags, idx_nombre, idx_desc = struct.unpack_from(">HHH", datos, pos)
        pos += 6
        pos, anotaciones = _leer_atributos(datos, pos, utf8)
        miembros.append(
            MetodoLeido(
                nombre=utf8.get(idx_nombre, ""),
                descriptor=utf8.get(idx_desc, ""),
                anotaciones=anotaciones,
            )
        )
    return pos, miembros


def _tipos_en_bloque_de_anotaciones(bloque: bytes, utf8: dict[int, str]) -> set[str]:
    """Extrae los tipos de anotacion de forma tolerante.

    Se leen los indices del principio de cada anotacion en vez de recorrer el
    arbol completo de element_value: basta para saber QUE anotaciones lleva un
    metodo, que es lo unico que necesitan los validadores.

    Sobre-aproxima, y el error esta ACOTADO por construccion: solo puede
    devolver tipos cuyo descriptor ya existe como cadena UTF-8 en el pool de
    esta misma clase, asi que a lo sumo adelanta un tipo que la clase
    referencia por otra via — nunca inventa uno.
    """
    encontrados: set[str] = set()
    for i in range(0, max(0, len(bloque) - 1), 1):
        idx = struct.unpack_from(">H", bloque, i)[0]
        texto = utf8.get(idx, "")
        if texto.startswith("L") and texto.endswith(";"):
            encontrados.add(_normalizar(texto))
    return encontrados
