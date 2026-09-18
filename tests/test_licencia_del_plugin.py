"""El forge declara bajo que licencia se distribuye EL FORGE.

Aviso de la lente oficial (`plugin-validator`, ciclo 9): no habia ni `LICENSE`
en la raiz del plugin ni campo `license` en el manifiesto. La confusion facil
--y la que el aviso subraya-- es dar por cubierto el hueco con
`assets/plantillas/comun/LICENSE.tmpl`: esa plantilla es la licencia que se
copia a los proyectos GENERADOS, no la del generador. Un plugin que somete a
los plug-ins que produce a una puerta de copyleft (`verificar_licencias.py`
sobre el SBOM) y no dice bajo que se distribuye el mismo es incoherente en el
unico sitio donde la incoherencia tiene consecuencias legales.

`claude plugin validate` NO sirve de guardian aqui: pasaba igual de verde con
el manifiesto sin `license` y sin fichero `LICENSE`. De ahi este fichero.
"""

import json
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parents[1]
LICENCIA = RAIZ / "LICENSE"
MANIFIESTO = RAIZ / ".claude-plugin" / "plugin.json"

# El identificador SPDX se escribe aqui, literal, y se compara contra los dos
# lados. Derivar uno del otro dejaria pasar que ambos cambiaran a la vez, que es
# exactamente el fallo que este proyecto persigue en sus guardianes.
SPDX = "MIT"


def test_el_plugin_trae_su_fichero_de_licencia():
    assert LICENCIA.is_file(), (
        "no hay LICENSE en la raiz del plugin; `assets/plantillas/comun/"
        "LICENSE.tmpl` es la de los proyectos generados, no la del forge"
    )
    texto = LICENCIA.read_text(encoding="utf-8")
    assert texto.splitlines()[0].strip() == f"{SPDX} License"
    # Sin titular y sin ano, el texto no concede nada a nadie.
    assert "Copyright (c) 2026" in texto


def test_el_manifiesto_declara_la_misma_licencia_que_el_fichero():
    """Los dos sitios donde un tercero la busca tienen que decir lo mismo.

    El campo lo lee quien instala desde un marketplace sin abrir el arbol; el
    fichero, quien clona el checkout. Que discrepen es peor que que falte uno.
    """
    manifiesto = json.loads(MANIFIESTO.read_text(encoding="utf-8"))
    assert manifiesto.get("license") == SPDX, (
        f"el manifiesto declara {manifiesto.get('license')!r} y el fichero "
        f"LICENSE es {SPDX}"
    )
    # El titular del copyright y el autor declarado son la misma persona: si el
    # manifiesto cambia de autor, la licencia deja de cubrir a quien firma.
    autor = manifiesto["author"]["name"]
    assert autor in LICENCIA.read_text(encoding="utf-8"), (
        f"LICENSE no nombra a «{autor}», que es quien el manifiesto declara autor"
    )
