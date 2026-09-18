# Contrato — Smart service, forma mínima

El único de los cuatro tipos al que la puerta determinista sí exige `required`
en cada entrada y `paleta` en la clase: sin ese dato no compila, y la paleta
decide en qué categoría lo coloca Appian.

Se distingue de `smart-service-completo.md` en que aquí no sobra nada.

```toml
[plugin]
key = "com.raul.appian.archivar"
nombre = "Archive Document"
version = "1.0.0"
paquete = "com.raul.appian.archivar"
tipo = "smart-service"
perfil = "estandar"
application_version_min = "23.2"
descripcion = "Moves a document to the archive folder."

[clase]
nombre = "ArchivarDocumentoSmartService"
paleta = "Document Management"

[bundle]
nombre = "archivarDocumento"

[[entradas]]
nombre = "documentoOrigen"
tipo_java = "Long"
required = "ALWAYS"
descripcion = "Document to archive."

[[salidas]]
nombre = "documentoArchivado"
tipo_java = "Long"
descripcion = "Archived document."

[capacidades]
parsea_formatos_ajenos = false
sale_a_la_red = false
toca_credenciales = false
datos_personales = false

[confirmacion]
usuario_confirmo = true
```
