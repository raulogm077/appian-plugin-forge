"""Lee el resultado REAL de `./gradlew build` y lo trae al certificado.

Este orquestador no invoca Gradle --no puede: el build tarda minutos, necesita
red la primera vez y su toolchain es del proyecto generado, no de aqui--. Pero
NO invocarlo no autoriza a callar sobre el. Cinco puertas del certificado
declaraban el comando que las ejecutaria y nada leia jamas su resultado: un
servlet cuyo build fallaba en `spotbugsMain` certificaba EXACTAMENTE IGUAL que
un `function` que pasaba. Sexta instancia del verde vacuo, y la de mas arriba.

Delegar es nombrar a quien mira. Este modulo es el que va a buscar lo que ese
alguien vio.

Regla, la misma que ya rige para el JAR ausente: no poder mirar no es «ya lo
miraremos». Un log ausente, truncado, rancio o que se contradice con su codigo
de salida vale lo mismo que un log que dice BUILD FAILED — rojo. Una fila que
no puede distinguir exito de fracaso es peor que una fila en rojo, porque la
primera miente y la segunda solo declara ignorancia.
"""

from __future__ import annotations

import codecs
import dataclasses
import pathlib
import re

# Como termino el build. Solo los dos primeros son constancia de algo; los
# otros tres son formas distintas de no saberlo, y ninguna se resuelve a favor.
EXITOSO = "exitoso"
FALLIDO = "fallido"
INDETERMINADO = "indeterminado"   # el log existe pero no dice como acabo
AUSENTE = "ausente"               # no hay log
RANCIO = "rancio"                 # el log es anterior al codigo que certifica

# Donde el paso 4 · BUILD deja su salida. Que haya una ruta convenida es lo que
# permite que el camino normal funcione sin argumentos extra; `--salida-build`
# la sobreescribe cuando el build se capturo en otro sitio.
RUTA_POR_DEFECTO = pathlib.Path("build") / "salida-build.log"

# El `mkdir -p` va DENTRO del comando y no es adorno: el shell abre la
# redireccion antes de lanzar Gradle, asi que sobre un proyecto recien
# andamiado --donde `build/` todavia no existe, que es justo cuando esta puerta
# manda capturar por primera vez-- el comando sin el falla con «No such file or
# directory» y no se construye nada. La cadena es la MISMA que publica el paso 5
# de la SKILL, y un test la ata a un literal propio para que no puedan divergir.
COMANDO_DE_CAPTURA = "mkdir -p build && ./gradlew build --console=plain > build/salida-build.log 2>&1"

# Ficheros cuyo cambio deja obsoleto un log anterior. `exclude.xml` esta en la
# lista por el flujo del SECSP: descomentar la exclusion y no volver a
# construir dejaria un log viejo certificando un codigo que ya no es el que se
# entrega.
FUENTES_QUE_INVALIDAN = (
    "build.gradle",
    "config/spotbugs/exclude.xml",
    # Los dos textos legales que `build.gradle` copia a `META-INF` y que R-J07
    # lee de DENTRO del JAR: tocarlos cambia el artefacto y el log no se
    # enteraba. Y el wrapper, que fija la version de Gradle con la que se
    # construyo. Levantado por el gate del ciclo 16.
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "gradle/wrapper/gradle-wrapper.properties",
)

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_TAREA = re.compile(r"^>\s+Task\s+(:[\w:.\-]+)(?:\s+([A-Z][A-Z\-]*))?\s*$")
_MARCADOR = re.compile(r"^BUILD (SUCCESSFUL|FAILED)\b")
_FALLO_DE_TAREA = re.compile(r"Execution failed for task '(:[\w:.\-]+)'")


@dataclasses.dataclass
class ResultadoBuild:
    desenlace: str
    tareas: dict[str, str] = dataclasses.field(default_factory=dict)
    motivo: str = ""
    origen: str = ""

    @property
    def consta(self) -> bool:
        """Si hay constancia de COMO termino. Ni `rancio` ni `indeterminado`
        la tienen, y por eso valen lo mismo que no tener log."""
        return self.desenlace in (EXITOSO, FALLIDO)

    @property
    def tarea_que_fallo(self) -> str:
        return next((t for t, d in self.tareas.items() if d == "FAILED"), "")


def _decodificar(datos: bytes) -> str:
    """UTF-8, UTF-16 o cp1252, segun quien capturase el log.

    `./gradlew build > log 2>&1` desde PowerShell 5.1 escribe UTF-16LE con BOM.
    Leido como UTF-8 no aparece ningun marcador y la puerta saldria roja por el
    motivo equivocado --«no consta el build»-- teniendo el build delante.
    Misma familia que la trampa del cp1252 ya documentada en este repositorio.
    """
    for bom, codec in (
        (codecs.BOM_UTF8, "utf-8-sig"),
        (codecs.BOM_UTF16_LE, "utf-16"),
        (codecs.BOM_UTF16_BE, "utf-16"),
    ):
        if datos.startswith(bom):
            return datos.decode(codec)
    # UTF-16 sin BOM no falla al decodificar como UTF-8 --el byte NUL es UTF-8
    # valido--, asi que no basta con probar y ver si revienta.
    if b"\x00" in datos[:400]:
        for codec in ("utf-16-le", "utf-16-be"):
            try:
                return datos.decode(codec)
            except UnicodeDecodeError:
                pass
    for codec in ("utf-8", "cp1252"):
        try:
            return datos.decode(codec)
        except UnicodeDecodeError:
            pass
    return datos.decode("utf-8", errors="replace")


def leer(ruta: pathlib.Path) -> str:
    return _decodificar(pathlib.Path(ruta).read_bytes())


def analizar(texto: str, codigo: int | None = None) -> ResultadoBuild:
    """El desenlace y el estado de cada tarea, de la ULTIMA corrida del log.

    Un log al que se le va anadiendo cada `./gradlew build` del paso 4 lleva
    varias corridas pegadas; lo vigente es la ultima, no la primera.
    """
    lineas = _ANSI.sub("", texto or "").splitlines()
    marcadores = [i for i, l in enumerate(lineas) if _MARCADOR.match(l.strip())]

    if not marcadores:
        return ResultadoBuild(
            INDETERMINADO,
            _tareas(lineas),
            "el log no llega a decir como termino el build (truncado o interrumpido): "
            "no saberlo no se resuelve a favor",
        )

    ultimo = marcadores[-1]
    inicio = marcadores[-2] + 1 if len(marcadores) > 1 else 0
    corrida = lineas[inicio:ultimo + 1]
    cierre = lineas[ultimo].strip()
    tareas = _tareas(corrida)
    desenlace = EXITOSO if cierre.startswith("BUILD SUCCESSFUL") else FALLIDO

    if codigo is not None and (codigo == 0) != (desenlace == EXITOSO):
        return ResultadoBuild(
            INDETERMINADO,
            tareas,
            f"el codigo de salida ({codigo}) contradice el «{cierre}» del log: "
            f"la evidencia esta corrupta y no se resuelve a favor",
        )

    if desenlace == EXITOSO:
        return ResultadoBuild(EXITOSO, tareas, cierre)

    culpable = next(
        (m.group(1) for m in map(_FALLO_DE_TAREA.search, corrida) if m), ""
    ) or next((t for t, d in tareas.items() if d == "FAILED"), "")
    motivo = f"{cierre} — fallo `{culpable}`" if culpable else cierre
    return ResultadoBuild(FALLIDO, tareas, motivo)


def _tareas(lineas: list[str]) -> dict[str, str]:
    """`:spotbugsMain` -> `FAILED`. Sin sufijo, Gradle quiere decir ejecutada
    y correcta; se anota como OK para que la ausencia sea distinguible.
    """
    tareas: dict[str, str] = {}
    for linea in lineas:
        m = _TAREA.match(linea.strip())
        if m:
            tareas[m.group(1)] = m.group(2) or "OK"
    return tareas


# QUE DEJA RANCIO A QUE. Dos conjuntos de insumos, no tres nociones distintas
# con el mismo nombre --que es como acabo el ciclo 15, con la prosa llamando
# «el fuente» a tres alcances diferentes--.
#
# `INSUMOS_DEL_BUILD` es el arbol de `src/` ENTERO, no solo los `.java`.
# Restringirlo a `.java` fue el error del ciclo 14 y su justificacion escrita
# era falsa: `build` reejecuta `processResources` y `jar`, asi que tocar
# `src/main/resources/**` --donde viven `appian-plugin.xml` y los
# `bundle_*.properties`, o sea los dos ficheros con los errores que la guia
# documenta como bloqueantes de despliegue-- cambia el artefacto que el log
# certifica. Los dos conjuntos se leen SIEMPRE junto a `FUENTES_QUE_INVALIDAN`,
# que es donde estan los insumos de fuera de `src/`; ver `_mas_reciente`.
#
# Es esta lista y no «todo lo que el build consume»: esa forma universal es la
# que el ciclo 16 encontro falsa, porque prometia cubrir ficheros que nadie
# miraba. Si aparece un insumo nuevo, entra aqui a mano — declarar de menos se
# arregla; prometer de mas se descubre tarde.
#
# `INSUMOS_DEL_CERTIFICADO` anade `docs/contrato.md`, que el build no lee pero
# tres puertas si: un contrato editado despues de certificar deja el
# certificado describiendo otra cosa.
INSUMOS_DEL_BUILD = ("src/**/*",)
INSUMOS_DEL_CERTIFICADO = ("src/**/*", "docs/contrato.md")


def _mas_reciente(
    raiz: pathlib.Path, patrones: tuple[str, ...] = INSUMOS_DEL_BUILD
) -> tuple[float, pathlib.Path] | None:
    candidatos = [p for patron in patrones for p in raiz.glob(patron) if p.is_file()]
    candidatos += [raiz / n for n in FUENTES_QUE_INVALIDAN if (raiz / n).is_file()]
    if not candidatos:
        return None
    return max((p.stat().st_mtime, p) for p in candidatos)


def fuente_posterior_a(
    raiz: pathlib.Path,
    artefacto: pathlib.Path,
    insumos: tuple[str, ...] = INSUMOS_DEL_CERTIFICADO,
) -> pathlib.Path | None:
    """El insumo cuyo cambio deja RANCIO a `artefacto`, o None si no lo hay.

    Es la MISMA MECANICA que `ingerir()` aplica al log del build, sobre un
    conjunto de insumos que el llamador elige: el certificado responde de mas
    cosas que el log --de ahi el defecto por defecto--. Expuesta para que todo
    artefacto derivado pueda DECLARAR su rancidez en vez de callarla, que es la
    regla de la casa: lo ausente ya se declaraba y lo rancio no se veia.
    El caso que la pedia: el paso 6 de la SKILL manda corregir codigo
    y el paso 7 empotra `docs/CERTIFICADO.md` en el dossier; un certificado
    anterior a esa correccion describe un arbol que ya no se entrega. En este
    repositorio lo ausente se declara y lo rancio no se veia.
    """
    artefacto = pathlib.Path(artefacto)
    if not artefacto.is_file():
        return None
    reciente = _mas_reciente(pathlib.Path(raiz), insumos)
    if reciente and artefacto.stat().st_mtime < reciente[0]:
        return reciente[1]
    return None


def ingerir(
    raiz: pathlib.Path,
    ruta: pathlib.Path | None = None,
    codigo: int | None = None,
) -> ResultadoBuild:
    """El resultado del build de este proyecto, o por que no consta."""
    raiz = pathlib.Path(raiz)
    destino = pathlib.Path(ruta) if ruta else raiz / RUTA_POR_DEFECTO

    if not destino.is_file():
        return ResultadoBuild(
            AUSENTE,
            {},
            f"no consta ninguna ejecucion de `./gradlew build`: no existe "
            f"`{RUTA_POR_DEFECTO.as_posix()}`. Capturarla con `{COMANDO_DE_CAPTURA}` "
            f"--o pasar `--salida-build <ruta>`-- y volver a certificar",
        )

    reciente = _mas_reciente(raiz)
    if reciente and destino.stat().st_mtime < reciente[0]:
        return ResultadoBuild(
            RANCIO,
            {},
            f"el log del build es RANCIO: `{destino.name}` es anterior a "
            f"`{reciente[1].name}`, asi que certifica un codigo que ya no es el que se "
            f"entrega. Volver a ejecutar `{COMANDO_DE_CAPTURA}`",
        )

    resultado = analizar(leer(destino), codigo)
    resultado.origen = str(destino)
    return resultado
