"""Genera el dossier que viaja con el plugin y hace posible la Fase 2.

Seis piezas (spec §8.1). Las piezas 3 (inventario de API) y 6 (firma publica
congelada) NO se escriben a mano: salen del bytecode y del contrato, en la
misma pasada que alimenta las puertas de verificacion, para que no puedan
desincronizarse del codigo.

La pieza 6 es la que evita romper produccion: sin la firma anterior no hay
contra que comparar cuando la Fase 2 edite este plugin (auditoria §7.4).
"""

from __future__ import annotations

import json
import re

VERSION_SDK = "26.3"

# Las dos piezas de prosa que el modelo escribe y el dossier solo LEE. Viven
# fuera porque `main_con_raiz` reescribe DOSSIER.md entero en cada pasada: todo
# lo que se escriba dentro se pierde en la siguiente.
ARCHIVO_DECISIONES = "docs/decisiones.md"
ARCHIVO_REVISION = "docs/hallazgos-revision.md"


def extraer_firma(datos_contrato: dict) -> dict:
    """La firma congelada, con la MISMA forma que lee R-F08.

    `key` va HERMANA de `firma`, no dentro. No es un detalle de estilo: R-F08
    compara `anterior.get("key")` con la key del contrato, asi que con la key
    metida dentro del objeto firma la comparacion era `None != key`, siempre
    falsa, y la regla callaba — justo al pegar el bloque que la propia
    documentacion nombra como la unica fuente contra la que comparar.

    Formato «nombre:tipo» en entradas y salidas, el mismo que compara R-F08:
    guardar solo el nombre dejaba pasar un cambio de tipo con nombre igual,
    que rompe los procesos vivos exactamente igual que anadir un input.
    """
    return {
        "key": datos_contrato["plugin"]["key"],
        "version": datos_contrato["plugin"]["version"],
        "firma": {
            # Sin la guarda de forma de `contrato.seccion` a proposito: las dos
            # lineas de arriba ya indexan `["plugin"]["key"]` en duro, asi que
            # esta funcion trabaja sobre un contrato YA validado y anadir aqui
            # media guarda daria una robustez que la funcion no tiene.
            "clase": datos_contrato.get("clase", {}).get("nombre", ""),
            "entradas": [
                f"{e['nombre']}:{e['tipo_java']}" for e in datos_contrato.get("entradas", [])
            ],
            "salidas": [
                f"{s['nombre']}:{s['tipo_java']}" for s in datos_contrato.get("salidas", [])
            ],
        },
    }


def toml_de_version_anterior(congelada: dict) -> str:
    """El mismo dato, listo para pegar en el contrato de la version siguiente.

    El contrato es TOML y esta firma solo se congelaba en JSON, que no se
    puede pegar en un contrato. Era la otra mitad de por que nadie poblaba
    nunca `version_anterior` y R-F08 no llegaba a dispararse jamas.

    Se deriva del MISMO diccionario que el bloque JSON, en la misma funcion:
    no pueden divergir.
    """
    firma = congelada["firma"]
    lineas = [
        "[version_anterior]",
        f"key = {json.dumps(congelada['key'])}",
        f"version = {json.dumps(congelada['version'])}",
        "",
        "[version_anterior.firma]",
        f"clase = {json.dumps(firma['clase'])}",
        f"entradas = {json.dumps(firma['entradas'])}",
        f"salidas = {json.dumps(firma['salidas'])}",
    ]
    return "\n".join(lineas)


def perfil_publicado(datos_contrato: dict, certificado_md: str) -> str:
    """El perfil con el que se VERIFICO, no solo el que el contrato promete.

    El dossier empotra el CERTIFICADO.md entero en su pieza 4, y ese certificado
    ya publica el perfil RESUELTO con su nota. Esta cabecera lo leia del
    contrato, asi que un mismo fichero podia afirmar `**Perfil:** ESTANDAR`
    arriba y `**Perfil:** RIGUROSO — lo pide quien lanzo la verificacion` dentro:
    las dos afirmaciones contrarias, que es literalmente el dano que el ciclo 7
    cito para justificar la resolucion de perfil. La correccion cerro la rama de
    degradacion y dejo abierta esta, la de subida, hasta el ciclo 8.

    Sin certificado se dice que es lo que el contrato declara, no se calla: es
    la misma regla que aplican `_revision_git` y `_indice_usado`.
    """
    m = re.search(r"^\*\*Perfil:\*\* (.+)$", certificado_md or "", re.M)
    if m:
        return m.group(1).strip()
    return (
        f"{datos_contrato['plugin']['perfil'].upper()} — _declarado en el contrato; "
        f"no hay certificado que diga con cual se verifico_"
    )


def render(
    datos_contrato: dict,
    inventario: dict | None,
    certificado_md: str,
    firma: dict,
    decisiones: str | None = None,
    revision: str | None = None,
) -> str:
    plugin = datos_contrato["plugin"]
    lineas = [
        f"# Dossier — {plugin['nombre']} {plugin['version']}",
        "",
        f"**Tipo:** {plugin['tipo']} · "
        f"**Perfil:** {perfil_publicado(datos_contrato, certificado_md)}",
        f"**SDK:** com.appian:appian-plug-in-sdk:{VERSION_SDK} · **Java:** release 17",
        f"**application-version min:** {plugin['application_version_min']}",
        # Si la lente de juicio corrio, y donde esta lo que dijo. Sin esto un
        # dossier no distingue «revisado y sin hallazgos» de «nadie lo miro»,
        # que son afirmaciones muy distintas.
        f"**Revision independiente:** {revision or ARCHIVO_REVISION + ' — _no consta_'}",
        "",
        "## 1. El contrato",
        "",
        "La entrevista congelada. Sin el no se distingue el comportamiento intencionado",
        "del accidental. Vive en `docs/contrato.md`.",
        "",
        "## 2. Decisiones y su porque",
        "",
    ]
    # Se LEE de un fichero aparte, nunca se escribe aqui. Antes esta seccion
    # era un stub en cursiva que `main_con_raiz` reimprimia en cada ejecucion
    # sobre el DOSSIER.md entero: quien la rellenaba a mano la perdia en la
    # siguiente pasada. No era una seccion que nadie poblara, era una que
    # castigaba a quien la poblaba.
    if decisiones and decisiones.strip():
        lineas.append(decisiones.strip())
    else:
        lineas.append(
            f"_pendiente: no existe `{ARCHIVO_DECISIONES}`. Estilo ADR: que API se eligio y "
            f"contra que alternativa, por que ese manejo de errores._"
        )
    lineas += [
        "",
        "## 3. Inventario de API de Appian usada",
        "",
        "Extraido del *constant pool* de las clases compiladas, en la misma pasada que",
        "alimenta la puerta de superficie: puerta y documentacion no pueden discrepar.",
        "",
        "| Tipo | Referenciado desde |",
        "|---|---|",
    ]
    if inventario is None:
        # None y {} no son lo mismo: None es "no se ha ejecutado el escaneo
        # todavia" (el proyecto no esta compilado); {} es "se ejecuto y no
        # encontro ninguna referencia a com.appiancorp.*". Confundirlos
        # convertia esta seccion en un verde vacuo -- afirmaba "extraido del
        # constant pool" de un escaneo que nunca corrio.
        lineas.append("| _pendiente: no se ha ejecutado el escaneo de superficie_ | — |")
    else:
        for tipo in sorted(inventario):
            lineas.append(f"| `{tipo}` | {', '.join(inventario[tipo])} |")
        if not inventario:
            lineas.append("| _ninguno_ | — |")

    lineas += [
        "",
        "## 4. Certificado de verificacion",
        "",
        certificado_md or "_pendiente de ejecutar la verificacion_",
        "",
        "## 5. Historial de versiones",
        "",
        f"- {plugin['version']} — version inicial.",
        "",
        "## 6. Firma publica congelada",
        "",
        "**No editar a mano.** Es el dato contra el que la Fase 2 comprueba si un cambio",
        "de inputs u outputs obliga a clave nueva. Sobrescribir la clave tras cambiarlos",
        "puede romper procesos vivos en produccion (auditoria §7.4).",
        "",
        "### Para pegar en el contrato de la version siguiente",
        "",
        "Copiar este bloque, tal cual, dentro del bloque TOML del contrato nuevo. Es lo que",
        "hace comprobable la regla de clave nueva: sin el, `R-F08` no tiene contra que",
        "comparar, y un bloque ausente se lee como «no hay cambio».",
        "",
        "```toml",
        toml_de_version_anterior(firma),
        "```",
        "",
        "### El mismo dato, en JSON",
        "",
        "```json",
        json.dumps(firma, ensure_ascii=False, indent=2),
        "```",
    ]
    return "\n".join(lineas)


def main() -> int:
    import pathlib
    import sys

    if len(sys.argv) < 2:
        print("uso: generar_dossier.py <raiz-proyecto>")
        return 2
    return main_con_raiz(pathlib.Path(sys.argv[1]))


def _leer_si_existe(ruta) -> str | None:
    """None si el fichero no esta. No se resuelve a favor: «no consta» y
    «existe y esta vacio» son afirmaciones distintas, igual que con el
    inventario de la pieza 3."""
    return ruta.read_text(encoding="utf-8") if ruta.is_file() else None


def main_con_raiz(raiz) -> int:
    import contrato
    import salida_build

    datos = contrato.cargar(raiz / "docs" / "contrato.md")

    # None (no {}) si el fichero no existe: {} significa "escaneado, cero
    # resultados", un dato que aqui no tenemos. Ver el comentario en render().
    inventario = None
    ruta_inv = raiz / "build" / "reports" / "inventario-api.json"
    if ruta_inv.is_file():
        inventario = json.loads(ruta_inv.read_text(encoding="utf-8")).get("inventario", {})

    certificado_md = ""
    ruta_cert = raiz / "docs" / "CERTIFICADO.md"
    if ruta_cert.is_file():
        certificado_md = ruta_cert.read_text(encoding="utf-8")
        # Un certificado que FALTA ya se declaraba («_pendiente de ejecutar la
        # verificacion_»); uno RANCIO pasaba en silencio, y es el caso que el
        # propio Proceso fabrica: el paso 6 manda corregir el codigo y el 7
        # empotra este fichero sin que nadie vuelva al 5. El resultado seria un
        # dossier afirmando READY_FOR_APPIAN_SUBMISSION sobre el arbol de antes
        # de la correccion. Misma MECANICA que la del log del build, sobre un
        # conjunto de insumos mas ancho: el certificado responde tambien de
        # `docs/contrato.md`, que el build no lee y tres puertas si.
        posterior = salida_build.fuente_posterior_a(raiz, ruta_cert)
        if posterior is not None:
            certificado_md = (
                f"> **AVISO: este certificado es RANCIO y no vale como verificacion.** "
                f"`docs/CERTIFICADO.md` es anterior a `{posterior.name}`, asi que describe "
                f"un arbol que ya no es el que se entrega. Volver a ejecutar "
                f"`verificar_todo.py` --el paso 5 de la SKILL-- y regenerar este dossier.\n\n"
                + certificado_md
            )

    decisiones = _leer_si_existe(raiz / ARCHIVO_DECISIONES)
    hallazgos = _leer_si_existe(raiz / ARCHIVO_REVISION)
    revision = None
    if hallazgos is not None:
        # reversed(): la ULTIMA linea VEREDICTO, no la primera. Una revision
        # con mas de una pasada -correccion + re-revision, el camino que
        # describe el paso 6 de SKILL.md- deja varias lineas VEREDICTO en el
        # fichero, y el dossier tiene que describir el estado actual, no el
        # de la primera pasada.
        veredicto = next(
            (l.strip() for l in reversed(hallazgos.splitlines()) if l.strip().startswith("VEREDICTO")),
            "sin linea VEREDICTO",
        )
        revision = f"`{ARCHIVO_REVISION}` — {veredicto}"

    destino = raiz / "docs" / "DOSSIER.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        render(datos, inventario, certificado_md, extraer_firma(datos), decisiones, revision),
        encoding="utf-8",
    )
    print(f"Dossier escrito en {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
