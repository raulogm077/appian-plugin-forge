# Contrato — Function, forma mínima

La forma **mínima** que la puerta determinista acepta para una `function`: sin
`required` (que solo se exige a los smart services), sin `[clase] paleta`, y
**sin sección `[funcion]`**, que es opcional a propósito — el nombre de la
función cae a un valor derivado, y ese valor tiene que ser el mismo para el
andamiador y para el validador de bundles.

No es un ejemplo bonito: es el contrato más pobre que el sistema promete
aceptar. Si el andamiador no lo procesa, la puerta determinista está mintiendo.

```toml
[plugin]
key = "com.raul.appian.saludo"
nombre = "Greeting"
version = "1.0.0"
paquete = "com.raul.appian.saludo"
tipo = "function"
perfil = "estandar"
application_version_min = "26.1"
descripcion = "Returns a greeting composed from a name."

[clase]
nombre = "SaludoFunction"

[bundle]
nombre = "saludo"

[[entradas]]
nombre = "nombre"
tipo_java = "String"
descripcion = "Name to greet."

[[salidas]]
nombre = "saludo"
tipo_java = "String"
descripcion = "Composed greeting."

[capacidades]
parsea_formatos_ajenos = false
sale_a_la_red = false
toca_credenciales = false
datos_personales = false

[confirmacion]
usuario_confirmo = true
```
