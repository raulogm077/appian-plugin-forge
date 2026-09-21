---
name: crear-plugin-appian
description: Genera un plugin de Appian de tipo Function —de lectura o writer—, Smart Service o Servlet a partir de una entrevista al usuario, y lo verifica en cuatro capas hasta el limite de lo posible en local. Use when el usuario pide crear, generar o construir un plugin de Appian, una funcion de expresion personalizada, un smart service propio o un servlet de Appian; o necesita guardar datos desde una pantalla al pulsar un boton (function writer, no smart service, porque un smart service de plug-in no se puede usar en una expresion); o quiere exponer un endpoint HTTP propio, que es lo que hace un servlet; o menciona appian-plugin.xml, AppianSmartService, el SDK de plug-ins de Appian o el AppMarket. No usar para Components ni Connected Systems, que tienen cadena de herramientas propia, ni para modificar, auditar o migrar de version un plugin que ya existe.
---

## Overview

Existe por una asimetría de costes que atraviesa todo el diseño. El despliegue de un plugin
de Appian no está a nuestro alcance: Appian exige aprobación previa —para AppMarket público o
para uso privado por igual—, con escaneos SAST/SCA propios, y documenta que una función queda
disponible «within a week». De ahí dos consecuencias que rigen toda la skill:
**nunca se puede ejecutar el plugin generado antes de entregarlo**, y **cada error que no se
atrape en local cuesta un ciclo completo de una semana**, con una revisión de seguridad ajena
de por medio. Todo lo que esta skill hace —entrevista disciplinada, plantillas, cuatro capas
de verificación, certificado explícito— es mover hacia lo local todo lo que se pueda mover.

Cubre únicamente la **creación desde cero** de un plugin nuevo.

Las rutas con el prefijo `${CLAUDE_PLUGIN_ROOT}/` apuntan a ficheros del propio plugin. Ese
prefijo es un **marcador** —`CLAUDE_PLUGIN_ROOT`, con la sintaxis `${…}`— que Claude Code
**sustituye por la ruta absoluta del plugin al cargar este fichero** (`--plugin-dir` o
instalado): con el plugin cargado, estas líneas ya llegan con la ruta puesta y no hay nada que
traducir. **No es una variable de entorno**, así que donde el marcador aparezca literal
—trabajando dentro del repo del forge sin cargarlo como plugin, o en una referencia abierta con
`Read`— se sustituye a mano por la raíz del plugin: `appian-plugin-forge/` en el repo. Las
referencias de este directorio se citan enteras la primera vez y como `referencias/<fichero>.md`
a partir de ahí.

**Y lo mismo vale para los tres agentes que esta skill lanza**, que es menos evidente porque no
son rutas: `appian-plugin-forge:<nombre>` solo resuelve como `subagent_type` con el plugin
cargado. Sin cargarlo, ese nombre no existe y la llamada falla; se lanza entonces un agente
`general-purpose` pegándole como prompt el cuerpo de la definición del agente —un fichero por
agente, con su mismo nombre, en el directorio de agentes del forge— seguido del encargo concreto
que indica el paso. Lo que no se hace es saltarse el agente: su valor es mirar sin memoria de
esta conversación.

## When to Use

**Se dispara** en las condiciones que enumera la `description` del frontmatter. La distinción
que evita el error caro —guardar datos desde una pantalla al pulsar un botón es una *function
writer*, no un smart service, porque un smart service de plug-in no se puede usar en una
expresión— y las demás filas de tipo están en
`${CLAUDE_PLUGIN_ROOT}/skills/crear-plugin-appian/referencias/tipos-de-plugin.md`.

**No usar cuando:**

- El usuario pide un **Component** (interfaz HTML/CSS/JS con React) o un **Connected
  System**. Ambos quedan fuera: tienen cadena de herramientas propia —npm/`sail-tools`/React
  con descriptor `appian-component-plugin.xml` el primero; el Integration SDK
  (`connected-systems-core`, `connected-systems-client`) el segundo—, y ni las plantillas ni
  los validadores de este plugin los cubren.
- El usuario quiere **modificar, auditar o ampliar un plugin ya existente**, incluido un
  `.jar` suelto sin fuente. Eso es el modo EDITAR, que aún no existe.
- El usuario quiere **subir de versión de Appian** un plugin ya desplegado, o adaptar
  deprecaciones. Eso es el modo MIGRAR, que aún no existe.
- El usuario solo necesita **una firma exacta de la API de Appian** (¿existe esta clase?,
  ¿qué parámetros admite?) y no un plugin completo. Eso no necesita el ciclo entero: es una
  consulta puntual, vía `javap` sobre el JAR del SDK o el agente
  `appian-plugin-forge:appian-docs-researcher`, que se LANZA con la herramienta `Agent`.

## Process

En runtime la skill sigue el ciclo de vida de `agent-skills` —DEFINE → PLAN → BUILD → VERIFY →
REVIEW → SHIP— con nombres propios y adaptado al dominio. Las dos piezas que esa adopción
añadió sobre el ciclo genérico son el paso **PLAN** y la construcción
**incremental por slices** con commit atómico.

```
ENTREVISTA ─► CONTRATO ─► PLAN ─► ANDAMIAJE ─► SLICES ─► VERIFICACIÓN ─► REVISIÓN ─► DOSSIER
             (+ perfil)  (tareas)  (plantilla)  (TDD/commit)  (4 capas)     (lente)   (+ certificado)
   DEFINE ────────────►   PLAN     BUILD ─────────────────►   VERIFY       REVIEW      SHIP
                                                                  ▲            │
                                                                  └────────────┘
                                                         si la revisión corrigió código
```

**La única flecha que vuelve atrás es esa**, y no es opcional: corregir en el paso 6 cambia el
código que el paso 5 ya certificó, así que el certificado deja de describir lo que se entrega.
El dossier lo declara —empotra el certificado marcado como `RANCIO` si es anterior a cualquiera
de **sus** insumos: el árbol de `src/` entero, `docs/contrato.md` y los ficheros de configuración
y empaquetado que enumera
`${CLAUDE_PLUGIN_ROOT}/skills/crear-plugin-appian/referencias/certificado.md` —dos de ellos no
están en la raíz—, pero declararlo es la red, no el procedimiento: el procedimiento es volver a
verificar.

**Antes del paso 1, un minuto de comprobación de entorno**, porque lo que falte aquí se descubre
en el paso 4 con el proyecto ya andamiado: `java -version` tiene que decir **17** —la plantilla
clava el *toolchain* a 17 y no descarga otro: con solo un JDK 21, Gradle para en «No matching
toolchains found»—; `git --version`, porque el proyecto generado es un repositorio y cada tarea es
un commit; `python --version` 3.11 o superior; y red en la primera build, que baja Gradle 8.14.3
de `services.gradle.org` y el SDK de Maven Central (unos 230 MB, varios minutos). Gradle no se
instala: cada proyecto trae su wrapper. Sin Java, `./gradlew` lo dice claro —`JAVA_HOME is not set
and no 'java' command could be found`—, pero para entonces ya hay un proyecto a medias.

### 1 · ENTREVISTA (DEFINE)

Una pregunta por turno, sin opción múltiple, formato `Q` / `GUESS` / `CONFIDENCE`. El tipo de
plugin **no se pregunta**: se deduce de lo que el usuario describe y se propone con su
porqué (`referencias/tipos-de-plugin.md`). El perfil de rigor —ESTÁNDAR o RIGUROSO— tampoco se
pregunta aparte: se deduce de cuatro de las preguntas de admisión y se propone
(`${CLAUDE_PLUGIN_ROOT}/skills/crear-plugin-appian/referencias/entrevista.md`).

Produce `docs/contrato.md`: un Markdown con un bloque ```toml``` que cumple el esquema de
`${CLAUDE_PLUGIN_ROOT}/scripts/contrato.py`.

**Para saber qué forma tiene, mira un ejemplo antes que el fuente:**
`${CLAUDE_PLUGIN_ROOT}/tests/fixtures/contratos/` trae uno canónico por cada uno de los cuatro
tipos —`function-minimo.md`, `writer-function-minimo.md`, `smart-service-minimo.md`,
`servlet-minimo.md`— más un quinto, `smart-service-completo.md`, que enseña hasta dónde llega un
contrato con todo declarado. Los cinco los ejerce la suite, así que no pueden quedarse rancios. Los `-minimo` son la **forma mínima real**, no el camino feliz; qué llevan
de más sin que la puerta lo exija, y por qué, en `referencias/entrevista.md`.

**Criterio de salida:** las dos puertas de `referencias/entrevista.md` en verde —
`python "${CLAUDE_PLUGIN_ROOT}/scripts/contrato.py" docs/contrato.md` sin ninguna línea
`FALTA`, y un «sí» explícito del usuario a la puerta de confianza—. Ninguna basta sola. El «sí»
se escribe en el contrato como `[confirmacion]` / `usuario_confirmo = true`
(`referencias/entrevista.md`) — sin ese bloque, la puerta determinista de arriba nunca cierra en
verde, así que la propia herramienta hace imposible generar sobre un contrato que nadie confirmó.

> **En PowerShell, el marcador `CLAUDE_PLUGIN_ROOT` no se copia tal cual**: `${…}` es sintaxis de
> variable de sesión y se expande a cadena vacía sin avisar. Y traducirlo a `$env:CLAUDE_PLUGIN_ROOT`
> no arregla nada, porque **no es una variable de entorno y está vacía**. Con el plugin cargado esta
> línea ya llega con la ruta absoluta y no hay nada que traducir; si el marcador aparece literal, se
> escribe la ruta absoluta del plugin, entre comillas dobles. Detalle y por qué, en
> `${CLAUDE_PLUGIN_ROOT}/skills/crear-plugin-appian/referencias/entorno-windows.md`.

Un `AVISO` **no es una `FALTA`** y no bloquea, pero tampoco sale gratis, y el único que existe
hoy conviene entenderlo aquí: si las `[capacidades]` proponen RIGUROSO y el contrato declara
`estandar`, **la verificación sube el perfil por su cuenta** y el certificado dice qué
capacidad lo pidió. O sea que declararlo `estandar` no ahorra las cuatro puertas rigurosas: solo
las aparta de la vista de quien lea el contrato. Decide el perfil aquí, con el usuario delante.

### 2 · PLAN DE TAREAS (PLAN)

El contrato se descompone en tareas pequeñas y verificables —slices verticales, no capas
técnicas—, cada una con su criterio de aceptación y los requisitos del contrato que cubre. Es
el `/plan` del ciclo de referencia: sin él, «lógica hasta que los tests pasen» es un bloque
opaco. Se escribe como `docs/plan.md`, junto al contrato.

**Criterio de salida:** todo input y todo output declarado en el contrato está cubierto por
al menos una tarea del plan — la matriz requisito→tarea de la que luego sale la matriz
requisito→test del dossier.

### 3 · ANDAMIAJE (BUILD, parte 1)

Sin modelo de por medio:
`python "${CLAUDE_PLUGIN_ROOT}/scripts/andamiar.py" docs/contrato.md <directorio-destino>`
sustituye variables sobre las plantillas de `${CLAUDE_PLUGIN_ROOT}/assets/plantillas/` y
genera **el adaptador de Appian**: una clase en `<paquete>.<smartservice|function|servlet>`
—son tres subpaquetes para cuatro tipos: una *writer function* aterriza en `function`, igual
que una de lectura, porque comparte con ella manifiesto y bundles—
con las firmas del contrato, el `build.gradle` compuesto según el perfil, el *wrapper* de
Gradle, `appian-plugin.xml` y —salvo en servlets, que no cargan bundle— los `.properties`
`_en_US`/`_es_ES`, y deja una copia literal del contrato en `<directorio-destino>/docs/contrato.md`,
de donde la leen VERIFICACIÓN (paso 5) y DOSSIER (paso 7). Es sustitución de variables: sale
bien siempre, y son justo los ficheros donde un error cuesta un ciclo de aprobación entero.
Deja también `docs/decisiones.md` —la pieza 2 del dossier, y donde `R-F14` busca la firma de cada
exclusión activa de SpotBugs—, que en un smart service nace ya con una decisión escrita: la
exclusión de `CRLF_INJECTION_LOGS` que la propia plantilla activa, con su porqué y con la
condición bajo la que deja de valer. Si el fichero ya existe, no se toca.

**El dominio NO se andamia, y saberlo importa:** la separación dominio / adaptador la
construye el paso 4, no éste. El convenio es `<paquete>.dominio`
(`contrato.SUBPAQUETE_DOMINIO`), y la capa 2 comprueba ahí que **ninguna clase de dominio
referencie el SDK** — que es lo que permite que los tests JUnit corran sin cargarlo. La
columna de insumo del certificado declara cuántas clases de dominio miró: un andamiaje recién
generado dice `0 clases de dominio`, que es legítimo y visible, no un aprobado.

**Tres trampas al escribir los tests.**
`SmartServiceException.Builder.build()` **lanza `NullPointerException` fuera del runtime de
Appian** —resuelve el bundle contra un contexto que en JUnit no existe—, así que el test del
adaptador que ejercita el camino de error se monta con `mockConstruction`; no es un fallo tuyo
ni de la plantilla. Si el perfil es RIGUROSO, el certificado
busca clases `*FuzzTest`/`*PropertyTest` **por el nombre**: nombrarlas así al escribirlas cuesta
cero, y descubrirlo en el paso 5 cuesta otra pasada (el detalle, en `referencias/certificado.md`).
Y también en RIGUROSO, **PIT y JaCoCo no cuentan igual un constructor privado vacío**: JaCoCo lo
filtra de su métrica de líneas y PIT no, así que una clase de utilidad estática pasa la cobertura
de JaCoCo y falla el umbral de PIT (`Line coverage of 88 is below threshold of 90`) sin que el
mensaje diga qué líneas. La salida es no hacerla estática —instancia inmutable en un campo
`final` del adaptador—, nunca bajar el umbral.

**En RIGUROSO, antes de cerrar el primer slice:** `./gradlew dependencies --write-locks` y commitear
el `gradle.lockfile` que deja. `build.gradle` activa `dependencyLocking`, pero Gradle no escribe
ni exige el lockfile por su cuenta: sin él el cierre de dependencias no fija nada, y `R-F15` lo
pone en rojo. Se regenera con el mismo comando cada vez que cambien las dependencias.

**El andamiaje no crea el repositorio, y el paso 4 lo necesita:** si `<directorio-destino>` no
está dentro de un repositorio, `git init` ahí antes del primer slice. El paso 4 commitea una vez
por slice y la cabecera del certificado registra la revisión del fuente que describe; sin
repositorio, esa línea degrada a «sin repositorio git — el certificado no queda atado a ningun
commit» y la cabecera pierde una de las cinco cosas que declara. No lo hace `andamiar.py` a
propósito: es sustitución de variables y por eso sale bien siempre, y lanzarle un subproceso le
añadiría un modo de fallo que hoy no tiene.

**Criterio de salida:** `andamiar.py` termina en 0, cada ruta que imprime como escrita existe de
verdad en el destino, y el destino está dentro de un repositorio git. Ojo con lo que ese criterio
NO puede ver: lo que falta no se imprime, así que no sirve para comprobar que se generó todo lo
que se esperaba.

### 4 · CONSTRUCCIÓN INCREMENTAL POR SLICES (BUILD, parte 2)

Cada tarea del plan es un ciclo TDD completo: sus casos JUnit primero (rojo), la lógica
mínima que los pone en verde, y un **commit atómico por slice**. *One slice at a time*: nunca
hay más de una tarea abierta a la vez, y el proyecto compila y pasa sus tests entre slice y
slice. La lógica va en el **dominio**, que no importa `com.appiancorp.*`; el adaptador Appian
solo traduce.

El agente `appian-plugin-forge:plugin-compiler-fixer` --lanzado con `Agent`-- cierra el bucle
compilar/corregir de cada slice. Se le lanza sin memoria de esta conversación, así que el
prompt lleva lo mínimo que necesita para no adivinar: la ruta absoluta del proyecto generado
y la tarea del plan que se acaba de implementar —«Compila y corrige
`<ruta-absoluta-del-proyecto-generado>`. Tarea actual del plan: `<la tarea de docs/plan.md que
se acaba de escribir>`. Devuelve el informe completo.»—.

**Si no vuelve pronto, no te quedes esperando: haz tú el trabajo y sigue.** Vale para los tres
agentes de esta skill. Un ejecutor parado en silencio no está avanzando, y hay relojes de
inactividad que lo dan por muerto: el caso más frecuente es un ejecutor esperando a un hijo que
ya había terminado su trabajo. Ejecuta el comando por tu cuenta, anota en el informe que lo
hiciste, y cuando el informe del agente llegue, reconcílialo: llegar tarde no lo invalida, y
puede traer hallazgos reales que tú no viste. Lo que no vale es darlo por hecho sin que llegue.

**Ese agente deja capturada la salida del
último build en `build/salida-build.log`**, que es lo que el paso 5 lee: si se construye a mano en
su lugar, hay que capturarla igual, con el comando que publica ese paso. Para cualquier duda sobre una firma, una clave o un valor
admitido de la API de Appian, la jerarquía de fuentes es `javap` sobre el JAR del SDK > agente
`appian-plugin-forge:appian-docs-researcher` > javadoc web. Una guía o un tutorial de terceros
puede servir de estructura, nunca de fuente de estos hechos (ver `## Common Rationalizations`).

**Dónde está ese JAR**, porque `javap` se exige a lo largo de esta skill —encabeza la jerarquía de
fuentes de aquí arriba, y volverá en `## Common Rationalizations` y en `## Red Flags`— y sin la
ruta la obligación no se puede cumplir. La coordenada es `com.appian:appian-plug-in-sdk:26.3`, la
misma que declara la plantilla de Gradle, y **el JAR aparece en la caché de Gradle solo después
del primer `./gradlew build`** (paso 4). Cómo se busca —y la trampa de PowerShell con `find`/`$JAR`
vacío y con el comodín de versión— en `referencias/entorno-windows.md`.

**Antes de que ese build exista** —los pasos 1 y 2 pueden necesitar un hecho de API para decidir
un `tipo_java` o confirmar que una clase existe— no hay JAR en ninguna parte. Ahí la jerarquía
baja un escalón por necesidad, no por comodidad: se usa el agente
`appian-plugin-forge:appian-docs-researcher` **y se marca el hecho como no verificado contra el
JAR**, para volver a comprobarlo en el paso 4. Se le lanza con la pregunta concreta y qué
decisión depende de ella, nunca con la duda general —«Necesito saber
`<pregunta concreta sobre la API de Appian>` para decidir `<qué campo o tipo_java depende de la
respuesta>`. Marca el hecho como no verificado contra el JAR.»—. La regla es una: cuando no hay
fundamento, se marca; no se aparenta certeza.

**Prerequisitos de entorno**: los de la comprobación previa al paso 1 —JDK 17, git, Python 3.11+ y
red la primera vez—. `javap` viene con ese mismo JDK, el que compila los plug-ins.

**La única excepción admitida al `BUILD SUCCESSFUL`, y no es una avería: `SECSP` en un
servlet.** Un servlet recién andamiado **no pasa `./gradlew build`** hasta que se implemente
`ejecutar()` y se decida, con conocimiento, si la exclusión de FindSecBugs procede. El argumento
completo vive ya redactado en `config/spotbugs/exclude.xml` del proyecto generado —se lee allí, no
se copia aquí—; qué la dispara y por qué es deliberado, en
`${CLAUDE_PLUGIN_ROOT}/skills/crear-plugin-appian/referencias/secsp-servlet.md`. Lo que **no** se
hace es excluir el detector para que el build pase, ni relajar `reportLevel` ni `ignoreFailures`
en `build.gradle`; y hasta que la decisión se tome, la puerta de SpotBugs del certificado sale en
rojo, que es la verdad.

**Criterio de salida:** al cierre de cada slice, `./gradlew build` termina con
`BUILD SUCCESSFUL` en su salida real —salvo el `SECSP` de un servlet mientras esa decisión siga
sin tomarse, que es el único fallo esperado—, y existe exactamente un commit nuevo para esa
tarea.

### 5 · VERIFICACIÓN (VERIFY)

`python "${CLAUDE_PLUGIN_ROOT}/scripts/verificar_todo.py" <raíz-del-proyecto-generado>
<perfil>` ejecuta las capas disponibles y escribe `docs/CERTIFICADO.md`. Las cuatro capas están
en `## Verification` más abajo; **para interpretar la tabla que sale de aquí —los seis estados,
la columna de insumo, quién ejecuta cada puerta, y cualquier fila que no salga verde— se abre
`${CLAUDE_PLUGIN_ROOT}/skills/crear-plugin-appian/referencias/certificado.md`**. Las reglas
concretas, con su fuente e ID, en `${CLAUDE_PLUGIN_ROOT}/assets/reglas-de-validacion.md` — no se
repiten aquí.

**`<perfil>` sube el listón, nunca lo baja.** Vale el más estricto entre lo que declara el
contrato y lo que se pide aquí, y el certificado dice cuál de los dos ganó. Omitirlo sobre un
contrato `riguroso` **no** rebaja la verificación: si la rebajara, las cuatro puertas rigurosas
no fallarían —desaparecerían de la tabla—, y el certificado quedaría más limpio por haber
mirado menos.

**El orquestador no invoca Gradle, pero sí lee lo que Gradle hizo**, y media tabla sale de ahí.
Capturar su salida en la ruta convenida, que es donde la busca:

```
mkdir -p build && ./gradlew build --console=plain > build/salida-build.log 2>&1
```

El `mkdir` no es adorno y en PowerShell el comando es otro; por qué, y qué hace el orquestador
cuando la salida no consta, está rancia, está truncada o su código contradice al log, en
`referencias/certificado.md` § *La salida de `./gradlew build`*.

**Con perfil RIGUROSO ese comando no basta, y el criterio de salida se vuelve inalcanzable si no
se sabe**: tres de sus cuatro puertas —`jacocoTestCoverageVerification`, `mutationTest` y
`releaseCheck`— **no forman parte de `build`**, así que sin invocarlas salen en rojo para siempre.
`releaseCheck` arrastra las tres y exige un worktree de git limpio, así que el commit del slice va
antes:

```
mkdir -p build && ./gradlew build releaseCheck --console=plain > build/salida-build.log 2>&1
```

**«Worktree limpio» es TODO el árbol, no solo `src/`**, y hay dos formas típicas de ensuciarlo
sin querer: escribir `docs/decisiones.md` mientras el build corre, y **el propio
`docs/CERTIFICADO.md`** al repetir la puerta —el certificado que la pasada anterior acaba de
escribir—. Así que antes de lanzarla: commitear todo, `docs/` incluido, y si hay que repetirla,
commitear también el certificado de la pasada previa.

**El criterio no hay que aplicarlo a mano: el certificado lo publica.** Su cabecera abre con
`**STATUS: READY_FOR_APPIAN_SUBMISSION**` o `**STATUS: NOT_READY**`, y cuando dice `NOT_READY`
lista debajo qué puerta lo impide y por qué, una línea por motivo — es este mismo criterio de
salida, mecanizado en `verificar_todo.estado_de_sumision`. Leerlo no exime de mirar la tabla,
pero invierte la carga. Qué cuenta y qué no, y qué significa cada código de salida, en
`referencias/certificado.md` § *El `STATUS`*.

**Criterio de salida**, en tres partes, y las tres se comprueban sobre el certificado:

1. **Ninguna puerta en «pendiente».** «Pendiente» significa que nadie la miró y nadie dijo por
   qué; es el único estado sin explicación, y por eso es el que no puede quedar.
2. **Ninguna puerta en «NO VERIFICADO»**, salvo las dos filas estructuralmente rojas siempre
   —resolución OSGi en la plataforma, ejecución en Appian real—.
3. **Cada puerta delegada trae su salida real, no solo el nombre de quien la ejecuta.** Delegar
   **no es aprobar**, y ya no hace falta creerlo: la tabla lo comprueba. Solo quedan en
   «delegada» las que un `BUILD SUCCESSFUL` no puede aprobar por mucho que se ejecute —hoy
   **dos**: el bytecode de las copias *dentro* del JAR, y la reproducibilidad del build, que
   la plantilla configura y ninguna tarea comprueba—, y ahí cada fila registra igualmente que
   el build corrió y cómo terminó. El juicio sobre el copyleft **no** está entre ellas:
   `verificar_licencias.py` lee el SBOM, así que esa puerta se ejecuta como cualquier otra de
   la capa 1.

Un servlet recién andamiado **no llega a este criterio**, y no es una excepción que se le
conceda: es el criterio funcionando. Su build falla en `spotbugsMain` por el `SECSP` que el
paso 4 deja abierto a propósito, así que el bloque entero del paso 4 sale en rojo hasta que se
implemente `ejecutar()` y se tome la decisión. Se cierra decidiendo, nunca relajando la puerta.

### 6 · REVISIÓN (REVIEW)

El agente `appian-plugin-forge:plugin-contract-reviewer` —lanzado con `Agent`, la única lente de
juicio del pipeline—
compara el código contra el contrato, requisito a requisito, y comprueba lo que ningún script
mecaniza: separación dominio/adaptador, ausencia de estado mutable en clases de función,
`ServiceLocator` dentro de constructores, manejo de errores y de recursos. Sus hallazgos se
corrigen antes de emitir el expediente.

Se le lanza sin memoria de lo que se acaba de construir —esa distancia es la ventaja, no un
defecto—, así que el prompt le da lo que necesita para no adivinar en su lugar: la ruta absoluta
del proyecto generado y dónde está cada cosa —«Revisa `<ruta-absoluta-del-proyecto-generado>`
contra su `docs/contrato.md`. El código está en `src/`. Devuelve el veredicto en el formato
obligatorio de tu agente.»—. Un prompt que solo diga «revisa esto» es indistinguible de una
revisión sin hacer: el agente puede acabar leyendo de menos y dando `cumple` sin haber mirado lo
que hace falta.

**Su salida se escribe tal cual en `docs/hallazgos-revision.md`**, en el proyecto generado, y
se le añade la fecha y el rango revisado. No es burocracia: sin ese rastro, un dossier no puede
distinguir «revisado y sin hallazgos» de «nadie lo miró», que son afirmaciones muy distintas, y
una sesión nueva —tras `/clear` o días después -- no recupera ni un hallazgo. El dossier lee de
ahí su línea de cabecera.

**Tope del bucle: tres pasadas.** Si a la tercera siguen apareciendo hallazgos de severidad
alta, se para y se escala a decisión humana, dejando en `docs/hallazgos-revision.md` lo que
quede abierto. Corregir y volver a pasar es el ciclo correcto; hacerlo indefinidamente es
otra cosa, y sin tope no se distinguen.

**Criterio de salida:** `VEREDICTO: cumple`, o cada hallazgo de la última pasada corregido y
la clase afectada vuelta a pasar por el agente — con un máximo de tres pasadas. **Y si se
corrigió una sola línea de código, volver al paso 5 antes del 7**: el certificado que emitió
aquel paso describe el árbol de antes de la corrección, y es el que el dossier empotra. Cada
corrección va además en su propio commit, igual que los slices del paso 4 — un arreglo sin
commit no aparece en la revisión de git que el certificado publica.

### 7 · DOSSIER (SHIP)

`python "${CLAUDE_PLUGIN_ROOT}/scripts/generar_dossier.py" <raíz-del-proyecto-generado>`
escribe `docs/DOSSIER.md`. **Reescribe el fichero entero en cada pasada**, así que las dos
piezas de prosa que no se derivan de ningún artefacto viven fuera y él solo las lee:

- `<raíz-del-proyecto-generado>/docs/decisiones.md` — la pieza 2, estilo ADR: qué API se eligió
  y contra qué alternativa, por qué ese manejo de errores. Se escribe **según se decide**, no al
  final: es lo que una sesión nueva no puede reconstruir por sí sola, porque no se deriva del
  código. **La raíz importa y aquí es la del proyecto generado**: conviven dos `docs/` —el del
  directorio de trabajo, de donde el paso 3 toma el contrato, y el del proyecto andamiado—, y
  el generador solo mira el segundo. Decidir antes de que exista el destino es lo normal; lo que
  no puede quedarse es el fichero en el `docs/` de trabajo, porque entonces esta pieza viaja
  vacía y el dossier lo declarará como ausente.
- `<raíz-del-proyecto-generado>/docs/hallazgos-revision.md` — lo que dejó el paso 6.

Escribir cualquiera de las dos *dentro* de `DOSSIER.md` es perderla en la siguiente ejecución.

El dossier reúne seis piezas: el contrato, las decisiones y su porqué, el
inventario de API usada (extraído del bytecode, no escrito a mano), el certificado del paso
5, el historial de versiones, y la **firma pública congelada** —clave, y nombre y tipo de
cada input/output— que es lo único que hace comprobable la regla de clave nueva
(`referencias/entrevista.md`, séptima pregunta) en una futura edición. No es un despliegue:
es un expediente de sumisión, un disparo sin rollback, con una semana de latencia y un
tercero decidiendo.

**Criterio de salida:** las seis piezas están presentes, y la firma congelada corresponde al
contrato final aceptado en el paso 1 — no a una versión intermedia de una entrevista
corregida a mitad de camino.

**Documentación de usuario, aparte del dossier.**
`python "${CLAUDE_PLUGIN_ROOT}/scripts/generar_documentacion_usuario.py" <raíz-del-proyecto-generado>`
escribe `docs/GUIA_INTEGRACION.md` (para el desarrollador Appian que va a integrar el plugin: cómo
invocarlo según el tipo, tabla de entradas/salidas, versión mínima requerida) y
`docs/FICHA_APPMARKET.md` (texto de ficha para quien lo encuentra en el Marketplace). Los dos se
derivan enteramente de `docs/contrato.md`, sin preguntar nada nuevo, y **no son piezas del
dossier**: el dossier tiene audiencia interna —quien edite este mismo plugin más adelante—; estos
dos documentos son para quien lo va a usar. Se generan siempre, en la misma pasada que el dossier.

**Criterio de salida, completo:** las seis piezas del dossier están presentes con la firma
congelada correcta, **y** `docs/GUIA_INTEGRACION.md` y `docs/FICHA_APPMARKET.md` existen con
contenido no vacío.

## Common Rationalizations

| Racionalización | Realidad |
|---|---|
| «Ya compila, los tests son opcionales» | Compilar prueba que las firmas existen, no que el plugin haga nada correcto |
| «Esta clase de `com.appiancorp` seguro que existe» | `javap` sobre el JAR tarda un segundo y es evidencia primaria |
| «Lo dice una guía / un tutorial» *(sobre una firma, una clave o un valor admitido)* | Una guía es fuente de **estructura**, no de hechos de API: circulan guías cuyo formato de `.properties` para smart services —sin sufijo de locale— **impide desplegar**, y cuyo `paletteCategory = "Appian Smart Services"` ya no es válido. Para un hecho, `javap` o la documentación |
| «Ya lo probarás al desplegar» | Desplegar cuesta una semana y una aprobación ajena |
| «Es un plugin pequeño, no hace falta contrato» | Sin contrato no hay tests, y sin tests no hay nada que verificar |
| «Es solo añadir un input, dejo la misma clave» | Cambiar inputs u outputs sin clave nueva **rompe procesos vivos en producción**: la documentación de Appian (*Smart Service Plug-ins › Best practices › Upgrading*) lo dice con todas las letras —«You must use a new key. If you overwrite the plug-in, existing nodes may fail»—. Es el único error de esta lista cuya factura no la paga el despliegue — **y ninguna capa lo detecta**: sin `[version_anterior]` en el contrato, `R-F08` no salta, ni con error ni con aviso. La red es la séptima pregunta de la entrevista, y no hay otra |
| «Uso la constante del SDK, así que la paleta está bien» | El SDK expone 7 valores y solo 4 son válidos; tres se remapean en silencio. La documentación de Appian solo admite `Workflow`, `Automation Smart Services`, `Deprecated Services` y `Hidden`: «any other value will be mapped to Automation Smart Services» |
| «El perfil riguroso tarda mucho para lo que es» | El perfil lo decide lo que el plug-in toca, no la prisa. Si parsea formatos ajenos o sale a la red, el espacio de entradas no es nuestro |
| «No hay `import` de esa clase, no la estoy usando» | Un nombre cualificado no genera `import`. Por eso el escáner mira el bytecode y no el fuente |
| «El build lo corrí yo y pasó, el log da igual» | Sin log, la tabla no puede distinguir esa palabra de un build que falló: sus **filas delegadas** —**ocho** en RIGUROSO, **cuatro** en ESTÁNDAR— certificarían idéntico |

## Red Flags

- Se escribe lógica de negocio antes de que exista un solo caso JUnit.
- Se escribe lógica sin plan de tareas, para una tarea que no figura en el plan, o con más de
  un slice abierto a la vez.
- Se escribe `[confirmacion]` con `usuario_confirmo = true` antes de que el usuario haya dicho
  que sí, o se deja el bloque de una confirmación anterior tras editar el contrato.
- Se afirma que una clase o método de `com.appiancorp` existe sin haber ejecutado `javap`.
- El `.properties` generado no lleva sufijo de locale.
- Se declara un plug-in terminado sin certificado, o con una puerta marcada como pasada que
  no se ejecutó.
- Se certifica sin haber capturado la salida de `./gradlew build`, o con una capturada antes
  del último cambio del fuente.
- Se excluye `SECSP` para que el build de un servlet pase, antes de haber escrito `ejecutar()`.
- Se copia una regla de validación dentro de la skill en vez de referenciarla.
- Se responde a una duda de API citando una guía o un tutorial en vez de `javap` o la
  documentación.
- Se reutiliza la clave de un plug-in desplegado tras cambiar sus inputs u outputs.
- Aparece un campo mutable —de instancia o `static`— en una clase de función.
- El dominio importa `com.appiancorp.*`, o un test de dominio necesita el SDK para arrancar.
- Se valida la superficie de API contra `latest` en vez de contra la versión del SDK.
- Se genera un locale nuevo sin comprobar la paridad de claves con `_en_US`.

## Verification

Cuatro capas, todas mecanizadas por script y reunidas por
`${CLAUDE_PLUGIN_ROOT}/scripts/verificar_todo.py`; las reglas exactas, con su fuente y su ID
(`R-F*`, `R-A*`, `R-B*`, `R-J*`), viven en
`${CLAUDE_PLUGIN_ROOT}/assets/reglas-de-validacion.md` — no se duplican aquí.

| Capa | Qué atrapa | Ejecutor |
|---|---|---|
| 1 · Reglas del framework + políticas AppMarket | lo que impide desplegar y lo que hace que Appian rechace el envío, **incluido el copyleft de las dependencias** — la política más tajante de AppMarket, que se juzga leyendo el SBOM del build | `${CLAUDE_PLUGIN_ROOT}/scripts/verificar_framework.py`, `${CLAUDE_PLUGIN_ROOT}/scripts/verificar_appmarket.py`, `${CLAUDE_PLUGIN_ROOT}/scripts/verificar_bundles.py`, `${CLAUDE_PLUGIN_ROOT}/scripts/verificar_licencias.py` |
| 2 · Compilación + escáner de bytecode | clases y firmas inventadas, y uso de API no documentada — también cuando no hay `import` | `./gradlew build` + `${CLAUDE_PLUGIN_ROOT}/scripts/verificar_superficie.py` contra `${CLAUDE_PLUGIN_ROOT}/assets/indice-tipos-26.3.json` |
| 3 · Tests unitarios | comportamiento contra el contrato | JUnit 5 + Mockito, vía `./gradlew build` |
| 4 · Empaquetado, dependencias y toolchain | fuente embebida, manifiesto en la raíz, cierre de dependencias, licencias, bytecode del artefacto | `${CLAUDE_PLUGIN_ROOT}/scripts/verificar_jar.py` sobre el JAR ya construido |

El perfil RIGUROSO añade cuatro puertas más (cobertura JaCoCo, mutación PIT, *property
tests*/fuzz sembrado, build reproducible). El perfil no cambia qué reglas se cumplen, solo
qué puertas se ejecutan: las reglas del framework y las políticas de AppMarket son
innegociables en los dos perfiles.

Dos reglas gobiernan la lectura de la tabla y ninguna se negocia: **una puerta que no se
ejecutó nunca se marca como pasada** —ni «pendiente» ni «delegada» son «OK»— y **un verde sobre
un insumo vacío no cuenta como verde**. La mecánica que las hace comprobables —los seis estados
posibles y la regla de `no aplica`, la unidad portante en la que se mide «vacío», qué puerta
ejecuta quién, y por qué la de build reproducible no llega a verde nunca— vive en
`referencias/certificado.md`.

Dos filas van siempre en rojo, y decirlo con todas las letras es la función del certificado,
no un defecto: la resolución OSGi real de la plataforma y la ejecución en Appian real no son
verificables en local. Un plugin ESTÁNDAR no debe poder pasar por RIGUROSO
leyendo el dossier: la cabecera del certificado declara el perfil, la versión del SDK, la del
índice de tipos con su hash, y la revisión de git.
