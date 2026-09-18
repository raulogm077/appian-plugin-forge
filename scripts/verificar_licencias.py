"""Capa 1B (licencias): copyleft entre las dependencias de terceros.

Es la politica mas tajante de toda la pagina de AppMarket, y la unica que usa
un absoluto: *"Plug-ins must not include **any** third-party libraries licensed
under copyleft or similar terms which require software distributed with or
linking to those libraries to be distributed under similar terms"*
(docs.appian.com, AppMarket Submission Policies for Plug-Ins).

Hasta ahora NO estaba mecanizada, y el orquestador lo decia con todas las
letras en la evidencia de su puerta: «el juicio sobre copyleft NO esta
mecanizado -- R-J07 solo comprueba que LICENSE y THIRD_PARTY_NOTICES.md
existan». Un hueco declarado, no una mentira; pero un hueco que puede costar el
rechazo del envio, que es una semana.

De donde sale el dato, y por que no de la red. El build ya genera un SBOM
CycloneDX (`./gradlew cyclonedxDirectBom`) resolviendo el `runtimeClasspath`
de verdad. Este validador LO LEE, igual que `salida_build` lee el log de
Gradle: quien resuelve dependencias es Gradle, no nosotros. La alternativa
--bajarse los POM de Maven Central desde aqui-- metaria red en tiempo de
verificacion, y ahora mismo ningun script del forge la toca.

LIMITE DECLARADO, y conviene leerlo antes de confiar: esto es una comprobacion
mecanica sobre identificadores SPDX, no un dictamen legal. Cubre lo que el
SBOM declara; una dependencia con la licencia mal declarada en su POM se
escapa, y una licencia doble se resuelve por la mas restrictiva.
"""

from __future__ import annotations

import json
import pathlib
import re

import contrato
from verificar_framework import Hallazgo

RUTA_SBOM_POR_DEFECTO = "build/reports/sbom"

# Familias SIN numero de version a proposito: el mismo identificador llega
# como `GPL-3.0`, `GPL-3.0-only`, `GPL-2.0-or-later` o con el nombre largo, y
# enumerar versiones obliga a mantener una lista que se queda corta sola.
#
# Copyleft fuerte: contamina la obra entera. Rechazo directo.
COPYLEFT_FUERTE = ("AGPL", "SSPL", "OSL-", "EUPL", "GPL")
# Copyleft debil: obliga a distribuir bajo terminos similares lo que se enlaza
# o deriva. La politica de Appian dice «or similar terms», asi que entran; se
# separan de los fuertes solo para que el mensaje pueda decir cual es.
COPYLEFT_DEBIL = ("LGPL", "MPL", "EPL", "CDDL", "CPL", "CC-BY-SA")

# EL ORDEN IMPORTA Y NO ES ESTETICO: `LGPL` contiene `GPL`. Si se comprobara
# primero lo fuerte, toda LGPL se clasificaria como fuerte y el mensaje
# mentiria sobre cual de las dos es.
_FAMILIAS = (("debil", COPYLEFT_DEBIL), ("fuerte", COPYLEFT_FUERTE))

# El nombre largo, que es como lo escribe media Maven Central. Se comprueban
# ANTES que las siglas porque no contienen la sigla: «Eclipse Public License»
# no lleva «EPL» dentro. Ordenados de mas especifico a menos: «Lesser General
# Public License» tiene que ganarle a «General Public License».
NOMBRES_LARGOS = (
    ("AFFERO-GENERAL-PUBLIC-LICENSE", "fuerte"),
    ("SERVER-SIDE-PUBLIC-LICENSE", "fuerte"),
    ("EUROPEAN-UNION-PUBLIC-LICENCE", "fuerte"),
    ("EUROPEAN-UNION-PUBLIC-LICENSE", "fuerte"),
    ("OPEN-SOFTWARE-LICENSE", "fuerte"),
    ("GENERAL-PUBLIC-LICENSE", "gpl"),   # resuelve fuerte/debil por LESSER|LIBRARY
    ("ECLIPSE-PUBLIC-LICENSE", "debil"),
    ("MOZILLA-PUBLIC-LICENSE", "debil"),
    ("COMMON-DEVELOPMENT-AND-DISTRIBUTION-LICENSE", "debil"),
    ("COMMON-PUBLIC-LICENSE", "debil"),
    ("COMMON-PUBLIC-ATTRIBUTION-LICENSE", "debil"),
    ("RECIPROCAL-PUBLIC-LICENSE", "debil"),
    ("SHARE-ALIKE", "debil"),
)


def _normalizar(texto: str) -> str:
    """`GPL 3.0` / `gpl_3` / `GPL-3.0-only` -> una forma comparable.

    Se normalizan LOS DOS lados de la comparacion. Normalizar solo la entrada
    --que fue el primer intento-- hacia que ninguna marca con punto casara
    jamas: `GPL-3.0` no aparece nunca dentro de `GPL-3-0`.
    """
    return re.sub(r"[\s_.]+", "-", texto.upper())


def clasificar(licencia: str) -> str | None:
    """«fuerte», «debil» o None si no parece copyleft.

    Se normaliza a mayusculas y se quitan separadores porque el mismo texto
    llega como `GPL-3.0-only`, `GPL 3.0`, `gpl_3` o `GNU General Public
    License v3.0` segun quien haya rellenado el POM.
    """
    normalizada = _normalizar(licencia)

    # Los nombres largos PRIMERO: `Eclipse Public License 2.0` no contiene
    # `EPL` por ninguna parte, y sin esta tabla escapaban enteros --con la
    # puerta imprimiendo «0 hallazgos» sin haber podido ver nada, que es la
    # forma exacta del verde vacuo--. Antes solo la familia GPL tenia
    # tratamiento de nombre largo.
    for patron, familia in NOMBRES_LARGOS:
        if patron in normalizada:
            if familia == "gpl":
                return "debil" if ("LESSER" in normalizada or "LIBRARY" in normalizada) else "fuerte"
            return familia

    # Y las siglas con LIMITE a los dos lados, nunca por subcadena suelta.
    # `MPL` es subcadena de `SIMPLIFIED`, asi que
    # `BSD 2-Clause "Simplified" License` --el nombre canonico SPDX de una
    # licencia permisiva-- se clasificaba como copyleft debil y bloqueaba el
    # READY acusando en falso. El limite tambien resuelve solo el caso de
    # `GPL` dentro de `AGPL`/`LGPL`, que antes dependia del orden.
    for familia, marcas in _FAMILIAS:
        for m in marcas:
            marca = re.escape(_normalizar(m).strip("-"))
            if re.search(rf"(?<![A-Z0-9]){marca}(?![A-Z0-9])", normalizada):
                return familia
    return None


def licencias_de(componente: dict) -> list[str]:
    """Todo texto de licencia que el componente declare, en cualquiera de las
    tres formas que admite CycloneDX: `license.id`, `license.name` y
    `expression` (que es donde acaban los `OR`/`AND` de las licencias dobles).
    """
    encontradas: list[str] = []
    for entrada in componente.get("licenses") or []:
        if "expression" in entrada:
            encontradas.append(entrada["expression"])
        licencia = entrada.get("license") or {}
        for clave in ("id", "name"):
            if licencia.get(clave):
                encontradas.append(licencia[clave])
    return encontradas


def comprobar(sbom: dict) -> list[Hallazgo]:
    hallazgos: list[Hallazgo] = []
    for componente in sbom.get("components") or []:
        coordenada = ":".join(
            str(componente.get(c, "")) for c in ("group", "name", "version")
        ).strip(":")
        licencias = licencias_de(componente)

        if not licencias:
            # No se resuelve a favor: no se puede afirmar que cumple una
            # politica de licencias sobre una licencia que no consta. Es el
            # mismo criterio que UNKNOWN -> FAIL del escaner de superficie.
            hallazgos.append(
                Hallazgo("R-L02", "error",
                         f"{coordenada} no declara licencia en el SBOM: no se puede afirmar que "
                         f"no sea copyleft. Declararla en el POM o justificarla a mano")
            )
            continue

        # Una licencia doble se resuelve por la MAS restrictiva: si cualquiera
        # de las declaradas es copyleft, hay que poder elegir la otra, y esa
        # eleccion no la puede hacer un script.
        for texto in licencias:
            familia = clasificar(texto)
            if familia:
                hallazgos.append(
                    Hallazgo("R-L01", "error",
                             f"{coordenada} usa «{texto}», copyleft {familia}: AppMarket prohibe "
                             f"expresamente incluir CUALQUIER libreria de terceros con copyleft "
                             f"«or similar terms». Sustituirla, o aportar la licencia alternativa "
                             f"si es doble")
                )
                break
    return hallazgos


def localizar_sbom(raiz: pathlib.Path) -> pathlib.Path | None:
    directorio = raiz / RUTA_SBOM_POR_DEFECTO
    if not directorio.is_dir():
        return None
    return next(iter(sorted(directorio.glob("*.json"))), None)


def main() -> int:
    import sys

    if len(sys.argv) < 2:
        print("uso: verificar_licencias.py <raiz-proyecto|sbom.json>")
        return 2

    argumento = pathlib.Path(sys.argv[1])
    ruta = argumento if argumento.suffix == ".json" else localizar_sbom(argumento)
    if ruta is None or not ruta.is_file():
        # No poder mirar no es «ya lo miraremos»: mismo criterio que el JAR
        # ausente en la capa 4.
        print(f"ERROR no hay ningun SBOM en {argumento / RUTA_SBOM_POR_DEFECTO}: generarlo con "
              f"`./gradlew cyclonedxDirectBom`. Sin el no se puede juzgar ninguna licencia.")
        return 1

    try:
        sbom = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR el SBOM {ruta} no se pudo leer: {e}")
        return 1

    componentes = sbom.get("components") or []
    hallazgos = comprobar(sbom)
    # Sin unidad portante A PROPOSITO: cero dependencias de terceros es
    # legitimo y frecuente --el SDK y log4j son `compileOnly`, los provee el
    # contenedor--, asi que exigir que no sea cero seria una alarma que salta
    # siempre, y una alarma que salta siempre ensena a ignorarla.
    #
    # Pero el insumo NO es solo la cuenta de dependencias: es el SBOM leido.
    # Declarar unicamente `dependencias=0` hacia que la regla de «todas las
    # unidades a cero» marcara la puerta como verde vacuo y bloqueara el READY
    # de cualquier plug-in sin terceros --que son la mayoria--. El trabajo
    # hecho aqui es real y se declara: se leyo UN SBOM, y tenia N componentes.
    return contrato.informar(
        hallazgos,
        insumo=contrato.linea_de_insumo(sbom_leido=1, dependencias=len(componentes)),
        detalle=f" sobre {len(componentes)} dependencias de terceros",
    )


if __name__ == "__main__":
    raise SystemExit(main())
