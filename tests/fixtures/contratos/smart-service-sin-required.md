# Contrato — Ejemplo Smart Service

Prosa para el humano: lo que el plug-in hace y por que.

```toml
[plugin]
key = "com.raul.appian.ejemplo"
nombre = "Example"
version = "1.0.0"
paquete = "com.raul.appian.ejemplo"
tipo = "smart-service"
perfil = "estandar"
application_version_min = "23.2"

[clase]
nombre = "EjemploSmartService"
paleta = "Document Management"

[[entradas]]
nombre = "documentoOrigen"
tipo_java = "Long"
descripcion = "Input document"

[[entradas]]
nombre = "sufijo"
tipo_java = "String"
required = "OPTIONAL"
descripcion = "Optional suffix"

[[salidas]]
nombre = "documentoResultado"
tipo_java = "Long"
descripcion = "Generated document"

[capacidades]
parsea_formatos_ajenos = false
sale_a_la_red = false
toca_credenciales = false
datos_personales = false
```
