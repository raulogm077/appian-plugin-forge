# Contrato — Writer function, forma mínima

Igual de pobre que `function-minimo.md`, y por la misma razón. El tipo
`writer-function` comparte manifiesto y bundles con `function` (son
compatibles: una writer function se declara en el XML con el mismo
`<function key=…/>`, solo cambia el tipo de retorno en Java), así que si la
forma mínima rompe, rompe en los dos a la vez.

```toml
[plugin]
key = "com.raul.appian.registrar"
nombre = "Log Note"
version = "1.0.0"
paquete = "com.raul.appian.registrar"
tipo = "writer-function"
perfil = "estandar"
application_version_min = "26.1"
descripcion = "Returns a Writer that logs a note when executed."

[clase]
nombre = "RegistrarNotaFunction"

[bundle]
nombre = "registrarNota"

[[entradas]]
nombre = "texto"
tipo_java = "String"
descripcion = "Text of the note to log."

[capacidades]
parsea_formatos_ajenos = false
sale_a_la_red = false
toca_credenciales = false
datos_personales = false

[confirmacion]
usuario_confirmo = true
```
