# appian-plugin-forge

Plugin de Claude Code que genera plug-ins de Appian —Function, Writer Function, Smart Service y
Servlet— a partir de una entrevista en castellano, y los verifica en local antes de entregarlos.
Existe porque un plug-in de Appian no se puede ejecutar antes de desplegarlo: Appian exige
aprobación previa y documenta que tarda «within a week». Cada error que no se atrape en local
cuesta un ciclo entero de aprobación, así que todo lo que se afirme sobre el plug-in tiene que ser
verdad a la primera.

Repositorio público: https://github.com/raulogm077/appian-plugin-forge

Este README cubre requisitos, instalación, primer uso y solución de problemas. **Cómo funciona
por dentro lo explica `docs/como-funciona.md`**: qué pasa en cada uno de los siete pasos, quién
lo hace, las cuatro capas de verificación, cómo leer el certificado y lo que el sistema no puede
comprobar. Si vas a generar un plug-in que alguien va a desplegar, léelo una vez entero.

## Para quién es y qué genera

Para quien programa plug-ins de Appian en Java y trabaja con Claude Code. La entrevista y todos
los documentos que se generan están en castellano.

| Si pides… | Genera | Ejemplo |
|---|---|---|
| calcular o transformar algo dentro de una expresión o interfaz | **Function** | validar un IBAN |
| guardar datos desde una pantalla al pulsar un botón | **Writer Function** | registrar una auditoría |
| un paso propio de un modelo de proceso | **Smart Service** | leer un CSV adjunto |
| un endpoint HTTP dentro de Appian para un sistema externo | **Servlet** | calcular un hash |

El tipo no se pregunta: se deduce de lo que describes y se propone con su porqué. Es donde más se
falla, y el error más caro —un smart service donde hacía falta una writer function— no lo detecta
ninguna verificación posterior (`skills/crear-plugin-appian/referencias/tipos-de-plugin.md`).

**Lo que no hace:** Components (React) y Connected Systems, que tienen cadena de herramientas
propia; modificar, auditar o migrar un plug-in que ya existe; desplegar en Appian.

## Requisitos

| Qué | Versión | Por qué |
|---|---|---|
| Claude Code | con soporte de plugins (probado con 2.1.263) | es un plugin: una skill, tres agentes y scripts |
| Python | 3.11 o superior | los scripts usan solo la biblioteca estándar; `pytest` solo para la suite |
| JDK | **17, exactamente** | la plantilla clava el *toolchain* a 17 y no trae resolutor que descargue otro: con solo un JDK 21, Gradle para en «No matching toolchains found» |
| Git | cualquiera | el proyecto generado tiene que ser un repositorio: la skill hace un commit por tarea y el certificado registra la revisión |
| Gradle | no se instala | cada proyecto generado lleva su wrapper (8.14.3, con SHA fijado) |
| Red | la primera vez | el wrapper descarga Gradle de `services.gradle.org` y el build resuelve el SDK de Appian y los plugins de análisis desde Maven Central: unos 230 MB en la caché de Gradle y varios minutos, solo en el primer `./gradlew build` |
| MCP `appian-docs` | opcional | lo usa el agente que consulta la documentación; sin él cae a `javap` sobre el JAR del SDK y a `WebFetch` |

No hace falta Node ni npm. En Windows, los comandos de la skill son de **bash** (Git Bash); la
traducción a PowerShell 5.1, con sus trampas, vive en
`skills/crear-plugin-appian/referencias/entorno-windows.md`.

Está comprobado sobre un clon limpio del repositorio en Windows 11 con solo JDK 17, Python 3.11
y Git for Windows instalados: la suite, el linter, los evals y una build en frío pasan a la
primera, también con espacios y `ñ` en las rutas.

## Instalación

Desde el marketplace del propio repositorio, dentro de Claude Code:

```
/plugin marketplace add raulogm077/appian-plugin-forge
/plugin install appian-plugin-forge@appian-plugin-forge
```

O desde un clon local, sin instalar nada, para una sesión:

```
git clone https://github.com/raulogm077/appian-plugin-forge
claude --plugin-dir "<ruta-absoluta-del-clon>"
```

Esta segunda vía lee el plugin tal como está en disco, así que es la adecuada si vas a tocarlo. Lo
que Claude Code registra con ella —la skill `crear-plugin-appian` y los tres agentes, todos con el
prefijo `appian-plugin-forge:`— se ve con:

```
claude --plugin-dir "<ruta-absoluta-del-clon>" plugin details appian-plugin-forge
claude plugin validate "<ruta-absoluta-del-clon>/.claude-plugin/plugin.json"
```

El manifiesto del plugin se valida con su ruta explícita a propósito: `claude plugin validate`
sobre el directorio valida el `marketplace.json` que hay al lado, no el plugin.

## Primer uso

Pide el plug-in en lenguaje natural. Con algo como «necesito una función que valide un IBAN desde
una regla de expresión», la skill `crear-plugin-appian` se dispara sola y arranca la
**entrevista**: una pregunta por turno, sin opción múltiple, enseñando siempre su hipótesis para
que la corrijas de un plumazo. Un primer turno orientativo:

```
Q: ¿Qué recibe la función y qué devuelve? Por ejemplo: recibe el IBAN como texto y devuelve verdadero o falso.
GUESS: Una Function de lectura —se invoca desde una expresión y no guarda nada— con una entrada `iban` de tipo String y una salida booleana.
CONFIDENCE: ~60%
```

Siguen siete preguntas de admisión: si parsea formatos ajenos, si sale a la red, si toca
credenciales, si maneja datos personales, si usa librerías de terceros, si toca ficheros y si es
una versión nueva de un plug-in ya desplegado. Las cuatro primeras deciden el **perfil** de rigor.
Nada se genera hasta que dices «sí» al **contrato**: un Markdown con un bloque TOML que fija
nombre, clave, paquete, entradas y salidas, y que queda en `docs/contrato.md`.

Después, Claude sigue los siete pasos de la skill sin preguntar más: plan de tareas, andamiaje
determinista con `scripts/andamiar.py`, implementación tarea a tarea con tests primero y un commit
por cada una, verificación con `scripts/verificar_todo.py`, revisión contra el contrato por un
agente que no ha visto la conversación, y dossier. El primer `./gradlew build` descarga Gradle y
las dependencias y tarda varios minutos; los siguientes, segundos. La primera vez que la skill abra
una de sus referencias desde tu proyecto, Claude Code pedirá permiso de lectura sobre la carpeta
del plugin: es normal, acéptalo.

Lo que obtienes es un proyecto Gradle en el directorio que indiques:

```
<proyecto>/
  build.gradle, settings.gradle, gradlew, gradle/wrapper/    # cadena de build, con Gradle fijado
  config/spotbugs/exclude.xml                                # exclusiones de SpotBugs, cada una con su porqué
  src/main/java/<paquete>/<function|smartservice|servlet>/   # el adaptador de Appian
  src/main/java/<paquete>/dominio/                           # tu lógica, sin dependencia del SDK
  src/main/resources/appian-plugin.xml                       # manifiesto, más los bundles _en_US y _es_ES
  src/test/java/                                             # JUnit 5 + Mockito
  docs/contrato.md                                           # lo que acordaste en la entrevista
  docs/decisiones.md                                         # cada decisión que se aparta del andamiaje, con su porqué
  docs/CERTIFICADO.md                                        # qué se verificó, con qué evidencia
  docs/DOSSIER.md                                            # expediente de sumisión: contrato, decisiones, API usada, certificado, firma
  docs/GUIA_INTEGRACION.md                                   # para el desarrollador Appian que lo integra
  docs/FICHA_APPMARKET.md                                    # texto de ficha para el AppMarket
  build/libs/<artefacto>-<versión>.jar                       # lo que se envía a Appian
```

Justo después del andamiaje solo existen la cadena de build, el adaptador, el manifiesto, los
bundles y `docs/contrato.md`; el resto aparece a lo largo del ciclo.

## Cómo leer el certificado

`docs/CERTIFICADO.md` no es un semáforo: es un libro mayor con una fila por puerta —13 en
ESTÁNDAR, 17 en RIGUROSO— que dice qué se ejecutó, sobre cuánto insumo y con qué resultado. Lo
primero es la cabecera: `STATUS: READY_FOR_APPIAN_SUBMISSION` o `STATUS: NOT_READY`, y en el
segundo caso, debajo, qué puerta lo impide y por qué. **Dos filas van siempre en rojo** —resolución
OSGi en la plataforma y ejecución en Appian real— porque no se pueden comprobar en local; no
cuentan contra el `STATUS` y no son un defecto del plug-in, son el límite declarado. Una puerta que
no se ejecutó nunca aparece como pasada, y un verde sobre cero tests o cero clases tampoco cuenta.
Los seis estados y la columna de insumo, en `skills/crear-plugin-appian/referencias/certificado.md`.

## Cómo funciona por dentro

Lo determinista lo hacen scripts de Python y lo que exige juicio lo hace Claude leyendo la skill.
La entrevista produce un contrato; el andamiaje sustituye variables sobre plantillas, sin modelo de
por medio; la verificación son cuatro capas mecanizadas —reglas del framework y políticas de
AppMarket sobre el bytecode, compilación más escáner de la API usada contra el índice del SDK,
tests, y empaquetado del JAR—; y tres agentes cierran lo que un script no puede:
`appian-plugin-forge:appian-docs-researcher` (documentación de Appian: un hecho con su fuente),
`appian-plugin-forge:plugin-compiler-fixer` (bucle compilar/corregir) y
`appian-plugin-forge:plugin-contract-reviewer` (¿el código hace lo que dice el contrato?).

Lo que hay que leer para entenderlo, y en qué orden:

| Si quieres saber… | Está en |
|---|---|
| Qué pasa en cada paso, quién lo hace y con qué; las cuatro capas; los seis estados de una puerta; lo que **no** se puede comprobar | `docs/como-funciona.md` |
| Por qué una regla rechaza algo, con su identificador y su fuente en la documentación de Appian | `assets/reglas-de-validacion.md` |
| Cómo se lee la tabla del certificado y qué significa cada `STATUS` | `skills/crear-plugin-appian/referencias/certificado.md` |
| Cómo se conduce la entrevista y qué campos admite el contrato | `skills/crear-plugin-appian/referencias/entrevista.md` |
| Cómo se deduce el tipo de plug-in a partir de lo que pides | `skills/crear-plugin-appian/referencias/tipos-de-plugin.md` |
| Las trampas de PowerShell y de la codificación en Windows | `skills/crear-plugin-appian/referencias/entorno-windows.md` |
| El único fallo de build esperado, en servlets, y cómo se cierra | `skills/crear-plugin-appian/referencias/secsp-servlet.md` |
| El procedimiento exacto que sigue Claude, paso a paso | `skills/crear-plugin-appian/SKILL.md` |

### Los dos perfiles

**ESTÁNDAR** ejecuta las cuatro capas. **RIGUROSO** añade cobertura JaCoCo, mutación PIT, property
tests y build reproducible. Se propone en la entrevista cuando el plug-in parsea formatos ajenos,
sale a la red, toca credenciales o maneja datos personales, y lo confirmas tú. El perfil no cambia
qué reglas se cumplen, solo cuántas puertas se ejecutan; entre lo que declara el contrato y lo que
se pide al verificar, manda el más estricto.

## Solución de problemas

| Síntoma | Causa | Dónde está la salida |
|---|---|---|
| En PowerShell, `python /scripts/contrato.py` falla con una ruta que nadie escribió | El marcador de la raíz del plugin, `${CLAUDE_PLUGIN_ROOT}`, es sintaxis de variable de PowerShell y se expande a vacío. No es una variable de entorno: se escribe la ruta absoluta del plugin. `&&` tampoco existe en PowerShell 5.1 | `skills/crear-plugin-appian/referencias/entorno-windows.md` |
| El build de un servlet recién andamiado falla en `spotbugsMain` con `SERVLET_PARAMETER` | Es esperado: la exclusión queda abierta hasta que implementes `ejecutar()` y decidas si procede. No se relaja la puerta; se decide y se escribe en `docs/decisiones.md` | `skills/crear-plugin-appian/referencias/secsp-servlet.md` |
| SpotBugs ignora `config/spotbugs/exclude.xml` y el build sigue en verde | El fichero lleva BOM (`Out-File` lo pone por defecto) y SpotBugs descarta el filtro entero. La regla `R-F14` lo detecta | reescribir el fichero sin BOM |
| El primer `./gradlew build` falla | Sin Java dice `JAVA_HOME is not set and no 'java' command could be found`; con un JDK que no es 17, «No matching toolchains found» (la plantilla no descarga otro); sin red no puede bajar Gradle ni el SDK | instalar JDK 17; repetir con red |
| Claude Code pide permiso para leer `skills/crear-plugin-appian/referencias/…` | El plugin vive fuera de tu proyecto y la skill abre sus referencias con `Read` | aceptar; con `claude --plugin-dir` puede añadirse `--add-dir "<ruta-del-clon>"` |
| El certificado dice que la salida del build no consta | `./gradlew clean build` borra `build/`, y el log vive ahí. Primero se limpia, después se captura | `skills/crear-plugin-appian/referencias/certificado.md` |
| En RIGUROSO tres filas dicen «ese comando no se ejecutó» | Cobertura, mutación y `releaseCheck` no forman parte de `build`: se invocan con `./gradlew build releaseCheck` sobre un worktree limpio | `skills/crear-plugin-appian/SKILL.md`, paso 5 |
| El agente investigador no encuentra el MCP `appian-docs` | Es opcional y este plugin no lo trae; el agente cae a `javap` y `WebFetch` | nada que arreglar |

## Limitaciones

- **No despliega ni ejecuta el plug-in.** Quien aprueba es Appian. `READY_FOR_APPIAN_SUBMISSION`
  significa que las puertas ejecutables en local se ejecutaron y pasaron sobre insumos reales, no
  que el envío vaya a aprobarse.
- **Dos filas del certificado van siempre en rojo**, a propósito.
- **Component y Connected System quedan fuera**, igual que editar o migrar un plug-in existente.
- **Que el tipo deducido sea el correcto solo se comprueba en la entrevista**: un tipo equivocado
  compila, pasa sus tests y se empaqueta.
- Algunas reglas son heurísticas declaradas, el juicio sobre licencias es mecánico y no legal, y la
  puerta de property tests cuenta nombres de clase. Está todo escrito en `docs/como-funciona.md`,
  sección 7.

## Contribuir y verificar

Desde la raíz del plugin, con `PYTHONUTF8=1` por delante (sin ello nada falla, pero la salida con
acentos sale deformada en Git Bash):

| Comando | Qué es |
|---|---|
| `python -m pytest` | la suite: unos 690 tests en un par de minutos; en un equipo que no es el del autor, 14 se saltan solos y dicen por qué |
| `python scripts/skill_lint.py` | linter de la skill: frontmatter, secciones obligatorias y citas rotas |
| `python scripts/run_evals.py` | evals de disparo de la skill; sin red ni API |
| `python -m pytest -m e2e tests/test_humo_e2e.py -v -s` | humo de punta a punta: construye un proyecto real con Gradle, tarda minutos y necesita JDK 17 y red |

`scripts/generar_indice_tipos.py` regenera `assets/indice-tipos-26.3.json`, el índice contra el
que la capa 2 decide si una clase del SDK existe; solo se ejecuta cuando cambia la versión del SDK.
Varios tests leen este README y fijan lo que tiene que decir: los nombres de los tres agentes, los
scripts que cita, el enlace al mapa y las órdenes de instalación.

## Licencia y procedencia

El forge es **MIT** (`LICENSE`; un test lo ata al manifiesto). Los plug-ins que genera llevan su
propio `LICENSE`, también MIT por defecto y a nombre del `vendor` del contrato: es un valor por
omisión del andamiaje, y el `THIRD_PARTY_NOTICES.md` generado lo dice. Las plantillas de Gradle
derivan del `build.gradle` de un smart service del mismo autor publicado en el AppMarket bajo
Apache-2.0, y el derivado puede ser MIT porque el titular del copyright es el mismo: Apache-2.0
es la concesión de ese proyecto a terceros, no una atadura sobre su autor. El wrapper de Gradle
es un redistribuible de Gradle Inc. La estructura de las clases generadas sigue una guía de uso
interno que no declara licencia ni autor; queda dicho aquí por transparencia.

Los cambios por versión están en `CHANGELOG.md`. Cada entrada abre con lo que afecta a plug-ins
ya generados, así que conviene leerlo al actualizar.
