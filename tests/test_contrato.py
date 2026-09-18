import pathlib
import re

import pytest

import contrato

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "contratos"
RAIZ_SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"


def test_carga_contrato_completo():
    datos = contrato.cargar(FIXTURES / "smart-service-completo.md")
    assert datos["plugin"]["key"] == "com.raul.appian.ejemplo"
    assert datos["plugin"]["tipo"] == "smart-service"
    assert len(datos["entradas"]) == 2
    assert datos["entradas"][0]["nombre"] == "documentoOrigen"


def test_contrato_completo_no_tiene_faltantes():
    datos = contrato.cargar(FIXTURES / "smart-service-completo.md")
    assert contrato.validar(datos) == []


def test_input_sin_required_es_campo_faltante():
    datos = contrato.cargar(FIXTURES / "smart-service-sin-required.md")
    faltantes = contrato.validar(datos)
    assert any("required" in f for f in faltantes)


def test_perfil_se_deduce_riguroso_si_parsea_formatos_ajenos():
    assert contrato.perfil_propuesto({"parsea_formatos_ajenos": True}) == "riguroso"
    assert contrato.perfil_propuesto({"toca_ficheros": True}) == "estandar"


def test_texto_sin_bloque_toml_da_error():
    try:
        contrato.extraer_toml("# Solo markdown, sin bloque")
    except ValueError as e:
        assert "toml" in str(e).lower()
    else:
        raise AssertionError("deberia haber lanzado ValueError")


# --- Identificadores bien formados, no solo presentes ----------------------
# `paquete`, `key` y `clase.nombre` viajan al `.java`, al manifiesto y a la
# RUTA de los ficheros generados (`paquete` se convierte en directorios, `key`
# en la ruta del bundle). Un espacio, un guion o una palabra reservada
# producen un proyecto que NO COMPILA, y sin esta comprobacion el fallo no
# aparecia en la puerta determinista --instantanea-- sino dentro de
# `./gradlew build`, minutos despues y con un error del compilador que no
# menciona el contrato. La puerta existe precisamente para que eso no pase.


@pytest.mark.parametrize("valor", [
    "com.raul.appian.ejemplo", "com.raul.appian.emailfilereader", "a.b.c", "com.raul_2.appian",
])
def test_paquetes_validos_pasan(valor):
    assert contrato._error_de_identificador(valor, cualificado=True) is None


@pytest.mark.parametrize("valor,razon", [
    ("com.raul appian.x", "espacio"),
    ("com.raul-appian.x", "guion"),
    ("com..raul", "segmento vacio"),
    ("com.raul.", "punto final"),
    ("2com.raul", "empieza por digito"),
    ("com.new.raul", "palabra reservada"),
    ("com.class.raul", "palabra reservada"),
    ("../../../evil", "traversal"),
    ("com.raul$inner", "dolar: lo reservan las clases internas y el escaner lo normaliza"),
])
def test_paquetes_invalidos_se_rechazan(valor, razon):
    assert contrato._error_de_identificador(valor, cualificado=True) is not None, razon


@pytest.mark.parametrize("valor", ["EjemploSmartService", "Clase_2", "_x"])
def test_nombres_de_clase_validos_pasan(valor):
    assert contrato._error_de_identificador(valor, cualificado=False) is None


@pytest.mark.parametrize("valor", ["Mi Clase", "Clase-2", "int", "com.raul.Clase", "2Clase"])
def test_nombres_de_clase_invalidos_se_rechazan(valor):
    assert contrato._error_de_identificador(valor, cualificado=False) is not None


def test_la_puerta_rechaza_un_paquete_que_no_compilaria():
    datos = contrato.cargar(FIXTURES / "smart-service-minimo.md")
    assert contrato.validar(datos) == [], "el fixture de partida deberia estar limpio"
    datos["plugin"]["paquete"] = "com.raul appian.ejemplo"
    fallos = contrato.validar(datos)
    assert any("plugin.paquete" in f for f in fallos), fallos


def test_falta_confirmacion_bloquea_la_puerta():
    """La puerta de confianza de la entrevista (spec de Fase 1 §6.2) exige un «si»
    explicito antes de generar nada, pero hasta ahora ningun script lo comprobaba:
    `andamiar.py` se paraba solo con un contrato mal formado, nunca con uno que
    nadie confirmo. Mecanismo nuevo: spec 2026-09-18, capacidad B.
    """
    datos = contrato.cargar(FIXTURES / "smart-service-completo.md")
    datos.pop("confirmacion", None)  # por si el fixture ya lo trae en este punto del plan
    faltantes = contrato.validar(datos)
    assert any("confirmacion.usuario_confirmo" in f for f in faltantes), faltantes


def test_confirmacion_false_bloquea_la_puerta():
    datos = contrato.cargar(FIXTURES / "smart-service-completo.md")
    datos["confirmacion"] = {"usuario_confirmo": False}
    faltantes = contrato.validar(datos)
    assert any("confirmacion.usuario_confirmo" in f for f in faltantes), faltantes


def test_confirmacion_con_forma_invalida_no_revienta():
    """Confundir la seccion con un campo (`confirmacion = "si"`) pasa por
    `contrato.seccion()` (linea 70) y se lee como vacio: la puerta lo rechaza con
    su propia FALTA, no con un AttributeError.
    """
    datos = contrato.cargar(FIXTURES / "smart-service-completo.md")
    datos["confirmacion"] = "si"
    faltantes = contrato.validar(datos)
    assert any("confirmacion.usuario_confirmo" in f for f in faltantes), faltantes


def test_confirmacion_true_no_bloquea():
    datos = contrato.cargar(FIXTURES / "smart-service-completo.md")
    datos["confirmacion"] = {"usuario_confirmo": True}
    assert not any("confirmacion" in f for f in contrato.validar(datos))


def test_la_puerta_rechaza_una_clase_con_palabra_reservada():
    datos = contrato.cargar(FIXTURES / "smart-service-minimo.md")
    datos["clase"]["nombre"] = "int"
    fallos = contrato.validar(datos)
    assert any("clase.nombre" in f and "reservada" in f for f in fallos), fallos


def test_la_puerta_rechaza_una_key_con_traversal():
    """`key` se convierte en la RUTA del bundle: `key.replace('.', '/')`."""
    datos = contrato.cargar(FIXTURES / "smart-service-minimo.md")
    datos["plugin"]["key"] = "../../../evil"
    fallos = contrato.validar(datos)
    assert any("plugin.key" in f for f in fallos), fallos


def test_los_siete_fixtures_del_corpus_siguen_pasando_la_puerta():
    """La regla nueva RECHAZA cosas que antes pasaban: eso es lo que busca.
    Pero no puede rechazar el corpus con el que el sistema promete funcionar,
    y el del EML es un plug-in aprobado por Appian de verdad.
    """
    for fixture in sorted(FIXTURES.glob("*.md")):
        datos = contrato.cargar(fixture)
        fallos = [f for f in contrato.validar(datos) if "no es " in f or "reservada" in f]
        assert fallos == [], f"{fixture.name}: {fallos}"


def test_contrato_con_finales_de_linea_crlf():
    # El repositorio esta en Windows y git convierte a CRLF al hacer checkout:
    # sin normalizar, el \r final antes de la valla de cierre rompe tomllib.
    texto = FIXTURES.joinpath("smart-service-completo.md").read_text(encoding="utf-8")
    crlf = texto.replace("\r\n", "\n").replace("\n", "\r\n")
    datos = contrato.extraer_toml(crlf)
    assert datos["plugin"]["key"] == "com.raul.appian.ejemplo"


# --- La paleta: dos gates y dos lecciones --------------------------------
#
# Ciclo 3: `entrevista.md` decia «solo cuatro valores validos (R-F01)» citando
# CATEGORIAS. Se arreglo publicando una lista de once... copiada del mapa que ya
# vivia en `andamiar.py`.
#
# Ciclo 4: esa lista era la equivocada. `javap -v` sobre el SDK 26.3 dice que
# `Workflow` es la CATEGORIA de las cuatro `Workflow*` y que la subpaleta de
# `WorkflowActivities` se llama `Activities`; y que faltaban cinco subpaletas
# reales. O sea: la puerta aceptaba lo que no existe (`Workflow`, que aterrizaba
# en `Activities` sin decirlo) y rechazaba lo que si (`Activities`, `Human
# Tasks`, `Robotic Processes`, `Test Management`, `Social`, `Analytics`).
#
# La leccion de metodo, que es la que estos tests tienen que proteger: un mapa
# del propio repositorio es fuente de SEGUNDA mano. Para un nombre admitido,
# `javap` o la documentacion.

def _smart_service(paleta):
    datos = contrato.cargar(FIXTURES / "smart-service-minimo.md")
    datos["clase"]["paleta"] = paleta
    return datos


def _fallos_de_paleta(paleta):
    return [f for f in contrato.validar(_smart_service(paleta)) if "clase.paleta" in f]


def test_las_diecisiete_subpaletas_de_la_familia_segura_pasan():
    """Las 17 anotaciones de `…process.palette` cuya categoria es una de las
    cuatro validas en 26.x. Las otras 15 hornean una que Appian remapea."""
    assert len(contrato.ANOTACION_POR_PALETA) == 17
    for paleta in contrato.ANOTACION_POR_PALETA:
        assert not _fallos_de_paleta(paleta), paleta


def test_una_categoria_no_cuela_como_subpaleta_y_el_mensaje_dice_por_que():
    """El defecto del ciclo 4, fijado. `Workflow` ACEPTABA y se convertia en
    `Activities` en silencio."""
    for categoria in contrato.CATEGORIAS_DE_PALETA:
        fallos = _fallos_de_paleta(categoria)
        assert fallos, f"«{categoria}» es una categoria y no puede pasar como subpaleta"
        assert "CATEGORIA" in fallos[0], fallos
    # Y la pista tiene que llevar a la respuesta correcta, no solo negar.
    assert "Activities" in _fallos_de_paleta("Workflow")[0]


def test_las_cinco_que_faltaban_son_subpaletas_de_verdad():
    """`Human Tasks` es el smart service mas corriente que hay, y se rechazaba
    con el mensaje «no es una subpaleta de Appian», que era falso."""
    for paleta in ("Human Tasks", "Robotic Processes", "Test Management",
                   "Social", "Analytics", "Activities"):
        assert not _fallos_de_paleta(paleta), paleta


def test_analytics_apunta_a_la_anotacion_segura_no_a_la_escueta():
    """Colision real: dos anotaciones producen `palette="Analytics"`. La
    escueta hornea `Appian Smart Services` --que R-F01 rechaza-- y ademas esta
    `@Deprecated`. Por eso la traduccion no es derivable del nombre."""
    assert contrato.ANOTACION_POR_PALETA["Analytics"] == "AutomationSmartServicesAnalitycs"


ABRE_SECCION = "### Las subpaletas que existen"
CIERRA_SECCION = "**Enseñar"


def _publicadas_en_la_entrevista():
    """Las subpaletas que la referencia publica, leidas de las CELDAS de la tabla.

    No de los backticks de la seccion entera: ese fue el defecto. La prosa que
    hay debajo de la tabla nombra `Workflow` y `Activities` para explicar la
    diferencia entre los dos niveles, asi que un `findall` sobre la seccion
    metia seis tokens de ruido --`R-F01`, `Workflow`, `clase.paleta`,
    `contrato.ANOTACION_POR_PALETA`, `javap`, `paletteCategory`-- y obligaba a
    aseverar en un solo sentido.
    """
    import re as _re

    entrevista = (
        pathlib.Path(__file__).resolve().parents[1]
        / "skills" / "crear-plugin-appian" / "referencias" / "entrevista.md"
    ).read_text(encoding="utf-8")
    # Las dos anclas se ASEVERAN antes de recortar. Si alguien renombra la de
    # cierre, el recorte se come el resto del documento y arrastra la tabla de
    # admision: el test seguiria rojo, pero con un motivo enganoso («publica de
    # mas ['ContentService']») que manda a quien lo lea al sitio equivocado.
    assert entrevista.count(ABRE_SECCION) == 1, f"falta el ancla «{ABRE_SECCION}»"
    assert entrevista.count(CIERRA_SECCION) == 1, f"falta el ancla «{CIERRA_SECCION}»"
    seccion = entrevista.split(ABRE_SECCION)[1].split(CIERRA_SECCION)[0]

    publicadas = set()
    for linea in seccion.splitlines():
        if not linea.startswith("|") or linea.startswith("|---") or "Categoría" in linea:
            continue
        partes = linea.split("|")
        # Una fila que no llegue a tres campos reventaba con IndexError en vez
        # de decir que pasa. Es rojo igual, pero un rojo que no explica nada.
        assert len(partes) > 2, f"fila de la tabla con formato inesperado: {linea!r}"
        publicadas |= set(_re.findall(r"`([^`]+)`", partes[2]))
    return publicadas


def test_la_lista_publicada_en_la_entrevista_no_puede_divergir_del_mapa():
    """La costura que el gate del ciclo 4 marco [media]: la lista vive en el
    codigo y en la referencia que el modelo lee en runtime, y nada las ataba.
    Anadir una clave al mapa dejaba la skill enseñando una lista incompleta sin
    que nada se pusiera rojo."""
    publicadas = _publicadas_en_la_entrevista()
    esperadas = set(contrato.ANOTACION_POR_PALETA)
    # LAS DOS DIRECCIONES. La primera version solo miraba `esperadas -
    # publicadas`, y por ese lado no cabe el error historico: lo que costo dos
    # gates fue publicar `Workflow` COMO SI fuera subpaleta. Con la comparacion
    # antigua eso no movia la asercion --`Workflow` ya estaba en `publicadas`,
    # por la prosa de debajo-- asi que la referencia podia enseñar la lista mal
    # y nada se ponia rojo.
    assert publicadas == esperadas, (
        f"la entrevista no publica {sorted(esperadas - publicadas)} "
        f"y publica de mas {sorted(publicadas - esperadas)}"
    )


def test_una_function_sin_salidas_no_pasa_la_puerta():
    """[media] preexistente que levanto el gate del ciclo 5.

    De la salida de una function sale el TIPO DE RETORNO del metodo Java. Sin
    declararla, `andamiar.py:352` elegia `String` en silencio y emitia
    `public String saludofunction(...)` — un tipo que el contrato no menciona,
    y que ninguna puerta posterior puede atrapar porque no hay salida declarada
    contra la que comparar. Misma familia que la paleta, y alcanzable por el
    CLI: `validar` APROBABA.
    """
    datos = contrato.cargar(FIXTURES / "function-minimo.md")
    assert contrato.validar(datos) == [], "el fixture deberia estar limpio"
    datos["salidas"] = []
    assert any(f.startswith("salidas:") for f in contrato.validar(datos))


def test_un_smart_service_sin_salidas_SI_pasa():
    """Y no es una asimetria por descuido: en un smart service las salidas son
    campos con accesor, la clase no devuelve nada, y el propio proyecto declara
    legitimo un contrato sin salidas."""
    datos = contrato.cargar(FIXTURES / "smart-service-minimo.md")
    datos["salidas"] = []
    assert not [f for f in contrato.validar(datos) if f.startswith("salidas:")]


def test_una_writer_function_sin_salidas_SI_pasa():
    """Su plantilla hornea `public Writer …`: el tipo de retorno no sale de la
    salida, asi que ahi no hay nada que elegir en silencio. La primera version
    de la regla de arriba la incluia y rompio su fixture — el fixture tenia
    razon, y esta asimetria es deliberada."""
    datos = contrato.cargar(FIXTURES / "writer-function-minimo.md")
    assert not [f for f in contrato.validar(datos) if f.startswith("salidas:")]


def test_una_function_con_dos_salidas_no_pasa_la_puerta():
    """[media] del gate del ciclo 6. Un metodo Java devuelve UN valor: con dos
    salidas declaradas, `andamiar` tomaba `salidas[0]` y la segunda no llegaba
    ni al `.java` ni al bundle; invertir el orden en el TOML cambiaba el tipo
    de retorno sin que nada lo dijera."""
    datos = contrato.cargar(FIXTURES / "function-minimo.md")
    datos["salidas"] = list(datos["salidas"]) + [
        {"nombre": "codigo", "tipo_java": "Long", "descripcion": "un codigo"}
    ]
    fallos = [f for f in contrato.validar(datos) if f.startswith("salidas:")]
    assert fallos and "UNA" in fallos[0], fallos


def test_una_writer_function_con_salida_declarada_no_pasa_la_puerta():
    """Su plantilla hornea `public Writer …`, asi que una salida declarada
    describe un artefacto que no existe: el contrato decia `String` y el
    metodo devolvia `Writer`."""
    datos = contrato.cargar(FIXTURES / "writer-function-minimo.md")
    datos["salidas"] = [{"nombre": "resultado", "tipo_java": "String", "descripcion": "x"}]
    fallos = [f for f in contrato.validar(datos) if f.startswith("salidas:")]
    assert fallos and "Writer" in fallos[0], fallos


def test_un_servlet_no_puede_declarar_salidas():
    """Su plantilla no consume ninguna: escribe en el `HttpServletResponse`.

    Salia exit 0, y de ahi viajaban: `generar_dossier` las publica en la firma
    y R-F08 las compara, asi que el DOSSIER de un servlet afirmaba unas salidas
    que ningun `.java`, `.xml` ni `.properties` generado menciona. Mismo
    argumento con el que ya se le prohibe a la writer-function; la mitad que
    faltaba del hallazgo del ciclo 6.
    """
    datos = contrato.cargar(FIXTURES / "servlet-minimo.md")
    assert contrato.validar(datos) == [], "el fixture de servlet ya no valida"
    datos["salidas"] = [
        {"nombre": "resultado", "tipo_java": "String", "descripcion": "lo que devuelve"}
    ]
    errores = contrato.validar(datos)
    assert any("un servlet no declara ninguna" in e for e in errores), (
        f"un servlet con salidas declaradas se acepto: {errores}"
    )


def test_una_seccion_capacidades_QUE_NO_ES_TABLA_da_FALTA_en_vez_de_reventar():
    """La puerta que posee la forma del contrato tiene que comprobarla.

    Con `capacidades = 5`, el bucle hacia `5 not in 5` --`TypeError`, la puerta
    determinista del paso 1 muriendo con traza en vez de imprimir `FALTA`--; y
    con una cadena pasaba LIMPIA, porque `in` sobre un `str` compara
    subcadenas, para reventar dos lineas despues en `perfil_propuesto`. Las dos
    formas de fallar son peores que un `FALTA`: la primera no dice que arreglar
    y la segunda deja pasar un contrato que ningun consumidor puede leer.
    Levantado por el /simplify del ciclo 9 al ver que `verificar_todo` si tenia
    esta guarda y la puerta del contrato no.
    """
    base = contrato.cargar(FIXTURES / "smart-service-completo.md")
    for basura in (5, "parsea_formatos_ajenos sale_a_la_red", ["sale_a_la_red"]):
        faltantes = contrato.validar({**base, "capacidades": basura})
        assert any(f.startswith("capacidades:") for f in faltantes), (
            f"`capacidades = {basura!r}` no produjo ningun FALTA sobre la forma: {faltantes}"
        )
        # Y las cuatro claves siguen reclamandose: una seccion ilegible no es
        # una seccion presente, y callarlas dejaria creer que solo sobra tipo.
        assert sum(f.startswith("capacidades.") for f in faltantes) == 4, faltantes

    # Control: la fixture real no produce ninguno de esos FALTA.
    assert not any(f.startswith("capacidades") for f in contrato.validar(base))


# ---------------------------------------------------------------------------
# LA GUARDA DE FORMA ENTERA, NO SOLO SU PRIMERA CLAUSULA
#
# El gate del ciclo 11 dejo escrito el canario y no lo ejecuto: «la tupla
# declara siete secciones y el unico fixture que la ejerce solo pasa
# `capacidades` -- se puede encoger a `("capacidades", dict)` y la suite sigue
# verde». Se ejecuto en el ciclo 12 y era cierto: encogida la tupla, 503
# passed. Seis de las siete formas declaradas no tenian guardian, y con ellas
# el bucle de elementos entero.
#
# Por que la suite no lo veia. El unico test que pasaba secciones ilegibles por
# el camino ancho --`test_verificar_todo.test_un_contrato_con_SECCIONES_
# ILEGIBLES_deja_certificado_igual`-- entra por `ejecutar()` y afirma lo
# irrenunciable: que hay certificado y que la cabecera declara la averia. Esa
# cabecera la escribe `_resolver_perfil`, que tiene guarda propia. La de
# `contrato.validar` podia irse entera sin que nadie lo notara.
#
# COMO SE CUMPLE LA REGLA DE LA CASA --el aserto no deriva su expectativa de lo
# que vigila--: las siete secciones y su forma van LITERALES aqui abajo. Leerlas
# de `contrato.py` volveria a hacer verde el canario, porque encoger la tupla
# encogeria tambien al test. Esta lista es el conocimiento PROPIO del test sobre
# el esquema del contrato, y su fuente son los fixtures, no el validador:
# `test_las_siete_secciones_son_las_que_los_fixtures_declaran` lo comprueba.
# ---------------------------------------------------------------------------

# Cada seccion del contrato con la forma que TOML le da, y un valor de otro
# tipo que un contrato mal tecleado produce de verdad: `plugin = "smart-service"`
# es lo que escribe quien confunde la seccion con un campo, y `[[clase]]` --que
# TOML convierte en lista-- lo que escribe quien repite el doble corchete.
FORMAS_DEL_CONTRATO = (
    ("plugin", dict, "smart-service"),
    ("clase", dict, 7),
    ("bundle", dict, ["ejemplo"]),
    ("funcion", dict, "sumar"),
    ("capacidades", dict, "pendiente"),
    ("servlet", dict, "/estado"),
    ("entradas", list, {"nombre": "documentoOrigen"}),
    ("salidas", list, "resultado"),
    ("dependencias", list, "com.example:lib:1.0"),
)


@pytest.mark.parametrize("seccion,forma,basura", FORMAS_DEL_CONTRATO)
def test_cada_seccion_MAL_FORMADA_da_FALTA_en_vez_de_reventar(seccion, forma, basura):
    """La puerta del paso 1 solo sabe imprimir lineas `FALTA`: morir con traza
    no es un fallo mas ruidoso, es un fallo que su lector no sabe leer.

    Lo que se afirma es lo minimo y lo unico irrenunciable -- que `validar`
    TERMINA y que la seccion sale nombrada--, no el texto del mensaje. El
    numero de `FALTA` que arrastre detras depende de que campos reclame cada
    seccion y no es asunto de este test.
    """
    base = contrato.cargar(FIXTURES / "smart-service-completo.md")
    faltantes = contrato.validar({**base, seccion: basura})
    assert any(f.startswith(f"{seccion}:") for f in faltantes), (
        f"`{seccion} = {basura!r}` no produjo ningun FALTA sobre la forma: {faltantes}"
    )


@pytest.mark.parametrize("seccion", ("entradas", "salidas"))
def test_un_elemento_de_lista_QUE_NO_ES_TABLA_da_FALTA_con_SU_indice(seccion):
    """La mitad de dentro: `entradas = ["nombre"]` es TOML valido y llegaba al
    `.get(campo)` del bucle de contenido.

    El indice que se imprime es el del CONTRATO que el lector tiene delante:
    con un elemento malo delante de uno bueno, filtrar y volver a enumerar
    daria dos `[[entradas]]` distintos etiquetados igual. En una puerta cuya
    salida entera son lineas accionables, el indice ES el dato.

    DONDE SE MIRA LA RENUMERACION, y por que aqui y no en la linea de forma.
    La primera version de este test buscaba una linea `<seccion>[N]:` con N el
    indice del elemento sano, y el gate del ciclo 12 la declaro VACUA: no puede
    aparecer nunca. Las dos familias de `FALTA` se escriben distinto --la de
    forma es `<seccion>[i]: cada entrada es …`, con DOS PUNTOS, y la de campo
    es `<seccion>[i].<campo>`, con PUNTO-- y solo hay una linea de forma,
    siempre en el indice del unico elemento malo, que el test pone el primero.
    Renumerar o no renumerar daba `[0]:` en los dos casos. (Se describe el
    separador y no el numero de linea: los dos numeros que llevaba esta nota se
    quedaron rancios en el mismo commit que los escribio, y el separador es lo
    que no se mueve.)
    Lo que SI cambia al renumerar son los FALTA POR CAMPO del elemento sano
    incompleto: con la lista entera salen como `<seccion>[1].<campo>` y con la
    lista filtrada pasarian a `[0]`. Ahi es donde mira ahora el aserto, y por
    eso el elemento sano se elige INCOMPLETO a proposito -- uno completo no
    produce ningun FALTA y no habria nada que mirar.
    """
    base = contrato.cargar(FIXTURES / "smart-service-completo.md")
    # Incompleto a proposito: solo `nombre`. Sus campos que faltan son los que
    # llevan el indice, y son la senal de este test.
    incompleto = {"nombre": "sinTipoNiDescripcion"}

    faltantes = contrato.validar({**base, seccion: ["basura", incompleto]})
    assert any(f.startswith(f"{seccion}[0]:") for f in faltantes), (
        f"un elemento de `{seccion}` que no es tabla no produjo FALTA: {faltantes}"
    )

    por_campo = [f for f in faltantes if f.startswith(f"{seccion}[") and "]." in f]
    assert por_campo, (
        f"el elemento incompleto de `{seccion}` no produjo ningun FALTA por campo, "
        f"asi que este test no tendria nada que mirar: {faltantes}"
    )
    assert all(f.startswith(f"{seccion}[1].") for f in por_campo), (
        f"la lista se renumero: el elemento sano ocupa el indice 1 del contrato y sus "
        f"FALTA salen con otro indice. Con la lista filtrada pasaria a `[0]`, y el "
        f"lector buscaria en su contrato un `[[{seccion}]]` que no es el que falla: "
        f"{por_campo}"
    )


def test_la_guarda_cubre_TODAS_las_secciones_que_el_andamiador_consume():
    """El suelo antivacuidad de los dos tests de arriba, y la costura que el
    gate del ciclo 12 encontro abierta.

    El guardian anterior derivaba la lista de los FIXTURES, y por eso no vio
    nada: NINGUN fixture declara `[servlet]` ni `[dependencias]` --las dos
    secciones que se quedaron fuera de la guarda-- asi que la comprobacion
    salia verde sobre el conjunto que ya estaba cubierto. Un guardian que solo
    mira donde ya se miro.

    La fuente correcta es el CONSUMIDOR: `andamiar.py` es quien procesa el
    contrato, y la promesa escrita de `validar` es que «lo que esta puerta
    acepta, el andamiador lo procesa». Se leen sus accesos de primer nivel del
    fuente --`datos.get("x")`, `datos["x"]`, `contrato.seccion(datos, "x")`--
    y se exige que la guarda los cubra todos.
    """
    fuente = (RAIZ_SCRIPTS / "andamiar.py").read_text(encoding="utf-8")
    consumidas = set(re.findall(
        r'datos(?:\.get\(|\[)"(\w+)"|contrato\.seccion\(datos, "(\w+)"', fuente
    ))
    consumidas = {a or b for a, b in consumidas}

    # Suelo antivacuidad: si el patron deja de casar, `consumidas` se vacia y
    # la comprobacion de abajo se satisface sin mirar nada -- que es el defecto
    # que este test viene a cerrar, no uno que pueda permitirse.
    # OCHO, no nueve: `andamiar` no lee `[capacidades]`. Esa la consumen
    # `contrato.perfil_propuesto` y `verificar_todo._resolver_perfil`, y por eso
    # la guarda es un SUPERCONJUNTO de lo que consume el andamiador. La
    # direccion que importa es la de abajo: nada consumido puede quedar fuera.
    assert len(consumidas) >= 8, (
        f"solo se detectaron {len(consumidas)} secciones consumidas en andamiar.py "
        f"({sorted(consumidas)}): el patron dejo de leer el fuente y este guardian "
        f"se habria quedado ciego"
    )
    declaradas = {nombre for nombre, _, _ in FORMAS_DEL_CONTRATO}
    sin_guarda = consumidas - declaradas
    assert not sin_guarda, (
        f"`andamiar.py` consume secciones que la guarda de forma no vigila: "
        f"{sorted(sin_guarda)}. Una seccion sin guarda llega mal formada al "
        f"andamiador con la puerta en verde"
    )


def test_una_dependencia_SUELTA_no_se_itera_letra_a_letra():
    """La seccion silenciosa de las dos que el ciclo 12 encontro sin guarda.

    `dependencias = "com.example:lib:1.0"` --sin corchetes-- es TOML valido y
    es la errata natural de quien declara UNA sola dependencia. `validar`
    devolvia `[]` y los tres consumidores iteraban la cadena caracter a
    caracter: el `build.gradle` generado salia con `implementation 'c'`,
    `implementation 'o'`, `implementation 'm'`… y `THIRD_PARTY_NOTICES.md` con
    una linea por letra. El fallo aparecia lejisimos --en la resolucion de
    dependencias de Gradle-- y sin mencionar el contrato.
    """
    base = contrato.cargar(FIXTURES / "smart-service-completo.md")
    faltantes = contrato.validar({**base, "dependencias": "com.example:lib:1.0"})
    assert any(f.startswith("dependencias:") for f in faltantes), (
        f"una dependencia suelta como cadena paso la puerta: {faltantes}"
    )

    # Y la forma BUENA sigue pasando: una lista de cadenas es lo que el
    # andamiador espera, y exigirle tablas habria sido cambiar un rechazo malo
    # por otro.
    assert not any(
        f.startswith("dependencias") for f in
        contrato.validar({**base, "dependencias": ["com.example:lib:1.0"]})
    )


# --- La misma promesa, contra TODOS los consumidores ------------------------
# El guardian de arriba lee solo `andamiar.py`, y la promesa de la guarda es
# mas ancha: hay cuatro scripts mas que leen secciones de primer nivel del
# contrato. Hoy no hay hueco, pero el caso que lo demuestra ya existe --
# `version_anterior` lo consume solo `verificar_framework.py` y aquel barrido
# no lo ve-- asi que la siguiente seccion que nazca para un `verificar_*` no
# encontraria red. Levantado por el gate del ciclo 13.

# Nombres que el barrido encuentra y que NO son secciones del contrato, cada
# uno con su motivo comprobado. Escritos a mano a proposito: ampliar esta tabla
# tiene que ser una decision, no un efecto colateral.
_NO_SON_SECCIONES = {
    # `verificar_todo._version_del_indice` carga `inventario-api.json` en una
    # variable llamada tambien `datos`. Son claves de ESE json, no del contrato.
    "hash_indice",
    "version_indice",
}
# Secciones reales del contrato que la guarda de forma NO cubre porque tienen
# validador propio, mas especifico que «es un dict».
_CON_VALIDADOR_PROPIO = {"version_anterior": "_validar_version_anterior"}


def test_la_guarda_cubre_las_secciones_que_consume_CUALQUIER_script():
    patron = re.compile(
        r'datos(?:_contrato)?(?:\.get\(|\[)"(\w+)"'
        r'|contrato\.seccion\(datos(?:_contrato)?, "(\w+)"'
    )
    consumidas: dict[str, set[str]] = {}
    for script in sorted(RAIZ_SCRIPTS.glob("*.py")):
        # Sin comentarios: `contrato.py` explica la guarda usando `datos.get("x")`
        # como ejemplo, y un ejemplo en prosa no es un consumidor.
        codigo = "\n".join(
            l for l in script.read_text(encoding="utf-8").splitlines()
            if not l.lstrip().startswith("#")
        )
        halladas = {a or b for a, b in patron.findall(codigo)}
        if halladas:
            consumidas[script.name] = halladas

    # Suelo antivacuidad, en las dos dimensiones que pueden vaciarse: si el
    # patron deja de casar, o si deja de barrerse mas de un fichero, la
    # comprobacion de abajo se satisface sin mirar nada.
    assert len(consumidas) >= 5, (
        f"el barrido solo encontro consumidores en {sorted(consumidas)}: el patron dejo de "
        f"leer el fuente y este guardian se habria quedado ciego"
    )
    assert "verificar_framework.py" in consumidas, (
        "el barrido ya no ve `verificar_framework.py`, que es el consumidor que motiva este "
        "test: es el unico que lee `version_anterior`"
    )

    declaradas = {nombre for nombre, _, _ in FORMAS_DEL_CONTRATO}
    todas = {s for halladas in consumidas.values() for s in halladas}
    sin_guarda = todas - declaradas - _NO_SON_SECCIONES - set(_CON_VALIDADOR_PROPIO)
    assert not sin_guarda, (
        f"estos scripts consumen secciones de primer nivel que nadie vigila: "
        f"{sorted(sin_guarda)}. O entran en la guarda de forma de `contrato.validar`, o "
        f"llevan validador propio y se declaran arriba con su motivo. "
        f"Consumidores: { {k: sorted(v) for k, v in consumidas.items()} }"
    )


def test_la_seccion_exenta_de_la_guarda_tiene_de_verdad_su_validador_propio():
    """Suelo de la tabla de excepciones: exentar una seccion es prometer que
    otro la valida. Si ese otro desaparece, la exencion se convierte en un
    agujero declarado por escrito, que es peor que uno olvidado.
    """
    for seccion, validador in _CON_VALIDADOR_PROPIO.items():
        assert hasattr(contrato, validador), (
            f"`{seccion}` esta exenta de la guarda de forma porque `contrato.{validador}` la "
            f"valida, y esa funcion ya no existe: la seccion se quedo sin nadie que la mire"
        )
        # Se mira que la linea hable de ESTA seccion. `validar` devuelve
        # faltantes por otras razones sobre cualquier contrato incompleto, asi
        # que un `assert validar(...)` a secas pasaria con la exencion vacia:
        # es el aserto-que-no-puede-fallar que este repositorio persigue.
        base = contrato.cargar(FIXTURES / "smart-service-completo.md")
        suyas = [
            f for f in contrato.validar({**base, seccion: "esto-no-es-una-seccion"})
            if f.startswith(seccion)
        ]
        assert suyas, (
            f"`contrato.{validador}` existe pero `{seccion} = \"...\"` mal formada no produce "
            f"ni una linea FALTA que hable de `{seccion}`: la exencion no la cubre nadie"
        )


# --- Las dos cuentas del mapa, ancladas -------------------------------------
# `docs/como-funciona.md` describe esta guarda con dos numeros escritos a mano
# --cuantas secciones vigila y cuantas consume el andamiador-- justo en el
# fichero donde el ciclo 12 anclo OTRO numeral. Exactos hoy y sin nadie que los
# mire. Levantado por el gate del ciclo 13.

MAPA = pathlib.Path(__file__).resolve().parents[1] / "docs" / "como-funciona.md"


def test_el_mapa_cuenta_bien_LAS_SECCIONES_QUE_LA_GUARDA_VIGILA():
    texto = MAPA.read_text(encoding="utf-8")
    numerales = {"siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12}

    escritas = re.findall(r"\*\*(\w+) secciones\*\*", texto)
    assert escritas, (
        f"`{MAPA.name}` ya no dice cuantas secciones vigila la guarda de forma: el numero "
        f"que este test ancla desaparecio de la prosa"
    )
    palabra = escritas[0]
    assert palabra in numerales, (
        f"`{MAPA.name}` escribe «{palabra}», que no es un numeral que este test sepa leer"
    )
    assert numerales[palabra] == len(FORMAS_DEL_CONTRATO), (
        f"`{MAPA.name}` dice «{palabra}» secciones y la guarda cubre "
        f"{len(FORMAS_DEL_CONTRATO)}: {sorted(n for n, _, _ in FORMAS_DEL_CONTRATO)}"
    )

    consumidas = re.findall(r"las (\w+) que consume el andamiador", texto)
    assert consumidas, (
        f"`{MAPA.name}` ya no dice cuantas de esas secciones consume el andamiador: es la "
        f"mitad de la frase que explica por que la guarda es un superconjunto"
    )
    fuente = (RAIZ_SCRIPTS / "andamiar.py").read_text(encoding="utf-8")
    del_andamiador = {
        a or b
        for a, b in re.findall(
            r'datos(?:\.get\(|\[)"(\w+)"|contrato\.seccion\(datos, "(\w+)"', fuente
        )
    }
    assert len(del_andamiador) >= 2, (
        f"el barrido de `andamiar.py` encontro {len(del_andamiador)} secciones: dejo de leer "
        f"el fuente y esta cuenta se habria comprobado contra nada"
    )
    assert numerales[consumidas[0]] == len(del_andamiador), (
        f"`{MAPA.name}` dice que el andamiador consume «{consumidas[0]}» y su fuente lee "
        f"{len(del_andamiador)}: {sorted(del_andamiador)}"
    )
