
import verificar_bundles as vb

CONTRATO_SS = {
    "plugin": {"key": "com.raul.appian.ejemplo", "tipo": "smart-service", "nombre": "Ejemplo"},
    "bundle": {"nombre": "ejemplo"},
    "clase": {"nombre": "EjemploSmartService"},
    "entradas": [{"nombre": "documentoOrigen", "tipo_java": "Long", "required": "ALWAYS", "descripcion": "d"}],
    "salidas": [{"nombre": "resultado", "tipo_java": "String", "descripcion": "r"}],
}

BUNDLE_SS_OK = """name=Ejemplo
input.documentoOrigen.displayName=Documento origen
input.documentoOrigen.comment=El documento de entrada
output.resultado.displayName=Resultado
output.resultado.comment=El resultado
"""

CONTRATO_FN = {
    "plugin": {"key": "com.raul.appian.texto", "tipo": "function", "nombre": "Texto"},
    "bundle": {"nombre": "funcionesTexto"},
    "clase": {"nombre": "InvertirCadena"},
    "entradas": [{"nombre": "texto", "tipo_java": "String", "descripcion": "d"}],
    "salidas": [],
    "funcion": {"nombre": "invertircadena"},
}

BUNDLE_FN_OK = """function.invertircadena.description=Invierte una cadena
function.invertircadena.param.texto.description=El texto a invertir
"""

def reglas(hallazgos):
    return {h.regla for h in hallazgos}


def test_ruta_convierte_puntos_de_la_key_en_separadores():
    assert vb.ruta_esperada("com.raul.appian.ejemplo", "ejemplo", "en_US") == (
        "com/raul/appian/ejemplo/ejemplo_en_US.properties"
    )


def test_bundle_de_smart_service_correcto_no_da_hallazgos():
    rutas = {"com/raul/appian/ejemplo/ejemplo_en_US.properties": BUNDLE_SS_OK}
    assert vb.comprobar(CONTRATO_SS, rutas) == []


def test_falta_el_bundle_en_us_es_error():
    assert "R-B01" in reglas(vb.comprobar(CONTRATO_SS, {}))


def test_fichero_sin_sufijo_de_locale_es_error():
    """Con el `_en_US` canonico PRESENTE, que es lo que hace que este test
    ejerza lo que su nombre dice.

    Estaba verde por la rama equivocada: montaba `{ejemplo.properties}` a secas
    --sin `_en_US` canonico--, asi que saltaba la OTRA mitad de R-B01 («falta el
    bundle obligatorio»), que corta con un `return` antes de llegar al sufijo.
    Como asertaba solo sobre el identificador `R-B01`, que las dos mitades
    emiten, pasaba sin ejecutar nunca la comprobacion que le da nombre. Medido:
    desactivando el predicado del sufijo, seguia verde.

    Ahora el `_en_US` esta donde debe, el unico defecto es el sufijo, y se
    aserta sobre el MENSAJE, no sobre la etiqueta compartida.
    """
    rutas = {
        "com/raul/appian/ejemplo/ejemplo_en_US.properties": BUNDLE_SS_OK,
        "com/raul/appian/ejemplo/ejemplo.properties": BUNDLE_SS_OK,
    }
    hallazgos = vb.comprobar(CONTRATO_SS, rutas)
    sufijo = [h for h in hallazgos if "sufijo de locale" in h.mensaje]
    assert sufijo, (
        f"el fichero sin sufijo de locale no se reporto. Hallazgos: "
        f"{[(h.regla, h.mensaje) for h in hallazgos]}"
    )
    assert "ejemplo.properties" in sufijo[0].mensaje


def test_el_SUFIJO_se_juzga_AUNQUE_falte_el_en_US_canonico():
    """La cuarta vuelta del defecto de esta funcion: una comprobacion cegada
    por un `return` ajeno.

    El sufijo de locale vivia por debajo del `return` con el que R-B01 corta
    cuando falta el `_en_US`. Efecto: un proyecto al que le faltan las dos cosas
    se enteraba solo de la primera, arreglaba, y entonces descubria la segunda.
    R-B01 cegandose a si misma.

    Solo mira RUTAS, asi que no depende de nada de lo que el `return` guarda.
    """
    rutas = {"com/raul/appian/ejemplo/suelto.properties": BUNDLE_SS_OK}
    mensajes = [h.mensaje for h in vb.comprobar(CONTRATO_SS, rutas)]

    assert any("falta el bundle obligatorio" in m for m in mensajes), (
        "sin `_en_US` canonico R-B01 tiene que seguir reclamandolo"
    )
    assert any("sufijo de locale" in m for m in mensajes), (
        f"falta el `_en_US` y `comprobar` vuelve sin mirar el sufijo de los ficheros que SI "
        f"estan: `suelto.properties` no lo lleva y nadie lo dice. Mensajes: {mensajes}"
    )


def test_convenio_de_function_aplicado_a_smart_service_es_error():
    # El error exacto de la guia (auditoria §7.11): generalizar a los smart
    # services el convenio que si rige en las funciones.
    malo = """name=Ejemplo
smartservice.ejemplo.input.documentoOrigen.description=Documento
smartservice.ejemplo.output.resultado.description=Resultado
"""
    rutas = {"com/raul/appian/ejemplo/ejemplo_en_US.properties": malo}
    assert "R-B02" in reglas(vb.comprobar(CONTRATO_SS, rutas))


def test_bundle_de_function_usa_su_propio_convenio_y_es_correcto():
    rutas = {"com/raul/appian/texto/funcionesTexto_en_US.properties": BUNDLE_FN_OK}
    assert vb.comprobar(CONTRATO_FN, rutas) == []


def test_falta_la_clave_name_en_smart_service_es_error():
    sin_name = BUNDLE_SS_OK.replace("name=Ejemplo\n", "")
    rutas = {"com/raul/appian/ejemplo/ejemplo_en_US.properties": sin_name}
    assert "R-B03" in reglas(vb.comprobar(CONTRATO_SS, rutas))


def test_locale_extra_sin_paridad_de_error_y_validation_es_error():
    en = BUNDLE_SS_OK + "error.lectura=Cannot read\nvalidation.vacio=Required\n"
    es = BUNDLE_SS_OK + "error.lectura=No se puede leer\n"
    rutas = {
        "com/raul/appian/ejemplo/ejemplo_en_US.properties": en,
        "com/raul/appian/ejemplo/ejemplo_es_ES.properties": es,
    }
    assert "R-B04" in reglas(vb.comprobar(CONTRATO_SS, rutas))


def test_acentos_sin_escapar_en_unicode_son_aviso():
    es = BUNDLE_SS_OK.replace("Documento origen", "Documento de orígen")
    rutas = {
        "com/raul/appian/ejemplo/ejemplo_en_US.properties": BUNDLE_SS_OK,
        "com/raul/appian/ejemplo/ejemplo_es_ES.properties": es,
    }
    assert "R-B05" in reglas(vb.comprobar(CONTRATO_SS, rutas))


def test_R_B05_JUZGA_EL_en_US_CANONICO_que_es_el_unico_que_ve_un_usuario():
    """El caso que ningun fixture ejercitaba, y por eso el hueco vivio dos ciclos.

    Este test entra por el JUEZ, no por el emisor. Los dos tests de escapado que
    escribio el ciclo 16 leen los ficheros que el andamiador ESCRIBE: cubren que
    el forge escape bien, y no que el validador mire. Como la exencion vivia en
    el `continue` del bucle de R-B04 —no en el predicado que se cambio—, un
    `en_US` editado a mano tras andamiar (el flujo normal: rellenar los textos
    de display) pasaba las cuatro capas en silencio, y R-B05 es el UNICO chequeo
    de codificacion de todo el sistema.

    La ruta es la CANONICA a proposito: con cualquier otra el test pasaba ya
    antes del arreglo, que es exactamente la mitad que se creyo cerrada.
    """
    en_con_tilde = BUNDLE_SS_OK.replace("Documento origen", "Documento de orígen")
    rutas = {"com/raul/appian/ejemplo/ejemplo_en_US.properties": en_con_tilde}
    assert "R-B05" in reglas(vb.comprobar(CONTRATO_SS, rutas)), (
        "el `en_US` en su ruta canonica lleva una tilde cruda y R-B05 calla: es el fichero "
        "del que Appian saca los textos de display y el unico cuyo mojibake ve un usuario"
    )


def test_un_en_US_LIMPIO_en_la_ruta_canonica_no_dispara_R_B05():
    """La direccion contraria, para que el de arriba no pase con un aviso que
    salte siempre sobre el `en_US`."""
    rutas = {"com/raul/appian/ejemplo/ejemplo_en_US.properties": BUNDLE_SS_OK}
    assert "R-B05" not in reglas(vb.comprobar(CONTRATO_SS, rutas))


def test_R_B05_SIGUE_MIRANDO_cuando_R_B01_YA_REPROBO_la_ruta():
    """La tercera vuelta del mismo defecto: el alcance de R-B05 fijado por un
    control de flujo ajeno.

    El ciclo 17 lo saco del bucle de R-B04 —cuyo `continue` eximia al `en_US`—
    y lo dejo al final de `comprobar`, o sea POR DEBAJO del `return` con el que
    R-B01 corta cuando el `_en_US` no esta en su ruta canonica. Efecto: un
    proyecto que renombra `[bundle].nombre` sin renombrar los ficheros (o al
    reves) se lleva el error de R-B01 y NINGUN aviso de codificacion sobre los
    bundles que si existen —y R-B05 es el unico chequeo de codificacion de todo
    el sistema—. El aviso solo aparecia despues de arreglar otra cosa.

    Entra por el juez y por el INSUMO: dos ficheros reales, uno con la tilde
    cruda, y una ruta que R-B01 rechaza. Antes de mover el bucle este test es
    rojo, con `R-B01` como unica regla devuelta.
    """
    es = BUNDLE_SS_OK.replace("Documento origen", "Documento de orígen")
    rutas = {
        # El contrato dice `[bundle].nombre = "ejemplo"`; los ficheros se
        # llaman `mensajes`. Ninguno casa con la ruta canonica.
        "com/raul/appian/ejemplo/mensajes_en_US.properties": BUNDLE_SS_OK,
        "com/raul/appian/ejemplo/mensajes_es_ES.properties": es,
    }
    encontradas = reglas(vb.comprobar(CONTRATO_SS, rutas))
    assert "R-B01" in encontradas, (
        "el bundle no esta en su ruta canonica y R-B01 no lo dice; sin ese error el caso que "
        "este test monta no es el que dice ser"
    )
    assert "R-B05" in encontradas, (
        f"falta el `_en_US` canonico y `comprobar` vuelve sin mirar la codificacion de nada: "
        f"el `_es_ES` presente lleva una tilde cruda y nadie la ve. Reglas devueltas: "
        f"{sorted(encontradas)}"
    )


# Las reglas que NO dependen del contenido del `_en_US`, y por tanto las unicas
# que pueden correr antes del `return` de R-B01. Hoy es una sola. Si anades una
# regla nueva que mire el contenido CRUDO de los bundles, va aqui arriba y a
# esta lista; si mira claves parseadas del `_en_US`, va debajo del `return` y
# esta lista no cambia.
REGLAS_QUE_NO_NECESITAN_EN_US = {"R-B05"}


def test_QUE_reglas_sobreviven_a_un_en_US_AUSENTE_esta_clavado():
    """El guardian de arriba protege a R-B05; este protege LA PROPIEDAD.

    La posicion de una regla dentro de `comprobar()` es semanticamente
    significativa --arriba del `return` de R-B01 corren las que leen contenido
    crudo, debajo las que necesitan `pares_en_us`-- y esa distincion no vive en
    ninguna estructura de datos: vive en el orden de las lineas. Es una bomba de
    relojeria para la regla que se anada manana, que puede caer debajo del
    `return` sin depender del `_en_US` y nacer ciega, exactamente como nacio
    R-B05 y como siguio despues de su primer arreglo.

    Este test convierte esa decision implicita en una explicita: clava el
    conjunto EXACTO de reglas que sobreviven a un `_en_US` ausente. Quien mueva
    una regla de fase, o anada una arriba, tiene que tocar
    `REGLAS_QUE_NO_NECESITAN_EN_US` a proposito, y ahi es donde se piensa.

    El insumo esta cargado a mala fe: los bundles traen ademas claves del
    convenio equivocado (`function.*` en un smart service, que es R-B02) y una
    clave `input.*` inventada (R-B06). Si alguna de esas reglas corriera sin
    `_en_US`, apareceria en el conjunto y este test lo diria.
    """
    veneno = (
        BUNDLE_SS_OK
        + "function.loQueSea.description=convenio equivocado, esto es R-B02\n"
        + "input.noExiste.displayName=entrada inventada, esto es R-B06\n"
    )
    rutas = {
        "com/raul/appian/ejemplo/mensajes_en_US.properties": veneno,
        "com/raul/appian/ejemplo/mensajes_es_ES.properties": veneno.replace(
            "Documento origen", "Documento de orígen"
        ),
    }
    encontradas = reglas(vb.comprobar(CONTRATO_SS, rutas))

    assert encontradas == {"R-B01"} | REGLAS_QUE_NO_NECESITAN_EN_US, (
        f"cambio el conjunto de reglas que corren sin un `_en_US` canonico.\n"
        f"  esperado: {sorted({'R-B01'} | REGLAS_QUE_NO_NECESITAN_EN_US)}\n"
        f"  obtenido: {sorted(encontradas)}\n"
        f"Si has anadido una regla que mira el contenido crudo de los bundles, ponla ANTES del "
        f"`return` de R-B01 y anadela a `REGLAS_QUE_NO_NECESITAN_EN_US`. Si mira claves "
        f"parseadas del `_en_US`, tiene que ir DESPUES y no entra en esa lista. La posicion no "
        f"es estilo: es el alcance de la regla"
    )


def test_parsea_properties_ignorando_comentarios():
    d = vb.parsear_properties("# comentario\n! otro comentario\nclave=valor\n\notra = con espacios \n")
    assert d == {"clave": "valor", "otra": "con espacios"}


def test_una_clave_de_error_terminada_en_description_no_dispara_r_b02():
    # Falso positivo real: `error.io.description` es una clave legitima —y de
    # la familia que R-B04 EXIGE—, pero casar por sufijo «.description» la
    # tomaba por convenio de Function colado en un smart service. Dos reglas
    # del mismo validador contradiciendose.
    bundle = BUNDLE_SS_OK + "error.io.description=No se pudo leer el fichero\n"
    rutas = {"com/raul/appian/ejemplo/ejemplo_en_US.properties": bundle}
    assert vb.comprobar(CONTRATO_SS, rutas) == []


def test_convenio_de_smart_service_aplicado_a_function_es_error():
    # La direccion contraria del cruce, que no tenia test: claves input./output.
    # coladas en una funcion.
    malo = BUNDLE_FN_OK + "input.texto.displayName=Texto\n"
    rutas = {"com/raul/appian/texto/funcionesTexto_en_US.properties": malo}
    assert "R-B02" in reglas(vb.comprobar(CONTRATO_FN, rutas))


def test_un_servlet_no_necesita_bundle():
    # Rama de salida temprana sin ningun test que la disparase.
    contrato_servlet = {**CONTRATO_SS,
                        "plugin": {**CONTRATO_SS["plugin"], "tipo": "servlet"}}
    assert vb.comprobar(contrato_servlet, {}) == []


def test_locale_con_paridad_de_error_pero_sin_displayname_no_da_hallazgo():
    # Fuera de en_US, Appian solo lee error.* y validation.*: exigir paridad
    # total seria un falso positivo. Este test fija que NO se exige.
    en = BUNDLE_SS_OK + "error.lectura=Cannot read\nvalidation.vacio=Required\n"
    es = "error.lectura=No se puede leer\nvalidation.vacio=Obligatorio\n"
    rutas = {
        "com/raul/appian/ejemplo/ejemplo_en_US.properties": en,
        "com/raul/appian/ejemplo/ejemplo_es_ES.properties": es,
    }
    assert [h for h in vb.comprobar(CONTRATO_SS, rutas) if h.severidad == "error"] == []


# Los dos huecos que el revisor senalo como menores, no obligatorios: cubrirlos
# porque son baratos con el patron ya presente en este fichero, no porque el
# brief los pidiera.

def test_falta_la_clave_description_en_function_es_error():
    # R-B03 solo tenia test para smart-service (test_falta_la_clave_name...);
    # la rama de claves_esperadas() para function/writer-function nunca se
    # probo detectando una clave obligatoria ausente.
    sin_descripcion = BUNDLE_FN_OK.replace("function.invertircadena.description=Invierte una cadena\n", "")
    rutas = {"com/raul/appian/texto/funcionesTexto_en_US.properties": sin_descripcion}
    assert "R-B03" in reglas(vb.comprobar(CONTRATO_FN, rutas))


# --- R-B06: lo que SOBRA, no solo lo que falta -----------------------------
# R-B03 compara `esperadas - presentes`: mira en una sola direccion. Una clave
# con la caja cambiada no falta (la esperada nunca estuvo en el conjunto) y no
# casa con ningun prefijo prohibido de R-B02, asi que era invisible para las
# CUATRO capas. Fue un defecto real de la plantilla de smart service, que
# horneaba `output.errorOccurred` mientras la clase declara
# `getErrorOccurred()` --y Appian lee el nombre del ACCESOR--.

def test_una_clave_de_salida_con_la_caja_equivocada_es_error():
    # El defecto exacto: `resultado` declarado, `Resultado` escrito.
    malo = BUNDLE_SS_OK.replace("output.resultado.displayName", "output.Resultado.displayName")
    rutas = {"com/raul/appian/ejemplo/ejemplo_en_US.properties": malo}
    hallazgos = vb.comprobar(CONTRATO_SS, rutas)
    assert "R-B06" in reglas(hallazgos)
    # Y ademas debe sugerir la clave correcta: es un error de una sola letra y
    # el validador tiene el dato para decirlo.
    assert any("output.resultado.displayName" in h.mensaje for h in hallazgos)


def test_una_clave_de_entrada_inventada_es_error():
    malo = BUNDLE_SS_OK + "input.noExiste.displayName=Fantasma\n"
    assert "R-B06" in reglas(vb.comprobar(CONTRATO_SS, malo_rutas(malo)))


def test_las_salidas_de_error_horneadas_no_cuentan_como_sobrantes():
    # `ErrorOccurred` y `ErrorMessage` los declara SIEMPRE la plantilla de
    # smart service (campo, getter y manejo de errores), aunque el contrato no
    # los enumere. Son legitimos y R-B06 no debe marcarlos.
    con_horneadas = BUNDLE_SS_OK + (
        "output.ErrorOccurred.displayName=Error occurred\n"
        "output.ErrorOccurred.comment=True if the execution failed\n"
        "output.ErrorMessage.displayName=Error message\n"
        "output.ErrorMessage.comment=Description of the error, if any\n"
    )
    assert vb.comprobar(CONTRATO_SS, malo_rutas(con_horneadas)) == []


def test_las_salidas_de_error_en_minuscula_si_son_sobrantes():
    # La forma exacta del defecto encontrado en la plantilla: Appian expone el
    # output como `ErrorOccurred` (del accesor `getErrorOccurred()`), asi que
    # `output.errorOccurred.*` no etiqueta nada y los dos outputs de error se
    # quedan sin nombre en el Process Modeler.
    como_estaba_la_plantilla = BUNDLE_SS_OK + (
        "output.errorOccurred.displayName=Error occurred\n"
        "output.errorMessage.displayName=Error message\n"
    )
    hallazgos = vb.comprobar(CONTRATO_SS, malo_rutas(como_estaba_la_plantilla))
    assert "R-B06" in reglas(hallazgos)
    assert any("output.ErrorOccurred.displayName" in h.mensaje for h in hallazgos)


def test_las_claves_error_y_validation_nunca_son_sobrantes():
    # No llevan prefijo input./output., asi que R-B06 ni las mira. Este test
    # fija que seguira siendo asi: son las que R-B04 EXIGE en otros locales.
    bundle = BUNDLE_SS_OK + "error.io=No se pudo leer\nvalidation.required=Obligatorio\n"
    assert vb.comprobar(CONTRATO_SS, malo_rutas(bundle)) == []


def malo_rutas(contenido: str) -> dict[str, str]:
    return {"com/raul/appian/ejemplo/ejemplo_en_US.properties": contenido}


def test_writer_function_usa_el_mismo_convenio_que_function():
    # claves_esperadas() y R-B02 miran `tipo in ("function", "writer-function")`,
    # pero ningun test instanciaba nunca un contrato con ese tipo literal. El
    # caso feliz solo no basta: si se borrara "writer-function" de esa tupla,
    # claves_esperadas() devolveria un set vacio, R-B03 nunca tendria nada que
    # echar en falta y este caso seguiria en verde igual. El negativo obliga a
    # que la rama exista de verdad: una clave obligatoria ausente debe seguir
    # disparando R-B03 tambien para este tipo.
    contrato_wf = {**CONTRATO_FN, "plugin": {**CONTRATO_FN["plugin"], "tipo": "writer-function"}}
    rutas = {"com/raul/appian/texto/funcionesTexto_en_US.properties": BUNDLE_FN_OK}
    assert vb.comprobar(contrato_wf, rutas) == []

    sin_descripcion = BUNDLE_FN_OK.replace("function.invertircadena.description=Invierte una cadena\n", "")
    rutas_incompletas = {"com/raul/appian/texto/funcionesTexto_en_US.properties": sin_descripcion}
    assert "R-B03" in reglas(vb.comprobar(contrato_wf, rutas_incompletas))


# ─── R-B07 · un bundle por modulo del MANIFIESTO ──────────────────────────
#
# La unica regla de la capa que no deriva del contrato. El contrato describe UN
# modulo; el manifiesto puede declarar varios, y cada uno necesita el suyo
# porque Appian lo busca como `<key del plug-in>.<key del modulo>`.

MANIFIESTO_FN = (
    '<appian-plugin key="com.raul.appian.texto">'
    '<function key="funcionesTexto" class="com.raul.appian.texto.function.InvertirCadena"/>'
    "</appian-plugin>"
)


def test_el_bundle_de_cada_modulo_declarado_esta_presente():
    rutas = {"com/raul/appian/texto/funcionesTexto_en_US.properties": BUNDLE_FN_OK}
    assert vb.comprobar(CONTRATO_FN, rutas, MANIFIESTO_FN) == []


def test_un_segundo_modulo_sin_su_bundle_dispara_R_B07():
    """El caso que no desplego en un Appian real: varios modulos, un bundle."""
    manifiesto = (
        '<appian-plugin key="com.raul.appian.texto">'
        '<function key="funcionesTexto" class="com.raul.appian.texto.function.InvertirCadena"/>'
        '<function key="otrasFunciones" class="com.raul.appian.texto.function.Otra"/>'
        "</appian-plugin>"
    )
    rutas = {"com/raul/appian/texto/funcionesTexto_en_US.properties": BUNDLE_FN_OK}
    hallazgos = vb.comprobar(CONTRATO_FN, rutas, manifiesto)
    assert "R-B07" in reglas(hallazgos)
    mensaje = " ".join(h.mensaje for h in hallazgos if h.regla == "R-B07")
    assert "otrasFunciones_en_US.properties" in mensaje
    assert "funcionesTexto_en_US.properties" not in mensaje


def test_R_B07_dispara_cuando_la_key_del_modulo_no_es_el_nombre_del_bundle():
    """El defecto que traia la plantilla de function: la key del modulo salia
    del nombre de la funcion y el .properties de `bundle.nombre`. Cada cosa
    estaba bien por separado y el plug-in no desplegaba."""
    manifiesto = (
        '<appian-plugin key="com.raul.appian.texto">'
        '<function key="invertircadena" class="com.raul.appian.texto.function.InvertirCadena"/>'
        "</appian-plugin>"
    )
    rutas = {"com/raul/appian/texto/funcionesTexto_en_US.properties": BUNDLE_FN_OK}
    hallazgos = vb.comprobar(CONTRATO_FN, rutas, manifiesto)
    assert "R-B07" in reglas(hallazgos)
    assert any("invertircadena_en_US.properties" in h.mensaje for h in hallazgos)


def test_R_B07_corre_aunque_falte_el_bundle_del_contrato():
    """R-B01 corta con un `return` cuando no encuentra el bundle que deriva del
    contrato. R-B07 va ANTES a proposito: si no, el proyecto al que le faltan
    los dos se entera de uno cada vez."""
    manifiesto = (
        '<appian-plugin key="com.raul.appian.texto">'
        '<function key="otrasFunciones" class="com.raul.appian.texto.function.Otra"/>'
        "</appian-plugin>"
    )
    hallazgos = vb.comprobar(CONTRATO_FN, {}, manifiesto)
    assert {"R-B01", "R-B07"} <= reglas(hallazgos)


def test_sin_manifiesto_R_B07_lo_dice_en_vez_de_callar():
    rutas = {"com/raul/appian/texto/funcionesTexto_en_US.properties": BUNDLE_FN_OK}
    hallazgos = vb.comprobar(CONTRATO_FN, rutas, "")
    assert "R-B07" in reglas(hallazgos)
    assert any("no hay appian-plugin.xml" in h.mensaje for h in hallazgos)


def test_un_modulo_sin_key_es_hallazgo():
    manifiesto = (
        '<appian-plugin key="com.raul.appian.texto">'
        '<function class="com.raul.appian.texto.function.InvertirCadena"/>'
        "</appian-plugin>"
    )
    rutas = {"com/raul/appian/texto/funcionesTexto_en_US.properties": BUNDLE_FN_OK}
    hallazgos = vb.comprobar(CONTRATO_FN, rutas, manifiesto)
    assert "R-B07" in reglas(hallazgos)
    assert any("sin atributo key" in h.mensaje for h in hallazgos)


def test_el_datatype_no_es_un_modulo_con_bundle():
    """Sus <class> no son modulos; exigirles bundle seria un falso positivo en
    todo plug-in que publique tipos propios."""
    manifiesto = (
        '<appian-plugin key="com.raul.appian.texto">'
        '<datatype key="tipos" name="Tipos"><class>com.raul.appian.texto.T</class></datatype>'
        '<function key="funcionesTexto" class="com.raul.appian.texto.function.InvertirCadena"/>'
        "</appian-plugin>"
    )
    rutas = {"com/raul/appian/texto/funcionesTexto_en_US.properties": BUNDLE_FN_OK}
    assert vb.comprobar(CONTRATO_FN, rutas, manifiesto) == []
