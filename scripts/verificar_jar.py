"""Capa 4: empaquetado, cierre de dependencias y contenido del artefacto.

Compilar y testear no dice nada de lo que finalmente se entrega. Reproduce en
Python, fuera de Gradle, las comprobaciones que la tarea `verifyPluginJar` de
la plantilla hace sobre el JAR, para tener una sola herramienta en todas las
capas.

Lo que NO cubre, y se declara en el certificado: la resolucion OSGi
real de la plataforma. El cierre de dependencias atrapa el fallo mas probable
—una clase que falta— pero no un conflicto de versiones con lo que Appian ya
carga.
"""

from __future__ import annotations

import pathlib
import zipfile

from verificar_framework import Hallazgo

TOPE_TAMANO_BYTES = 15 * 1024 * 1024
PROVISTAS_POR_EL_CONTENEDOR = ("appian-plug-in-sdk", "log4j-")


def jar_esperado(coordenada: str) -> str:
    """`grupo:artefacto:version` -> `artefacto-version.jar`, que es como Gradle
    nombra el fichero que copia a META-INF/lib."""
    partes = coordenada.split(":")
    if len(partes) < 3:
        return coordenada
    return f"{partes[1]}-{partes[2]}.jar"


def dependencias_del_contrato(datos_contrato: dict) -> list[str]:
    """Lo que R-J05 debe buscar dentro del JAR, derivado del contrato.

    Antes salia de `sys.argv[3:]`, asi que con la CLI documentada llegaba
    SIEMPRE vacia: la regla que evita un `NoClassDefFoundError` visible solo
    DESPUES de desplegar —el fallo que mas tarde se detecta de toda la
    cadena— pasaba por vacuidad, y sin la guarda de lista vacia que si tenian
    los otros dos validadores. El dato ya estaba en el contrato.

    Alcance declarado: cubre las dependencias DIRECTAS que el contrato
    declara, no sus transitivas. El SBOM (`./gradlew cyclonedxDirectBom`) es
    el inventario completo.
    """
    return [jar_esperado(d) for d in datos_contrato.get("dependencias", [])]


def comprobar(
    ruta_jar: pathlib.Path, datos_contrato: dict, dependencias_esperadas: list[str]
) -> list[Hallazgo]:
    hallazgos: list[Hallazgo] = []
    plugin = datos_contrato["plugin"]

    with zipfile.ZipFile(ruta_jar) as z:
        entradas = [i.filename for i in z.infolist()]

    en_lib = [e for e in entradas if e.startswith("META-INF/lib/") and e.endswith(".jar")]

    # R-J01 · el descriptor va en la RAIZ: «Every Appian Plug-in must have an
    # appian-plugin.xml at the root of the Plug-in jar».
    if "appian-plugin.xml" not in entradas:
        hallazgos.append(
            Hallazgo("R-J01", "error",
                     "appian-plugin.xml no esta en la raiz del JAR, que es donde Appian lo busca")
        )

    # R-J02 · fuente embebida: «Plug-ins must include the source code within the
    # executable» (politica de AppMarket).
    if not any(e.startswith("src/") and e.endswith(".java") for e in entradas):
        hallazgos.append(
            Hallazgo("R-J02", "error",
                     "el JAR no embebe la fuente en src/; AppMarket lo exige")
        )

    # R-J03 · nada de tests ni fixtures dentro del entregable.
    intrusos = [e for e in entradas if e.endswith(("Test.class", "Test.java")) or e.startswith("fixtures/")]
    if intrusos:
        hallazgos.append(
            Hallazgo("R-J03", "error", f"el JAR contiene clases o fixtures de test: {intrusos[:3]}")
        )

    # R-J04 · SDK y log4j los provee el contenedor: NO deben viajar dentro.
    for e in en_lib:
        if any(p in e for p in PROVISTAS_POR_EL_CONTENEDOR):
            hallazgos.append(
                Hallazgo("R-J04", "error",
                         f"{e} esta en META-INF/lib pero lo provee el contenedor; debe declararse "
                         f"compileOnly (auditoria §7.2)")
            )

    # R-J05 · cierre de dependencias: es lo que evita un NoClassDefFoundError
    # que solo aparece DESPUES de desplegar.
    nombres_en_lib = {e.rsplit("/", 1)[-1] for e in en_lib}
    for esperada in dependencias_esperadas:
        if esperada not in nombres_en_lib:
            hallazgos.append(
                Hallazgo("R-J05", "error",
                         f"la dependencia {esperada} esta en runtimeClasspath pero no en "
                         f"META-INF/lib; seria un NoClassDefFoundError tras desplegar")
            )

    # R-J06 · el bundle _en_US tiene que viajar dentro del JAR.
    if plugin["tipo"] != "servlet":
        nombre_bundle = datos_contrato.get("bundle", {}).get("nombre", "")
        ruta_bundle = f"{plugin['key'].replace('.', '/')}/{nombre_bundle}_en_US.properties"
        if ruta_bundle not in entradas:
            hallazgos.append(
                Hallazgo("R-J06", "error",
                         f"falta {ruta_bundle} dentro del JAR; sin bundle el plug-in no despliega")
            )

    # R-J07 · licencia y notices.
    for obligatorio in ("META-INF/LICENSE", "META-INF/THIRD_PARTY_NOTICES.md"):
        if obligatorio not in entradas:
            hallazgos.append(Hallazgo("R-J07", "error", f"falta {obligatorio} en el JAR"))

    # R-J08 · sin entradas duplicadas.
    if len(entradas) != len(set(entradas)):
        duplicadas = sorted({e for e in entradas if entradas.count(e) > 1})
        hallazgos.append(Hallazgo("R-J08", "error", f"el JAR tiene entradas duplicadas: {duplicadas[:3]}"))

    # R-J09 · tope de tamano.
    tamano = ruta_jar.stat().st_size
    if tamano > TOPE_TAMANO_BYTES:
        hallazgos.append(
            Hallazgo("R-J09", "error",
                     f"el JAR pesa {tamano / 1024 / 1024:.1f} MB y supera el tope de "
                     f"{TOPE_TAMANO_BYTES / 1024 / 1024:.0f} MB")
        )

    return hallazgos


def main() -> int:
    import sys

    if len(sys.argv) < 3:
        print("uso: verificar_jar.py <plugin.jar> <contrato.md> [dependencia.jar…]")
        return 2
    return main_con_argumentos(sys.argv[1:])


def main_con_argumentos(argumentos: list[str], datos_contrato: dict | None = None) -> int:
    import contrato

    datos = datos_contrato if datos_contrato is not None else contrato.cargar(
        pathlib.Path(argumentos[1])
    )
    # Las del contrato SIEMPRE; los argumentos sueltos anaden (transitivas que
    # el contrato no puede conocer), no sustituyen.
    esperadas = sorted(set(dependencias_del_contrato(datos)) | set(argumentos[2:]))
    hallazgos = comprobar(pathlib.Path(argumentos[0]), datos, esperadas)
    import zipfile as _zip

    with _zip.ZipFile(pathlib.Path(argumentos[0])) as z:
        entradas_jar = len(z.infolist())
    # La guarda que faltaba. Cero dependencias esperadas es legitimo, pero
    # entonces R-J05 no comprueba NADA, y la evidencia del certificado no
    # puede parecerse a «comprobado y correcto»: se dice con todas las letras.
    declaracion_r_j05 = (
        f"R-J05 comprobo {len(esperadas)} dependencias: {', '.join(esperadas)}"
        if esperadas else
        "R-J05 no comprobo ninguna dependencia: el contrato no declara ninguna"
    )
    return contrato.informar(hallazgos, insumo="\n".join([
        contrato.linea_de_insumo(
            entradas_del_jar=entradas_jar, dependencias_esperadas=len(esperadas),
            # Un zip sin entradas es no haber analizado nada.
            # `dependencias_esperadas` NO es portante: cero dependencias es
            # legitimo, y R-J05 ya lo declara con todas las letras justo debajo.
            portante="entradas_del_jar",
        ),
        declaracion_r_j05,
    ]))


if __name__ == "__main__":
    raise SystemExit(main())
