> **Nota — esto NO es una plantilla ejecutable.** Es una referencia estatica
> de la forma del dossier (spec S8.1) para quien no quiera leer el codigo.
> Vive fuera de `assets/plantillas/` (y sin sufijo `.tmpl`) a proposito: ese
> directorio son los ficheros que `andamiar.py` puede llegar a copiar a un
> proyecto generado, y sus marcadores `{{MARCADOR}}` son los que reconoce
> `sustituir()`. Este fichero usa `<marcador>` porque no es de esa familia
> -- `andamiar.py` no lo mapea y `generar_dossier.render()` no lo lee--, y
> mezclado alli, un `<marcador>` no dispara el chequeo de "marcadores sin
> resolver" si algun dia el mapa de plantillas pasara a un glob (hallazgo de
> revision, tarea 16 ronda 1). El dossier real lo escribe
> `scripts/generar_dossier.py`: las piezas 3 (inventario de API) y 6 (firma
> publica congelada) salen del bytecode y del contrato en cada ejecucion, no
> se escriben a mano ni se copian de aqui.
>
> **El perfil de la cabecera es el RESUELTO**, no el que declara el contrato: se
> lee del `**Perfil:**` del certificado que la pieza 4 empotra, que es el perfil
> con el que se verifico de verdad. Un mismo fichero no puede afirmar dos
> perfiles contrarios sobre el mismo plug-in.
>
> **Como se leen los huecos.** `<a|b|c>` es un conjunto cerrado (el valor real
> es uno de esos, y son los que valida `scripts/contrato.py`); `<cualquier otra
> cosa>` es un valor libre; `[...]` es un tramo que puede no aparecer. No es
> adorno: `tests/test_generar_dossier.py` lee esta cabecera y la pieza 6 como
> patron y las compara con lo que `render()` produce de verdad, que es lo unico
> que impide que esta referencia vuelva a divergir del generador en silencio.

# Dossier — <nombre-del-plugin> <version>

**Tipo:** <function|writer-function|smart-service|servlet> · **Perfil:** <ESTANDAR|RIGUROSO>[ — <por que ese perfil: la nota del certificado, o que no hay certificado y esto es lo que declara el contrato>]
**SDK:** com.appian:appian-plug-in-sdk:26.3 · **Java:** release 17
**application-version min:** <version-minima-declarada>
**Revision independiente:** <`docs/hallazgos-revision.md` con su linea VEREDICTO, o esa misma ruta seguida de «— _no consta_» si la lente de juicio no dejo rastro>

## 1. El contrato

La entrevista congelada. Sin el no se distingue el comportamiento intencionado
del accidental. Vive en `docs/contrato.md`.

## 2. Decisiones y su porque

<contenido integro de `docs/decisiones.md`, o un «_pendiente: no existe
`docs/decisiones.md`_» seguido del recordatorio de estilo ADR --que API se
eligio y contra que alternativa, por que ese manejo de errores-- si ese fichero
todavia no esta>

**No escribir esta seccion dentro del dossier.** `main_con_raiz` reescribe
`docs/DOSSIER.md` ENTERO en cada pasada, asi que lo que se teclee aqui se
pierde en la siguiente: la prosa vive en `docs/decisiones.md` y el dossier solo
la lee.

## 3. Inventario de API de Appian usada

Extraido del *constant pool* de las clases compiladas, en la misma pasada que
alimenta la puerta de superficie: puerta y documentacion no pueden discrepar.

| Tipo | Referenciado desde |
|---|---|
| `com.appiancorp.<paquete>.<Tipo>` | `<ClaseQueLoUsa>` |

Si el proyecto todavia no se ha compilado ni escaneado, esta seccion lo dice
explicitamente ("pendiente: no se ha ejecutado el escaneo de superficie") en
vez de mostrar una tabla vacia sin mas: una tabla vacia sin declarar podria
leerse como "se escaneo y no hay nada", que es una afirmacion distinta y
falsa cuando en realidad no se escaneo nada todavia.

## 4. Certificado de verificacion

<contenido integro de docs/CERTIFICADO.md, o "_pendiente de ejecutar la verificacion_"
si todavia no existe>

## 5. Historial de versiones

- <version> — <que cambio y por que>.

## 6. Firma publica congelada

**No editar a mano.** Es el dato contra el que la Fase 2 comprueba si un cambio
de inputs u outputs obliga a clave nueva. Sobrescribir la clave tras cambiarlos
puede romper procesos vivos en produccion (auditoria S7.4).

### Para pegar en el contrato de la version siguiente

Copiar este bloque, tal cual, dentro del bloque TOML del contrato nuevo. Es lo que
hace comprobable la regla de clave nueva: sin el, `R-F08` no tiene contra que
comparar, y un bloque ausente se lee como «no hay cambio».

```toml
[version_anterior]
key = "<key-del-plugin>"
version = "<version>"

[version_anterior.firma]
clase = "<NombreDeLaClase>"
entradas = ["<nombre>:<TipoJava>"]
salidas = ["<nombre>:<TipoJava>"]
```

### El mismo dato, en JSON

```json
{
  "key": "<key-del-plugin>",
  "version": "<version>",
  "firma": {
    "clase": "<NombreDeLaClase>",
    "entradas": ["<nombre>:<TipoJava>"],
    "salidas": ["<nombre>:<TipoJava>"]
  }
}
```

`key` y `version` van HERMANAS de `firma`, no dentro: `R-F08` lee
`anterior["key"]`, y con la key metida en el objeto firma la comparacion era
`None != key` —siempre falsa— y la regla callaba. `contrato.py` exige ademas que
`version_anterior.firma` sea una tabla, asi que un bloque plano copiado de aqui
producia un contrato que la puerta rechaza.

Formato de cada entrada del array: `nombre:tipo`, no solo el nombre. Es lo
que compara R-F08 en `verificar_framework.py`: un cambio de tipo con el
nombre igual (`doc: Long` a `doc: String`) rompe los procesos vivos exactamente
igual que anadir un input, y solo se detecta si la firma guarda el tipo.
