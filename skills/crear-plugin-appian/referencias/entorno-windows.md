# Trampas de PowerShell en esta skill

Fuente: `SKILL.md` pasos 1 y 4 (repo de desarrollo; no viaja con el plugin). Extraído del cuerpo
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
