# Contrato — Ejemplo Smart Service

Lo que lo distingue de `smart-service-minimo.md`: una **segunda entrada
declarada `required = "OPTIONAL"`**. Es la que ejercita la rama del andamiador
que NO emite `requireNonNull` y en su lugar escribe el `if (x == null)` con el
`LOG.debug` del nombre del campo -- la unica rama de `construir_variables` que
la forma minima no toca.

(Aqui hubo primero un marcador de relleno, y luego una prosa que decia que este
fichero llevaba ademas `plugin.descripcion`. Era al reves: quien la lleva es
`smart-service-minimo.md`. Lo cazaron DOS lentes del gate del ciclo 5 por
separado, una como VACUA y otra como [baja], y el ciclo salio NO APTO por ello.
Se deja escrito porque la skill manda leer esta prosa para saber que distingue
a cada fixture: una prosa que miente aqui es peor que ninguna.)

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

[bundle]
nombre = "ejemplo"

[[entradas]]
nombre = "documentoOrigen"
tipo_java = "Long"
required = "ALWAYS"
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

[confirmacion]
usuario_confirmo = true
```
