import zipfile

import pytest

import verificar_jar as vj

CONTRATO = {
    "plugin": {"key": "com.raul.appian.ejemplo", "tipo": "smart-service", "version": "1.0.0"},
    "bundle": {"nombre": "ejemplo"},
}

BASE = {
    "appian-plugin.xml": "<appian-plugin/>",
    "com/raul/appian/ejemplo/ejemplo_en_US.properties": "name=Ejemplo",
    "src/com/raul/appian/ejemplo/Ejemplo.java": "package com.raul.appian.ejemplo;",
    "META-INF/LICENSE": "MIT",
    "META-INF/THIRD_PARTY_NOTICES.md": "notas",
    "com/raul/appian/ejemplo/Ejemplo.class": "\xca\xfe\xba\xbe",
}


def construir_jar(tmp_path, entradas):
    ruta = tmp_path / "plugin.jar"
    with zipfile.ZipFile(ruta, "w") as z:
        for nombre, contenido in entradas.items():
            z.writestr(nombre, contenido)
    return ruta


def reglas(hallazgos):
    return {h.regla for h in hallazgos}


def test_jar_correcto_no_da_hallazgos(tmp_path):
    ruta = construir_jar(tmp_path, BASE)
    assert vj.comprobar(ruta, CONTRATO, []) == []


def test_descriptor_fuera_de_la_raiz_es_error(tmp_path):
    entradas = {k: v for k, v in BASE.items() if k != "appian-plugin.xml"}
    entradas["META-INF/appian-plugin.xml"] = "<appian-plugin/>"
    assert "R-J01" in reglas(vj.comprobar(construir_jar(tmp_path, entradas), CONTRATO, []))


def test_falta_la_fuente_embebida_es_error(tmp_path):
    entradas = {k: v for k, v in BASE.items() if not k.startswith("src/")}
    assert "R-J02" in reglas(vj.comprobar(construir_jar(tmp_path, entradas), CONTRATO, []))


def test_clases_de_test_dentro_del_jar_son_error(tmp_path):
    entradas = dict(BASE, **{"com/raul/appian/ejemplo/EjemploTest.class": "x"})
    assert "R-J03" in reglas(vj.comprobar(construir_jar(tmp_path, entradas), CONTRATO, []))


def test_sdk_dentro_de_meta_inf_lib_es_error(tmp_path):
    entradas = dict(BASE, **{"META-INF/lib/appian-plug-in-sdk-26.3.jar": "x"})
    assert "R-J04" in reglas(vj.comprobar(construir_jar(tmp_path, entradas), CONTRATO, []))


def test_log4j_dentro_de_meta_inf_lib_es_error(tmp_path):
    entradas = dict(BASE, **{"META-INF/lib/log4j-1.2.17.jar": "x"})
    assert "R-J04" in reglas(vj.comprobar(construir_jar(tmp_path, entradas), CONTRATO, []))


def test_dependencia_declarada_y_ausente_es_error(tmp_path):
    ruta = construir_jar(tmp_path, BASE)
    hallazgos = vj.comprobar(ruta, CONTRATO, ["gson-2.14.0.jar"])
    assert "R-J05" in reglas(hallazgos)


def test_dependencia_declarada_y_presente_no_es_error(tmp_path):
    entradas = dict(BASE, **{"META-INF/lib/gson-2.14.0.jar": "x"})
    ruta = construir_jar(tmp_path, entradas)
    assert "R-J05" not in reglas(vj.comprobar(ruta, CONTRATO, ["gson-2.14.0.jar"]))


def test_falta_el_bundle_en_el_jar_es_error(tmp_path):
    entradas = {k: v for k, v in BASE.items() if not k.endswith(".properties")}
    assert "R-J06" in reglas(vj.comprobar(construir_jar(tmp_path, entradas), CONTRATO, []))


def test_falta_license_o_notices_es_error(tmp_path):
    entradas = {k: v for k, v in BASE.items() if k != "META-INF/LICENSE"}
    assert "R-J07" in reglas(vj.comprobar(construir_jar(tmp_path, entradas), CONTRATO, []))


def test_entradas_duplicadas_es_error(tmp_path):
    # El brief no traia test para R-J08 aunque el validador si la implementa;
    # se añade aqui para que las nueve reglas documentadas queden cubiertas.
    # Un dict no admite dos claves iguales, asi que no se puede pasar por
    # construir_jar(): se escribe el mismo nombre dos veces a mano.
    ruta = tmp_path / "plugin.jar"
    with zipfile.ZipFile(ruta, "w") as z:
        for nombre, contenido in BASE.items():
            z.writestr(nombre, contenido)
        with pytest.warns(UserWarning, match="Duplicate name"):
            z.writestr("appian-plugin.xml", "<appian-plugin/>")
    assert "R-J08" in reglas(vj.comprobar(ruta, CONTRATO, []))


def test_supera_el_tope_de_tamano_es_error(tmp_path):
    # Igual que R-J08: el brief no la testeaba. ZIP_STORED es el modo por
    # defecto de zipfile (sin compresion), asi que un relleno de 16 MiB basta
    # para que el .jar en disco supere el tope de 15 MiB sin trucos.
    entradas = dict(BASE, **{"relleno.bin": b"0" * (16 * 1024 * 1024)})
    ruta = construir_jar(tmp_path, entradas)
    assert "R-J09" in reglas(vj.comprobar(ruta, CONTRATO, []))


# --- Important 5: R-J05 salia verde sin comprobar nada --------------------
# `dependencias_esperadas` salia de `sys.argv[3:]`, asi que con la CLI
# documentada llegaba SIEMPRE vacia y la regla del cierre de dependencias
# --la que evita un NoClassDefFoundError que solo aparece tras desplegar--
# pasaba por vacuidad. Y sin la guarda de lista vacia que si se anadio a los
# otros dos validadores. El contrato ya trae `dependencias`.

CONTRATO_CON_DEPENDENCIAS = {
    **CONTRATO,
    "dependencias": ["org.apache.poi:poi:5.2.5", "org.jsoup:jsoup:1.17.2"],
}


def test_las_dependencias_del_contrato_se_traducen_al_jar_que_gradle_produce():
    assert vj.jar_esperado("org.apache.poi:poi:5.2.5") == "poi-5.2.5.jar"


def test_R_J05_detecta_una_dependencia_del_contrato_que_no_viaja(tmp_path):
    ruta = construir_jar(tmp_path, {**BASE, "META-INF/lib/poi-5.2.5.jar": "x"})
    hallazgos = vj.comprobar(ruta, CONTRATO_CON_DEPENDENCIAS,
                             vj.dependencias_del_contrato(CONTRATO_CON_DEPENDENCIAS))
    assert "R-J05" in reglas(hallazgos)
    assert any("jsoup" in h.mensaje for h in hallazgos)


def test_R_J05_pasa_cuando_todas_viajan(tmp_path):
    ruta = construir_jar(tmp_path, {**BASE,
                                    "META-INF/lib/poi-5.2.5.jar": "x",
                                    "META-INF/lib/jsoup-1.17.2.jar": "x"})
    hallazgos = vj.comprobar(ruta, CONTRATO_CON_DEPENDENCIAS,
                             vj.dependencias_del_contrato(CONTRATO_CON_DEPENDENCIAS))
    assert "R-J05" not in reglas(hallazgos)


def test_un_contrato_sin_dependencias_lo_declara_en_vez_de_callar(tmp_path, capsys):
    """La guarda que faltaba. Cero dependencias es legitimo, pero entonces
    R-J05 no comprueba nada y el certificado tiene que poder decirlo: la
    evidencia no puede parecerse a «comprobado y correcto».
    """
    ruta = construir_jar(tmp_path, BASE)
    assert vj.dependencias_del_contrato(CONTRATO) == []
    codigo = vj.main_con_argumentos([str(ruta), "no-usado"], datos_contrato=CONTRATO)
    assert codigo == 0
    assert "R-J05" in capsys.readouterr().out
