"""Los canarios no pueden entrar en la tanda 0 (spec gate-de-ciclo §7).

Un canario que engordara el recuento de `pytest` seria el verde vacuo
inverso: un rojo fabricado contando como trabajo real. Dos guardas:
ninguno se llama como un test, y la recoleccion de pytest desde la raiz
del REPO (donde tambien se ha ejecutado pytest: hay .pytest_cache) no
tiene nada RECOLECTABLE bajo canarios/ (pytest SÍ recorre ese arbol de directorios).

Este modulo mira ESTRUCTURA DEL REPO DE DESARROLLO (docs/validaciones/),
que no viaja con el plugin. Fuera del repo —un forge instalado o copiado—
se salta entero, como hace test_extremo_a_extremo.py con su dependencia
externa: un skipped honesto, no un rojo falso. Dentro del repo, donde el
gate corre siempre, los asserts son duros. NO «simplificar» quitando el
skipif: convertiria la suite del entregable en dependiente del repo.

El assert del test 3 comprueba la RUTA docs/validaciones/canarios, no la palabra:
el nombre de este propio fichero la contiene y un assert por palabra se falla a si mismo.

Rama de fallo demostrada el 2026-08-09: fichero test real plantado puso en rojo los tests 2 y 3, y se retiro.
"""

import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
CANARIOS = REPO / "docs" / "validaciones" / "canarios"

pytestmark = pytest.mark.skipif(
    not (REPO / "docs" / "superpowers").is_dir(),
    reason="suite ejecutada fuera del repo de desarrollo del forge",
)


def test_los_canarios_existen_antes_de_afirmar_nada_sobre_ellos():
    # Guarda anti verde vacuo del propio test: si los canarios no estan,
    # los otros dos tests pasarian sobre un directorio vacio.
    assert CANARIOS.is_dir(), f"no existe {CANARIOS}"
    assert sorted(d.name for d in CANARIOS.iterdir() if d.is_dir()) == [
        "auditor", "certificador", "revisor",
    ]


def test_ningun_canario_se_llama_como_un_test():
    assert list(CANARIOS.rglob("test_*.py")) == []
    assert list(CANARIOS.rglob("*_test.py")) == []


def test_la_recoleccion_desde_la_raiz_del_repo_no_entra_en_canarios():
    res = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=REPO, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120,
    )
    # Guarda de sanidad: si la recoleccion misma revienta, stdout llega vacio y el assert de abajo pasaria vacuamente -- el verde vacuo inverso del propio guardian.
    assert res.returncode == 0, (
        f"la recoleccion de pytest desde la raiz del repo fallo (returncode {res.returncode}); "
        f"stdout:\n{res.stdout[-2000:]}\nstderr:\n{res.stderr[-2000:]}"
    )
    lineas_canario = [
        l for l in res.stdout.splitlines()
        if "docs/validaciones/canarios" in l or "docs\\validaciones\\canarios" in l
    ]
    assert lineas_canario == [], (
        "pytest desde la raiz del repo recolecta dentro de docs/validaciones/canarios/:\n"
        + "\n".join(lineas_canario)
    )
