---
name: crear-plugin-appian
description: Genera un plugin de Appian de tipo Function —de lectura o writer—, Smart Service o Servlet a partir de una entrevista al usuario, y lo verifica en cuatro capas hasta el limite de lo posible en local. Use when el usuario pide crear, generar o construir un plugin de Appian, una funcion de expresion personalizada, un smart service propio o un servlet de Appian; o necesita guardar datos desde una pantalla al pulsar un boton (function writer, no smart service, porque un smart service de plug-in no se puede usar en una expresion); o quiere exponer un endpoint HTTP propio, que es lo que hace un servlet; o menciona appian-plugin.xml, AppianSmartService, el SDK de plug-ins de Appian o el AppMarket. No usar para Components ni Connected Systems, que tienen cadena de herramientas propia, ni para modificar, auditar o migrar de version un plugin que ya existe.
---

## Overview

Existe por una asimetría de costes que atraviesa todo el diseño. El despliegue de un plugin
de Appian no está a nuestro alcance: Appian exige aprobación previa —para AppMarket público o
para uso privado por igual—, con escaneos SAST/SCA propios, y documenta que una función queda
disponible «within a week» (spec §3.3). De ahí dos consecuencias que rigen toda la skill:
**nunca se puede ejecutar el plugin generado antes de entregarlo**, y **cada error que no se
atrape en local cuesta un ciclo completo de una semana**, con una revisión de seguridad ajena
de por medio. Todo lo que esta skill hace —entrevista disciplinada, plantillas, cuatro capas
de verificación, certificado explícito— es mover hacia lo local todo lo que se pueda mover.

Cubre únicamente el modo **CREAR** (Fase 1 del proyecto): generación desde cero.

La spec de referencia es `docs/superpowers/specs/2026-08-08-appian-plugin-forge-design.md`
(repo de desarrollo; no viaja con el plugin — «la spec» en el resto de este documento); las
secciones citadas son las suyas. Las rutas con el prefijo `${CLAUDE_PLUGIN_ROOT}/` apuntan a
ficheros del propio plugin: Claude Code define esa variable cuando la skill corre como plugin
cargado (`--plugin-dir` o instalado), y si se trabaja dentro del repo del forge sin cargarlo
como plugin, se sustituye por la raíz `appian-plugin-forge/`. Las tres referencias de este
directorio se citan enteras la primera vez y como `referencias/<fichero>.md` a partir de ahí.

## When to Use

**Se dispara** en las condiciones que enumera la `description` del frontmatter. La distinción
que evita el error caro —guardar datos desde una pantalla al pulsar un botón es una *function
writer*, no un smart service, porque un smart service de plug-in no se puede usar en una
expresión— y las demás filas de tipo están en
`${CLAUDE_PLUGIN_ROOT}/skills/crear-plugin-appian/referencias/tipos-de-plugin.md`.

**No usar cuando:**

- El usuario pide un **Component** (interfaz HTML/CSS/JS con React) o un **Connected
  System**. Ambos quedan fuera de la Fase 1 (spec §2.2): tienen cadena de herramientas
  propia —npm/`sail-tools`/React con descriptor `appian-component-plugin.xml` el primero; el
  Integration SDK (`connected-systems-core`, `connected-systems-client`) el segundo—, y ni
  las plantillas ni los validadores de este plugin los cubren.
- El usuario quiere **modificar, auditar o ampliar un plugin ya existente**, incluido un
  `.jar` suelto sin fuente. Eso es el modo EDITAR (Fase 2, spec §2.1), que aún no existe.
- El usuario quiere **subir de versión de Appian** un plugin ya desplegado, o adaptar
  deprecaciones. Eso es el modo MIGRAR (Fase 3, spec §2.1), que aún no existe.
- El usuario solo necesita **una firma exacta de la API de Appian** (¿existe esta clase?,
  ¿qué parámetros admite?) y no un plugin completo. Eso no necesita el ciclo entero: es una
  consulta puntual, vía `javap` sobre el JAR del SDK o el agente
  `appian-plugin-forge:appian-docs-researcher`, que se LANZA con la herramienta `Agent`.

## Process

En runtime la skill sigue el ciclo de vida de `agent-skills` —DEFINE → PLAN → BUILD → VERIFY →
REVIEW → SHIP— con nombres propios y adaptado al dominio (spec §5.2, decisión D21). Las dos
piezas que esa adopción añadió sobre el ciclo genérico son el paso **PLAN** y la construcción
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
`FALTA`, y un «sí» explícito del usuario a la puerta de confianza—. Ninguna basta sola.

> **En PowerShell, esta línea y todas las `${CLAUDE_PLUGIN_ROOT}` de este documento se traducen a
> `$env:CLAUDE_PLUGIN_ROOT`** — si no, la ruta se expande a cadena vacía sin avisar, y si la
> variable no está puesta en el entorno falla igual de callado. Detalle y por qué, en
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

**El dominio NO se andamia, y saberlo importa:** la separación dominio / adaptador (spec
§5.6, D19) la construye el paso 4, no éste. El convenio es `<paquete>.dominio`
(`contrato.SUBPAQUETE_DOMINIO`), y la capa 2 comprueba ahí que **ninguna clase de dominio
referencie el SDK** — que es lo que permite que los tests JUnit corran sin cargarlo. La
columna de insumo del certificado declara cuántas clases de dominio miró: un andamiaje recién
generado dice `0 clases de dominio`, que es legítimo y visible, no un aprobado.

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
compilar/corregir de cada slice. Para cualquier duda sobre una firma, una clave o un valor
admitido de la API de Appian, la jerarquía de fuentes es `javap` sobre el JAR del SDK > agente
`appian-plugin-forge:appian-docs-researcher` > javadoc web (spec §6.3) — la guía
local (`docs/AI Plugin Generator skill Support Guide.md`, repo de desarrollo; no viaja con el
plugin) es fuente de estructura, nunca de estos hechos (ver `## Common Rationalizations`).

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
JAR**, para volver a comprobarlo en el paso 4. Es lo que manda spec §6.3: cuando no hay
fundamento, se marca; no se aparenta certeza.

**Prerequisitos de entorno**, que esta skill da por supuestos y conviene comprobar una vez: JDK 17
(`javap -version`; el mismo que compila los plug-ins), acceso de red a Maven Central para que
`./gradlew build` resuelva el SDK la primera vez, y `python` para los validadores. Gradle no hace
falta instalarlo: cada proyecto generado trae su wrapper.

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

El dossier reúne las seis piezas de la spec §8.1: el contrato, las decisiones y su porqué, el
inventario de API usada (extraído del bytecode, no escrito a mano), el certificado del paso
5, el historial de versiones, y la **firma pública congelada** —clave, y nombre y tipo de
cada input/output— que es lo único que hace comprobable la regla de clave nueva
(`referencias/entrevista.md`, séptima pregunta) en una futura edición. No es un despliegue:
es un expediente de sumisión, un disparo sin rollback, con una semana de latencia y un
tercero decidiendo (spec §9).

**Criterio de salida:** las seis piezas están presentes, y la firma congelada corresponde al
contrato final aceptado en el paso 1 — no a una versión intermedia de una entrevista
corregida a mitad de camino.

## Common Rationalizations

| Racionalización | Realidad |
|---|---|
| «Ya compila, los tests son opcionales» | Compilar prueba que las firmas existen, no que el plugin haga nada correcto |
| «Esta clase de `com.appiancorp` seguro que existe» | `javap` sobre el JAR tarda un segundo y es evidencia primaria |
| «La guía dice que…» *(sobre una firma, una clave o un valor admitido)* | La guía es fuente de **estructura**, no de hechos de API: su formato de `.properties` para smart services **impide desplegar** y su `paletteCategory` ya no es válido. Para un hecho, `javap` o la documentación |
| «Ya lo probarás al desplegar» | Desplegar cuesta una semana y una aprobación ajena |
| «Es un plugin pequeño, no hace falta contrato» | Sin contrato no hay tests, y sin tests no hay nada que verificar |
| «Es solo añadir un input, dejo la misma clave» | Cambiar inputs u outputs sin clave nueva **rompe procesos vivos en producción** (auditoría §7.4). Es el único error de esta lista cuya factura no la paga el despliegue — **y ninguna capa lo detecta**: sin `[version_anterior]` en el contrato, `R-F08` no salta, ni con error ni con aviso. La red es la séptima pregunta de la entrevista, y no hay otra |
| «Uso la constante del SDK, así que la paleta está bien» | El SDK expone 7 valores y solo 4 son válidos; tres se remapean en silencio (auditoría §2.5) |
| «El perfil riguroso tarda mucho para lo que es» | El perfil lo decide lo que el plug-in toca, no la prisa. Si parsea formatos ajenos o sale a la red, el espacio de entradas no es nuestro |
| «No hay `import` de esa clase, no la estoy usando» | Un nombre cualificado no genera `import`. Por eso el escáner mira el bytecode y no el fuente (D16) |
| «El build lo corrí yo y pasó, el log da igual» | Sin log, la tabla no puede distinguir esa palabra de un build que falló: sus **filas delegadas** —**ocho** en RIGUROSO, **cuatro** en ESTÁNDAR— certificarían idéntico |

## Red Flags

- Se escribe lógica de negocio antes de que exista un solo caso JUnit.
- Se escribe lógica sin plan de tareas, para una tarea que no figura en el plan, o con más de
  un slice abierto a la vez.
- Se afirma que una clase o método de `com.appiancorp` existe sin haber ejecutado `javap`.
- El `.properties` generado no lleva sufijo de locale.
- Se declara un plug-in terminado sin certificado, o con una puerta marcada como pasada que
  no se ejecutó.
- Se certifica sin haber capturado la salida de `./gradlew build`, o con una capturada antes
  del último cambio del fuente.
- Se excluye `SECSP` para que el build de un servlet pase, antes de haber escrito `ejecutar()`.
- Se copia una regla de la auditoría dentro de la skill en vez de referenciarla.
- Se responde a una duda de API citando la guía local.
- Se reutiliza la clave de un plug-in desplegado tras cambiar sus inputs u outputs.
- Aparece un campo mutable —de instancia o `static`— en una clase de función.
- El dominio importa `com.appiancorp.*`, o un test de dominio necesita el SDK para arrancar.
- Se valida la superficie de API contra `latest` en vez de contra la versión del SDK.
- Se genera un locale nuevo sin comprobar la paridad de claves con `_en_US`.

## Verification

Cuatro capas (spec §5.3), todas mecanizadas por script y reunidas por
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
qué puertas se ejecutan (spec §2.3): las reglas del framework y las políticas de AppMarket
son innegociables en los dos perfiles.

Dos reglas gobiernan la lectura de la tabla y ninguna se negocia: **una puerta que no se
ejecutó nunca se marca como pasada** —ni «pendiente» ni «delegada» son «OK»— y **un verde sobre
un insumo vacío no cuenta como verde**. La mecánica que las hace comprobables —los seis estados
posibles y la regla de `no aplica`, la unidad portante en la que se mide «vacío», qué puerta
ejecuta quién, y por qué la de build reproducible no llega a verde nunca— vive en
`referencias/certificado.md`.

Dos filas van siempre en rojo, y decirlo con todas las letras es la función del certificado,
no un defecto: la resolución OSGi real de la plataforma y la ejecución en Appian real no son
verificables en local (spec §8.2). Un plugin ESTÁNDAR no debe poder pasar por RIGUROSO
leyendo el dossier: la cabecera del certificado declara el perfil, la versión del SDK, la del
índice de tipos con su hash, y la revisión de git.
