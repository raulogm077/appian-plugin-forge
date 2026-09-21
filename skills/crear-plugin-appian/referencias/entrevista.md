# Formato de la entrevista

Cómo se conduce la entrevista del paso 1 de `SKILL.md`: el formato de cada turno, la doble
puerta de parada, el reparto entre lo que se pregunta y lo que se decide, y las siete preguntas
de admisión.

## Una pregunta por turno, sin opción múltiple

Quien pide un plugin normalmente no sabe aún lo que quiere, y ofrecerle opciones le hace
elegir en vez de pensar: ensancha la búsqueda en lugar de estrecharla.

Cada turno enseña la hipótesis del modelo, para que se pueda corregir de un plumazo en vez de
contestar desde cero:

```
Q: <una pregunta enfocada>
GUESS: <hipótesis de la respuesta, con el razonamiento que la produjo>
CONFIDENCE: ~30%
```

El tipo de plugin no se pregunta así — se deduce; ver
`${CLAUDE_PLUGIN_ROOT}/skills/crear-plugin-appian/referencias/tipos-de-plugin.md`.

## Condición de parada: doble puerta

Son dos cosas distintas y ninguna basta sola.

- **Puerta determinista** — que no falte ningún campo obligatorio del tipo. Que falte el
  `Required` de un input de Smart Service no es opinable: sin ese dato no compila. Lo
  comprueba un script:
  `python "${CLAUDE_PLUGIN_ROOT}/scripts/contrato.py" docs/contrato.md`.
  En PowerShell, si el marcador de la raíz del plugin llega literal, se escribe la ruta absoluta
  del plugin: `${…}` es sintaxis de variable de sesión y se expande a cadena vacía sin avisar, y
  `$env:CLAUDE_PLUGIN_ROOT` no existe; el porqué, en
  `${CLAUDE_PLUGIN_ROOT}/skills/crear-plugin-appian/referencias/entorno-windows.md`.
- **Puerta de confianza** — *«¿puedo predecir tu reacción a las tres siguientes preguntas
  que haría?»*. Si no, seguir. Con **suelo antibucle**: si tras varias rondas la confianza
  no sube, parar y preguntar qué falta en vez de seguir indagando indefinidamente.

**Se exige un «sí» explícito antes de generar nada.** Ni la puerta determinista sola —el
contrato puede estar completo en sus campos y aun así no reflejar lo que el usuario quiere—
ni la puerta de confianza sola —la intención puede estar clara mientras falta un campo sin el
que el andamiaje no puede generarse— bastan por separado.

## Qué se decide y qué se pregunta

El esquema completo vive en `${CLAUDE_PLUGIN_ROOT}/scripts/contrato.py` y no se duplica aquí.
Lo que sí hace falta aquí es **el reparto**, porque sin él el gradiente natural ante una puerta
en rojo es preguntar, y un contrato mínimo real tiene **entre 17 y 23 asignaciones** —según el
tipo: 17 el servlet, 18 la writer-function, 21 la function, 23 el smart service— frente a las
siete preguntas de más abajo. Convertir esas veintitantas asignaciones en otros tantos turnos
sería lo contrario de lo que este sistema busca.

La regla es una sola: **se pregunta lo que el usuario sabe y no se puede deducir; se decide y
se enseña todo lo demás.**

| Campo | Quién lo pone | Cómo |
|---|---|---|
| `plugin.tipo` | **Deducido** | De lo que el usuario describe (`tipos-de-plugin.md`). Se propone con su porqué, nunca se pregunta |
| `plugin.perfil` | **Deducido** | De las cuatro preguntas marcadas abajo. Se propone; lo confirma el usuario |
| `plugin.nombre` | **Decidido** | Del propósito que el usuario ya describió |
| `plugin.key`, `plugin.paquete` | **Decidido** | Convención `com.<organización>.appian.<algo>`. Se enseñan una vez, juntos, para confirmar de un vistazo |
| `plugin.version` | **Decidido** | `1.0.0` si se estrena. Solo se pregunta si hay versión anterior (séptima pregunta) |
| `plugin.application_version_min` | **Decidido** | La mínima que soporte lo que el plug-in usa. Si el contrato pide `useKeywords`, mínimo `26.1` (`R-F05`) |
| `clase.nombre` | **Decidido** | Del nombre del plug-in, en PascalCase |
| `clase.paleta` | **Decidido** | De lo que hace el paso. Es la **subpaleta** — ver la lista debajo de esta tabla |
| `bundle.nombre` | **Decidido** | Igual que la clave del módulo — ver abajo, es el único que además **bloquea la puerta** |
| `entradas`/`salidas`: **nombre y para qué** | **PREGUNTADO** | Es el contrato funcional: nadie más lo sabe |
| `entradas`/`salidas`: `tipo_java` | **Decidido** | Del sentido del dato. Ojo con los no inferibles (`R-F04`) y con `Timestamp`/`Time` |
| `entradas[].required` | **Decidido, confirmado** | Se propone `ALWAYS` salvo que el usuario haya dicho que el dato puede faltar. Un primitivo no admite `OPTIONAL` (`R-F02`) |
| `descripcion` de cada uno | **Decidido** | Se redacta y se enseña: acaba en el `.properties` que ve el diseñador |
| `servlet.url_pattern`, `servlet.parametro` | **Decidido** | **Solo en `tipo = servlet`**, y los nombres son exactamente esos —`url_pattern` con guion bajo—. `url_pattern` es la ruta que declara el manifiesto (`/lo-que-sea`); `parametro`, el nombre del parámetro de petición que lee el andamiaje |
| `dependencias` | **Decidido, confirmado** | Solo si la respuesta a «¿usa librerías de terceros?» es sí: una lista de coordenadas Maven, `dependencias = ["grupo:artefacto:versión"]`, con la versión concreta comprobada en Maven Central. **Es clave de raíz del TOML y va en la primera línea del bloque, antes de `[plugin]`**: escrita después de cualquier tabla, TOML la cuelga de esa tabla y el andamiador no la ve —la puerta determinista lo rechaza con una `FALTA` que dice la posición—. De ahí salen el `implementation` de `build.gradle`, la línea de `THIRD_PARTY_NOTICES.md` y, vía el SBOM, la capa de licencias. El ejemplo canónico es `tests/fixtures/contratos/function-con-dependencia.md` |
| Las seis de admisión y la séptima | **PREGUNTADO** | Son la tabla de abajo |

### Las subpaletas que existen (`clase.paleta`)

La lista cerrada vive en `contrato.ANOTACION_POR_PALETA` y sale de `javap` sobre el JAR del
SDK 26.3, no de ningún resumen. **La puerta determinista rechaza cualquier otra**, y el mensaje
de rechazo dice en cuál de los dos niveles está el error.

| Categoría (`paletteCategory`) | Subpaletas — esto es lo que va en el contrato |
|---|---|
| Automation Smart Services | `Analytics`, `Business Rules`, `Communication`, `Data Services`, `Document Generation`, `Document Management`, `Identity Management`, `Integration & APIs`, `Process Management`, `Robotic Processes`, `Social`, `Test Management` |
| Workflow | `Activities`, `Events`, `Gateways`, `Human Tasks` |
| Deprecated Services | `Forum Management` — válida, pero **no se propone** en un plug-in nuevo |

**Los dos niveles no son lo mismo, y confundirlos escribe en el contrato un valor que la puerta
rechaza.** `R-F01` rige sobre
la **categoría**, que el contrato no escribe: la hornea la anotación de conveniencia que emite la
plantilla. Lo que se escribe en `clase.paleta` es la **subpaleta**. `Workflow` es una categoría,
así que no vale como valor; si el paso es una actividad de flujo, la subpaleta se llama
`Activities`.

**Enseñar no es preguntar.** Los campos decididos se muestran en bloque —«esto es lo que voy a
generar»— y se corrigen de un plumazo, que es justo lo que el formato `GUESS`/`CONFIDENCE`
persigue. Lo que no se hace es convertir cada identificador en un turno.

**Y un campo decidido mal puesto ya no llega lejos:** la puerta determinista comprueba que
`paquete`, `key`, `clase.nombre` y `bundle.nombre` sean identificadores Java válidos, así que
un espacio o una palabra reservada se rechazan en el acto y no dentro de `./gradlew build`.

El que más cara cuesta olvidar, porque no es una decisión de diseño sino un identificador:

**`[bundle] nombre`** — la clave del módulo. Alimenta **dos cosas que tienen que coincidir**: el
atributo `key` del módulo en el manifiesto (`<function>`, `<smart-service>`) y el nombre base del
`.properties`. Y tienen que coincidir porque **Appian resuelve el bundle de cada módulo como
`<key del plug-in>.<key del módulo>`**; si no lo encuentra, el plug-in no despliega y el servidor
nombra al módulo culpable:

```
The Plug-in <key> Module <key del módulo> is missing the following internationalization
bundle(s) for Locale en_US: [<key>.<key del módulo>] (APNX-1-4200-000)
```

El plug-in publicado en el AppMarket declara `key="readEmailFile"` y su bundle es
`readEmailFile_en_US.properties`: mismo nombre, y por eso es un solo campo. Se pide a los tres
tipos que cargan bundle —`function`, `writer-function`, `smart-service`—; el `servlet` no lo
lleva, su clave de módulo sale del nombre del artefacto.

**La `key` de `<function>` nombra el MÓDULO, no la función.** La función se invoca en SAIL por el
nombre de su método Java en minúsculas, que es también el que llevan las claves
`function.<nombre>.description` dentro del bundle. Por eso el ejemplo oficial de la documentación
tiene un solo bundle, `twitterFunctions_en_US.properties`, con las claves de **dos** funciones:
`function.twittertrends.description` y `function.twittersearch.description`. Un módulo, dos
funciones, un bundle que se llama como el módulo.

De ahí la consecuencia que importa al escribir un manifiesto a mano: **un módulo `<function>` de
más es un bundle de más**. Cinco funciones declaradas como cinco `<function key="…">` necesitan
cinco `.properties` por locale, uno por key, aunque las claves de dentro sigan el nombre del
método. `R-B07` lo comprueba leyendo el manifiesto —no el contrato, que solo describe un módulo—
y `R-J06` repite la comprobación sobre el JAR ya construido.

Por qué `[bundle] nombre` bloquea la puerta: sin él saldría `key=""` y un fichero llamado
`_en_US.properties`, y `R-B01` no lo vería, porque deriva la ruta esperada del **mismo dato** que
produce el artefacto, así que los dos lados coincidirían en la nada. `R-B07` sí lo ve: su lista de
módulos sale del manifiesto.

### Qué llevan de más los contratos canónicos

Los fixtures `-minimo` de `${CLAUDE_PLUGIN_ROOT}/tests/fixtures/contratos/` son la **forma
mínima real** que la puerta acepta, no el camino feliz, y conviene saber qué traen **sin que la
puerta lo exija**, para no confundirlo con lo obligatorio:

- `plugin.descripcion`, en los cuatro. Sano tener, y es prosa que se decide y se enseña.
- `salidas`, en el smart-service. Ahí son campos con accesor, así que un contrato sin ellas es
  legítimo — a diferencia de una `function`, donde de la salida sale el tipo de retorno.

## Las preguntas que deciden admisión y perfil

Preguntas baratas en la entrevista y carísimas de descubrir tarde. Son **siete**: seis viven
en la tabla de abajo, y una séptima va aparte porque no decide admisión — decide otra cosa
igual de cara. Cuatro de las seis deciden además el **perfil de rigor** —van marcadas—, así
que el perfil no se pregunta por separado: se deduce y se propone.

| Pregunta | Si la respuesta es sí | Perfil |
|---|---|---|
| ¿Parsea formatos que no controlamos? | el espacio de entradas es ajeno | **RIGUROSO** |
| ¿Sale a la red? | timeouts, topes y política de reintentos | **RIGUROSO** |
| ¿Toca credenciales? | Secure Credentials Store, obligatorio | **RIGUROSO** |
| ¿Maneja datos personales? | nada de datos en **logs**; correlación por identificador | **RIGUROSO** |
| ¿Usa librerías de terceros? | mirar licencia; copyleft es rechazo automático | — |
| ¿Toca ficheros? | `ContentService`; prohibido el sistema de ficheros | — |

⚠️ **«Nada de datos en logs» no es «nada de datos personales».** Si el contrato del plug-in *es*
escribir quién hizo qué —una traza de auditoría, por ejemplo—, ese dato va a su destino declarado y
eso no incumple nada: lo que la fila prohíbe es que además acabe en el **log de la plataforma**, que
es un sitio que el contrato no nombra y que ve mucha más gente. La regla es sobre el canal, no sobre
el dato.

**Las cuatro marcadas se escriben en el contrato**, y no como prosa: son el bloque
`[capacidades]`, con una clave booleana por cada pregunta marcada, aquí en el orden de la
tabla: `parsea_formatos_ajenos`, `sale_a_la_red`, `toca_credenciales` y `datos_personales`. Las
**cuatro van siempre, aunque valgan `false`**: la puerta determinista las exige presentes, y de
sus valores salen las dos cosas que dependen de esta tabla — el perfil propuesto
(`contrato.perfil_propuesto`) y el AVISO de escalada que se imprime cuando el contrato declara
ESTÁNDAR y alguna capacidad pide RIGUROSO. Un bloque incompleto no se lee como «todo `false`»:
no pasa la puerta.

**Por qué «toca ficheros» no dispara el perfil por sí solo.** Mover o crear un documento no
expone la lógica a nada que no controlemos; interpretar su contenido, sí — y eso ya lo recoge
la primera pregunta. Mantenerlas separadas evita que casi cualquier plug-in acabe siendo
RIGUROSO por tecnicismo, que es como un perfil deja de significar nada.

**La séptima, que no decide admisión pero evita el peor accidente posible:**

**¿Es una versión nueva de un plug-in que ya está desplegado?** Si lo es, y cambian inputs u
outputs, hace falta **clave nueva**, clase o paquete distintos, y deprecar el anterior:
sobrescribir la clave puede **romper procesos vivos en producción**. Lo dice la documentación
de Appian (*Smart Service Plug-ins › Best practices › Upgrading*): «You must use a new key. If
you overwrite the plug-in, existing nodes may fail». Es la
única regla del proyecto cuya consecuencia cae sobre producción y no sobre el despliegue, y
solo es comprobable porque el dossier de una versión anterior guarda la firma pública
congelada contra la que comparar.

**Si la respuesta es sí, la entrevista no ha terminado hasta que el contrato lleve el bloque.**
`R-F08` compara contra `[version_anterior]`, y **un bloque ausente se lee como «no hay
cambio»**: la regla no salta, y **lo hace en silencio** — ni error, ni aviso, ni una línea
informativa. Por eso esta pregunta es la única guarda que hay, y está en la regla cuya
factura la paga producción. El bloque no se escribe a mano — el
`DOSSIER.md` de la versión anterior lo trae ya formateado para pegar, en su sección 6:

```
[version_anterior]
key = "com.raul.appian.ejemplo"
version = "1.0.0"

[version_anterior.firma]
clase = "EjemploSmartService"
entradas = ["documentoOrigen:Long"]
salidas = ["documentoResultado:Long"]
```

La `key` va **hermana** de `firma`, no dentro: es lo que `R-F08` compara con `plugin.key`. La
puerta determinista rechaza un `[version_anterior]` a medias, porque es peor que ninguno —
parece que hay línea base y no la hay.

## El bloque `[confirmacion]`

La puerta de confianza de arriba —el «sí» explícito— tiene un mecanismo, no solo una
convención: `contrato.validar()` exige

```toml
[confirmacion]
usuario_confirmo = true
```

**Se escribe SOLO después de que el usuario haya dicho que sí a la puerta de confianza — nunca
antes, y nunca como parte de la hipótesis `GUESS`.** Es el último campo que se añade al contrato,
después de todos los demás.

**Si el contrato se edita después de escribir este bloque** —una corrección, un campo que
cambia—, hay que volver a pedir confirmación y reescribirlo. El campo es un booleano simple, no un
hash del contenido: no detecta por sí solo que el contrato cambió bajo él, así que la garantía
depende de seguir esta regla, no solo de que el campo exista.
