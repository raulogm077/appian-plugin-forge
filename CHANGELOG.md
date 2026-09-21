# Cambios

Por fecha, el más reciente arriba. Lo que afecta a plug-ins ya generados va al principio de su
entrada. Los cambios anteriores al 21-sep-2026 no se registraron aquí: están en el historial de
git del repositorio.

## 2026-09-21 · versión 0.2.0 — campaña de portabilidad y pruebas adversarias

Lo que afecta a plug-ins **ya generados**: ninguno cambia de veredicto por las reglas nuevas
salvo que tenga una exclusión de SpotBugs **sin `pattern`** (`category`/`code`), que ahora `R-F14`
rechaza, o le falte alguno de los ficheros que el andamiaje escribe (`LICENSE`,
`THIRD_PARTY_NOTICES.md`, `config/spotbugs/exclude.xml`, `build.gradle`,
`gradle/wrapper/gradle-wrapper.properties`), que ahora deja el certificado `RANCIO`.

- **Instalación desde GitHub**: el repositorio lleva `.claude-plugin/marketplace.json`, así que
  `/plugin marketplace add raulogm077/appian-plugin-forge` + `/plugin install
  appian-plugin-forge@appian-plugin-forge` bastan. Probado además que el plugin **carga de verdad**
  con `--plugin-dir`: skill, tres agentes con prefijo y rutas resueltas.
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
  `CRLF_INJECTION_LOGS` de la plantilla ya firmada: al generalizar `R-F14` el 21-sep, todo smart
  service recién andamiado nacía `NOT_READY` por una exclusión que nadie había escrito. Los
  demás tipos nacen con el fichero y sin exclusiones.
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

Del primer ensayo con una **dependencia de terceros real** (libphonenumber, perfil RIGUROSO,
`READY`):

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

## 2026-09-21 · primera tanda

⚠️ **Si generaste un smart service con una versión anterior a esta, míralo.** La plantilla
horneaba la clave `error.unexpected` en los dos *bundles* y **no la usaba**: cableaba la frase
en castellano, así que en un Appian con locale `en_US` el usuario veía español y el
identificador de correlación no le llegaba. Ya está corregido; en un plug-in ya generado se
arregla añadiendo `.userMessage("error.unexpected", idCorrelacion)` al `SmartServiceException`.

Lo demás de esta tanda, todo en el sentido de «que la puerta no se pueda apagar sin que se note»:

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

El cotejo completo de las políticas de Appian Cloud contra lo que este forge garantiza —con lo
que queda fuera— vive en el repositorio de desarrollo, en
`docs/auditoria-politicas-appmarket-vs-forge.md` (repo de desarrollo; no viaja con el plugin).
