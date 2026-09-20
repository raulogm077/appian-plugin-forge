import pathlib

import andamiar
import contrato as c
import generar_documentacion_usuario as gdu

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "contratos"
PLANTILLAS = pathlib.Path(__file__).resolve().parents[1] / "assets" / "plantillas"
SERVLET = "servlet-minimo.md"


def _cargar(nombre: str) -> dict:
    return c.cargar(FIXTURES / nombre)


def _proyecto_servlet(tmp_path):
    """Un servlet andamiado de verdad: manifiesto y clase reales en disco."""
    datos = _cargar(SERVLET)
    andamiar.generar(datos, PLANTILLAS, tmp_path, FIXTURES / SERVLET)
    return datos


def test_guia_de_function_incluye_la_llamada_sail_con_la_key():
    md = gdu.render_guia_integracion(_cargar("function-minimo.md"))
    assert "saludofunction(" in md


def test_guia_de_smart_service_menciona_paso_de_proceso():
    md = gdu.render_guia_integracion(_cargar("smart-service-completo.md"))
    assert "modelo de proceso" in md.lower()


def test_guia_de_servlet_no_promete_expresion_sail():
    md = gdu.render_guia_integracion(_cargar("servlet-minimo.md"))
    assert "endpoint" in md.lower()
    assert "expresion sail" not in md.lower() and "expresión sail" not in md.lower()


def test_guia_de_servlet_cita_la_ruta_y_los_metodos_del_proyecto_generado(tmp_path):
    """«Segun lo declarado en appian-plugin.xml» obliga a abrir el manifiesto.

    Era el unico de los cuatro tipos cuya guia no decia como se invoca: cumplia
    el criterio de «contenido no vacio» y remitia a otro fichero. Con el proyecto
    delante los dos datos que faltaban son hechos leidos, no deducciones.
    """
    datos = _proyecto_servlet(tmp_path)
    md = gdu.render_guia_integracion(datos, raiz=tmp_path)
    assert "`/estado`" in md, md
    assert "`GET`" in md, md


def test_la_ruta_del_servlet_sale_del_MANIFIESTO_y_no_del_contrato(tmp_path):
    """El discriminador entre leer el hecho y re-derivarlo.

    `andamiar.py` saca el `url-pattern` de `[servlet].url_pattern` con relleno
    por defecto cuando falta --que es el caso de este contrato--, asi que
    re-derivarlo daria el mismo `/estado` y los dos tests de arriba pasarian
    igual. Quien implementa el servlet puede cambiarlo en el XML, y entonces la
    guia tiene que decir lo que se entrega, no lo que el contrato sugeria.
    """
    datos = _proyecto_servlet(tmp_path)
    manifiesto = tmp_path / "src" / "main" / "resources" / "appian-plugin.xml"
    manifiesto.write_text(
        manifiesto.read_text(encoding="utf-8").replace(
            "<url-pattern>/estado</url-pattern>", "<url-pattern>/otra-ruta</url-pattern>"
        ),
        encoding="utf-8",
    )
    md = gdu.render_guia_integracion(datos, raiz=tmp_path)
    assert "`/otra-ruta`" in md, md
    assert "/estado" not in md, "la guia re-derivo la ruta del contrato en vez de leer el XML"


def test_guia_de_servlet_sin_proyecto_delante_no_se_inventa_la_ruta():
    """Sin manifiesto que leer, la frase generica; nunca una ruta supuesta."""
    md = gdu.render_guia_integracion(_cargar(SERVLET))
    assert "appian-plugin.xml" in md
    assert "/estado" not in md, "se invento la ruta sin haber abierto el manifiesto"


def test_guia_de_writer_function_menciona_saveInto():
    md = gdu.render_guia_integracion(_cargar("writer-function-minimo.md"))
    assert "saveInto" in md


def test_tabla_de_entradas_lleva_columna_required_solo_en_smart_service():
    md_smart_service = gdu.render_guia_integracion(_cargar("smart-service-completo.md"))
    assert "Obligatorio" in md_smart_service

    md_function = gdu.render_guia_integracion(_cargar("function-minimo.md"))
    assert "Obligatorio" not in md_function

    md_servlet = gdu.render_guia_integracion(_cargar("servlet-minimo.md"))
    assert "Obligatorio" not in md_servlet


def test_tabla_de_entradas_incluye_nombre_tipo_y_descripcion_del_contrato():
    md = gdu.render_guia_integracion(_cargar("smart-service-completo.md"))
    assert "documentoOrigen" in md
    assert "Long" in md
    assert "Input document" in md


def test_sin_capacidades_exigentes_no_hay_seccion_de_notas():
    md = gdu.render_guia_integracion(_cargar("function-minimo.md"))
    assert "Notas de seguridad" not in md


def test_con_capacidad_exigente_declarada_aparece_su_nota():
    datos = _cargar("eml-referencia.md")  # declara parsea_formatos_ajenos y datos_personales
    md = gdu.render_guia_integracion(datos)
    assert "Notas de seguridad" in md
    assert "formato de entrada no lo controla Appian" in md
    assert "datos personales" in md.lower()


def test_version_minima_de_appian_aparece_literal():
    md = gdu.render_guia_integracion(_cargar("smart-service-minimo.md"))
    datos = _cargar("smart-service-minimo.md")
    assert datos["plugin"]["application_version_min"] in md


def test_ficha_incluye_nombre_descripcion_y_categoria():
    md = gdu.render_ficha_appmarket(_cargar("smart-service-completo.md"))
    assert "Example" in md
    assert "Document Management" in md


def test_ficha_sin_capacidades_no_lleva_nota_de_transparencia():
    md = gdu.render_ficha_appmarket(_cargar("function-minimo.md"))
    assert "Transparencia" not in md


def test_ficha_de_function_no_promete_una_subcategoria_que_no_existe():
    # clase.paleta es especifica de smart-service; function y servlet nunca
    # la piden en la entrevista, asi que su ficha no debe prometer una
    # "Subcategoria" que ese tipo de plugin no puede tener.
    md_function = gdu.render_ficha_appmarket(_cargar("function-minimo.md"))
    assert "Subcategoria" not in md_function

    md_servlet = gdu.render_ficha_appmarket(_cargar("servlet-minimo.md"))
    assert "Subcategoria" not in md_servlet


def test_ficha_con_datos_personales_lleva_nota_de_transparencia():
    md = gdu.render_ficha_appmarket(_cargar("eml-referencia.md"))
    assert "Transparencia" in md
    assert "datos personales" in md.lower()


def test_main_con_raiz_escribe_los_dos_ficheros(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "contrato.md").write_text(
        (FIXTURES / "smart-service-completo.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    assert gdu.main_con_raiz(tmp_path) == 0

    guia = (tmp_path / "docs" / "GUIA_INTEGRACION.md").read_text(encoding="utf-8")
    ficha = (tmp_path / "docs" / "FICHA_APPMARKET.md").read_text(encoding="utf-8")
    assert "Como invocarlo" in guia
    assert "Document Management" in ficha
