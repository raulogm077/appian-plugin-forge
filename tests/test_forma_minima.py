"""La forma MINIMA que la puerta determinista acepta, para los cuatro tipos.

Por que este modulo existe. La bateria anterior corria sobre fixtures con la
forma del camino feliz de UN SOLO tipo: `test_andamiar._contrato()` inyecta
siempre `required`, `paleta` y `bundle`, tres campos que `contrato.validar`
solo exige a los smart services. Ningun test ejercitaba jamas un contrato con
la forma que la puerta de verdad admite, asi que la suite no podia ver ni el
`KeyError: 'required'` que mataba a tres de los cuatro tipos ni el `key=""`
que producia un contrato sin `[bundle]`.

La invariante que se fija aqui es una sola, y es exactamente aquello para lo
que la puerta determinista existe:

    LO QUE LA PUERTA DEJA PASAR, EL ANDAMIADOR LO PROCESA.

Si `validar()` devuelve la lista vacia, `generar()` no puede morir. Que
fallara ahi era el peor sitio posible: la puerta es la que promete que no
ocurra.

Los fixtures no son ejemplos bonitos a proposito — son el contrato mas pobre
que el sistema promete aceptar para cada tipo.
"""

import pathlib
import re
import xml.etree.ElementTree as ET

import pytest

import andamiar
import contrato
import verificar_bundles

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "contratos"
PLANTILLAS = pathlib.Path(__file__).resolve().parents[1] / "assets" / "plantillas"

# Los cuatro tipos de la Fase 1, cada uno con su fixture de forma minima.
MINIMOS = {
    "function": "function-minimo.md",
    "writer-function": "writer-function-minimo.md",
    "smart-service": "smart-service-minimo.md",
    "servlet": "servlet-minimo.md",
}
TIPOS = sorted(MINIMOS)

# Los tres tipos que cargan un bundle de recursos. El servlet queda fuera: su
# name/description van como atributos del manifiesto, no en un .properties
# (nota de alcance de la capa 1C en assets/reglas-de-validacion.md).
TIPOS_CON_BUNDLE = ("function", "writer-function", "smart-service")


def cargar(tipo: str) -> dict:
    return contrato.cargar(FIXTURES / MINIMOS[tipo])


def ruta_contrato(tipo: str) -> pathlib.Path:
    """La ruta del fixture, para pasarla como `contrato_origen` a `generar()`.

    Nombre distinto de `cargar()`/`ruta` a proposito: varias funciones de
    este modulo ya usan `ruta` como variable local (p. ej. `for ruta in
    escritos:`), y una funcion de modulo con ese mismo nombre se volveria
    inalcanzable dentro de ellas -- Python trata el nombre como local en
    toda la funcion en cuanto se le asigna una vez, aunque sea mas abajo.
    """
    return FIXTURES / MINIMOS[tipo]


@pytest.mark.parametrize("tipo", TIPOS)
def test_la_forma_minima_pasa_la_puerta_determinista(tipo):
    """Si esto falla, el fixture dejo de ser «lo minimo que la puerta acepta»."""
    faltantes = contrato.validar(cargar(tipo))
    assert faltantes == [], f"{MINIMOS[tipo]} ya no pasa la puerta: {faltantes}"


@pytest.mark.parametrize("tipo", TIPOS)
def test_lo_que_la_puerta_deja_pasar_el_andamiador_lo_procesa(tipo, tmp_path):
    """LA invariante. Verificada en rojo antes de la correccion: con el
    `andamiar.py` sin corregir, los tres tipos que no son smart-service morian
    aqui con `KeyError: 'required'` —subindice duro sobre un campo que la
    puerta solo exige a los smart services—, y el smart service pasaba.
    """
    datos = cargar(tipo)
    assert contrato.validar(datos) == [], "el fixture debe pasar la puerta primero"

    escritos = andamiar.generar(datos, PLANTILLAS, tmp_path, ruta_contrato(tipo))

    assert escritos
    for ruta in escritos:
        assert ruta.is_file(), f"{ruta} se declaro escrita pero no existe"


@pytest.mark.parametrize("tipo", TIPOS)
def test_docs_contrato_md_es_copia_literal_del_fixture(tipo, tmp_path):
    """Critico 2 del gate de ciclo 1, los CUATRO tipos por igual:
    `verificar_todo.py` lee `docs/contrato.md` sin condicionar al tipo de
    plugin (Reglas del framework, Politicas AppMarket, Bundles y locales,
    Empaquetado), y `generar_dossier.py` tampoco distingue. "Copia literal"
    se comprueba BYTE A BYTE, no solo como texto: un roundtrip de texto en
    Windows convertiria los `\\n` del fixture a CRLF al escribir.
    """
    escritos = andamiar.generar(cargar(tipo), PLANTILLAS, tmp_path, ruta_contrato(tipo))
    destino = tmp_path / "docs" / "contrato.md"
    assert destino in escritos
    assert destino.read_bytes() == ruta_contrato(tipo).read_bytes()


@pytest.mark.parametrize("tipo", TIPOS)
def test_el_manifiesto_generado_nunca_lleva_una_key_vacia(tipo, tmp_path):
    """C5. Sobre un contrato sin `[bundle]`, la plantilla de smart service
    emitia `<smart-service key="" …/>` y la de servlet lo mismo, y las cuatro
    puertas decian que si. El oraculo lo zanja: el plug-in publicado en el
    AppMarket declara `key="readEmailFile"`.
    """
    andamiar.generar(cargar(tipo), PLANTILLAS, tmp_path, ruta_contrato(tipo))
    manifiesto = tmp_path / "src" / "main" / "resources" / "appian-plugin.xml"
    raiz = ET.fromstring(manifiesto.read_text(encoding="utf-8"))

    assert raiz.get("key"), "la raiz <appian-plugin> no declara key"
    for elemento in raiz.iter():
        if elemento is raiz or "key" not in elemento.attrib:
            continue
        assert elemento.get("key"), (
            f"<{elemento.tag}> se emitio con key vacia en el manifiesto de {tipo}"
        )


@pytest.mark.parametrize("tipo", TIPOS_CON_BUNDLE)
def test_la_puerta_exige_bundle_a_los_tipos_que_lo_usan(tipo):
    """C5, por el lado de la puerta. `bundle.nombre` alimenta la key del
    manifiesto y el nombre del `.properties`: dejarlo pasar vacio produce un
    artefacto roto que ninguna de las cuatro puertas ve.
    """
    datos = cargar(tipo)
    del datos["bundle"]
    faltantes = contrato.validar(datos)
    assert any("bundle" in f for f in faltantes), (
        f"la puerta acepto un contrato de {tipo} sin [bundle]: {faltantes}"
    )


def test_el_servlet_no_necesita_bundle():
    """La contraparte de la regla de arriba: exigirselo al servlet seria pedir
    un fichero que su capa de validacion excluye expresamente.
    """
    datos = cargar("servlet")
    assert "bundle" not in datos
    assert contrato.validar(datos) == []


@pytest.mark.parametrize("tipo", TIPOS_CON_BUNDLE)
def test_el_validador_de_bundles_aprueba_lo_que_el_andamiador_escribe(tipo, tmp_path):
    """La «quinta instancia» del verde vacuo, cerrada por los dos lados.

    `verificar_bundles` derivaba lo que espera del MISMO dato vacio que
    producia el artefacto roto: sin `[bundle]`, el andamiador escribia
    `_en_US.properties` y `ruta_esperada()` construia la ruta esperada desde
    ese mismo `""`. Los dos lados coincidian en la nada y la puerta salia
    verde. Aqui se comprueba que coinciden en algo REAL: el validador aprueba
    exactamente los ficheros que el andamiador acaba de escribir.
    """
    datos = cargar(tipo)
    andamiar.generar(datos, PLANTILLAS, tmp_path, ruta_contrato(tipo))

    raiz = tmp_path / "src" / "main" / "resources"
    bundles = {
        str(p.relative_to(raiz)).replace("\\", "/"): p.read_text(encoding="utf-8")
        for p in raiz.rglob("*.properties")
    }
    assert bundles, "el andamiador no escribio ningun .properties"
    assert not any(nombre.startswith("_") for nombre in bundles), (
        f"hay un bundle con el nombre base vacio: {sorted(bundles)}"
    )

    errores = [h for h in verificar_bundles.comprobar(datos, bundles) if h.severidad == "error"]
    assert errores == [], [f"{h.regla}: {h.mensaje}" for h in errores]


def test_las_salidas_de_error_se_etiquetan_con_el_nombre_del_accesor(tmp_path):
    """Appian lee el nombre del output del ACCESOR, no del campo.

    La plantilla horneaba `output.errorOccurred.*` mientras la clase genera
    `getErrorOccurred()`, asi que los dos outputs de error salian SIN ETIQUETA
    en el Process Modeler de todo smart service generado. Ninguna de las
    cuatro capas lo veia: R-B03 solo miraba lo que faltaba, nunca lo que
    sobraba, y la clave en minuscula no casa con ningun prefijo de R-B02.

    La caja correcta no es una opinion: el plug-in aprobado por la revision
    real de Appian escribe `output.ErrorOccurred.displayName` (auditoria §7.9).
    """
    datos = cargar("smart-service")
    andamiar.generar(datos, PLANTILLAS, tmp_path, ruta_contrato("smart-service"))

    raiz = tmp_path / "src" / "main" / "resources"
    clase = (tmp_path / "src" / "main" / "java").rglob("*.java")
    fuente = "\n".join(p.read_text(encoding="utf-8") for p in clase)

    for bundle in sorted(raiz.rglob("*.properties")):
        pares = verificar_bundles.parsear_properties(bundle.read_text(encoding="utf-8"))
        for nombre in contrato.SALIDAS_HORNEADAS:
            assert f"output.{nombre}.displayName" in pares, (
                f"{bundle.name} no etiqueta el output «{nombre}», que la clase SI expone"
            )
            # Y el accesor tiene que existir de verdad: si alguien renombrara
            # el getter, esta clave dejaria de etiquetar nada y el test debe
            # caer con el.
            assert f"get{nombre}()" in fuente, (
                f"la clase generada no declara get{nombre}(), pero el bundle lo etiqueta"
            )


@pytest.mark.parametrize("tipo", TIPOS_CON_BUNDLE)
def test_ningun_bundle_generado_repite_una_clave(tipo, tmp_path):
    """Una clave duplicada no rompe el despliegue --gana la ultima-- y por eso
    puede vivir anos en un artefacto sin que nadie la vea.

    El caso real: `CLAVES_SALIDAS` iteraba TODAS las salidas mientras la
    plantilla horneaba ya las dos de error, asi que un contrato que las
    declarase --el del plug-in aprobado del AppMarket las declara-- emitia
    `output.ErrorOccurred.displayName` dos veces.
    """
    datos = cargar(tipo)
    andamiar.generar(datos, PLANTILLAS, tmp_path, ruta_contrato(tipo))

    raiz = tmp_path / "src" / "main" / "resources"
    for bundle in sorted(raiz.rglob("*.properties")):
        claves = [
            linea.split("=", 1)[0].strip()
            for linea in bundle.read_text(encoding="utf-8").splitlines()
            if linea.strip() and not linea.strip().startswith(("#", "!")) and "=" in linea
        ]
        repetidas = sorted({k for k in claves if claves.count(k) > 1})
        assert not repetidas, f"{bundle.name} repite las claves {repetidas}"


# ---------------------------------------------------------------------------
# C3, agravante · el andamiador nunca escribia LICENSE ni
# THIRD_PARTY_NOTICES.md, y R-J07 los exige dentro del JAR. Todo plug-in
# recien generado incumplia una regla del propio sistema: `build.gradle` los
# copia de la raiz a META-INF, pero no habia nada que copiar.
# ---------------------------------------------------------------------------

FICHEROS_DE_LICENCIA = ("LICENSE", "THIRD_PARTY_NOTICES.md")


@pytest.mark.parametrize("tipo", TIPOS)
@pytest.mark.parametrize("nombre", FICHEROS_DE_LICENCIA)
def test_el_andamiador_emite_los_ficheros_que_R_J07_exige(tipo, nombre, tmp_path):
    escritos = andamiar.generar(cargar(tipo), PLANTILLAS, tmp_path, ruta_contrato(tipo))
    ruta = tmp_path / nombre
    assert ruta in escritos, f"{nombre} no figura entre los ficheros escritos"
    assert ruta.is_file()
    assert ruta.read_text(encoding="utf-8").strip(), f"{nombre} se escribio vacio"


def test_el_bloque_de_empaquetado_copia_de_donde_el_andamiador_escribe(tmp_path):
    """Los dos extremos de la misma cadena: `build.gradle` copia
    `LICENSE`/`THIRD_PARTY_NOTICES.md` de la RAIZ del proyecto a `META-INF/`,
    que es donde R-J07 los busca. Si el andamiador los pusiera en otro sitio,
    los tests de arriba pasarian y el JAR seguiria incumpliendo.
    """
    andamiar.generar(cargar("smart-service"), PLANTILLAS, tmp_path, ruta_contrato("smart-service"))
    build = (tmp_path / "build.gradle").read_text(encoding="utf-8")
    assert "into('META-INF')" in build
    for nombre in FICHEROS_DE_LICENCIA:
        assert f"from('{nombre}')" in build
        assert (tmp_path / nombre).is_file()


# ---------------------------------------------------------------------------
# Hallazgo de la verificacion final (fuera del encargo, misma familia): dos de
# los cuatro tipos andamiados NO podian pasar su propio criterio de salida del
# paso BUILD --`./gradlew build` con BUILD SUCCESSFUL-- porque `spotbugsMain`
# fallaba sobre codigo que escribe la PLANTILLA:
#
#   smart-service  CRLF_INJECTION_LOGS  en el LOG.error del manejo de errores
#   servlet        SnVI                 sin serialVersionUID
#                  SECSP                getParameter, inherente a un servlet
#
# Los dos primeros los cierra esta tanda. El proyecto de referencia --publicado
# y aprobado por la revision real de Appian, con esta MISMA cadena
# SpotBugs+FindSecBugs-- resuelve el CRLF con una exclusion acotada a la clase
# y al patron, con el motivo escrito dentro, y conserva `ignoreFailures =
# false` y `reportLevel = LOW`. La cadena de plantillas habia adoptado
# SpotBugs pero NO su fichero de exclusiones: adopcion incompleta.
#
# `SECSP` se queda abierto a proposito: ver la nota dentro del propio
# exclude.xml generado.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tipo", TIPOS)
def test_el_proyecto_generado_trae_el_filtro_de_exclusiones_de_spotbugs(tipo, tmp_path):
    andamiar.generar(cargar(tipo), PLANTILLAS, tmp_path, ruta_contrato(tipo))
    filtro = tmp_path / "config" / "spotbugs" / "exclude.xml"
    assert filtro.is_file(), "el proyecto de referencia lo trae y la plantilla no lo copiaba"
    assert "excludeFilter = file('config/spotbugs/exclude.xml')" in (
        tmp_path / "build.gradle"
    ).read_text(encoding="utf-8")
    # Lo que NO se toca: relajar el umbral seria un verde vacuo con cara de
    # fichero de configuracion.
    build = (tmp_path / "build.gradle").read_text(encoding="utf-8")
    assert "ignoreFailures = false" in build
    assert "Confidence.valueOf('LOW')" in build


def test_la_exclusion_del_CRLF_apunta_a_la_clase_generada_y_dice_por_que(tmp_path):
    """Acotada a la clase real y al patron concreto, como la del proyecto de
    referencia. Una exclusion global seria silenciar al validador.
    """
    andamiar.generar(cargar("smart-service"), PLANTILLAS, tmp_path, ruta_contrato("smart-service"))
    filtro = (tmp_path / "config" / "spotbugs" / "exclude.xml").read_text(encoding="utf-8")
    assert "CRLF_INJECTION_LOGS" in filtro
    assert "com.raul.appian.archivar.smartservice.ArchivarDocumentoSmartService" in filtro
    assert "UUID" in filtro, "una exclusion sin su porque es una exclusion a ciegas"


def test_el_servlet_declara_serialVersionUID(tmp_path):
    andamiar.generar(cargar("servlet"), PLANTILLAS, tmp_path, ruta_contrato("servlet"))
    java = (tmp_path / "src/main/java/com/raul/appian/estado/servlet/EstadoServlet.java"
            ).read_text(encoding="utf-8")
    assert "serialVersionUID" in java


def test_una_function_no_excluye_el_CRLF_que_no_puede_cometer(tmp_path):
    """Excluir un fallo que ese tipo no puede cometer es ruido, y ensena a
    coleccionar exclusiones por si acaso.
    """
    andamiar.generar(cargar("function"), PLANTILLAS, tmp_path, ruta_contrato("function"))
    filtro = (tmp_path / "config" / "spotbugs" / "exclude.xml").read_text(encoding="utf-8")
    assert "<Match>" not in filtro


# ---------------------------------------------------------------------------
# RESERVA 2 · la SKILL fijaba un criterio que un servlet no puede cumplir.
#
# Su criterio de salida del paso BUILD es «BUILD SUCCESSFUL al cierre de cada
# slice». Un servlet recien andamiado NO lo consigue: SECSP dispara en todo
# servlet que lea un parametro, y eso se dejo abierto A PROPOSITO (NOTA_SECSP
# en andamiar.py). El defecto no es la exclusion abierta --esa decision esta
# razonada-- sino que `SECSP` no aparecia NI UNA VEZ en la SKILL: quien
# condujera el pipeline leeria un fallo ESPERADO como una averia y lo
# «arreglaria» por el camino equivocado, que es excluir el detector.
#
# Un criterio que nadie puede cumplir ensena a saltarselo. Es el mismo defecto
# que el Critical 3, reubicado.
# ---------------------------------------------------------------------------

SKILL_MD = (
    pathlib.Path(__file__).resolve().parents[1]
    / "skills" / "crear-plugin-appian" / "SKILL.md"
)


def _seccion(texto: str, encabezado: str) -> str:
    """El cuerpo de una seccion `### ...`, hasta el siguiente encabezado."""
    lineas = texto.splitlines()
    inicio = next(
        (i for i, l in enumerate(lineas) if l.startswith("### ") and encabezado in l), None
    )
    assert inicio is not None, f"la SKILL ya no tiene la seccion «{encabezado}»"
    fin = next(
        (i for i, l in enumerate(lineas[inicio + 1:], inicio + 1) if l.startswith(("## ", "### "))),
        len(lineas),
    )
    return "\n".join(lineas[inicio:fin])


def test_la_seccion_BUILD_de_la_skill_nombra_la_excepcion_SECSP():
    """Sin esto, el criterio «BUILD SUCCESSFUL» es insatisfacible para un
    servlet y nadie lo sabe leyendo la SKILL.
    """
    build = _seccion(SKILL_MD.read_text(encoding="utf-8"), "BUILD, parte 2")
    assert "SECSP" in build, (
        "la seccion BUILD exige BUILD SUCCESSFUL y no nombra el unico fallo que un "
        "servlet recien generado tiene ABIERTO a proposito"
    )
    assert "servlet" in build.lower()


def test_la_skill_dice_que_hacer_con_el_SECSP_y_enlaza_el_argumento():
    """Nombrar la excepcion sin decir que hacer solo cambia una confusion por
    otra. Lo que hay que hacer es implementar la logica del servlet y decidir
    ENTONCES, con conocimiento, si la exclusion procede.
    """
    build = _seccion(SKILL_MD.read_text(encoding="utf-8"), "BUILD, parte 2")
    assert "config/spotbugs/exclude.xml" in build, (
        "no enlaza el fichero donde vive el argumento completo"
    )


def test_la_skill_enlaza_la_nota_del_exclude_en_vez_de_copiarla():
    """Regla del proyecto: no duplicar, enlazar. Dos copias divergen, y la que
    se queda vieja es siempre la del documento que nadie regenera.
    """
    build = _seccion(SKILL_MD.read_text(encoding="utf-8"), "BUILD, parte 2")
    assert "<Match>" not in build and "<Bug pattern" not in build, (
        "la SKILL copia el bloque XML del exclude.xml en vez de enlazarlo"
    )


# ---------------------------------------------------------------------------
# LOS NUMEROS DE LA PROSA, ANCLADOS EN LA PUERTA QUE LOS PRODUCE
#
# El gate del ciclo 11 encontro dos numeros que el codigo desmiente: la SKILL
# decia «cinco filas delegadas» sobre un `PUERTAS_DELEGADAS` de ocho claves
# --fosil de cuando «Licencias de terceros» seguia ahi-- y su criterio de
# salida hablaba de «la unica» puerta que un BUILD SUCCESSFUL no puede aprobar
# sobre un conjunto de dos. El segundo no era cosmetico: quien aplicase ese
# criterio a mano sobre un proyecto RIGUROSO que el script certifica READY
# concluiria que hay algo roto que esta bien.
#
# Los dos se corrigieron a mano, y a mano se vuelven a desincronizar la
# proxima vez que una puerta entre o salga del conjunto. Por eso van anclados
# aqui y no en una revision: la revision es la capa que ya fallo.
#
# COMO SE CUMPLE LA REGLA DE LA CASA --el aserto no deriva su expectativa de lo
# que vigila--: lo vigilado es la PROSA, y la expectativa sale de las
# constantes de `verificar_todo`. Son dos fuentes independientes; el test lee
# el numeral escrito en la SKILL y lo compara con un recuento del fuente. Lo
# que NO hace, y seria vacuo, es reescribir la prosa desde la constante.
# ---------------------------------------------------------------------------

# Los numerales que la prosa de la SKILL puede escribir. Literal PROPIO del
# test, no derivado de nada: es el diccionario que traduce la lengua de la
# prosa a la del codigo. Si la SKILL escribe un numeral que no esta aqui, el
# test falla diciendo eso en vez de absolver por no entenderlo.
_NUMERALES = {
    "una": 1, "unica": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11,
}

# Un numeral escrito en negrita: asi los escribe la prosa de la SKILL, y la
# negrita es lo que impide capturar cualquier palabra suelta de alrededor.
_PATRON_NUMERAL = r"\*\*([A-Za-zÁÉÍÓÚáéíóúÑñ]+)\*\*"


def _numeral(palabra: str, donde: str) -> int:
    clave = palabra.strip().lower().replace("ú", "u").replace("í", "i")
    assert clave in _NUMERALES, (
        f"{donde}: la SKILL escribe «{palabra}», que no es un numeral que este test sepa "
        f"leer. Anadelo a _NUMERALES o escribe el numero con una palabra de la lista"
    )
    return _NUMERALES[clave]


def test_la_skill_cuenta_bien_sus_filas_delegadas():
    """«Cinco filas delegadas» sobre ocho claves: el numero que el codigo
    desmiente. Se lee el numeral de la prosa y se cuenta el fuente aparte.
    """
    import verificar_todo as vt

    texto = SKILL_MD.read_text(encoding="utf-8")
    assert "filas delegadas" in texto, (
        "la SKILL ya no habla de sus «filas delegadas»: la frase que este test ancla "
        "desaparecio de la prosa"
    )
    en_estandar = set(vt.PUERTAS_DELEGADAS) & set(vt.PUERTAS_AMBOS_PERFILES)
    for perfil, esperado, detalle in (
        ("RIGUROSO", len(vt.PUERTAS_DELEGADAS), sorted(vt.PUERTAS_DELEGADAS)),
        ("ESTÁNDAR", len(en_estandar), sorted(en_estandar)),
    ):
        escritos = re.findall(_PATRON_NUMERAL + r" en " + perfil, texto)
        # Suelo antivacuidad: un patron que deja de casar nada satisface el
        # bucle sin mirar nada, que es el defecto que este test cierra.
        assert escritos, (
            f"la SKILL ya no dice cuantas filas delegadas trae un certificado {perfil}: "
            f"el numero que este test ancla desaparecio de la prosa"
        )
        for palabra in escritos:
            assert _numeral(palabra, f"filas delegadas en {perfil}") == esperado, (
                f"la SKILL dice «{palabra}» filas delegadas en {perfil} y el fuente cuenta "
                f"{esperado}: {detalle}"
            )


def test_el_criterio_de_salida_cuenta_bien_las_que_el_build_no_aprueba():
    """El criterio del paso 5 decia «la unica» sobre un conjunto de dos.

    Es el numero con consecuencia: aplicado a mano, un proyecto RIGUROSO que el
    script certifica READY incumple el criterio tal como estaba escrito.
    """
    import verificar_todo as vt

    texto = SKILL_MD.read_text(encoding="utf-8")
    # Anclado en «no puede aprobar», que es la frase propia de ESTE criterio: el
    # punto 2 del mismo bloque tambien dice «dos» --las dos filas rojas
    # estructurales, que son otras-- y anclar por cercania a «delegada» las
    # confundiria. El numeral va DESPUES de la frase, dentro de la misma oracion
    # (`[^.]`), que es como esta escrito el criterio.
    escritos = re.findall(r"no puede aprobar[^.]{0,120}?" + _PATRON_NUMERAL, texto)
    assert escritos, (
        "la SKILL ya no dice cuantas puertas quedan en «delegada» por no poder aprobarlas un "
        "BUILD SUCCESSFUL: el numero que este test ancla desaparecio de la prosa"
    )
    esperado = len(vt.PUERTAS_QUE_EL_BUILD_NO_APRUEBA)
    for palabra in escritos:
        assert _numeral(palabra, "puertas que el build no aprueba") == esperado, (
            f"la SKILL dice «{palabra}» y `verificar_todo.PUERTAS_QUE_EL_BUILD_NO_APRUEBA` "
            f"tiene {esperado}: {sorted(vt.PUERTAS_QUE_EL_BUILD_NO_APRUEBA)}"
        )


# ---------------------------------------------------------------------------
# LOS NUMEROS DE `certificado.md`, ANCLADOS IGUAL QUE LOS DE LA SKILL
#
# El gate del ciclo 12 midio el reparto de guardianes y encontro el hueco:
# `SKILL.md` tenia dos tests que leen su prosa, `entrevista.md` uno,
# `tipos-de-plugin.md` no tiene numeros — y `certificado.md`, que es el fichero
# con MAS cuentas de los cuatro, no tenia ninguno. De las que la lente conto a
# mano, exactamente una estaba mal: «resuelve LAS DEMAS leyendo la salida del
# build» sobre un reparto de once menos seis, cuando las que salen del log son
# cuatro y la undecima es informativa.
#
# La regla de la casa se cumple igual que arriba: se lee el numeral de la PROSA
# y la expectativa se cuenta aparte, sobre las constantes de `verificar_todo`.
# Lo que no se hace, y seria vacuo, es reescribir la prosa desde la constante.
# ---------------------------------------------------------------------------

ENTREVISTA_MD = (
    pathlib.Path(__file__).resolve().parents[1]
    / "skills" / "crear-plugin-appian" / "referencias" / "entrevista.md"
)

CERTIFICADO_MD = (
    pathlib.Path(__file__).resolve().parents[1]
    / "skills" / "crear-plugin-appian" / "referencias" / "certificado.md"
)


def _numeral_tras(texto: str, anclaje: str, donde: str) -> int:
    """El numeral en negrita PEGADO a `anclaje` — solo espacios en medio.

    Pegado y no «dentro de la misma oracion», que es lo que hacen los dos
    anclajes de la SKILL: alli el numeral va separado de su frase y hay que
    barrer. Aqui la holgura era peligrosa y lo demostro el primer intento de
    este test — con `ejecuta[^.]{0,160}?` el encabezado «## Quien ejecuta cada
    puerta» casaba y capturaba el «once» del parrafo siguiente. Una expectativa
    leida del sitio equivocado es peor que ninguna: pasa o falla por su cuenta.
    """
    escritos = re.findall(anclaje + r"\s+" + _PATRON_NUMERAL, texto)
    assert escritos, (
        f"{donde}: `certificado.md` ya no dice el numero que este test ancla — la frase "
        f"«{anclaje}» dejo de ir seguida de un numeral en negrita"
    )
    return _numeral(escritos[0], donde)


def test_certificado_md_cuenta_bien_las_puertas_comunes():
    import verificar_todo as vt

    texto = CERTIFICADO_MD.read_text(encoding="utf-8")
    escrito = _numeral_tras(texto, r"comunes a los dos perfiles son", "puertas comunes")
    assert escrito == len(vt.PUERTAS_AMBOS_PERFILES), (
        f"`certificado.md` dice «{escrito}» puertas comunes y `PUERTAS_AMBOS_PERFILES` "
        f"tiene {len(vt.PUERTAS_AMBOS_PERFILES)}: {sorted(vt.PUERTAS_AMBOS_PERFILES)}"
    )


def test_certificado_md_reparte_las_once_sin_perder_ninguna():
    """El numero que estaba mal, y el que lo hace comprobable: las que ejecuta
    por invocacion directa mas las que resuelve del log mas la informativa
    tienen que sumar EXACTAMENTE las comunes. Un reparto que no suma es lo que
    dejo escrito «las demas» donde no cabian «las demas».
    """
    import verificar_todo as vt

    texto = CERTIFICADO_MD.read_text(encoding="utf-8")
    directas = _numeral_tras(texto, r"este script ejecuta", "puertas por invocacion directa")
    del_log = _numeral_tras(texto, r"resuelve", "puertas resueltas del log")

    # Los dos conjuntos se intersecan con `PUERTAS_AMBOS_PERFILES`, que es de
    # lo que habla la frase: «de esas ONCE, este script ejecuta seis…». Contar
    # `PUERTAS_CON_INVOCACION` entera coincide hoy --las seis con guion son
    # comunes-- y dejaria de coincidir en cuanto una puerta de RIGUROSO tuviera
    # script propio: la prosa seguiria diciendo la verdad y el test la pondria
    # roja. Es el patron que ya usa el test hermano de las filas delegadas.
    # Levantado por el /code-review del ciclo 12.
    comunes = set(vt.PUERTAS_AMBOS_PERFILES)
    con_guion = set(vt.PUERTAS_CON_INVOCACION) & comunes
    assert directas == len(con_guion), (
        f"«{directas}» por invocacion directa frente a las {len(con_guion)} comunes que la "
        f"tienen: {sorted(con_guion)}"
    )
    del_build = set(vt.PUERTAS_DELEGADAS) & comunes
    assert del_log == len(del_build), (
        f"«{del_log}» resueltas leyendo el log frente a las {len(del_build)} que lo son de "
        f"verdad: {sorted(del_build)}"
    )

    informativas = comunes - con_guion - del_build
    assert len(informativas) == 1, (
        f"el reparto de `certificado.md` no suma: {directas} directas + {del_log} del log "
        f"dejan {len(informativas)} sin explicar sobre {len(comunes)} comunes "
        f"({sorted(informativas)}). Cada puerta comun cae en una de las tres cestas"
    )

    # Y la prosa NOMBRA la que cierra la cuenta, por su nombre real de fila.
    # `"informativa" in texto` no valia: la leyenda de los seis estados ya trae
    # esa palabra, asi que el aserto se satisfacia aunque el parrafo entero
    # desapareciera --comprobado por el /code-review borrandolo: dos verdes--.
    # Un guardian que aprueba desde otra seccion del documento no vigila nada.
    # Se compara SIN TILDES: el nombre de la fila viaja en ASCII dentro de
    # `verificar_todo` («Deriva contra la version del entorno») y la prosa lo
    # escribe en castellano correcto, con tilde. Comparar en crudo habria
    # puesto rojo un documento bien escrito.
    (fila,) = informativas
    plano, fila_plana = _sin_tildes(texto), _sin_tildes(fila)
    assert fila_plana in plano, (
        f"el reparto suma pero la prosa ya no nombra «{fila}», que es la fila informativa "
        f"que cierra la cuenta de las {len(comunes)} comunes"
    )
    assert "informativa" in plano.split(fila_plana, 1)[1][:200], (
        f"la prosa nombra «{fila}» pero ya no la presenta como informativa donde la nombra"
    )


def _sin_tildes(texto: str) -> str:
    import unicodedata
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


def test_entrevista_cuenta_bien_las_asignaciones_de_cada_tipo():
    """Los cuatro numeros de `entrevista.md`, anclados a los fixtures.

    «16 el servlet, 17 la writer-function, 20 la function, 22 el smart
    service». El gate del ciclo 12 los verifico exactos y marco que nadie los
    vigila: son la misma clase de numero que este modulo ancla para la SKILL,
    contando lo mismo, y se quedaron a mano. El reparto es lo que sostiene el
    argumento de la seccion —«no conviertas veintitantas asignaciones en otros
    tantos turnos»—, asi que un numero rancio aqui deforma el consejo, no solo
    el dato.

    La expectativa se cuenta sobre los FIXTURES, que son fuente independiente
    de la prosa: una asignacion TOML es una linea `clave = valor` dentro del
    bloque, sin contar encabezados de seccion ni comentarios.
    """
    texto = ENTREVISTA_MD.read_text(encoding="utf-8")

    for tipo, fichero in sorted(MINIMOS.items()):
        # El numeral va en cifra y pegado al nombre del tipo: «16 el servlet».
        # El guion del tipo casa tambien como espacio: la prosa escribe «smart
        # service» en castellano corriente y `smart-service` es la clave del
        # esquema. El test lee la prosa como esta escrita en vez de obligarla a
        # deletrear una clave.
        nombre_en_prosa = re.escape(tipo).replace(r"\-", "[- ]")
        escritos = re.findall(r"(\d+)\s+(?:el|la)\s+" + nombre_en_prosa, texto)
        assert escritos, (
            f"`entrevista.md` ya no dice cuantas asignaciones trae el contrato minimo de "
            f"«{tipo}»: el numero que este test ancla desaparecio de la prosa"
        )
        real = _asignaciones_toml((FIXTURES / fichero).read_text(encoding="utf-8"))
        for escrito in escritos:
            assert int(escrito) == real, (
                f"`entrevista.md` dice «{escrito}» asignaciones para {tipo} y "
                f"{fichero} tiene {real}"
            )

    # Y el rango que la prosa enuncia encima tiene que abarcarlos de verdad.
    rango = re.search(r"\*\*entre (\d+) y (\d+) asignaciones\*\*", texto)
    assert rango, (
        "`entrevista.md` ya no enuncia el rango «entre N y M asignaciones»: es la frase "
        "que sostiene el argumento de la seccion, y este test la ancla"
    )
    minimo, maximo = rango.groups()
    reales = [
        _asignaciones_toml((FIXTURES / f).read_text(encoding="utf-8"))
        for f in MINIMOS.values()
    ]
    assert (int(minimo), int(maximo)) == (min(reales), max(reales)), (
        f"la prosa dice «entre {minimo} y {maximo}» y los cuatro fixtures dan "
        f"{min(reales)}–{max(reales)}"
    )


def _asignaciones_toml(markdown: str) -> int:
    """Las lineas `clave = valor` del bloque ```toml```, que es lo que un humano
    escribe al dictar el contrato. No cuentan encabezados `[seccion]`,
    `[[lista]]`, comentarios ni lineas en blanco.
    """
    dentro, total = False, 0
    for linea in markdown.splitlines():
        if linea.strip().startswith("```"):
            dentro = linea.strip().startswith("```toml")
            continue
        pelada = linea.strip()
        if dentro and pelada and not pelada.startswith(("#", "[")) and "=" in pelada:
            total += 1
    return total


# --- La unica flecha que vuelve atras --------------------------------------
# El paso 6 manda corregir codigo y ningun paso obligaba a volver al 5, asi que
# el paso 7 podia empotrar un certificado anterior a esa correccion. La skill
# ya prohibia el resultado en sus Red Flags --«se certifica [...] con una
# [salida] capturada antes del ultimo cambio del fuente»-- pero el Proceso no
# lo hacia cumplir. Levantado por el gate del ciclo 13.


def test_el_paso_6_manda_volver_a_VERIFICAR_lo_que_acaba_de_corregir():
    revision = _seccion(SKILL_MD.read_text(encoding="utf-8"), "REVISIÓN")
    criterio = revision.split("Criterio de salida")[-1]
    assert "paso 5" in criterio, (
        "el criterio de salida del paso 6 no manda volver a verificar tras corregir: el "
        "certificado que el paso 7 empotra describiria el arbol de antes de la correccion"
    )


def test_lo_que_el_paso_6_promete_lo_cumple_el_generador_del_dossier():
    """Suelo antivacuidad de la prosa de arriba: la SKILL puede prometer una red
    que nadie tiende. Aqui se comprueba que la pieza existe de verdad y que el
    dossier la usa --no que este escrita en un documento--.
    """
    import inspect

    import generar_dossier
    import salida_build

    assert hasattr(salida_build, "fuente_posterior_a"), (
        "desaparecio la nocion de rancidez reutilizable; el dossier no puede declarar un "
        "certificado rancio y la promesa del paso 6 se queda en prosa"
    )
    fuente = inspect.getsource(generar_dossier.main_con_raiz)
    assert "fuente_posterior_a" in fuente, (
        "`generar_dossier.main_con_raiz` volvio a empotrar `docs/CERTIFICADO.md` sin mirar si "
        "es anterior al ultimo cambio del fuente"
    )


# --- Los cuatro numerales que quedaban exactos y sin nadie que los mirara ----
# Misma familia que los que anclaron los ciclos 11 y 12: cuentas de prosa que
# se desincronizan en silencio en cuanto entra o sale una puerta. Levantados
# por el gate del ciclo 13.


def test_certificado_md_cuenta_bien_LAS_FILAS_de_cada_perfil():
    """«13 filas en ESTANDAR y 17 en RIGUROSO» es el numero que mas lee un
    humano, y el que mas se mueve: cambia con cada puerta que entra o sale.
    """
    import verificar_todo as vt

    texto = CERTIFICADO_MD.read_text(encoding="utf-8")
    escritos = re.findall(r"\*\*(\d+) filas en ESTÁNDAR y (\d+) en RIGUROSO\*\*", texto)
    assert escritos, (
        "`certificado.md` ya no dice cuantas filas trae la tabla de cada perfil: el numero "
        "que este test ancla desaparecio de la prosa"
    )
    estandar = len(vt.PUERTAS_AMBOS_PERFILES) + len(vt.PUERTAS_NUNCA_VERIFICABLES)
    riguroso = estandar + len(vt.PUERTAS_RIGUROSO)
    for e, r in escritos:
        assert (int(e), int(r)) == (estandar, riguroso), (
            f"`certificado.md` dice {e}/{r} filas y el fuente cuenta {estandar}/{riguroso}: "
            f"{len(vt.PUERTAS_AMBOS_PERFILES)} comunes + "
            f"{len(vt.PUERTAS_NUNCA_VERIFICABLES)} nunca verificables "
            f"(+ {len(vt.PUERTAS_RIGUROSO)} de RIGUROSO)"
        )


def test_certificado_md_cuenta_bien_LAS_PUERTAS_QUE_DECLARAN_PORTANTE():
    """La expectativa se cuenta sobre el fuente de los scripts --donde vive el
    `portante=`-- y lo vigilado es la prosa. Dos fuentes, como manda el patron.
    """
    import verificar_todo as vt

    texto = CERTIFICADO_MD.read_text(encoding="utf-8")
    escritos = re.findall(
        r"\*\*(\w+) puertas en RIGUROSO y (\w+) en ESTÁNDAR\*\*", texto
    )
    assert escritos, (
        "`certificado.md` ya no dice cuantas puertas declaran unidad portante: el numero "
        "que este test ancla desaparecio de la prosa"
    )

    portantes = [
        p
        for script in sorted((pathlib.Path(__file__).resolve().parents[1] / "scripts").glob("*.py"))
        for p in re.findall(r'portante="(\w+)"', script.read_text(encoding="utf-8"))
    ]
    assert len(portantes) >= 2, (
        f"el barrido de `portante=` encontro {len(portantes)}: dejo de leer el fuente y "
        f"este guardian se habria quedado ciego"
    )
    # La unica que no existe en ESTANDAR es la de property tests, que es una
    # puerta de RIGUROSO. Se comprueban las dos mitades de esa afirmacion.
    solo_riguroso = [p for p in portantes if p == "property_tests"]
    assert len(solo_riguroso) == 1, (
        f"cambio el reparto de portantes por perfil: {portantes}. Si `property_tests` dejo "
        f"de ser la unica exclusiva de RIGUROSO, esta cuenta hay que rehacerla"
    )
    assert any("property" in nombre.lower() for nombre in vt.PUERTAS_RIGUROSO), (
        "la puerta de property tests ya no esta en PUERTAS_RIGUROSO, asi que su portante "
        "cuenta tambien en ESTANDAR y la prosa se quedo vieja"
    )
    for riguroso, estandar in escritos:
        assert _numeral(riguroso, "portantes en RIGUROSO") == len(portantes), (
            f"`certificado.md` dice «{riguroso}» puertas con portante en RIGUROSO y el "
            f"fuente declara {len(portantes)}: {portantes}"
        )
        esperado_estandar = len(portantes) - len(solo_riguroso)
        assert _numeral(estandar, "portantes en ESTANDAR") == esperado_estandar, (
            f"`certificado.md` dice «{estandar}» en ESTANDAR y el fuente deja "
            f"{esperado_estandar} al quitar {solo_riguroso}"
        )


def test_certificado_md_cuenta_bien_LOS_ESTADOS_de_una_fila():
    import verificar_todo as vt

    texto = CERTIFICADO_MD.read_text(encoding="utf-8")
    escritos = re.findall(r"##\s+Los (\w+) estados posibles", texto)
    assert escritos, (
        "`certificado.md` ya no encabeza la leyenda con cuantos estados hay: el numero que "
        "este test ancla desaparecio"
    )
    assert _numeral(escritos[0], "estados posibles") == len(vt.SIMBOLO), (
        f"`certificado.md` dice «{escritos[0]}» estados y `SIMBOLO` define "
        f"{len(vt.SIMBOLO)}: {sorted(vt.SIMBOLO)}"
    )


def test_la_skill_cuenta_bien_LAS_PUERTAS_QUE_ANADE_RIGUROSO():
    import verificar_todo as vt

    texto = SKILL_MD.read_text(encoding="utf-8")
    escritos = re.findall(r"RIGUROSO añade (\w+) puertas más", texto)
    assert escritos, (
        "la SKILL ya no dice cuantas puertas anade RIGUROSO: el numero que este test ancla "
        "desaparecio de la prosa"
    )
    assert _numeral(escritos[0], "puertas que anade RIGUROSO") == len(vt.PUERTAS_RIGUROSO), (
        f"la SKILL dice «{escritos[0]}» puertas mas y `PUERTAS_RIGUROSO` tiene "
        f"{len(vt.PUERTAS_RIGUROSO)}: {sorted(vt.PUERTAS_RIGUROSO)}"
    )


# --- El aviso de Windows, donde el lector tropieza --------------------------
# El convenio `$env:` vivia SOLO en `referencias/certificado.md`, que la SKILL
# manda abrir en el paso 5; la primera linea ejecutable con
# `${CLAUDE_PLUGIN_ROOT}` se publica en el paso 1. Un usuario de PowerShell se
# comia la expansion vacia y silenciosa cuatro pasos antes de poder leer el
# documento que se lo advierte. Levantado por el gate del ciclo 14.

LINEAS_DE_MARGEN = 12


def test_el_aviso_de_POWERSHELL_va_JUNTO_al_primer_comando_que_lo_necesita():
    """Lo que se vigila es la PROXIMIDAD, no el orden.

    El nombre anterior --«llega antes que»-- prometia mas de lo que el aserto
    comprueba: la ventana se abre a los dos lados del comando, y hoy el aviso
    esta tres lineas POR DEBAJO. Eso es correcto y deliberado (en markdown
    renderizado se lee de un vistazo), pero un mensaje de fallo que describe un
    estado que se cumple mientras el test esta verde es el mismo defecto que
    este repositorio persigue en la prosa. Levantado por el gate del ciclo 15.
    """
    lineas = SKILL_MD.read_text(encoding="utf-8").splitlines()
    primera = next(
        (i for i, l in enumerate(lineas) if 'python "${CLAUDE_PLUGIN_ROOT}' in l), None
    )
    assert primera is not None, (
        "la SKILL ya no publica ninguna linea `python \"${CLAUDE_PLUGIN_ROOT}/...\"`: si los "
        "comandos cambiaron de forma, este guardian mira lo que ya no existe"
    )
    desde = max(0, primera - LINEAS_DE_MARGEN)
    ventana = "\n".join(lineas[desde: primera + 1 + LINEAS_DE_MARGEN])
    assert "$env:CLAUDE_PLUGIN_ROOT" in ventana, (
        f"el primer comando con `${{CLAUDE_PLUGIN_ROOT}}` esta en la linea {primera + 1} y en "
        f"las {LINEAS_DE_MARGEN} lineas de alrededor no hay aviso de que en PowerShell eso se "
        f"expande a cadena vacia: quien trabaje en Windows se come el fallo silencioso sin "
        f"tener la advertencia a la vista"
    )


def test_el_aviso_cubre_la_variable_AUSENTE_y_no_solo_la_sintaxis():
    """`$env:` con la variable sin poner falla igual de callado. El aviso que
    solo traduce la sintaxis deja al lector a mitad de camino.
    """
    texto = SKILL_MD.read_text(encoding="utf-8")
    bloque = next(
        (b for b in texto.split("\n\n") if "$env:CLAUDE_PLUGIN_ROOT" in b), ""
    )
    assert "no está puesta" in bloque or "no esta puesta" in bloque, (
        "el aviso de PowerShell traduce la sintaxis pero ya no dice que hacer si la variable "
        f"no existe en el entorno, que es el otro camino a la ruta vacia -> «{bloque[:200]}»"
    )


def test_el_aviso_de_rancidez_cita_EL_PASO_QUE_LA_SKILL_NUMERA():
    """`generar_dossier` cablea «el paso 5 de la SKILL» dentro del aviso de
    rancidez. Hoy es exacto; renumerar el Proceso lo dejaria mandando al lector
    al paso equivocado, en el unico mensaje que aparece cuando algo va mal.
    """
    import inspect
    import re as _re

    import generar_dossier

    encabezados = _re.findall(
        r"^###\s+(\d+)\s+·\s+([A-ZÁÉÍÓÚÑ]+)", SKILL_MD.read_text(encoding="utf-8"), _re.M
    )
    assert encabezados, "la SKILL ya no numera sus pasos con `### N · NOMBRE`"
    verificacion = [n for n, nombre in encabezados if nombre.startswith("VERIFICACI")]
    assert len(verificacion) == 1, (
        f"la SKILL tiene {len(verificacion)} pasos de VERIFICACION: {encabezados}"
    )

    fuente = inspect.getsource(generar_dossier.main_con_raiz)
    citado = _re.search(r"paso (\d+) de la SKILL", fuente)
    assert citado, (
        "el aviso de rancidez ya no dice a que paso volver: era la mitad accionable del "
        "mensaje"
    )
    assert citado.group(1) == verificacion[0], (
        f"el aviso manda al «paso {citado.group(1)}» y VERIFICACION es el paso "
        f"{verificacion[0]} de la SKILL: el unico mensaje que sale cuando algo va mal "
        f"mandaria al lector al sitio equivocado"
    )


# --- El bundle que un usuario de Appian lee de verdad ------------------------
# `en_US` salia en espanol y con la tilde en UTF-8 crudo mientras su hermano
# `_es_ES` la escapaba, y la exencion la compartian EMISOR (`andamiar`) y JUEZ
# (`verificar_bundles`, R-B05), asi que la cadena entera era ciega. El plug-in
# de referencia aprobado en AppMarket no tiene un solo no-ASCII en su `en_US`.
# Levantado por el gate del ciclo 16; hasta entonces ningun test lo fijaba.


@pytest.mark.parametrize("tipo", TIPOS_CON_BUNDLE)
def test_NINGUN_bundle_generado_lleva_un_no_ASCII_crudo(tipo, tmp_path):
    andamiar.generar(cargar(tipo), PLANTILLAS, tmp_path, ruta_contrato(tipo))
    bundles = sorted(tmp_path.rglob("*.properties"))
    assert bundles, f"el andamiaje de {tipo} no escribio ningun bundle"

    for bundle in bundles:
        crudos = contrato.PATRON_NO_ASCII.findall(bundle.read_text(encoding="utf-8"))
        assert not crudos, (
            f"`{bundle.name}` lleva {len(crudos)} caracter(es) no-ASCII sin escapar "
            f"({crudos[:5]}). `en_US` es el unico fichero cuyo mojibake veria un usuario de "
            f"Appian, y el escapado es seguro lea quien lea: `escapar_no_ascii` es idempotente"
        )


def test_el_guardian_del_NO_ASCII_tiene_algo_QUE_morder(tmp_path):
    """Suelo antivacuidad del de arriba, asertado sobre el INSUMO y sobre el juez.

    Que aquel guardian pueda ver algo depende de que el corpus traiga algo que
    escapar, y el corpus casi no trae nada: los `\\uXXXX` de `error.unexpected`
    vienen HORNEADOS en las plantillas `_es_ES` --son ASCII ya escrito-- y
    sobreviven intactos a que `escapar_no_ascii` no exista. Contar escapes en la
    salida los cuenta a ellos, y esa fue exactamente la vacuidad que levanto el
    gate del ciclo 17.

    Su suelo de entonces paso a vigilar otra cosa en `18b20c6` --que el texto de
    display nazca en ingles-- y nadie ocupo el sitio. Este lo ocupa.

    Medido, no razonado: mutando el sitio de emision (`andamiar`, el
    `if contrato.es_bundle(...)`), de los tres tipos con bundle solo muere
    `[smart-service]`; `function` y `writer-function` pasan en vacio porque su
    unico escape es el horneado. La UNICA fuente dinamica del corpus es la
    constante de abajo. Si alguien la traduce al ingles --que es la direccion
    que marca el propio `18b20c6`-- el guardian se queda sin nada que morder y
    R-B05 deja de estar ejercida de punta a punta, en silencio. El dia que pase,
    este test es el que se pone rojo.
    """
    acentos = [
        c
        for valor in andamiar.COMENTARIO_POR_DEFECTO_HORNEADO_ES.values()
        for c in contrato.PATRON_NO_ASCII.findall(valor)
        if c.isalpha()
    ]
    assert acentos, (
        "`COMENTARIO_POR_DEFECTO_HORNEADO_ES` ya no lleva una sola letra acentuada, y es la "
        "unica fuente no-ASCII que el andamiador escapa de verdad: sin ella "
        "`test_NINGUN_bundle_generado_lleva_un_no_ASCII_crudo` aprueba en vacio sobre los tres tipos"
    )

    andamiar.generar(
        cargar("smart-service"), PLANTILLAS, tmp_path, ruta_contrato("smart-service")
    )
    traducidos = sorted(tmp_path.rglob("*_es_ES.properties"))
    assert traducidos, "el andamiaje de smart-service no escribio ningun bundle traducido"

    # LITERAL A MANO, y no `escapar_no_ascii(...)` sobre la constante. Derivar el
    # esperado con la funcion que se esta probando hace que los dos lados se
    # muevan juntos: con `escapar_no_ascii` reducida a `return texto`, este
    # aserto seguia VERDE --medido-- mientras su hermano moria. O sea que el
    # test cuyo trabajo declarado es «el guardian tiene algo QUE morder» era
    # ciego a la forma mas directa de matar el escapado. Es exactamente el
    # patron de aserto vacuo que este repositorio lleva dos ciclos persiguiendo,
    # cometido dentro del suelo que venia a impedirlo. Lo levanto el
    # /code-review posterior.
    ESPERADO = r"Cierto si la ejecuci\u00f3n fall\u00f3"

    texto = traducidos[0].read_text(encoding="utf-8")
    assert ESPERADO in texto, (
        f"el texto acentuado no llega ESCAPADO al bundle traducido: se esperaba «{ESPERADO}» en "
        f"`{traducidos[0].name}`. Sin ese recorrido completo --insumo acentuado, juez que escapa, "
        f"bundle emitido-- el guardian del no-ASCII no ejerce nada"
    )


PATRON_ESCAPE = re.compile(r"\\u[0-9a-fA-F]{4}")


@pytest.mark.parametrize("tipo", TIPOS)
def test_LO_QUE_NO_ES_UN_BUNDLE_no_lleva_escapes_Unicode(tipo, tmp_path):
    """La direccion que faltaba, y sin la cual el guardian de arriba certifica
    como limpios exactamente los ficheros que corrompe.

    `\\uXXXX` solo significa algo dentro de un `.properties`. En
    `appian-plugin.xml` es el texto que Appian muestra en su consola; en
    `THIRD_PARTY_NOTICES.md`, el aviso legal que va dentro del JAR y que lee
    R-J07. Al quitar la exencion de `en_US` se quito la condicion entera y el
    escapado cayo sobre los dos, mas los `.java` y el `exclude.xml`: el mismo
    mojibake que se venia a arreglar, por el otro extremo. Lo levanto el
    /code-review posterior al ciclo 16.
    """
    andamiar.generar(cargar(tipo), PLANTILLAS, tmp_path, ruta_contrato(tipo))
    sospechosos = {
        p: len(PATRON_ESCAPE.findall(p.read_text(encoding="utf-8", errors="replace")))
        for p in tmp_path.rglob("*")
        if p.is_file() and p.suffix != ".properties"
    }
    assert sospechosos, "el andamiaje no escribio ningun fichero que no sea un bundle"
    con_escapes = {p.name: n for p, n in sospechosos.items() if n}
    assert not con_escapes, (
        f"el escapado de `.properties` se aplico a ficheros que no lo son: {con_escapes}. "
        f"Un `\\uXXXX` fuera de un bundle es texto literal, o sea el mojibake que este "
        f"escapado existe para evitar"
    )


def _valores_de_display(datos: dict) -> dict[str, str]:
    """Los valores del contrato que acaban en el texto que Appian MUESTRA.

    Sobre el contrato ya PARSEADO, no sobre las lineas del fichero. Casar por
    prefijo de linea (`nombre = `) era mas corto y traia de propina
    `[clase].nombre`, `[bundle].nombre` y el `nombre` de cada entrada y salida
    --identificadores Java, no texto de display--, con dos costes: una clase
    con tilde se habria reportado como «texto sin traducir», y sobre todo el
    suelo antivacuidad no podia fallar nunca, porque esos tres estan en todo
    contrato bien formado. Medido: borrando `[plugin].nombre` y
    `[plugin].descripcion` de un fixture, el guardian seguia verde.

    Devuelve un mapa etiqueta -> valor para que el fallo diga QUE campo es.
    """
    # `contrato.seccion`, no `datos.get("plugin", {})`: el `.get` repone el
    # defecto solo cuando la clave FALTA, asi que un `plugin = "smart-service"`
    # escalar --o un `[[plugin]]`, que TOML convierte en lista-- hace estallar
    # el `.get` encadenado con un AttributeError DENTRO del guardian, y el test
    # muere con traza en vez de emitir su propio mensaje. `seccion` existe
    # precisamente para cerrar esa clase (`contrato.py:70`, y lo midio el gate
    # del ciclo 11). Lo levanto la lente de reuso del ciclo 18.
    plugin = contrato.seccion(datos, "plugin")
    valores = {
        "plugin.nombre": plugin.get("nombre", ""),
        "plugin.descripcion": plugin.get("descripcion", ""),
    }
    for seccion in ("entradas", "salidas"):
        for i, campo in enumerate(datos.get(seccion) or []):
            if isinstance(campo, dict) and campo.get("descripcion") is not None:
                valores[f"{seccion}[{i}].descripcion"] = campo["descripcion"]
    return valores


@pytest.mark.parametrize("tipo", TIPOS)
def test_el_TEXTO_QUE_VE_EL_USUARIO_de_cada_contrato_esta_en_ingles(tipo):
    """El plug-in generado va en ingles, y esto lo fija sobre el insumo.

    Historia de este test en dos vueltas, porque las dos fueron el mismo error:
    nacio contando escapes en la SALIDA y era vacuo —la plantilla del `_es_ES`
    llevaba un `\\uXXXX` horneado, asi que medía la plantilla—. Se paso a mirar
    el contrato... y siguio pasando por la razon equivocada, porque encontraba
    las tildes de la PROSA que documenta el fixture, no las de los campos que
    viajan al artefacto. Dos veces el guardian aprobo por algo que no era lo
    suyo. Por eso ahora acota los campos, uno a uno --y sobre el contrato ya
    parseado, que es la tercera vuelta del mismo error: ver `_valores_de_display`.

    La comprobacion es de letras, no de bytes: los guiones largos y las
    comillas angulares de la prosa son tipografia legitima; una `á` en un campo
    de display es texto sin traducir.
    """
    valores = _valores_de_display(cargar(tipo))
    # El suelo, y este SI puede fallar. Ojo al alcance, que la version anterior
    # de este comentario exageraba: son los dos campos que declaran los CUATRO
    # fixtures `-minimo` sobre los que este test esta parametrizado, no «todo
    # contrato». `contrato.py` NO exige `[plugin].descripcion` --la
    # obligatoriedad de `descripcion` es de entradas y salidas-- y `andamiar`
    # tiene fallback explicito para su ausencia; de hecho dos de los siete
    # fixtures la omiten. Lo levanto la lente 10 del ciclo 18.
    vacios = sorted(c for c in ("plugin.nombre", "plugin.descripcion") if not valores.get(c))
    assert not vacios, (
        f"`{ruta_contrato(tipo).name}` no declara {vacios}: sin ellos este guardian mira texto "
        f"que no existe y aprueba en vacio"
    )
    con_acentos = {
        campo: acentos
        for campo, valor in valores.items()
        if (acentos := [c for c in contrato.PATRON_NO_ASCII.findall(valor) if c.isalpha()])
    }
    assert not con_acentos, (
        f"`{ruta_contrato(tipo).name}` lleva letras no inglesas en el texto que Appian muestra: "
        f"{con_acentos}. El artefacto generado va en ingles; el contrato es donde nace ese texto"
    )
