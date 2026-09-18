# Contrato — Servlet, forma mínima

Un servlet no lleva bundle de recursos: su `name`/`description` se declaran
como atributos en `appian-plugin.xml`, no en un `.properties`
(`assets/reglas-de-validacion.md`, nota de alcance de la capa 1C). Tampoco
lleva `required` ni `paleta`, y la sección `[servlet]` es opcional: sin ella
el `url-pattern` y el nombre del parámetro caen a valores de relleno
deterministas.

Queda así el contrato con menos campos de los cuatro tipos.

```toml
[plugin]
key = "com.raul.appian.estado"
nombre = "Service Status"
version = "1.0.0"
paquete = "com.raul.appian.estado"
tipo = "servlet"
perfil = "estandar"
application_version_min = "23.2"
descripcion = "Exposes the service status as JSON."

[clase]
nombre = "EstadoServlet"

[[entradas]]
nombre = "identificador"
tipo_java = "String"
descripcion = "Query identifier."

[capacidades]
parsea_formatos_ajenos = false
sale_a_la_red = false
toca_credenciales = false
datos_personales = false

[confirmacion]
usuario_confirmo = true
```
