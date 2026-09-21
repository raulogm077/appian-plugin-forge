# Contrato — Function con una dependencia de terceros

El ejemplo canónico de `dependencias`: una lista de coordenadas Maven, **clave
de raíz del TOML, en la primera línea del bloque, antes de `[plugin]`**. Escrita
después de cualquier tabla —`[[salidas]]`, `[capacidades]`— TOML la cuelga de
esa tabla en silencio y el andamiador no la ve; `contrato.py` lo rechaza.

De aquí salen el `implementation` de `build.gradle`, la línea de
`THIRD_PARTY_NOTICES.md` (que hay que cerrar a mano con la licencia real) y, vía
el SBOM que genera el build, la capa de licencias (`R-L*`). La dependencia acaba
dentro del JAR en `META-INF/lib`. El ejemplo usa libphonenumber, que es Apache-2.0.

```toml
dependencias = ["com.googlecode.libphonenumber:libphonenumber:9.0.39"]

[plugin]
key = "com.raul.appian.telefono"
nombre = "Telefono E164"
version = "1.0.0"
paquete = "com.raul.appian.telefono"
tipo = "function"
perfil = "estandar"
application_version_min = "26.1"
descripcion = "Normalizes an international phone number to E.164, or empty if invalid."

[clase]
nombre = "TelefonoE164Function"

[bundle]
nombre = "telefono"

[[entradas]]
nombre = "numero"
tipo_java = "String"
descripcion = "Phone number as typed by the user."

[[entradas]]
nombre = "paisPorDefecto"
tipo_java = "String"
descripcion = "ISO 3166-1 alpha-2 region for numbers without prefix."

[[salidas]]
nombre = "normalizado"
tipo_java = "String"
descripcion = "The number in E.164, or empty if it is not valid."

[capacidades]
parsea_formatos_ajenos = false
sale_a_la_red = false
toca_credenciales = false
datos_personales = false

[confirmacion]
usuario_confirmo = true
```
