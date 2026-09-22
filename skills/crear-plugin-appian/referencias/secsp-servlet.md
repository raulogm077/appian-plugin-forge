# La excepción `SECSP` en un servlet recién andamiado

El único fallo de build que un servlet recién andamiado tiene abierto a propósito, y los dos
patrones de FindSecBugs y SpotBugs que llegan después al implementarlo; se abre desde el paso 4
de `SKILL.md`.

**La única excepción admitida al `BUILD SUCCESSFUL`, y no es una avería.** Un servlet recién
andamiado **no pasa `./gradlew build`**. FindSecBugs dispara `SERVLET_PARAMETER` (`SECSP`) sobre
`request.getParameter(...)` —todo parámetro de petición es dato controlado por el cliente— y el
andamiaje deja esa exclusión **abierta a propósito**: la plantilla recibe el valor y lo entrega
tal cual, así que no puede afirmar que se trate con seguridad: eso solo lo sabe quien escriba
`ejecutar()`, y afirmarlo en su lugar sería exactamente lo que este sistema existe para impedir.

Qué hacer con él: **implementar la lógica del servlet y decidir entonces, con conocimiento**, si
la exclusión procede —comprobando que el valor no llega a una consulta, a una ruta de fichero ni a
un comando sin validar— y dejar escrito por qué es seguro. El bloque ya viene redactado y
comentado, con el argumento completo, en el `config/spotbugs/exclude.xml` del proyecto generado:
se lee allí, no se copia aquí. Lo que **no** se hace es excluir el detector para que el build pase,
ni relajar `reportLevel` ni `ignoreFailures` en `build.gradle`; y hasta que la decisión se tome, la
puerta de SpotBugs del certificado sale en rojo, que es la verdad.

`R-F14` lo comprueba: si la exclusión está **activa** y `docs/decisiones.md`
no la menciona, la capa 1 sale en rojo. Activarla sigue siendo legítimo —es la decisión que este
fichero describe—; lo que ya no se puede es tomarla en silencio.

## El segundo, que aparece después: `SECXSS2`

No lo dispara el andamiaje sino la implementación, así que llega cuando el `SECSP` ya se resolvió
y sorprende. En cuanto `doGet()` escribe en el `PrintWriter` algo construido a partir del
parámetro, FindSecBugs sigue el rastro hasta la petición y marca
*«could be vulnerable to XSS in the Servlet»* — **también cuando lo que se escribe no puede llevar
carga**, como un `boolean` interpolado en un JSON. El rastreo no distingue el tipo.

Se cierra igual que el otro: **sin excluir nada**. Si el valor es de un conjunto cerrado, se
escriben los literales completos y se elige entre ellos —`valido ? "{\"valid\":true}" :
"{\"valid\":false}"`— en vez de concatenar; el detector deja de tener rastro que seguir. Si de
verdad hay que devolver texto del cliente, se escapa antes, y eso sí es una exclusión que
justificar en `docs/decisiones.md`, con R-F14 mirando.

**Hay un tercer camino, y es el que sirve cuando el cuerpo no es ninguno de los dos casos**
—un JSON con varios campos derivados del parámetro, por ejemplo—: **construirlo con
`StringBuilder.append()` en pasos separados** en vez de con `+`, mismo contenido y mismo
escapado. Eso rompe el rastro; lo que **no** basta es extraer el cálculo a otro método y devolver
un objeto, porque FindSecBugs propaga la marca **al objeto entero** que devuelve un método con un
parámetro tintado, no solo al campo que de verdad deriva de él.

**Y un tercer patrón que no es de seguridad pero llega por el mismo sitio:**
`SE_TRANSIENT_FIELD_NOT_RESTORED`, si el servlet guarda una colaboradora en un campo de instancia.
`HttpServlet` es `Serializable`, así que un campo `transient` no se restauraría. Si la
colaboradora **no tiene estado** —el caso normal en un adaptador—, la salida es un `static final`:
se comparte sin riesgo y deja de entrar en la (de)serialización. Tampoco se excluye.

## El cuarto, que no se cierra como los otros tres: `CRLF_INJECTION_LOGS`

Llega en cuanto el servlet registra algo en el log construyendo el mensaje con datos propios.
**Los tres caminos de `SECXSS2` no sirven aquí** —el `StringBuilder.append()` en pasos no lo
quita— y saberlo ahorra un rato de intentos: lo que rompe el rastro de un detector no lo rompe
en el otro.

Es la **única de estas cuatro que suele acabar en exclusión legítima**, y ya hay un precedente
escrito: el andamiaje de smart service la excluye de serie y deja firmada su decisión en
`docs/decisiones.md`, con el argumento completo y con la condición bajo la que deja de valer.
Ese argumento es el que hay que poder repetir: que el único dato dinámico del mensaje **no puede
llevar CR ni LF** —un UUID, un identificador numérico, un valor de un conjunto cerrado— y que el
detalle del error viaja por el `Throwable`, nunca por la cadena. **Deja de valer en cuanto se
concatena un dato de entrada**: entonces se retira la exclusión o se sanea el valor. Si no puedes
firmar ese argumento, la salida es no meter el dato en el mensaje.

## Los nombres cortos del build no son los que se escriben en `exclude.xml`

La salida de SpotBugs enseña el **identificador corto** del detector; `<Bug pattern="…">` espera
el **nombre del patrón**, que es otro texto. Escribir el corto produce un fichero que parece
correcto, que SpotBugs carga sin protestar —no dice «Unable to read filter», como sí hace con un
BOM— y que **no excluye nada**:

| Lo que muestra el build | Lo que hay que escribir en `<Bug pattern="…">` |
|---|---|
| `SECSP` | `SERVLET_PARAMETER` |
| `SECCRLFLOG` | `CRLF_INJECTION_LOGS` |

Sobre un servlet con los dos patrones, con los nombres de la columna derecha `:spotbugsMain`
termina en `BUILD SUCCESSFUL`; sustituyendo cualquiera de los dos por su identificador corto,
`BUILD FAILED`, sin una sola línea que explique por qué.

No hay riesgo de que eso produzca un certificado verde —si la exclusión no se aplica, el hallazgo
sigue vivo, `:spotbugsMain` falla y la puerta sale en rojo—, pero cuesta un rato largo entender
qué pasa, porque el síntoma es idéntico al de una exclusión que no debería haberse intentado.

Y el nombre que `R-F14` busca en `docs/decisiones.md` es **el que está escrito en el XML**: una
decisión que nombre el identificador corto no la reconoce.

`SECXSS2` no aparece en la tabla a propósito: **no se excluye**, se arregla en el código.

## El andamiaje genera `doGet`, y solo `doGet`

Si el servlet tiene que atender `POST`, `PUT` o `DELETE`, esos métodos se escriben a mano — el
andamiaje no deja esqueleto. Y **leer un cuerpo de petición no trae nada hecho**: `build.gradle`
no declara ninguna librería JSON, así que o se añade una como dependencia del contrato —con su
licencia, su entrada en `THIRD_PARTY_NOTICES.md` y el `R-J04` de por medio— o se analiza el cuerpo
a mano, acotando **tamaño y profundidad** antes de recorrerlo. Lo que no se hace es leerlo entero
sin límite: es una entrada controlada por el cliente.
