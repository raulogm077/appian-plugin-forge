"""Capa 2: superficie de API usada, contra el indice documentado.

Compilar es necesario pero NO suficiente (spec §5.3): el JAR expone ~85 tipos
fuera del javadoc publico y compilan sin protesta. Appian exige usar «only the
classes and methods documented in the Public API javadocs», que es una politica
de soporte, no una barrera del compilador.

Residuo declarado: la carga dinamica por cadena (Class.forName) no la ve ningun
analisis estatico; por eso la reflexion sobre com.appiancorp.* se prohibe en la
capa 1 (verificar_appmarket.py).
"""

from __future__ import annotations

import dataclasses
import json
import pathlib

import contrato

PREFIJO_APPIAN = "com.appiancorp."

# Red gruesa de respaldo, y SOLO para cuando falte el indice congelado. Son los
# seis prefijos en que colapsan los 61 paquetes documentados del snapshot 26.3,
# asi que es un dato DERIVADO —regenerable desde assets/indice-tipos-26.3.json—
# y no una lista custodiada a mano.
# Es deliberadamente gruesa: deja pasar clases no documentadas que vivan dentro
# de estos prefijos, que es justo la razon por la que el indice a nivel de tipo
# es la via buena. Pero acepta AppianSmartService en vez de rechazarlo, que es
# lo que hacia la version anterior de este codigo.
PAQUETES_RESPALDO = (
    "com.appiancorp.suiteapi",
    "com.appiancorp.common",
    "com.appiancorp.services",
    "com.appiancorp.ap2",
    "com.appiancorp.exceptions",
    "com.appiancorp.type",
)


@dataclasses.dataclass
class Informe:
    no_documentados: list[tuple[str, str]]
    inventario: dict[str, list[str]]
    modo_degradado: bool


def analizar(clases: list, indice: dict | None) -> Informe:
    documentados = set(indice["tipos"]) if indice else set()
    paquetes = set(indice["paquetes"]) if indice else set()
    degradado = indice is None

    no_documentados: list[tuple[str, str]] = []
    inventario: dict[str, list[str]] = {}

    for leida in clases:
        for tipo in sorted(leida.tipos_referenciados):
            if not tipo.startswith(PREFIJO_APPIAN):
                continue
            inventario.setdefault(tipo, []).append(leida.nombre_clase)
            if degradado:
                # Red gruesa de respaldo: sin indice solo se puede mirar el
                # prefijo de paquete, y eso se DECLARA en el certificado.
                # Ojo: aqui NO sirve `paquetes`, que sin indice esta vacio y
                # haria que se rechazara el 100% de las referencias.
                if not any(tipo.startswith(p + ".") for p in PAQUETES_RESPALDO):
                    no_documentados.append((leida.nombre_clase, tipo))
            elif tipo not in documentados:
                no_documentados.append((leida.nombre_clase, tipo))

    for tipo in inventario:
        inventario[tipo] = sorted(set(inventario[tipo]))

    return Informe(no_documentados, inventario, degradado)


def comprobar_dominio_sin_sdk(clases: list, paquetes_dominio: list[str]) -> list[str]:
    """D19: el dominio no conoce el SDK.

    Es lo que permite que los tests JUnit —lo mas parecido a una ejecucion real
    de que disponemos— corran sin cargar el SDK.
    """
    violaciones: list[str] = []
    for leida in clases:
        if not any(
            leida.nombre_clase.startswith(p + ".") or leida.nombre_clase == p
            for p in paquetes_dominio
        ):
            continue
        for tipo in sorted(leida.tipos_referenciados):
            if tipo.startswith(PREFIJO_APPIAN):
                violaciones.append(
                    f"{leida.nombre_clase} pertenece al dominio y referencia {tipo} (D19)"
                )
    return violaciones


def cargar_clases(directorio: pathlib.Path) -> list:
    import struct

    import classfile

    clases = []
    for ruta in sorted(directorio.rglob("*.class")):
        try:
            clases.append(classfile.leer(ruta))
        except (IndexError, struct.error, EOFError) as error:
            # Un `.class` truncado --a medio escribir, o cortado por un build
            # interrumpido-- moria con `IndexError: index out of range` SIN el
            # nombre del fichero, que es lo unico que hace falta para
            # arreglarlo. Prueba adversaria del 21-sep-2026, caso 10a.
            raise ValueError(
                f"{ruta}: no se pudo leer como fichero .class ({type(error).__name__}: "
                f"{error}); si esta truncado, vuelve a construir con `./gradlew build`"
            ) from None
    return clases


RUTA_INVENTARIO_POR_DEFECTO = "build/reports/inventario-api.json"


def _extraer_inventario(argumentos: list[str]) -> tuple[list[str], pathlib.Path]:
    """Saca `--inventario RUTA` de la lista y devuelve el resto.

    El inventario se escribia SIEMPRE relativo al cwd, y `generar_dossier` lo
    lee relativo a la raiz del proyecto: la pieza 3 del dossier salia siempre
    «pendiente», y un inventario rancio de otro plug-in podia acabar publicado
    bajo un encabezado que afirma su procedencia («extraido del constant pool»
    de las clases de ESTE plug-in). Quien invoca dice donde va.
    """
    restantes: list[str] = []
    destino = pathlib.Path(RUTA_INVENTARIO_POR_DEFECTO)
    i = 0
    while i < len(argumentos):
        if argumentos[i] == "--inventario" and i + 1 < len(argumentos):
            destino = pathlib.Path(argumentos[i + 1])
            i += 2
            continue
        restantes.append(argumentos[i])
        i += 1
    return restantes, destino


def main() -> int:
    import sys

    argumentos, destino = _extraer_inventario(sys.argv[1:])
    if len(argumentos) < 2:
        print("uso: verificar_superficie.py <dir-clases> <indice.json> "
              "[--inventario <ruta.json>] [paquete-dominio…]")
        return 2
    dir_clases, ruta_indice_txt, paquetes_dominio = argumentos[0], argumentos[1], argumentos[2:]
    clases = cargar_clases(pathlib.Path(dir_clases))
    # Analizar CERO clases no es verificar: sin esto, un proyecto sin compilar
    # daba «0 problemas» y salia con 0, y el certificado lo mostraba en verde.
    # Es justo el verde vacuo que la regla «una puerta que no se ejecuto nunca
    # se marca como pasada» existe para impedir.
    if not clases:
        print(f"{contrato.PREFIJO_ERROR} no hay ninguna clase que analizar en {dir_clases}: "
              f"¿se ha compilado el proyecto? Analizar cero clases NO es verificar.")
        return 1
    ruta_indice = pathlib.Path(ruta_indice_txt)
    indice = json.loads(ruta_indice.read_text(encoding="utf-8")) if ruta_indice.is_file() else None
    informe = analizar(clases, indice)

    if informe.modo_degradado:
        print(f"{contrato.PREFIJO_AVISO}: sin indice de tipos; filtro por paquete "
              f"(declararlo en el certificado)")
    for clase_usa, tipo in informe.no_documentados:
        print(f"{contrato.PREFIJO_ERROR} {clase_usa} referencia API no documentada: {tipo}")

    violaciones = comprobar_dominio_sin_sdk(clases, paquetes_dominio)
    for v in violaciones:
        print(f"{contrato.PREFIJO_ERROR} {v}")

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(
            {
                "version_indice": (indice or {}).get("version"),
                "hash_indice": (indice or {}).get("hash_sha256"),
                "inventario": informe.inventario,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # Antes que el resumen: el orquestador se queda con la ULTIMA linea como
    # evidencia de una puerta verde, y esa sigue siendo la del inventario.
    # `clases_de_dominio` se DECLARA y no es portante, a propósito. D19 solo
    # puede violarse si hay clases en el paquete de dominio; cero es legitimo
    # --un andamiaje recien generado no tiene dominio todavia-- asi que exigirlo
    # seria una alarma que salta siempre. Pero callarlo era peor: hasta el ciclo
    # 6 el orquestador no pasaba ningun paquete de dominio, la comprobacion
    # devolvia `[]` SIEMPRE, y nada en la evidencia lo distinguia de «mire y
    # esta limpio». Ahora la celda dice cuantas clases se miraron.
    de_dominio = sum(
        1 for c in clases
        if any(c.nombre_clase.startswith(p + ".") or c.nombre_clase == p
               for p in paquetes_dominio)
    )
    print(contrato.linea_de_insumo(
        clases=len(clases), tipos_de_appian=len(informe.inventario),
        clases_de_dominio=de_dominio,
        # Cero tipos SOLO puede significar escaner roto: toda clase de un
        # plug-in referencia al menos sus anotaciones de Appian. Es la
        # instancia mas cara de la familia, y la que la regla vieja no veia.
        portante="tipos_de_appian",
    ))
    print(f"Inventario de API escrito en {destino} ({len(informe.inventario)} tipos)")
    return 1 if (informe.no_documentados or violaciones) else 0


if __name__ == "__main__":
    raise SystemExit(main())
