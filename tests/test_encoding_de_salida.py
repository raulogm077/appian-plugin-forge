"""Nada que pueda imprimirse sale del repertorio cp1252.

Por que importa, y no es teorico: `print()` solo SUSTITUYE el glifo cuando
stdout es una consola de verdad. Por TUBERIA lanza `UnicodeEncodeError`, y el
orquestador invoca a todos los validadores con `capture_output=True`, que es
una tuberia. La ruta que importa es siempre la peligrosa.

Este lint se escribio despues de caer en la trampa: el aviso de «insumo vacio»
se marco con `⚠` (U+26A0), que no esta en cp1252 y **solo se imprime cuando
una puerta verde tiene el insumo vacio** — habria reventado el certificado
justo en el caso que el aviso existe para hacer visible, y en ningun otro.

Los guillemets `« »` y los acentos si estan en cp1252 y no rompen nada.
"""

import pathlib

import pytest

SCRIPTS = sorted((pathlib.Path(__file__).resolve().parents[1] / "scripts").glob("*.py"))


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_ningun_caracter_fuera_de_cp1252(script):
    texto = script.read_text(encoding="utf-8")
    intrusos = sorted({c for c in texto if not _cabe_en_cp1252(c)})
    assert not intrusos, (
        f"{script.name} contiene caracteres que `print()` no puede emitir por tuberia: "
        f"{[(c, hex(ord(c))) for c in intrusos]}"
    )


def _cabe_en_cp1252(caracter: str) -> bool:
    try:
        caracter.encode("cp1252")
    except UnicodeEncodeError:
        return False
    return True
