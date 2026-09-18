# La excepción `SECSP` en un servlet recién andamiado

Fuente: `SKILL.md` paso 4 (repo de desarrollo; no viaja con el plugin). Extraído del cuerpo
principal en el cierre del ciclo 19 para bajar `SKILL.md` del tope de tamaño (hallazgo de
`11-skill-reviewer.md:107`).

**La única excepción admitida al `BUILD SUCCESSFUL`, y no es una avería.** Un servlet recién
andamiado **no pasa `./gradlew build`**. FindSecBugs dispara `SERVLET_PARAMETER` (`SECSP`) sobre
`request.getParameter(...)` —todo parámetro de petición es dato controlado por el cliente— y el
andamiaje deja esa exclusión **abierta a propósito**: la plantilla recibe el valor y lo entrega
tal cual, así que no puede afirmar que se trate con seguridad: eso solo lo sabe quien escriba
`ejecutar()`, y afirmarlo en su lugar sería exactamente lo que este sistema existe para impedir.

Qué hacer con él: **implementar la lógica del servlet y decidir entonces, con conocimiento**, si
la exclusión procede —comprobando que el valor no llega a una consulta, a una ruta de fichero ni a
un comando sin validar— y dejar escrito por qué es seguro. El bloque ya viene redactado y
comentado, con el argumento completo, en el `config/spotbugs/exclude.xml` del proyecto generado:
se lee allí, no se copia aquí. Lo que **no** se hace es excluir el detector para que el build pase,
ni relajar `reportLevel` ni `ignoreFailures` en `build.gradle`; y hasta que la decisión se tome, la
puerta de SpotBugs del certificado sale en rojo, que es la verdad.
