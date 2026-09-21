# Trampas de PowerShell en esta skill

Fuente: `SKILL.md` pasos 1 y 4. Extraído del cuerpo
principal en el cierre del ciclo 19 para bajar `SKILL.md` del tope de tamaño (hallazgo de
`11-skill-reviewer.md:107`).

Dos trampas distintas, y las dos comparten el mismo patrón: **fallan en silencio**, con un mensaje
que se lee como «la clase/ruta no existe» en vez de «esto es sintaxis de PowerShell, no de bash».

## 1 · `${CLAUDE_PLUGIN_ROOT}` no se expande en PowerShell (paso 1 y en general)

`${NOMBRE}` es sintaxis de variable **de PowerShell**, no de variable de entorno: se expande a
**cadena vacía sin avisar** — `python /scripts/contrato.py`, que falla por una ruta que nadie
escribió. Se escribe `$env:CLAUDE_PLUGIN_ROOT`. Y si la variable no está puesta en el entorno,
resolverla a mano a la raíz del checkout del plugin antes de seguir: vacía, `$env:` falla igual de
callado.

Esta traducción aplica a **todas** las `${CLAUDE_PLUGIN_ROOT}` de `SKILL.md`, no solo a la del
paso 1.

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
`python "${CLAUDE_PLUGIN_ROOT}/scripts/verificar_todo.py"` y sus hermanas—, porque `${NOMBRE}` es
sintaxis de variable de PowerShell, no de variable de entorno (ver § 1 arriba): se expande a cadena
vacía y no avisa. Medido en este equipo (Windows 11, PS 5.1) con la variable de entorno **puesta**:
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

⚠️ **El BOM que el lector del log sí tolera, SpotBugs no.** Si reescribes
`config/spotbugs/exclude.xml` desde PowerShell, el BOM que `Out-File` mete delante de `<?xml`
hace que SpotBugs **descarte el filtro entero** —*«Unable to read filter … Content is not allowed
in prolog»*— y **siga con `BUILD SUCCESSFUL`**. Tus exclusiones dejan de aplicarse y el build no
lo dice: ves hallazgos que creías excluidos. **No es que SpotBugs esté roto**, y la salida no es
saltarse la puerta con `-x spotbugsMain`: es reescribir el fichero sin BOM. `R-F14` lo detecta y
lo nombra, porque el síntoma lleva al diagnóstico contrario — pasó en una prueba E2E real del
21-sep-2026.
