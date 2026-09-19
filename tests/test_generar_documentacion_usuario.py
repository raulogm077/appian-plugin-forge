import pathlib

import contrato as c
import generar_documentacion_usuario as gdu

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "contratos"


def _cargar(nombre: str) -> dict:
    return c.cargar(FIXTURES / nombre)


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
