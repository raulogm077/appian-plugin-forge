"""Descarga y congela el indice de tipos documentados del javadoc de Appian.

Pineado a la version del SDK (26.3), NO a latest (spec D17): entre 26.3 y 26.7
hay 7 tipos que dejan de figurar, y validar contra latest rechazaria API
legitima. No choca con la regla global de no pinear versiones: esa regla es
para *enlazar documentacion*; esto es un contrato de compilacion y sigue al
artefacto.

Se congela como snapshot con hash y fecha para que la puerta sea reproducible
y no dependa de la red ni de que Appian reorganice su web.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import pathlib
import re
import urllib.request

URL_BASE = "https://docs.appian.com/suite/help/{version}/api/"
FICHERO_TIPOS = "type-search-index.js"
FICHERO_PAQUETES = "package-search-index.js"

PATRON_COORDENADA = re.compile(r"^[\w.\-]+:[\w.\-]+:([\w.\-]+)$")


def version_desde_coordenada(coordenada: str) -> str:
    coincidencia = PATRON_COORDENADA.match(coordenada.strip())
    if not coincidencia:
        raise ValueError(f"«{coordenada}» no es una coordenada Maven grupo:artefacto:version")
    return coincidencia.group(1)


def parsear_indice_js(texto: str) -> list[dict]:
    """Extrae el array JSON del fichero del buscador.

    El fichero es `nombreVariable = [ ... ];` mas cola, asi que json.loads
    directo falla: se usa raw_decode desde el primer corchete.
    """
    inicio = texto.find("[")
    if inicio == -1:
        raise ValueError("el fichero del buscador no contiene ningun array JSON")
    array, _fin = json.JSONDecoder().raw_decode(texto[inicio:])
    return array


def construir(version: str, texto_tipos: str, texto_paquetes: str) -> dict:
    tipos: list[str] = []
    for entrada in parsear_indice_js(texto_tipos):
        paquete = entrada.get("p")
        nombre = entrada.get("l", "")
        # Las entradas sin «p» son sinteticas del buscador («All Classes…»).
        if paquete and nombre:
            tipos.append(f"{paquete}.{nombre}")

    paquetes: list[str] = []
    for entrada in parsear_indice_js(texto_paquetes):
        nombre = entrada.get("l", "")
        # La entrada sintetica «All Packages» trae «u» y un nombre con espacios.
        if nombre and " " not in nombre:
            paquetes.append(nombre)

    tipos.sort()
    paquetes.sort()
    huella = hashlib.sha256(
        json.dumps({"tipos": tipos, "paquetes": paquetes}, ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    return {
        "version": version,
        "fecha": datetime.date.today().isoformat(),
        "hash_sha256": huella,
        "tipos": tipos,
        "paquetes": paquetes,
    }


def descargar(version: str) -> tuple[str, str]:
    base = URL_BASE.format(version=version)
    with urllib.request.urlopen(base + FICHERO_TIPOS, timeout=30) as r:
        tipos = r.read().decode("utf-8")
    with urllib.request.urlopen(base + FICHERO_PAQUETES, timeout=30) as r:
        paquetes = r.read().decode("utf-8")
    return tipos, paquetes


def main() -> int:
    import sys

    coordenada = sys.argv[1] if len(sys.argv) > 1 else "com.appian:appian-plug-in-sdk:26.3"
    version = version_desde_coordenada(coordenada)
    texto_tipos, texto_paquetes = descargar(version)
    snapshot = construir(version, texto_tipos, texto_paquetes)
    destino = pathlib.Path(__file__).resolve().parents[1] / "assets" / f"indice-tipos-{version}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Escrito {destino}: {len(snapshot['tipos'])} tipos en {len(snapshot['paquetes'])} paquetes, "
        f"hash {snapshot['hash_sha256'][:12]}…"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
