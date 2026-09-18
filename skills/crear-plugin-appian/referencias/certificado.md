# Cómo se lee el certificado

`${CLAUDE_PLUGIN_ROOT}/scripts/verificar_todo.py` escribe `docs/CERTIFICADO.md` con una fila por
puerta. Aquí está la mecánica de esa tabla: qué significa cada estado, qué mide la columna de
insumo, quién ejecuta cada puerta y por qué dos de las cuatro de RIGUROSO no llegan a verde por
su cuenta. Las reglas concretas, con su fuente y su ID (`R-F*`, `R-A*`, `R-B*`, `R-J*`), viven en
`${CLAUDE_PLUGIN_ROOT}/assets/reglas-de-validacion.md` — no se repiten aquí.

## Los seis estados posibles

`OK` (verde), `NO VERIFICADO` (rojo), `info` (informativa, no bloquea), `delegada` (la ejecuta
otro, y la evidencia dice cuál), `no aplica` (esa capa no rige para este tipo de plugin — un
servlet no carga bundle, y aprobarle la capa 1C sería un verde sobre cero unidades), `pendiente`
(nadie la ejecutó y nadie dijo por qué).

**Regla que no se negocia: una puerta que no se ejecutó nunca se marca como pasada.** Ni
«pendiente» ni «delegada» son «OK», y ninguna de las dos cuenta como verde: si `delegada` colara,
declarar motivos se convertiría en la vía limpia para blanquear una puerta sin ejecutarla.

**`no aplica` se deriva de un hecho declarado en el contrato, nunca de una ausencia de insumo**,
y como cuenta igual que pasado, el orquestador lo comprueba: la marca lleva dentro el par
clave/valor (`plugin.tipo = servlet`), se emite solo vía `contrato.linea_no_aplica`, y un hecho
ausente o que el contrato desmienta pone la puerta en rojo. «No encontré ningún fichero» no es un
hecho: es un insumo vacío con otro nombre.

## La cabecera

Declara **el `STATUS`, el perfil, la versión del SDK, la del índice de tipos con su hash, la
revisión de git y si `./gradlew build` se ejecutó y cómo terminó**. Sin el desenlace del build,
«delegada» no distingue un build fallido de uno correcto; sin el hash y la revisión, dos dossieres
de fechas distintas son indistinguibles.

La revisión de git es además donde deja rastro el criterio de salida del paso 3 —«el destino está
dentro de un repositorio git»—: un proyecto sin repositorio no se calla, sale declarado como tal y
el certificado dice que no queda atado a ningún commit.

## El `STATUS`, y por qué no hay que aplicar el criterio a mano

La cabecera abre con una de estas dos líneas:

```
**STATUS: READY_FOR_APPIAN_SUBMISSION**   ó   **STATUS: NOT_READY**
```

y, cuando dice `NOT_READY`, lista debajo **qué puerta lo impide y por qué**, una línea por motivo.
Es el criterio de salida del paso 5 de la SKILL —sus tres partes— mecanizado en
`verificar_todo.estado_de_sumision`, más las dos reglas de lectura de la tabla que enuncia la
sección `## Verification` de la SKILL; la segunda, la del insumo, es la que añade condición. Las
dos filas estructuralmente rojas no cuentan en contra: si contaran, el estado sería `NOT_READY`
para siempre.

Leer el `STATUS` no exime de mirar la tabla, pero sí invierte la carga: la tabla es el detalle de
un veredicto ya emitido, no trece a diecisiete filas que haya que interpretar para deducirlo.

**El código de salida del script no es el criterio**: una fila que sigue en «delegada» convive con
una salida en 0. Un build fallido, o no aportado, sí sale distinto de 0. Y una raíz que no existe
—o que no es un directorio— sale con **2**, sin escribir certificado ni crear ningún directorio:
ahí no hubo verificación que resumir, y confundirlo con el 1 de «hay filas rojas» haría que un
guion reintentase para siempre sobre una ruta equivocada.

## La salida de `./gradlew build`, que es de donde sale media tabla

El orquestador no invoca Gradle —el build tarda minutos y su toolchain es la del proyecto
generado— pero sí lee lo que Gradle hizo. Hay que capturar su salida en la ruta convenida, que es
donde el orquestador la busca:

```
mkdir -p build && ./gradlew build --console=plain > build/salida-build.log 2>&1
```

El `mkdir` no es adorno: el shell abre la redirección **antes** de lanzar Gradle, así que sobre un
proyecto recién andamiado —donde `build/` todavía no existe— el comando sin él falla («No such
file or directory») y no se construye nada.

**En PowerShell 5.1 ese comando no vale, y no es el único del pipeline que hay que traducir.** Aquí
no hay `&&`, y eso es error de parseo: ruidoso, se ve. El silencioso está en las **otras** líneas
ejecutables que publica la skill —las que invocan
`python "${CLAUDE_PLUGIN_ROOT}/scripts/verificar_todo.py"` y sus hermanas—, porque `${NOMBRE}` es
sintaxis de **variable de PowerShell**, no de variable de entorno: se expande a cadena vacía y no
avisa. Medido en este equipo (Windows 11, PS 5.1) con la variable de entorno **puesta**:
`"${CLAUDE_PLUGIN_ROOT}/scripts/verificar_todo.py"` imprime `/scripts/verificar_todo.py`, y
`"$env:CLAUDE_PLUGIN_ROOT/..."` imprime la ruta real. En PowerShell se escribe
`$env:CLAUDE_PLUGIN_ROOT`. Copiable:

```powershell
New-Item -ItemType Directory -Force build
& cmd /c ".\gradlew.bat build --console=plain > build\salida-build.log 2>&1"
```

La redirección va **dentro de `cmd`** a propósito, y el motivo es de fidelidad, no de veredicto.
Conviene decirlo con precisión porque es la tercera redacción de este párrafo: las dos anteriores
prometían un daño que al medirlo no aparecía. Capturado un fallo real de Gradle de las dos formas
y pasados los dos logs por el lector, **el resultado es el mismo** —`fallido`, con el mismo
motivo—. Hoy no hay ningún veredicto que se pierda por capturar con PowerShell.

Lo que sí se pierde es que el log **sea copia de lo que Gradle escribió**. PowerShell transforma
lo que le llega por stderr de dos maneras, las dos medidas: envuelve la **primera** línea en un
`ErrorRecord` y la escribe prefijada con el nombre del ejecutable, y **refluye todas** las líneas
al ancho de la consola —una de 250 caracteres salió partida en tres—. `cmd` no toca nada.

Hoy no muerde, y conviene saber por qué exactamente, porque las razones fáciles son falsas. El
marcador **no** siempre va por stdout: `BUILD SUCCESSFUL` sí, pero `BUILD FAILED` sale por stderr
y se salva por un accidente —Gradle escribe una línea en blanco antes del bloque `FAILURE:`, y esa
línea se come la decoración—. Y **no** todos los patrones van anclados: el que extrae el motivo
(`Execution failed for task '…'`) se busca sin ancla, y sobrevive por ser corto, no por su
posición. Lo que sí es sólido es que las líneas `> Task :…` viajan por stdout, así que el mapa de
tareas —del que salen cuatro puertas— es inmune a las dos transformaciones.

O sea: el margen existe, pero se apoya en dos accidentes y en una sola propiedad robusta. Un log
que no es copia fiel deja de responder de sí mismo, y esta puerta existe para leer evidencia.

La codificación da resultados distintos según quién mida, así que conviene saberlo antes de
comprobarlo: un PowerShell 5.1 normal escribe **UTF-16LE con BOM** (`FF FE`), pero dentro de una
sesión que traiga `Out-File:Encoding` fijado a `utf8` —Claude Code lo hace— sale **UTF-8 con BOM**
(`EF BB BF`). Las dos las contempla el lector (`salida_build.py` reconoce BOM UTF-8, UTF-16 LE/BE y
UTF-16 sin BOM), y lo que escribe `cmd` —ASCII puro en la práctica— entra por su rama UTF-8, con
la de cp1252 detrás para los bytes que UTF-8 no admita. Si al medirlo sale UTF-8, mírese
`$PSDefaultParameterValues` antes de concluir que la otra rama sobra.

El `--console=plain`, en cambio, no es opcional en ningún shell.

Ojo con lo que el propio certificado imprime cuando el log falta: repite la forma **bash**, que es
la canónica del proyecto. En Windows, traducirla con el bloque de arriba.

Con eso, cada puerta de la capa de build se resuelve con el resultado real: verde si su tarea
pasó, roja si el build falló, y **roja también si la salida no consta, está rancia** —anterior a
cualquiera de sus insumos, que son una lista concreta y no «todo lo que el build lee»: el árbol de
`src/` **entero** (no solo los `.java`: tocar `appian-plugin.xml` o un bundle también cambia el
JAR, porque `build` reejecuta `processResources` y `jar`), `build.gradle`, el `exclude.xml`, los
dos textos legales que acaban en `META-INF` —`LICENSE` y `THIRD_PARTY_NOTICES.md`— y el
`gradle-wrapper.properties`, que fija la versión de Gradle—, **está truncada, o su código de
salida contradice al texto del log**. No poder mirar no es «ya lo miraremos»: el mismo criterio que ya rige para el JAR
ausente. `--salida-build <ruta>` si se capturó en otro sitio; `--codigo-build <n>` para cruzar el
código de salida con el log.

**Ese alcance es también lo único que protege al JAR de estar rancio, y conviene saberlo porque la
capa 4 no lo comprueba.** Las puertas de empaquetado abren el JAR que encuentren en `build/libs` y
miran lo que hay dentro; ninguna compara su fecha con la del fuente. Quien avisa es la capa de
build: corregido un recurso sin reconstruir, el log queda rancio, sus filas salen rojas y el
`STATUS` no llega a `READY_FOR_APPIAN_SUBMISSION`. Por eso el alcance del párrafo anterior no es un
detalle de implementación —es la red que sostiene una capa entera—, y por eso capturar la salida
del build no es opcional aunque «ya se vea que compiló».

## El tamaño del insumo, y la unidad portante

**Cada puerta declara además el TAMAÑO del insumo que analizó**, en su propia columna: cuántas
clases, cuántos tipos, cuántas claves esperadas, cuántas dependencias. Un verde sobre un insumo
vacío queda marcado y **no cuenta como verde** — es una propiedad exigida a toda pieza que pueda
reportar éxito, no una guarda añadida caso por caso, así que cubre también la instancia que nadie
ha encontrado todavía.

**Vacío se mide en la unidad *portante***, no exigiendo que todas sean cero: la forma real del
fallo es **cero en la dimensión que importa, con las demás sanas** —`30 clases, 0 tipos de appian`
es un escáner roto—. La declaran **seis puertas en RIGUROSO y cinco en ESTÁNDAR**, y se ve en su
celda: superficie (`tipos de appian`), bundles (`claves esperadas`), empaquetado
(`entradas del jar`), las dos de bytecode —framework y AppMarket— con `clases`, y la sexta,
property tests (`property tests`), que solo existe en RIGUROSO.

**Donde el cero es legítimo no se inventa una portante** —sería una alarma que salta siempre, y
una alarma que salta siempre enseña a ignorarla— **y tampoco se deja una única unidad anulable**.
Sin portante rige la regla de siempre, «todas las unidades a cero» (`contrato.insumo_vacio`): una
puerta cuya única unidad admita el cero se marcaría a sí misma y bloquearía el `READY` justo
cuando ese cero es la respuesta correcta. Las dos formas que sí existen de no declarar portante:

- **Declarar además el trabajo hecho.** `verificar_licencias.py` emite
  `INSUMO 1 sbom leido, N dependencias`: cero dependencias de terceros es legítimo y frecuente
  —el SDK y log4j son `compileOnly`, los provee el contenedor—, así que `dependencias` no puede
  ser portante; el SBOM leído es la unidad que atestigua que la puerta miró algo real. Que la
  columna de esa puerta hable de dependencias de terceros es el detalle del recuento, no una
  unidad aparte.
- **Unidades secundarias de una puerta que sí declara portante**: `entradas` y `salidas` junto a
  `clases` en las reglas del framework, `dependencias esperadas` junto a `entradas del jar` en el
  empaquetado, `tests` junto a `property tests`.

Ese insumo cubre también lo que trae el build: `> Task :test NO-SOURCE` es un `BUILD SUCCESSFUL`
sobre **cero tests**, y es lo que imprime de verdad un proyecto recién andamiado. La columna lo
marca —`0 tests · AVISO: insumo vacio`— y el `STATUS` sale `NOT_READY` por ello, que es la
respuesta correcta: un andamiaje sin un solo test no está listo para enviarse.

## Quién ejecuta cada puerta

Las puertas comunes a los dos perfiles son **once**; con las dos que nunca son verificables en
local, la tabla sale a **13 filas en ESTÁNDAR y 17 en RIGUROSO** —las cuatro que añade el perfil
van más abajo—. De esas once, este script ejecuta **seis** por invocación directa —las cuatro de
capa 1, la de superficie y la de empaquetado (capa 4, sobre el JAR ya construido)—, resuelve
**cuatro** **leyendo la salida real de `./gradlew build`**, no dándolas por buenas, y la undécima
—«Deriva contra la versión del entorno»— es **informativa**: no la ejecuta nadie, no bloquea, y
declara en su propia fila que es insumo de la Fase 3. La capa 4 solo se puede
correr sobre un JAR: si no hay ninguno en `build/libs`, su puerta sale **roja**, no pendiente — no
poder mirar el artefacto es lo mismo que analizar cero clases, y allí también es rojo.

Que cada puerta traiga su motivo es lo que hace **satisfacible** el criterio de salida del paso 5.
Un criterio de «ninguna puerta en pendiente ni NO VERIFICADO» no lo cumple nadie mientras haya
puertas sin ninguna invocación enganchada: se quedan en «pendiente» para siempre. Ninguna lo está
—o la ejecuta alguien, o declara por qué no puede ejecutarse—, porque un criterio que dice la
verdad vale más que uno que nadie puede cumplir.

## Las cuatro puertas de RIGUROSO

**Tres** de ellas no forman parte de `build` (`jacocoTestCoverageVerification`, `mutationTest`,
`releaseCheck`): si el log no las menciona, nadie las ejecutó, y salen rojas diciendo exactamente
eso.

**La de build reproducible no llega a verde nunca, y es a propósito.** La plantilla lo *configura*
—`preserveFileTimestamps = false`, `reproducibleFileOrder = true`— pero ninguna tarea lo
*comprueba*: verificarlo exige construir dos veces y comparar el hash del JAR, y `releaseCheck` no
lo hace. Así que si nadie ejecutó el perfil, la fila sale **roja** («ese comando no se ejecutó»);
y si se ejecutó, se queda **delegada** diciendo qué es lo que esa tarea no mira. Un verde ahí
sería un verde sobre trabajo que no se hace.

La cuarta —*property tests*/fuzz— **sí** va dentro de `:test`, así que un `./gradlew build`
corriente la ejecuta. Por eso no se mide en tests: se mide en **property tests**, contando las
clases `*FuzzTest`/`*PropertyTest`. Una batería de tests normales sin ninguno de esos da
`0 property tests`, marca el insumo y bloquea el `READY` — salir verde ahí sería un verde sobre
trabajo que no se hizo.

**Y mide un nombre, no el trabajo.** Es fiable como *declaración* —dice en qué unidad se cuenta y
bloquea el `READY` cuando esa unidad es cero— pero se puede satisfacer renombrando una batería
corriente a `SaludoFuzzTest`, y no ve tres cosas: los convenios propios de otras bibliotecas
(jqwik nombra `…Properties`, y ninguna plantilla la declara), los property tests que vivan en su
propio *source set* —se leen los resultados de `:test` y nada más— y las clases anidadas **cuyo
nombre interno no lleve el sufijo** (un `Outer$MiPropertyTest` sí cuenta). Leída así, la fila dice
lo que dice: que existen clases con ese nombre y que sus tests corrieron dentro de `:test`, no que
alguien haya escrito propiedades.
