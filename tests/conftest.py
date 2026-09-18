"""`scripts/` en `sys.path`, una vez, para toda la bateria.

Estaba copiado verbatim en las primeras lineas de LOS 22 ficheros de test.
Mientras vivio ahi no habia ningun sitio donde arreglarlo una sola vez, y era
el orden de recoleccion el que decidia que copia del modulo acababa importando
cada fichero. `conftest.py` se importa antes que los modulos de test, asi que
este es el sitio.

DOS COSAS QUE SE DEJAN COMO ESTAN, a proposito, para que no parezca descuido:

- El helper `reglas(hallazgos)` sigue duplicado en los cinco tests de
  validador. Son dos lineas cada uno, y la unica forma de compartirlo desde
  aqui es una fixture, que obliga a declarar `reglas` como parametro en cada
  test que lo usa: mas ediciones en los sitios donde se afirma que lineas
  ahorradas.
- Los seis diccionarios de contrato escritos a mano en los tests NO pasan por
  `contrato.validar`, asi que un campo que la puerta determinista pase a exigir
  no rompe ninguno de ellos. Unificarlos sobre `tests/fixtures/contratos/*.md`
  --que `contrato.cargar` ya lee, y que `test_contrato.py` y
  `test_forma_minima.py` si usan-- es un rediseño de la bateria, no una
  limpieza; queda anotado en vez de hecho a medias.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
