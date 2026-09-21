# Trampas de PowerShell en esta skill

Las trampas de PowerShell que afectan a los pasos 1, 4 y 5 de `SKILL.md` —el marcador de la raíz
del plugin, la localización del JAR del SDK y la captura del build—; se abre desde esos pasos
cuando el shell es PowerShell.

Dos trampas distintas, y las dos comparten el mismo patrón: **fallan en silencio**, con un mensaje
que se lee como «la clase/ruta no existe» en vez de «esto es sintaxis de PowerShell, no de bash».

## 1 · El marcador de la raíz del plugin no es una variable de entorno (paso 1 y en general)

`${NOMBRE}` es sintaxis de variable **de PowerShell**: el marcador `CLAUDE_PLUGIN_ROOT` pegado tal
cual en un comando se expande a **cadena vacía sin avisar** — `python /scripts/contrato.py`, que
falla por una ruta que nadie escribió. Y traducirlo a `$env:CLAUDE_PLUGIN_ROOT` **no arregla
nada**: Claude Code no define esa variable de entorno, ni con el plugin cargado. Lo que hace es
**sustituir el marcador por la ruta absoluta del plugin al cargar `SKILL.md`**, así que con el
plugin cargado los comandos de la skill ya llegan con la ruta puesta. Donde el marcador aparezca
literal —trabajando dentro del repo del forge sin cargarlo, o en una referencia como esta abierta
con `Read`— se escribe la ruta absoluta del plugin, entre comillas dobles porque puede llevar
espacios: la misma que muestra `SKILL.md` cargado, o la raíz del checkout. Que
`$env:CLAUDE_PLUGIN_ROOT` parezca funcionar en una sesión es porque alguien la puso **a mano**,
que no es el caso de nadie que instale el plugin.

Esto vale para **todas** las apariciones del marcador en `SKILL.md`, no solo la del paso 1.

⚠️ Y una trampa vecina, del propio PowerShell 5.1: un `.ps1` guardado en UTF-8 **sin BOM** lo lee
como ANSI, así que una ruta con `ñ` o tilde dentro del script llega deformada (`frÃ­o Ã±`) y
`Set-Location` falla con «no se encuentra la ruta». Los `.ps1` con rutas no ASCII se guardan con
BOM, o se pasan las rutas por parámetro.

## 2 · Localizar el JAR del SDK y ejecutar `javap` (paso 4)

`javap` se exige a lo largo de esta skill —encabeza la jerarquía de fuentes (`SKILL.md` § paso
4)— y sin la ruta del JAR la obligación no se puede cumplir. La coordenada es
`com.appian:appian-plug-in-sdk:26.3`, la misma que declara la plantilla de Gradle, y **el JAR
aparece en la caché de Gradle solo después del primer `./gradlew build`** (paso 4). La ruta lleva
un tramo de hash impredecible, así que se busca, no se escribe a mano:

```bash
JAR=$(find ~/.gradle/caches -name "appian-plug-in-sdk-26.3.jar" | head -1)
javap -cp "$JAR" com.appiancorp.suiteapi.process.palette.PaletteInfo
```

⚠️ **Eso es bash. En PowerShell `find` es otro programa y falla dejando `$JAR` VACÍO**, con lo que
el `javap` siguiente se queja de una ruta que nadie escribió — y ese error se lee igual que «la
clase no existe», que es justo el fallo que esta jerarquía de fuentes existe para impedir. En
PowerShell:

```powershell
$JAR = (Get-ChildItem "$env:USERPROFILE\.gradle\caches" -Recurse -Filter "appian-plug-in-sdk-26.3.jar" |
        Select-Object -First 1 -ExpandProperty FullName)
javap -cp "$JAR" com.appiancorp.suiteapi.process.palette.PaletteInfo
```

Comprueba siempre que `$JAR` trae algo antes de fiarte de lo que diga `javap`.

**La versión va clavada en el patrón, y no es un detalle.** Con un comodín
(`appian-plug-in-sdk-*.jar`) el `find`/`Get-ChildItem` engancha también `-sources.jar` y
`-javadoc.jar` —que Gradle baja en cuanto un IDE los pide— y cualquier otra versión que conviva en
la caché. `javap` sobre el artefacto equivocado responde con firmas de otra release, o con «class
not found», **sin ninguna señal de que ha mirado el JAR que no era**: justo la evidencia primaria
de la jerarquía de fuentes convertida en ruido silencioso. El `26.3` es el mismo que declara
`assets/plantillas/comun/build.gradle.tmpl` y el mismo del `indice-tipos-26.3.json`; si algún día
sube, suben los tres a la vez.

## 3 · Capturar la salida de `./gradlew build` (paso 5)

El comando canónico que publica `referencias/certificado.md` es de bash:

```
mkdir -p build && ./gradlew build --console=plain > build/salida-build.log 2>&1
```

**En PowerShell 5.1 ese comando no vale, y no es el único del pipeline que hay que traducir.** Aquí
no hay `&&`, y eso es error de parseo: ruidoso, se ve. El silencioso está en las **otras** líneas
ejecutables que publica la skill —las que invocan
`python "${CLAUDE_PLUGIN_ROOT}/scripts/verificar_todo.py"` y sus hermanas— cuando el marcador
llega literal: `${NOMBRE}` es sintaxis de variable de PowerShell y se expande a cadena vacía sin
avisar (§ 1). La salida es la de § 1: la ruta absoluta del plugin, entre comillas dobles. Copiable:

```powershell
New-Item -ItemType Directory -Force build
& cmd /c ".\gradlew.bat build --console=plain > build\salida-build.log 2>&1"
```

La redirección va **dentro de `cmd`** a propósito, y el motivo es de fidelidad, no de veredicto.
Conviene decirlo con precisión, porque es fácil prometer un daño que no existe: capturado un
fallo real de Gradle de las dos formas y pasados los dos logs por el lector, **el resultado es el
mismo** —`fallido`, con el mismo motivo—. Hoy no hay ningún veredicto que se pierda por capturar
con PowerShell.

Lo que sí se pierde es que el log **sea copia de lo que Gradle escribió**. PowerShell transforma
lo que le llega por stderr de dos maneras: envuelve la **primera** línea en un
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

⚠️ **El BOM que el lector del log sí tolera, SpotBugs no.** Si reescribes
`config/spotbugs/exclude.xml` desde PowerShell, el BOM que `Out-File` mete delante de `<?xml`
hace que SpotBugs **descarte el filtro entero** —*«Unable to read filter … Content is not allowed
in prolog»*— y **siga con `BUILD SUCCESSFUL`**. Tus exclusiones dejan de aplicarse y el build no
lo dice: ves hallazgos que creías excluidos. **No es que SpotBugs esté roto**, y la salida no es
saltarse la puerta con `-x spotbugsMain`: es reescribir el fichero sin BOM. `R-F14` lo detecta y
lo nombra, porque el síntoma lleva al diagnóstico contrario.

Y el pariente peor: **`>` en PowerShell 5.1 escribe UTF-16LE**. Un `contrato.md`, un
`exclude.xml`, un `decisiones.md` o un `.properties` escritos así no son UTF-8, y los scripts lo
dicen con esas palabras («está guardado en UTF-16 … reescríbelo en UTF-8») en vez de morir con
`UnicodeDecodeError`. Para escribir ficheros desde PowerShell, `Out-File -Encoding utf8` —que
pone BOM, tolerable en todo menos en `exclude.xml`— o, mejor, el editor.
