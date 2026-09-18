# Deducción del tipo de plugin

Fuente: spec `docs/superpowers/specs/2026-08-08-appian-plugin-forge-design.md` §6.1 y §2.2
(repo de desarrollo; no viaja con el plugin).

## No se pregunta qué tipo de plugin se quiere

Preguntarlo asume que el usuario ya lo sabe, y la elección de tipo es justo donde más se
falla. Quien pide un plugin normalmente sabe describir **lo que quiere que pase**, no en qué
categoría de la API de Appian encaja eso. Se deduce del uso que describe y se propone **con
su porqué**, como cualquier otra hipótesis de la entrevista
(`${CLAUDE_PLUGIN_ROOT}/skills/crear-plugin-appian/referencias/entrevista.md`).

## Tabla de deducción (spec §6.1)

| El usuario describe… | Tipo |
|---|---|
| calcular o transformar algo dentro de una expresión o interfaz | **Function** |
| **guardar datos desde una pantalla** | **Function *writer*** — no Smart Service |
| un paso de un modelo de proceso | **Smart Service** |
| **exponer un endpoint HTTP dentro de Appian para que lo llame un sistema externo** | **Servlet** |

Si lo que describe no encaja en ninguna fila —una pieza HTML/CSS/JS con React, o un
Connected System— está fuera de la Fase 1: ver `## When to Use` en `SKILL.md`.

## La fila que evita el error caro

**«Quiero que al pulsar un botón se guarde algo en el sistema X» suena a Smart Service, y no
lo es.** Es una **Function *writer***, y la razón es una regla dura de la plataforma: **los
smart services de plug-in no se pueden usar en expresiones** (spec §2.2). Un smart service
solo se invoca desde un nodo de un modelo de proceso; si lo que hace falta es escribir datos
**desde una interfaz**, la única vía sancionada es una función que:

- se declara igual que cualquier otra función, con `<function>` en el manifiesto — **en el
  manifiesto** no es un tipo de plug-in aparte, es un patrón distinto dentro de Function;
- devuelve un objeto que implementa la interfaz `Writer` (método único `execute()`);
- se enlaza con `bind()` en el `saveInto` de un componente de la interfaz.

## Pero en el CONTRATO sí es un tipo propio

Lo de arriba es cierto del manifiesto y **falso del contrato**, que es lo que escribe quien
conduce la entrevista. En `docs/contrato.md` la *function writer* se declara con un valor
suyo:

```toml
[plugin]
tipo = "writer-function"
```

`writer-function` es uno de los **cuatro** valores que admite la puerta determinista
(`contrato.TIPOS_VALIDOS`), y los cuatro son los de la tabla de deducción de arriba:

| Valor de `tipo` | Fila de la tabla |
|---|---|
| `function` | calcular o transformar dentro de una expresión |
| `writer-function` | **guardar datos desde una pantalla** |
| `smart-service` | un paso de un modelo de proceso |
| `servlet` | un endpoint HTTP dentro de Appian |

Escribir `tipo = "function"` para una writer **no es un matiz de estilo**: `scripts/andamiar.py`
elige la plantilla de clase **por ese valor**, y solo `writer-function` trae la que hornea
`public Writer` como tipo de retorno. Con `function` se genera la clase equivocada.

**Y una writer-function no declara `[[salidas]]`.** Su método devuelve siempre un `Writer`, no
un valor descrito en el contrato, así que la puerta **rechaza** un contrato de tipo
`writer-function` que traiga salidas. El error simétrico —`tipo = "function"` con una salida
declarada, para lo que en realidad es una writer— **la puerta lo deja pasar**: es un contrato
de function perfectamente válido. Compila, aprueba sus tests, y solo falla cuando se intenta
enlazar con `bind()` en un `saveInto` y resulta que no devuelve ningún `Writer`. Es la misma
factura que describe la sección siguiente, cobrada por la vía del contrato en vez de por la
del tipo.

## El servlet declara `[[entradas]]` y su andamiaje NO las lee

La puerta exige `[[entradas]]` a los **cuatro** tipos (`contrato.py`, «entradas: el contrato no
declara ninguna»), pero el servlet generado no las cablea: lee **un solo** parámetro HTTP, y su
nombre sale de la sección opcional `[servlet]` (`parametro`, por defecto el literal `valor`), no
de las entradas declaradas. Un contrato que declare `identificador` produce un servlet que lee
`request.getParameter("valor")`.

**Es deliberado, no un olvido.** En un servlet las entradas del contrato documentan qué recibe
el endpoint —y de ahí salen la revisión y los tests—, mientras que la forma de recibirlas (query
string, cuerpo JSON, cabecera) es una decisión de diseño del endpoint que el andamiaje no puede
adivinar sin equivocarse. Derivar el parámetro de la primera entrada llegó a hacerse y **se
retiró**: acertaba solo cuando había exactamente una entrada y era una query string.

Consecuencia práctica, para que no sorprenda: el andamiaje del servlet es **el más incompleto de
los cuatro** a propósito. `ejecutar()` lanza `UnsupportedOperationException` como los demás, pero
además hay que escribir la lectura de cada entrada declarada. Es la asimetría frente al smart
service, cuyo andamiaje sí lee cada entrada y escribe cada salida.

## Por qué esto no lo atrapa ninguna capa de verificación

Deducir mal esta fila —generar un Smart Service cuando hacía falta una Function *writer*— no
lo detecta ni la compilación, ni el escáner de superficie, ni los tests unitarios, ni el
empaquetado: el smart service generado **compila y pasa sus propios tests** perfectamente
bien. El error solo aparece al integrarlo, cuando resulta que no hay forma de invocarlo desde
la interfaz que lo necesitaba — y para entonces ya se gastó un ciclo de construcción, o peor,
un ciclo de aprobación de Appian. Es el ejemplo concreto de por qué la entrevista es el único
sitio donde se comprueba que el plugin hace lo correcto (spec §9.1): no hay una segunda
oportunidad de detectarlo más adelante.
