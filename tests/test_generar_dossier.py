import json
import pathlib
import re
import tomllib

import pytest

import contrato as c
import generar_dossier as gd

REFERENCIA = pathlib.Path(__file__).resolve().parents[1] / "assets" / "dossier.md"

CONTRATO = {
    "plugin": {"key": "com.raul.appian.ejemplo", "nombre": "Ejemplo", "version": "1.0.0",
               "tipo": "smart-service", "perfil": "estandar", "paquete": "com.raul.appian.ejemplo",
               "application_version_min": "23.2"},
    "clase": {"nombre": "EjemploSmartService"},
    "entradas": [{"nombre": "doc", "tipo_java": "Long", "required": "ALWAYS", "descripcion": "d"}],
    "salidas": [{"nombre": "resultado", "tipo_java": "String", "descripcion": "r"}],
    "capacidades": {},
}


def test_firma_recoge_key_entradas_y_salidas_con_sus_tipos():
    congelada = gd.extraer_firma(CONTRATO)
    # La `key` va HERMANA de `firma`, no dentro: R-F08 lee `anterior["key"]`,
    # y con la key metida en el objeto firma la comparacion era `None != key`
    # —siempre falsa— y la regla callaba. Este test afirmaba la forma rota.
    assert congelada["key"] == "com.raul.appian.ejemplo"
    assert "key" not in congelada["firma"]
    # Con el tipo, no solo el nombre: es lo que compara R-F08 (tarea 6).
    assert congelada["firma"]["entradas"] == ["doc:Long"]
    assert congelada["firma"]["salidas"] == ["resultado:String"]


def test_el_dossier_incluye_el_inventario_de_api():
    md = gd.render(CONTRATO, {"com.appiancorp.suiteapi.content.ContentService": ["com.raul.X"]},
                   "| Puerta | Estado |", gd.extraer_firma(CONTRATO))
    assert "com.appiancorp.suiteapi.content.ContentService" in md


def test_el_dossier_incluye_la_firma_congelada_para_la_fase_2():
    md = gd.render(CONTRATO, {}, "", gd.extraer_firma(CONTRATO))
    assert "Firma publica congelada" in md
    assert '"entradas": [' in md or "entradas" in md


def test_el_dossier_declara_la_version_del_sdk():
    md = gd.render(CONTRATO, {}, "", gd.extraer_firma(CONTRATO))
    assert "26.3" in md


# --- La pieza 2 y la revision: lo que una sesion nueva no podia reconstruir --
# El CONTEXT RECOVERY fallaba en dos de nueve datos, y eran justo los dos que
# no se derivan de ningun artefacto: hay que volver a razonarlos. Peor aun, la
# pieza 2 no era «una seccion que nadie poblaba» sino una que CASTIGABA a quien
# la poblaba: `main_con_raiz` reescribe DOSSIER.md entero en cada pasada.


def test_la_pieza_2_se_lee_de_un_fichero_y_no_se_pisa_al_regenerar(tmp_path):
    import contrato as c

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "contrato.md").write_text(
        (pathlib.Path(__file__).resolve().parent / "fixtures" / "contratos"
         / "smart-service-minimo.md").read_text(encoding="utf-8"), encoding="utf-8")
    escrito_a_mano = "Se eligio ContentService sobre java.io porque AppMarket prohibe el FS."
    (tmp_path / "docs" / "decisiones.md").write_text(escrito_a_mano, encoding="utf-8")

    for pasada in (1, 2):
        assert gd.main_con_raiz(tmp_path) == 0
        md = (tmp_path / "docs" / "DOSSIER.md").read_text(encoding="utf-8")
        assert escrito_a_mano in md, f"pasada {pasada}: el dossier perdio las decisiones"
    assert (tmp_path / "docs" / "decisiones.md").read_text(encoding="utf-8") == escrito_a_mano
    assert c  # el import documenta la dependencia real de main_con_raiz


def test_sin_fichero_de_decisiones_la_pieza_2_lo_dice(tmp_path):
    md = gd.render(CONTRATO, {}, "cert", gd.extraer_firma(CONTRATO), decisiones=None)
    assert "pendiente" in md.lower()
    assert gd.ARCHIVO_DECISIONES in md


def test_el_dossier_distingue_una_revision_que_corrio_de_uNA_que_no():
    """«Revisado y sin hallazgos» y «nadie lo miro» son afirmaciones distintas,
    y el dossier no podia distinguirlas: la unica lente de juicio del pipeline
    no dejaba rastro en ningun fichero."""
    sin = gd.render(CONTRATO, {}, "cert", gd.extraer_firma(CONTRATO))
    assert "no consta" in sin

    con = gd.render(CONTRATO, {}, "cert", gd.extraer_firma(CONTRATO),
                    revision="`docs/hallazgos-revision.md` — VEREDICTO: cumple")
    assert "VEREDICTO: cumple" in con
    assert "no consta" not in con


def test_el_dossier_distingue_no_escaneado_de_escaneado_sin_resultados():
    # None: build/reports/inventario-api.json no existe todavia (nadie ha
    # compilado ni escaneado). {}: el escaneo SI se ejecuto y no encontro
    # ninguna referencia a com.appiancorp.*. Son afirmaciones distintas; el
    # dossier no puede decir "extraido del constant pool" de un escaneo que
    # nunca se ejecuto (es el verde vacuo que este proyecto persigue).
    # certificado_md no vacio a proposito: ese texto tiene su propio
    # "pendiente" (para el certificado que falta) y contaminaria la
    # asercion si se dejara "" como en los demas tests.
    # Se mira SOLO la pieza 3. Buscar «pendiente» en el documento entero era un
    # proxy mas ancho que su intencion: la pieza 2 tiene su propio «pendiente»
    # legitimo cuando no existe docs/decisiones.md, y dos secciones distintas
    # no deben poder romperse la una a la otra.
    def pieza_3(md: str) -> str:
        return md.split("## 3. Inventario")[1].split("## 4.")[0].lower()

    sin_escanear = pieza_3(gd.render(CONTRATO, None, "cert ok", gd.extraer_firma(CONTRATO)))
    escaneado_vacio = pieza_3(gd.render(CONTRATO, {}, "cert ok", gd.extraer_firma(CONTRATO)))
    assert "pendiente" in sin_escanear
    assert "ninguno" not in sin_escanear
    assert "ninguno" in escaneado_vacio
    assert "pendiente" not in escaneado_vacio


def test_el_dossier_publica_el_perfil_CON_EL_QUE_SE_VERIFICO():
    """Un fichero no puede afirmar dos perfiles contrarios sobre el mismo plugin.

    La cabecera leia el perfil del CONTRATO mientras la pieza 4 empotra el
    CERTIFICADO.md, que publica el perfil RESUELTO. En la direccion «subir si»
    —contrato estandar, verificacion en riguroso— el mismo DOSSIER decia
    ESTANDAR arriba y RIGUROSO dentro: exactamente el dano que el ciclo 7 cito
    para justificar la resolucion de perfil, sobreviviendo en la mitad que la
    correccion declaro legitima. Lo levanto el gate del ciclo 8.
    """
    cert = (
        "# Certificado de verificacion\n\n**STATUS: NOT_READY**\n\n"
        "**Perfil:** RIGUROSO — lo pide quien lanzo la verificacion; "
        "el contrato declara ESTANDAR\n"
    )
    md = gd.render(CONTRATO, {}, cert, gd.extraer_firma(CONTRATO))
    cabecera = md.split("\n\n", 2)[1]
    assert "RIGUROSO" in cabecera, (
        f"la cabecera del dossier ignora el perfil con el que se verifico: {cabecera!r}"
    )
    assert "ESTANDAR ·" not in cabecera and "Perfil:** ESTANDAR" not in cabecera, (
        f"el dossier publica dos perfiles contrarios en el mismo fichero: {cabecera!r}"
    )

    # Sin certificado no se calla: se dice que es lo que el contrato declara.
    sin_cert = gd.render(CONTRATO, {}, "", gd.extraer_firma(CONTRATO))
    assert "ESTANDAR — _declarado en el contrato" in sin_cert


# --------------------------------------------------------------------------
# El guardian de `assets/dossier.md`.
#
# Ese fichero es la referencia estatica de la forma del dossier "para quien no
# quiera leer el codigo", y hasta el ciclo 9 NADA lo sujetaba: no lo lee ningun
# script, no lo nombra el README ni la SKILL, y `render()` no lo consulta. Por
# eso divergio tres veces sin que nadie se enterase --la cabecera del perfil, la
# fila de revision independiente que le falta, y un bloque de firma plano que
# `contrato._validar_version_anterior` rechaza si alguien lo copia--. Una
# referencia que miente es peor que ninguna: quien la sigue produce un contrato
# invalido creyendo que va por el camino documentado.
#
# Lo que se ata aqui es la ESTRUCTURA, no el texto: la cabecera entera y la
# forma de la pieza 6. Las piezas 2 a 5 se dejan sueltas a proposito --su
# contenido depende de que ficheros existan en el proyecto y de que dijo el
# certificado, asi que no hay una forma unica que documentar-- y el propio
# fichero declara en su cabecera que no es una plantilla ejecutable.
# --------------------------------------------------------------------------

_OPCIONAL = re.compile(r"\[([^\[\]]*)\]")
_MARCADOR = re.compile(r"<([^<>]+)>")
_TOKEN_DE_ALTERNATIVA = re.compile(r"[A-Za-z-]+")


def _traducir_marcador(cuerpo: str) -> str:
    """`<a|b|c>` es una alternativa cerrada; cualquier otro `<...>`, valor libre.

    La distincion es la que da filo al guardian: con todo traducido a `.+` la
    referencia podria documentar cualquier cosa en el hueco del perfil y seguir
    en verde, que es justo como se colo la divergencia del ciclo 9.
    """
    tokens = cuerpo.split("|")
    if len(tokens) > 1 and all(_TOKEN_DE_ALTERNATIVA.fullmatch(t) for t in tokens):
        return "(?:" + "|".join(re.escape(t) for t in tokens) + ")"
    return ".+"


def _patron_llano(documentado: str) -> str:
    piezas, pos = [], 0
    for m in _MARCADOR.finditer(documentado):
        piezas.append(re.escape(documentado[pos:m.start()]))
        piezas.append(_traducir_marcador(m.group(1)))
        pos = m.end()
    piezas.append(re.escape(documentado[pos:]))
    return "".join(piezas)


def _patron(documentado: str) -> str:
    """La linea documentada, leida como patron que la real tiene que cumplir.

    Mini-lenguaje de la referencia, el mismo que ya usaba, hecho explicito:
    `<a|b|c>` alternativa cerrada, `<lo que sea>` valor libre no vacio, y
    `[...]` un tramo opcional (la nota del perfil solo existe si el certificado
    la trae; `verificar_todo._resolver_perfil` devuelve nota vacia cuando el
    contrato y lo pedido coinciden). Todo lo demas es literal: por eso una fila
    que el generador anada o quite rompe este test.
    """
    piezas, pos = [], 0
    for m in _OPCIONAL.finditer(documentado):
        piezas.append(_patron_llano(documentado[pos:m.start()]))
        piezas.append("(?:" + _patron_llano(m.group(1)) + ")?")
        pos = m.end()
    piezas.append(_patron_llano(documentado[pos:]))
    return "".join(piezas)


def _cabecera(texto: str) -> list[str]:
    """Titulo y filas de campo: de `# Dossier` al primer blanco que las cierra."""
    lineas = texto.splitlines()
    i = next(n for n, l in enumerate(lineas) if l.startswith("# Dossier"))
    bloque, n = [lineas[i]], i + 1
    while n < len(lineas) and not lineas[n].strip():
        n += 1
    while n < len(lineas) and lineas[n].strip():
        bloque.append(lineas[n])
        n += 1
    return bloque


def _bloque_cercado(texto: str, lenguaje: str) -> str:
    """Se queda SOLO para el JSON, que no tiene contraparte en `contrato.py`.

    El lado TOML lo hace `contrato.extraer_toml`, que es quien lee de verdad
    los contratos: reimplementarlo aqui hacia que la referencia se juzgara con
    un lector distinto del que la va a leer cuando alguien la pegue.
    """
    m = re.search(rf"^```{lenguaje}\n(.*?)^```", texto, re.S | re.M)
    assert m, f"la referencia no trae ningun bloque ```{lenguaje}"
    return m.group(1)


def _forma(valor):
    """La estructura de claves, sin los valores: es lo unico comparable entre
    una referencia con marcadores y una firma real."""
    if isinstance(valor, dict):
        return {k: _forma(v) for k, v in sorted(valor.items())}
    if isinstance(valor, list):
        return ["*"]
    return "*"


_CERT_CON_NOTA = (
    "# Certificado de verificacion\n\n**STATUS: NOT_READY**\n\n"
    "**Perfil:** RIGUROSO — lo pide quien lanzo la verificacion; "
    "el contrato declara ESTANDAR\n"
)
_CERT_SIN_NOTA = "# Certificado de verificacion\n\n**Perfil:** ESTANDAR\n"


def test_la_referencia_estatica_documenta_la_cabecera_QUE_EL_GENERADOR_EMITE():
    """Cada fila que `render()` escribe, documentada; ninguna de mas ni de menos.

    Se prueban las tres ramas que el pipeline produce de verdad: certificado con
    nota de perfil, certificado sin nota, y sin certificado. Si la referencia
    solo cubriera una, seguiria mintiendo en las otras dos.
    """
    documentada = _cabecera(REFERENCIA.read_text(encoding="utf-8"))
    casos = {
        "certificado con nota de perfil": gd.render(
            CONTRATO, {}, _CERT_CON_NOTA, gd.extraer_firma(CONTRATO),
            revision="`docs/hallazgos-revision.md` — VEREDICTO: cumple"),
        "certificado sin nota de perfil": gd.render(
            CONTRATO, {}, _CERT_SIN_NOTA, gd.extraer_firma(CONTRATO)),
        "sin certificado": gd.render(CONTRATO, {}, "", gd.extraer_firma(CONTRATO)),
    }
    for nombre, md in casos.items():
        real = _cabecera(md)
        assert len(real) == len(documentada), (
            f"[{nombre}] la cabecera real tiene {len(real)} filas y la referencia "
            f"documenta {len(documentada)}:\n  real: {real}\n  doc : {documentada}"
        )
        for fila_real, fila_doc in zip(real, documentada):
            assert re.fullmatch(_patron(fila_doc), fila_real), (
                f"[{nombre}] `assets/dossier.md` documenta una fila que el "
                f"generador ya no emite:\n  real: {fila_real!r}\n  doc : {fila_doc!r}"
            )


def test_los_campos_cerrados_de_la_referencia_son_los_que_ADMITE_EL_CONTRATO():
    """Anti-vacuidad: sin esto bastaria ensanchar un hueco a `<lo que sea>`.

    Los conjuntos se toman de `contrato.py`, que es quien los valida, no de la
    referencia ni del generador: un tercero al que ninguno de los dos lados de
    la costura puede mover para ponerse en verde.
    """
    cabecera = "\n".join(_cabecera(REFERENCIA.read_text(encoding="utf-8")))

    def documentadas(etiqueta: str) -> set:
        m = re.search(re.escape(f"**{etiqueta}:**") + r" <([^<>]+)>", cabecera)
        assert m, f"la referencia no documenta un conjunto cerrado para {etiqueta}"
        return set(m.group(1).split("|"))

    assert documentadas("Tipo") == c.TIPOS_VALIDOS
    assert documentadas("Perfil") == {p.upper() for p in c.PERFILES}


def test_la_referencia_nombra_LOS_FICHEROS_DE_PROSA_QUE_EL_DOSSIER_LEE():
    """Las dos piezas que el dossier LEE de fuera se nombran por su ruta real.

    La referencia presentaba la pieza 2 como un hueco de prosa para rellenar en
    el propio dossier. Es el consejo que `main_con_raiz` castiga: reescribe
    `docs/DOSSIER.md` entero en cada pasada, asi que lo tecleado ahi se pierde
    en la siguiente. Las rutas se toman de las constantes del generador, no se
    reescriben aqui: si `ARCHIVO_DECISIONES` o `ARCHIVO_REVISION` se mueven, la
    referencia deja de estar en verde hasta que los siga.
    """
    texto = REFERENCIA.read_text(encoding="utf-8")
    for constante in (gd.ARCHIVO_DECISIONES, gd.ARCHIVO_REVISION):
        assert constante in texto, (
            f"`assets/dossier.md` no nombra `{constante}`, que es de donde el "
            f"dossier saca esa pieza; quien siga la referencia escribira la prosa "
            f"dentro del DOSSIER.md y la perdera en la siguiente pasada"
        )


def test_la_referencia_congela_la_firma_CON_LA_FORMA_QUE_LEE_R_F08():
    """El bloque JSON de la pieza 6, con la forma que produce `extraer_firma`.

    Importa porque no es decorativo: quien copie un bloque plano --`clase`,
    `entradas` y `salidas` al mismo nivel que `key`-- para poblar
    `[version_anterior]` produce un contrato que `contrato.py` rechaza, y R-F08
    se queda sin nada contra que comparar. Hallazgo [media] del ciclo 1.
    """
    documentada = json.loads(_bloque_cercado(REFERENCIA.read_text(encoding="utf-8"), "json"))
    real = gd.extraer_firma(CONTRATO)
    assert _forma(documentada) == _forma(real)
    # El formato «nombre:tipo» es lo que hace detectable un cambio de tipo con
    # el nombre igual; una referencia que documentara solo el nombre ensenaria
    # a congelar una firma ciega a esa mitad.
    for lista in ("entradas", "salidas"):
        assert documentada["firma"][lista][0].count(":") == real["firma"][lista][0].count(":") == 1


def test_la_referencia_trae_EL_BLOQUE_TOML_PARA_PEGAR_en_el_contrato_siguiente():
    """El JSON no se puede pegar en un contrato, que es TOML.

    `toml_de_version_anterior` existe precisamente porque la firma solo
    congelada en JSON era la otra mitad de por que nadie poblaba nunca
    `[version_anterior]`. Una referencia que omite ese bloque manda al lector de
    vuelta al mismo callejon.

    Los dos lados SE PARSEAN, no se trocean por `=`. La version anterior tenia
    su propio lector de TOML de siete lineas (`_claves_toml`) que partia cada
    linea por el primer `=` sin parsear nada, asi que este guardian se quedaba
    en verde con un bloque que NO SE PUEDE PEGAR: medido quitando las comillas
    a `key = "<key-del-plugin>"` en `assets/dossier.md`, con
    `_claves_toml(roto) == _claves_toml(bueno)` en `True` y `tomllib` diciendo
    `TOMLDecodeError - Invalid value (at line 2, column 7)`.

    El lado documentado se lee con `contrato.extraer_toml`, que es la puerta
    por la que entra un contrato de verdad --y que normaliza CRLF a proposito,
    porque el repositorio esta en Windows y git convierte al hacer checkout;
    su comentario dice "comprobado, no supuesto"--. El lado real es una cadena
    TOML suelta, sin vallas, asi que va directo a `tomllib.loads`.

    Se compara con `_forma`, el mismo criterio que el bloque JSON: la
    ESTRUCTURA de claves, no los valores, que en la referencia son marcadores.
    Se pierde a sabiendas la comprobacion de ORDEN que hacia `_claves_toml`:
    en TOML el orden de las claves no cambia lo que se lee, y a cambio se gana
    que el bloque tenga que parsear.
    """
    documentada = c.extraer_toml(REFERENCIA.read_text(encoding="utf-8"))
    real = tomllib.loads(gd.toml_de_version_anterior(gd.extraer_firma(CONTRATO)))
    assert _forma(documentada) == _forma(real)


# --- El certificado RANCIO, que el propio Proceso fabrica -------------------
# Lo ausente se declaraba y lo rancio no se veia. El paso 6 de la SKILL manda
# corregir el codigo tras la lente de juicio, ningun paso obliga a volver al 5,
# y el 7 empotra `docs/CERTIFICADO.md` tal cual: un dossier podia afirmar
# READY_FOR_APPIAN_SUBMISSION describiendo el arbol de ANTES de la correccion.
# Levantado por el gate del ciclo 13.


# Los TRES fuentes que el andamiador escribe y que alguna puerta lee, no solo
# el `.java`. El fixture del ciclo 14 escribia unicamente el Java, o sea la
# unica forma donde la nocion estrecha de rancidez SI funcionaba: por eso la
# suite entera daba verde sobre un agujero. Levantado por el gate del ciclo 14.
FUENTES_DEL_PROYECTO = {
    "java": "src/main/java/Ejemplo.java",
    "manifiesto": "src/main/resources/appian-plugin.xml",
    "bundle": "src/main/resources/com/raul/appian/ejemplo/bundle_en_US.properties",
    # El contrato no lo lee el build, pero SI tres puertas y el propio dossier,
    # que de el extrae la firma congelada. Un contrato editado despues de
    # certificar deja el certificado describiendo otra cosa. Cuarta clase de
    # insumo, anadida por el gate del ciclo 15.
    "contrato": "docs/contrato.md",
}


def _proyecto_certificado(raiz: pathlib.Path, cert: str) -> dict[str, pathlib.Path]:
    """Proyecto minimo con las cuatro clases de insumo y un certificado."""
    (raiz / "docs").mkdir(parents=True, exist_ok=True)
    (raiz / "docs" / "contrato.md").write_text(
        (pathlib.Path(__file__).resolve().parent / "fixtures" / "contratos"
         / "smart-service-minimo.md").read_text(encoding="utf-8"), encoding="utf-8")
    escritos = {}
    for clave, relativa in FUENTES_DEL_PROYECTO.items():
        ruta = raiz / relativa
        ruta.parent.mkdir(parents=True, exist_ok=True)
        if not ruta.exists():
            ruta.write_text("contenido\n", encoding="utf-8")
        escritos[clave] = ruta
    (raiz / "docs" / "CERTIFICADO.md").write_text(cert, encoding="utf-8")
    return escritos


def _fechar(cert: pathlib.Path, fuentes: dict, posterior: str | None) -> None:
    """Certificado en medio; `posterior` es la unica fuente mas nueva que el."""
    import os

    for ruta in fuentes.values():
        os.utime(ruta, (999_000, 999_000))
    os.utime(cert, (1_000_000, 1_000_000))
    if posterior is not None:
        os.utime(fuentes[posterior], (1_003_600, 1_003_600))


CERT_VERDE = "# Certificado de verificacion\n\n**STATUS: READY_FOR_APPIAN_SUBMISSION**\n"


@pytest.mark.parametrize("tocada", sorted(FUENTES_DEL_PROYECTO))
def test_un_certificado_ANTERIOR_a_la_ultima_correccion_viaja_declarado_RANCIO(tocada, tmp_path):
    """El caso con dientes, por CADA clase de fuente que una puerta lee.

    Parametrizado a proposito: con un solo `.java` este test pasaba mientras el
    manifiesto y los bundles se colaban sin aviso, que es el agujero que el gate
    del ciclo 14 encontro. El `.java` es el caso facil; los otros dos son los
    que llevan los dos errores que la guia documenta como bloqueantes de
    despliegue, o sea la correccion tipica del paso 6.
    """
    fuentes = _proyecto_certificado(tmp_path, CERT_VERDE)
    cert = tmp_path / "docs" / "CERTIFICADO.md"
    _fechar(cert, fuentes, posterior=tocada)

    assert gd.main_con_raiz(tmp_path) == 0
    md = (tmp_path / "docs" / "DOSSIER.md").read_text(encoding="utf-8")
    assert "RANCIO" in md, (
        f"se toco `{FUENTES_DEL_PROYECTO[tocada]}` DESPUES de certificar y el dossier lo "
        f"empotro sin decirlo: afirma un veredicto sobre un arbol que ya no se entrega"
    )
    assert fuentes[tocada].name in md, (
        f"el aviso de rancidez no nombra `{fuentes[tocada].name}`, que es el fichero que "
        f"lo provoca, asi que el lector no sabe que cambio despues"
    )
    # El certificado sigue viajando entero: se declara, no se oculta.
    assert "READY_FOR_APPIAN_SUBMISSION" in md


def test_un_certificado_POSTERIOR_A_TODAS_las_fuentes_viaja_SIN_aviso(tmp_path):
    """La otra direccion, sin la cual los de arriba pasarian con un aviso
    escrito siempre. Mismo proyecto, ninguna fuente posterior al certificado."""
    fuentes = _proyecto_certificado(tmp_path, CERT_VERDE)
    cert = tmp_path / "docs" / "CERTIFICADO.md"
    _fechar(cert, fuentes, posterior=None)

    assert gd.main_con_raiz(tmp_path) == 0
    md = (tmp_path / "docs" / "DOSSIER.md").read_text(encoding="utf-8")
    assert "RANCIO" not in md, (
        "el dossier marca como rancio un certificado posterior a todas sus fuentes: una "
        "alarma que salta siempre ensena a ignorarla"
    )
