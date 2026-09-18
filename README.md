# appian-plugin-forge

Plugin de Claude Code que genera plug-ins de Appian **verificados antes de
desplegarse**: entrevista → contrato → andamiaje determinista → cuatro capas
de verificación → dossier y certificado. Existe porque un plug-in de Appian
no se puede ejecutar antes de entregarlo (el despliegue cuesta un ciclo de
aprobación): todo lo que se afirme sobre él tiene que ser verdad a la
primera.

## Qué genera

| Tipo | Estado |
|---|---|
| Function (y su variante *writer function*) | ✅ Fase 1 |
| Smart Service | ✅ Fase 1 |
| Servlet | ✅ Fase 1 |
| Component / Connected System | ❌ fuera de alcance (cadena de herramientas propia) |

## Requisitos de la máquina

- Python 3.11+ — los scripts usan solo biblioteca estándar (la suite de
  tests, en `tests/`, sí depende de `pytest`).
- JDK 17 — los plug-ins generados compilan con *release* 17.
- Gradle **no** se instala: cada proyecto generado lleva su wrapper
  (8.14.3, con `distributionSha256Sum` fijado).
- **Opcional, y conviene saber qué se pierde sin él:** el servidor MCP
  `appian-docs`. El agente `appian-plugin-forge:appian-docs-researcher` lo
  declara en su `tools`, y este plugin **no lo trae** — ni `.mcp.json` ni
  bloque `mcpServers`. En una máquina sin él, ese agente arranca sin su
  fuente principal y cae a `javap` sobre el JAR del SDK y a `WebFetch`.
  Degrada con dignidad y nada se rompe, pero un requisito que no está escrito
  no se puede cumplir a propósito.

## Instalación

Este plugin no está publicado en ningún marketplace: vive en un checkout
local. Hay dos rutas oficiales para activarlo en Claude Code.

### Antes de cualquiera de las dos rutas

```
claude plugin validate "<ruta-absoluta-a>/appian-plugin-forge"
```

### Ruta 1 — desarrollo e iteración (recomendada mientras el forge cambia)

```
claude --plugin-dir "<ruta-absoluta-a>/appian-plugin-forge"
```

Carga el plugin para esa sesión, sin marketplace ni instalación. Tras
editar cualquier fichero, `/reload-plugins` recoge los cambios sin
reiniciar la sesión.

### Ruta 2 — instalación persistente

Requiere `appian-plugin-forge/.claude-plugin/marketplace.json`, que no
existe en el repositorio — créalo la primera vez con el patrón
autorreferenciado (el propio checkout como marketplace de sí mismo):

```json
{
  "name": "appian-plugin-forge",
  "description": "Marketplace local del plugin appian-plugin-forge, para instalar un checkout del repositorio directamente.",
  "owner": { "name": "Raul Gomez Moya" },
  "plugins": [ { "name": "appian-plugin-forge", "source": "./", "version": "0.1.0" } ]
}
```

Después, dentro de Claude Code:

```
/plugin marketplace add "<ruta-absoluta-a>/appian-plugin-forge"
/plugin install appian-plugin-forge@appian-plugin-forge
```

**`/plugin install` copia la carpeta a caché — no lee en vivo.** Con
`version` fijada en `plugin.json`, `/plugin update` no trae cambios hasta
subir ese número. Mientras el forge esté en iteración activa, usa la
Ruta 1.

## Uso

Pide un plug-in de Appian en lenguaje natural («necesito un smart service
que lea ficheros EML…»); la skill `crear-plugin-appian` se dispara y guía:

1. **Entrevista** — una pregunta por turno hasta congelar el contrato.
2. **Perfil** — ESTÁNDAR por defecto; se propone RIGUROSO si el contrato
   parsea formatos ajenos, sale a la red, toca credenciales o maneja datos
   personales. Lo confirma siempre el usuario.
3. **Andamiaje** — determinista, desde plantillas (`scripts/andamiar.py`).
4. **Verificación** — cuatro capas (`scripts/verificar_todo.py`): reglas del
   framework y AppMarket, compilación + escáner de bytecode contra el índice
   del SDK, tests, empaquetado.
5. **Entrega** — dossier + certificado en `docs/` del proyecto generado.

## Cómo funciona por dentro

`docs/como-funciona.md` es el mapa del plugin, con diagramas: qué hace cada
paso, **quién** lo hace y **con qué**, las cuatro capas de validación, los
seis estados de una puerta del certificado y lo que este sistema **no** puede
comprobar. Es documentación y no una fuente de reglas — las señala en vez de
duplicarlas, porque dos copias divergen: viven en la skill y en
`assets/reglas-de-validacion.md`.

## Cómo leer el certificado

El certificado es un libro mayor, no un binario: qué puertas pasaron con qué
evidencia, cuáles no y por qué. **Dos filas van siempre en rojo** —
resolución OSGi en la plataforma y ejecución en Appian real — porque este
sistema no puede comprobarlas, y decirlo con todas las letras es su función.
Un rojo declarado no es un defecto del plug-in: es el límite honesto de la
verificación local.

## El equipo de runtime

| Agente | Papel |
|---|---|
| `appian-plugin-forge:appian-docs-researcher` | única puerta a la documentación de Appian |
| `appian-plugin-forge:plugin-compiler-fixer` | bucle compilar/corregir |
| `appian-plugin-forge:plugin-contract-reviewer` | ¿el código hace lo que dice el contrato? |

Scripts invocables a mano (desde la raíz del plugin, con `PYTHONUTF8=1`):
`python -m pytest` (suite), `python scripts/skill_lint.py` (lint de la
skill), `python scripts/run_evals.py` (evals de disparo),
`python -m pytest -m e2e tests/test_humo_e2e.py` (humo E2E con build real).

`python scripts/generar_indice_tipos.py` **regenera
`assets/indice-tipos-26.3.json`**, que es contra lo que la capa 2 decide si
una clase de Appian existe. Se ejecuta a mano y rara vez —cuando cambia la
versión del SDK—, y por eso estaba sin documentar: es el único productor de
un insumo del que depende una puerta entera, y sin esta línea había que
descubrirlo leyendo `scripts/`. Si el índice falta, el escáner **no** se
detiene: conmuta a un filtro grueso por paquete y lo declara en el
certificado como modo degradado.

Es reproducible: sobre el mismo SDK devuelve el mismo `hash_sha256` y los
mismos tipos, y lo único que cambia es el campo `fecha`. Así que si se ejecuta
sin que el SDK haya cambiado, el diff resultante es solo esa línea y se
descarta.

## Licencia y procedencia

El forge es **MIT** (`LICENSE`, y el campo `license` del manifiesto; un test los ata).
Los plug-ins que **genera** llevan su propio `LICENSE`, también MIT por defecto y a nombre
del `vendor` del contrato: es un valor por omisión del andamiaje, no una decisión tomada
por quien lo usa, y el `THIRD_PARTY_NOTICES.md` generado lo dice con esas palabras.

**De dónde vienen las plantillas de Gradle.** `assets/plantillas/comun/build.gradle.tmpl` y
`assets/plantillas/perfil-riguroso.gradle.tmpl` **derivan del `build.gradle` del proyecto de
referencia** —el smart service *Read EML*, publicado en el AppMarket—, no de la guía: medido,
el 77 % de sus líneas sustantivas es texto verbatim de aquel fichero y el 72 % solo existe
allí. La cadena de build entera (SpotBugs, JaCoCo, PIT, CycloneDX, *toolchain*, JAR
reproducible) es suya; la guía no la tiene.

Eso importa porque el proyecto de referencia es **Apache-2.0**, y conviene dejar escrito por
qué el derivado puede ser MIT: **el titular del copyright es el mismo** («Copyright 2026
Raul» en aquel `LICENSE`). Apache-2.0 es la concesión que ese proyecto hace a terceros, no
una atadura sobre su autor, así que relicenciar la obra propia es suyo y de nadie más. Si
alguna vez uno de los dos repositorios cambia de manos, esta nota es la que evita tener que
reconstruir esa cadena de memoria.

El `gradle-wrapper.jar` y los dos `gradlew` son redistribuibles de Gradle Inc., idénticos a
los de cualquier proyecto Gradle 8.14.3, y no cuentan como derivación de nada de aquí.

⚠️ **Lo que sigue sin resolver:** `docs/AI Plugin Generator skill Support Guide.md` (repo de
desarrollo; no viaja con el plugin), de la que
viene la *estructura* (patrón de clase, anotaciones, prohibiciones), **no declara licencia ni
autor** — es un prompt de sistema sin atribuir. No afecta a la licencia de este repositorio,
pero antes de publicar el forge conviene saber de quién es.

## Mantenimiento

El forge se valida por hitos con el **gate de ciclo** (`/validar-ciclo`):
equipo de agentes + certificador, informes en `docs/validaciones/` del repo
de desarrollo. Spec: `docs/superpowers/specs/2026-08-09-gate-de-ciclo-design.md`
(repo de desarrollo; no viaja con el plugin).

Reglas de contenido de este README: no promete lo que el sistema no
comprueba, y **enlaza en vez de duplicar** — las reglas viven en la skill,
la auditoría y la spec.
