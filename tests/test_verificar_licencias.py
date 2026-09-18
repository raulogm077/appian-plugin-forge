"""La politica mas tajante de AppMarket, y la ultima que quedaba sin mecanizar.

*"Plug-ins must not include **any** third-party libraries licensed under
copyleft or similar terms"*. El orquestador lo declaraba abiertamente en la
evidencia de su puerta --«el juicio sobre copyleft NO esta mecanizado»--, que
es honesto pero cuesta el rechazo del envio, y un envio son cinco dias.
"""

import json
import sys

import pytest

import contrato
import verificar_licencias as vl


def sbom(*componentes) -> dict:
    return {"specVersion": "1.6", "components": list(componentes)}


def componente(nombre, *licencias, grupo="org.ejemplo", version="1.0"):
    entrada = {"group": grupo, "name": nombre, "version": version}
    if licencias:
        entrada["licenses"] = [{"license": {"id": l}} for l in licencias]
    return entrada


def reglas(hallazgos):
    return {h.regla for h in hallazgos}


# --- clasificacion ---------------------------------------------------------

@pytest.mark.parametrize("licencia", [
    "GPL-3.0", "GPL-3.0-only", "GPL-2.0-or-later", "AGPL-3.0", "SSPL-1.0",
    "GNU General Public License v3.0",
])
def test_el_copyleft_fuerte_se_reconoce(licencia):
    assert vl.clasificar(licencia) == "fuerte"


@pytest.mark.parametrize("licencia", [
    "LGPL-2.1", "LGPL-3.0-only", "MPL-2.0", "EPL-2.0", "CDDL-1.1", "CC-BY-SA-4.0",
    "GNU Lesser General Public License v2.1",
])
def test_el_copyleft_debil_se_reconoce(licencia):
    """`LGPL` contiene `GPL`: si el orden de comparacion fuera el contrario,
    toda LGPL se clasificaria como fuerte y el mensaje mentiria sobre cual es."""
    assert vl.clasificar(licencia) == "debil"


@pytest.mark.parametrize("licencia", [
    "Apache-2.0", "MIT", "BSD-3-Clause", "ISC", "Unlicense",
    "The Apache Software License, Version 2.0",
])
def test_las_licencias_permisivas_no_son_copyleft(licencia):
    assert vl.clasificar(licencia) is None


# --- el juicio sobre el SBOM ----------------------------------------------

def test_una_dependencia_permisiva_no_da_hallazgos():
    assert vl.comprobar(sbom(componente("gson", "Apache-2.0"))) == []


def test_una_dependencia_copyleft_es_error():
    hallazgos = vl.comprobar(sbom(componente("libreria-gpl", "GPL-3.0")))
    assert "R-L01" in reglas(hallazgos)
    assert "libreria-gpl" in hallazgos[0].mensaje


def test_una_dependencia_sin_licencia_declarada_es_error():
    """No se resuelve a favor: no se puede afirmar que cumple una politica de
    licencias sobre una licencia que no consta. Mismo criterio que el
    UNKNOWN -> FAIL del escaner de superficie."""
    assert "R-L02" in reglas(vl.comprobar(sbom(componente("misteriosa"))))


def test_una_licencia_doble_se_resuelve_por_la_mas_restrictiva():
    """`MIT OR GPL-3.0` deja la eleccion al integrador, y esa eleccion no la
    puede hacer un script: se marca para que la haga una persona."""
    hallazgos = vl.comprobar(sbom(componente("doble", "MIT", "GPL-3.0")))
    assert "R-L01" in reglas(hallazgos)


def test_la_expresion_spdx_tambien_se_mira():
    """CycloneDX admite tres formas y los `OR`/`AND` acaban en `expression`;
    mirar solo `license.id` dejaba pasar justamente las dobles."""
    comp = {"group": "g", "name": "expr", "version": "1", "licenses": [{"expression": "GPL-3.0-only"}]}
    assert "R-L01" in reglas(vl.comprobar(sbom(comp)))


def test_un_sbom_sin_componentes_no_da_hallazgos():
    """Cero dependencias de terceros es legitimo y frecuente: el SDK y log4j
    son `compileOnly`, los provee el contenedor. Es exactamente lo que produce
    el fixture del humo E2E."""
    assert vl.comprobar(sbom()) == []


# --- la CLI, que es lo que invoca el orquestador --------------------------

def test_sin_sbom_sale_en_rojo_y_lo_dice(tmp_path, capsys):
    """No poder mirar no es «ya lo miraremos»: mismo criterio que el JAR
    ausente en la capa 4."""
    sys.argv = ["verificar_licencias.py", str(tmp_path)]
    assert vl.main() == 1
    salida = capsys.readouterr().out
    assert "ERROR" in salida and "SBOM" in salida


def test_con_sbom_limpio_sale_en_cero_y_declara_su_insumo(tmp_path, capsys):
    destino = tmp_path / vl.RUTA_SBOM_POR_DEFECTO
    destino.mkdir(parents=True)
    (destino / "x-sbom.json").write_text(
        json.dumps(sbom(componente("gson", "Apache-2.0"))), encoding="utf-8")
    sys.argv = ["verificar_licencias.py", str(tmp_path)]
    assert vl.main() == 0
    salida = capsys.readouterr().out
    assert "1 sbom leido, 1 dependencias" in salida


def test_un_sbom_ilegible_sale_en_rojo(tmp_path, capsys):
    destino = tmp_path / vl.RUTA_SBOM_POR_DEFECTO
    destino.mkdir(parents=True)
    (destino / "roto-sbom.json").write_text("{ esto no es json", encoding="utf-8")
    sys.argv = ["verificar_licencias.py", str(tmp_path)]
    assert vl.main() == 1
    assert "ERROR" in capsys.readouterr().out


def test_cero_dependencias_no_es_un_verde_vacuo(tmp_path, capsys):
    """Cero dependencias de terceros es legitimo y frecuente: el SDK y log4j
    son `compileOnly`. Si el insumo declarara SOLO `dependencias=0`, la regla
    de «todas las unidades a cero» marcaria la puerta como verde vacuo y
    bloquearia el READY de casi cualquier plug-in -- la alarma que salta
    siempre. El insumo real es el SBOM leido, y eso es lo que se declara.
    """
    destino = tmp_path / vl.RUTA_SBOM_POR_DEFECTO
    destino.mkdir(parents=True)
    (destino / "vacio-sbom.json").write_text(json.dumps(sbom()), encoding="utf-8")
    sys.argv = ["verificar_licencias.py", str(tmp_path)]
    assert vl.main() == 0
    salida = capsys.readouterr().out
    assert "portante" not in salida, "cero dependencias es legitimo: no lleva portante"
    linea = next(l for l in salida.splitlines() if l.startswith(contrato.PREFIJO_INSUMO))
    assert not contrato.insumo_vacio(linea), (
        f"la puerta bloquearia el READY de todo plug-in sin terceros: {linea!r}"
    )


# --- Los dos fallos que la revision adversarial encontro en esta pieza ------
# Los escribi yo y mis propios tests no los vieron, porque probe con
# identificadores SPDX y solo dos nombres largos, ambos de la familia GPL.

@pytest.mark.parametrize("permisiva", [
    'BSD 2-Clause "Simplified" License',   # nombre canonico SPDX de BSD-2-Clause
    "Simplified BSD License",
    "Sample License",
    "Template Public License",
])
def test_una_permisiva_no_se_acusa_de_copyleft(permisiva):
    """FALSO POSITIVO: `MPL` es SUBCADENA de `SIMPLIFIED`, asi que el nombre
    canonico de una licencia permisiva se clasificaba como copyleft debil y
    BLOQUEABA el READY acusando en falso. Las siglas se casan con limite a los
    dos lados, nunca como subcadena suelta."""
    assert vl.clasificar(permisiva) is None


@pytest.mark.parametrize("larga,familia", [
    ("Eclipse Public License 2.0", "debil"),
    ("Mozilla Public License, Version 2.0", "debil"),
    ("Common Development and Distribution License", "debil"),
    ("Server Side Public License", "fuerte"),
    ("Open Software License 3.0", "fuerte"),
    ("European Union Public Licence 1.2", "fuerte"),
    ("Creative Commons Attribution Share Alike 4.0", "debil"),
])
def test_el_copyleft_con_nombre_largo_no_escapa(larga, familia):
    """FALSO NEGATIVO, y de la peor clase: `Eclipse Public License 2.0` no
    contiene `EPL` por ninguna parte. Solo la familia GPL tenia tratamiento de
    nombre largo, asi que el resto escapaba entero y la puerta imprimia
    «0 hallazgos» sin haber podido ver nada. CycloneDX emite `license.name`
    verbatim cuando el POM no mapea a SPDX, que es el camino normal de
    logback (EPL), H2 (MPL) y los artefactos javax (CDDL)."""
    assert vl.clasificar(larga) == familia


def test_el_orden_no_es_lo_que_protege_a_LGPL_de_GPL():
    """Antes dependia de comprobar debil-antes-de-fuerte. Con limites, `GPL`
    ya no casa dentro de `LGPL` ni de `AGPL`, asi que la proteccion es
    estructural y no de orden."""
    assert vl.clasificar("LGPL-3.0-only") == "debil"
    assert vl.clasificar("AGPL-3.0") == "fuerte"
    assert vl.clasificar("GPL-3.0") == "fuerte"
