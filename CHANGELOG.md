# Cambios

Por versión, la más reciente arriba. Lo que afecta a plug-ins ya generados va al principio de su
entrada.

## 2026-09-21 · versión 0.2.2 — el bundle se llama como la key de su módulo

**Corrige un fallo que impedía desplegar todo plug-in de tipo `function` o `writer-function`
generado hasta aquí.** Appian resuelve el bundle de recursos de cada módulo como
`<key del plug-in>.<key del módulo>`, así que el `.properties` tiene que llamarse como la `key`
del módulo que lo usa. La plantilla del manifiesto de `function` ponía en esa `key` el nombre de
la función, mientras el fichero se llamaba como `[bundle] nombre`. Cada cosa parecía correcta por
separado y ninguna regla cruzaba las dos, de modo que el plug-in pasaba las cuatro capas y Appian
se negaba a cargarlo:

```
Unable To Deploy Plug-in
The Plug-in <key> Module <key del módulo> is missing the following internationalization
bundle(s) for Locale en_US: [<key>.<key del módulo>] (APNX-1-4200-000)
```

Lo que afecta a plug-ins **ya generados**:

- **Los de tipo `function` y `writer-function` cuyo `[funcion] nombre` no coincida con
  `[bundle] nombre` no despliegan**, aunque su certificado diga `READY_FOR_APPIAN_SUBMISSION`. El
  arreglo es de una línea en `src/main/resources/appian-plugin.xml`: poner en `key` el nombre base
  del `.properties`. La función se sigue invocando igual, porque su nombre sale del método Java,
  no de esa `key`. Después, `verificar_todo.py` lo confirma.
- Los `smart-service` y los `servlet` no están afectados: su plantilla ya usaba la misma clave en
  los dos sitios, y los servlets no cargan bundle.
- Un **manifiesto escrito o ampliado a mano** con varios `<function>` o `<smart-service>` necesita
  un bundle por módulo, uno por cada `key`. Eso antes no lo comprobaba nadie, porque el contrato
  describe un solo módulo.

Cambios:

- **`R-B07`, regla nueva** (capa 1C): un bundle `_en_US` por cada módulo declarado en
  `appian-plugin.xml`, llamado como su `key`. Es la única regla de la capa que lee el manifiesto
  en vez del contrato, y por eso ve lo que las demás no pueden: `R-B01` deriva su ruta del mismo
  dato que produce el artefacto, así que sus dos lados coinciden aunque el manifiesto diga otra
  cosa. Corre antes del `return` de `R-B01`, para que un proyecto al que le falten los dos
  bundles se entere de una vez y no de uno cada vez.
- **`R-J06` generalizada** (capa 4): la misma comprobación sobre el JAR ya construido, con la
  lista de módulos leída del `appian-plugin.xml` **que viaja dentro del JAR** — el mismo fichero
  que leerá Appian. Un manifiesto sin ningún módulo tampoco pasa: cero módulos era cero
  comprobaciones.
- **Plantilla de `function`**: `<function key="…">` toma el nombre base del bundle, como ya hacía
  la de `smart-service`.
- `referencias/entrevista.md` explica que la `key` de `<function>` nombra el **módulo** y no la
  función, con el ejemplo de la documentación de Appian: un bundle `twitterFunctions_en_US.properties`
  que sirve a dos funciones, `twittertrends` y `twittersearch`.

## 2026-09-21 · versión 0.2.1 — documentación para quien instala el plugin

Ningún cambio de comportamiento: los scripts, las plantillas y las reglas son los de 0.2.0.

- La documentación que viaja con el plugin —README, `docs/como-funciona.md`, la skill y sus
  referencias, `assets/reglas-de-validacion.md`, los agentes y este fichero— deja de citar
  documentos que no se distribuyen con el plugin, y de contar cómo se construyó. Cada regla de `assets/reglas-de-validacion.md` cita ahora su fuente primaria:
  la documentación de Appian, la página de políticas del AppMarket o el SDK.
- El README enlaza `docs/como-funciona.md` desde el principio y trae una tabla de qué leer para
  cada pregunta; `docs/como-funciona.md` abre con lo que ve quien usa el plugin, paso a paso.
- Dos tests vigilan que eso no vuelva: ninguna cita a documentos que no viajan, y ninguna
  narración de desarrollo (fechas de mediciones, ciclos, ensayos) en la prosa que se distribuye.

## 2026-09-21 · versión 0.2.0 — instalación desde GitHub, contrato más estricto y reglas nuevas

Lo que afecta a plug-ins **ya generados**: ninguno cambia de veredicto por las reglas nuevas
salvo que tenga una exclusión de SpotBugs **sin `pattern`** (`category`/`code`), que ahora `R-F14`
rechaza, o le falte alguno de los ficheros que el andamiaje escribe (`LICENSE`,
`THIRD_PARTY_NOTICES.md`, `config/spotbugs/exclude.xml`, `build.gradle`,
`gradle/wrapper/gradle-wrapper.properties`), que ahora deja el certificado `RANCIO`.

- **Instalación desde GitHub**: el repositorio lleva `.claude-plugin/marketplace.json`, así que
  `/plugin marketplace add raulogm077/appian-plugin-forge` + `/plugin install
  appian-plugin-forge@appian-plugin-forge` bastan. Con `--plugin-dir` carga igual: skill, tres
  agentes con prefijo y rutas resueltas.
- **`${CLAUDE_PLUGIN_ROOT}` no es una variable de entorno**: Claude Code lo sustituye por la ruta
  al cargar la skill. La nota de PowerShell que mandaba traducirlo a `$env:CLAUDE_PLUGIN_ROOT`
  era falsa con el plugin cargado (esa variable está vacía) y se ha corregido en la skill y sus
  referencias: si el marcador aparece literal, se escribe la ruta absoluta del plugin.
- **Comprobación de entorno antes del paso 1** en la skill: JDK 17 exactamente, git, Python 3.11+
  y red la primera vez. Antes se descubría en el paso 4, con el proyecto ya andamiado.
- **`R-F14`** rechaza también un `<Bug>` sin atributo `pattern` (apaga una familia o un detector
  entero sin dejar nombre que firmar).
- **La rancidez ve los borrados**: eliminar un fichero de los que el andamiaje escribe deja
  `RANCIO` el log y el certificado, que antes seguían READY sobre un árbol que Gradle ya no
  podía construir.
- **Los smart services nacen con `docs/decisiones.md`** y con la exclusión de
  `CRLF_INJECTION_LOGS` de la plantilla ya firmada: antes, todo smart service recién andamiado
  nacía `NOT_READY` por una exclusión que nadie había firmado. Los demás tipos nacen con el
  fichero y sin exclusiones.
- **La puerta del contrato** rechaza ahora, con `FALTA` y no con traza: escalares sin comillas
  (`application_version_min = 26`), versiones sin forma de versión (`"abc"`), capacidades
  escritas como cadena (`sale_a_la_red = "no"` contaba como verdadero) y nombres de entradas,
  salidas o función que no son identificadores (`nom bre`, `1x`, `class`).
- **Ficheros en UTF-16** (lo que escribe `>` en PowerShell 5.1) —contrato, `exclude.xml`,
  `decisiones.md`, `.properties`— dan un mensaje que dice qué hacer, no `UnicodeDecodeError`.
- **`verificar_todo.py`** exige la raíz del proyecto (sin argumentos escribía un certificado en
  el directorio actual) y su eco por consola ya no puede morir por la codificación de la consola
  después de haber escrito el certificado correcto.
- Un `.class` truncado se reporta con su nombre de fichero.
- README reescrito para quien llega nuevo; los cambios pasan a este fichero.

Con una **dependencia de terceros** declarada en el contrato:

- **`dependencias` mal colocada es `FALTA`, no silencio**: es clave de raíz del TOML y va antes
  de `[plugin]`; escrita tras una tabla, TOML la colgaba de esa tabla, el contrato daba «OK» y
  `build.gradle` salía sin la librería. Nuevo fixture `function-con-dependencia.md` y fila en
  `entrevista.md`.
- **`R-F15`**: con `dependencyLocking` (RIGUROSO) tiene que existir `gradle.lockfile`; Gradle no lo
  escribe ni lo exige solo. La skill manda generarlo con `./gradlew dependencies --write-locks`
  antes del primer slice. ⚠️ Un proyecto RIGUROSO ya generado **sin lockfile pasa a `NOT_READY`**
  hasta que lo genere y commitee.
- **`R-L03`**: `THIRD_PARTY_NOTICES.md` tiene que nombrar cada dependencia del SBOM y no llevar ya
  el «PENDIENTE DE COMPLETAR» del andamiaje; antes pasaba las cuatro capas sin cerrar.
- Documentada la tercera trampa de los tests en RIGUROSO: PIT y JaCoCo no cuentan igual un
  constructor privado vacío, y el umbral de PIT falla sin decir qué líneas.

## 2026-09-21 · versión 0.1.0

⚠️ **Si generaste un smart service con una versión anterior a esta, míralo.** La plantilla
horneaba la clave `error.unexpected` en los dos *bundles* y **no la usaba**: cableaba la frase
en castellano, así que en un Appian con locale `en_US` el usuario veía español y el
identificador de correlación no le llegaba. Ya está corregido; en un plug-in ya generado se
arregla añadiendo `.userMessage("error.unexpected", idCorrelacion)` al `SmartServiceException`.

Lo demás de esta versión, todo en el sentido de «que la puerta no se pueda apagar sin que se note»:

- **`R-A05`** deja de ser heurística y cubre el *«or any other method»* de la política de Appian:
  además de `System.setProperty`, vigila `Locale.setDefault`, `TimeZone.setDefault`,
  `Security.setProperty`, `System.setProperties` y `clearProperty`. Antes, una clase que solo
  llamara a los dos `setDefault` —que cambian la JVM para **todos** los plug-ins del servidor—
  pasaba las diez reglas de AppMarket con cero hallazgos.
- **`R-F14`** vigila ahora **toda** exclusión activa de `config/spotbugs/exclude.xml`, en los
  cuatro tipos de plug-in y una a una, y marca aparte un `<Match>` sin `<Bug>`, que no excluye un
  patrón sino que apaga SpotBugs entero. Excluir sigue siendo legítimo; hacerlo sin escribir el
  porqué en `docs/decisiones.md`, no.
- La lente de revisión lleva escritas tres exigencias que ningún script puede comprobar: cerrar
  los `Closeable` **siempre**, de quién es el contexto en un servlet, y no exportar datos ni
  saltarse la seguridad de la plataforma.
- El dossier ya no da por ausente un veredicto escrito como `## VEREDICTO: cumple`.

Qué políticas de Appian Cloud se comprueban mecánicamente, cuáles se delegan en la revisión y
cuáles quedan fuera, en `assets/reglas-de-validacion.md`.
