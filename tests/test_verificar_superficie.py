import pathlib
import sys

import classfile
import verificar_superficie as vs

INDICE = {
    "version": "26.3",
    "hash_sha256": "0" * 64,
    "tipos": [
        "com.appiancorp.suiteapi.process.framework.AppianSmartService",
        "com.appiancorp.common.query.Query",
    ],
    "paquetes": ["com.appiancorp.suiteapi.process.framework", "com.appiancorp.common.query"],
}


def clase(nombre, tipos):
    return classfile.ClaseLeida(
        nombre_clase=nombre, major=61, tipos_referenciados=set(tipos), cadenas=set(), metodos=[]
    )


def test_tipo_documentado_no_se_reporta():
    informe = vs.analizar(
        [clase("com.raul.X", ["com.appiancorp.suiteapi.process.framework.AppianSmartService"])],
        INDICE,
    )
    assert informe.no_documentados == []


def test_clase_no_documentada_dentro_de_paquete_documentado_si_se_reporta():
    # RecordQuerySource vive en com.appiancorp.common.query, que SI esta
    # documentado — un escaner por paquete la dejaria pasar (spec §5.3).
    informe = vs.analizar(
        [clase("com.raul.X", ["com.appiancorp.common.query.RecordQuerySource"])], INDICE
    )
    assert ("com.raul.X", "com.appiancorp.common.query.RecordQuerySource") in informe.no_documentados


def test_tipos_ajenos_a_appiancorp_se_ignoran():
    informe = vs.analizar([clase("com.raul.X", ["java.util.ArrayList", "org.json.JSONObject"])], INDICE)
    assert informe.no_documentados == []


def test_inventario_lista_quien_usa_cada_tipo():
    informe = vs.analizar(
        [
            clase("com.raul.X", ["com.appiancorp.common.query.Query"]),
            clase("com.raul.Y", ["com.appiancorp.common.query.Query"]),
        ],
        INDICE,
    )
    assert informe.inventario["com.appiancorp.common.query.Query"] == ["com.raul.X", "com.raul.Y"]


def test_sin_indice_cae_a_filtro_por_paquete_y_lo_declara():
    informe = vs.analizar([clase("com.raul.X", ["com.appiancorp.inventado.Cosa"])], None)
    assert informe.modo_degradado is True
    assert informe.no_documentados


def test_dominio_no_puede_importar_el_sdk():
    clases = [clase("com.raul.parser.Lector", ["com.appiancorp.suiteapi.content.ContentService"])]
    violaciones = vs.comprobar_dominio_sin_sdk(clases, ["com.raul.parser", "com.raul.model"])
    assert violaciones and "com.raul.parser.Lector" in violaciones[0]


def test_adaptador_si_puede_importar_el_sdk():
    clases = [clase("com.raul.smartservice.S", ["com.appiancorp.suiteapi.content.ContentService"])]
    assert vs.comprobar_dominio_sin_sdk(clases, ["com.raul.parser"]) == []


def test_el_modo_degradado_filtra_de_verdad_y_no_rechaza_todo():
    # El test anterior pasaria igual si el modo degradado marcara TODO sin
    # mirar nada: prueba menos de lo que su nombre promete. Este distingue las
    # dos conductas — un tipo de paquete documentado debe ACEPTARSE aunque no
    # haya indice, y uno de paquete inexistente debe rechazarse.
    informe = vs.analizar(
        [clase("com.raul.X", [
            "com.appiancorp.suiteapi.process.framework.AppianSmartService",
            "com.appiancorp.kougar.mapper.ConversionMap",
        ])],
        None,
    )
    reportados = {t for _, t in informe.no_documentados}
    assert "com.appiancorp.suiteapi.process.framework.AppianSmartService" not in reportados
    assert "com.appiancorp.kougar.mapper.ConversionMap" in reportados


def test_main_sin_clases_compiladas_devuelve_1(tmp_path, monkeypatch, capsys):
    # build/classes todavia no existe (nadie ha compilado): analizar CERO
    # clases no es verificar. Sin este arreglo, main() seguia adelante con una
    # lista vacia, no encontraba ningun problema y salia con 0 — el certificado
    # mostraba la puerta en verde sin haber comprobado nada.
    directorio_vacio = tmp_path / "build_classes"
    directorio_vacio.mkdir()
    ruta_indice = tmp_path / "indice.json"
    monkeypatch.setattr(sys, "argv", ["verificar_superficie.py", str(directorio_vacio), str(ruta_indice)])

    codigo_salida = vs.main()

    assert codigo_salida == 1
    salida = capsys.readouterr().out
    assert "ERROR" in salida
    assert "cero" in salida.lower() or "ninguna clase" in salida.lower()


# --- Important 1: el inventario se escribia relativo al cwd ----------------
# `verificar_superficie` lo escribia SIEMPRE en `build/reports/...` relativo al
# directorio desde el que se invocara, y `generar_dossier` lo lee relativo a la
# raiz del proyecto. La pieza 3 del dossier salia siempre «pendiente», y un
# inventario rancio de otro plug-in podia acabar publicado bajo un encabezado
# que afirma su procedencia («extraido del constant pool» de ESTAS clases).

def test_extraer_inventario_saca_la_ruta_y_deja_el_resto():
    argumentos, destino = vs._extraer_inventario(
        ["clases", "indice.json", "--inventario", "x/y.json", "com.raul.dominio"]
    )
    assert argumentos == ["clases", "indice.json", "com.raul.dominio"]
    assert str(destino).replace("\\", "/") == "x/y.json"


def test_sin_la_opcion_se_mantiene_la_ruta_por_defecto():
    argumentos, destino = vs._extraer_inventario(["clases", "indice.json"])
    assert argumentos == ["clases", "indice.json"]
    assert str(destino).replace("\\", "/") == vs.RUTA_INVENTARIO_POR_DEFECTO


def test_el_inventario_se_escribe_donde_lo_pide_quien_invoca(tmp_path, monkeypatch):
    """Verificado en rojo: sin `--inventario`, el fichero aparecia bajo el cwd
    del proceso y el dossier lo buscaba dentro del proyecto, asi que no lo
    encontraba nunca.
    """
    import shutil
    import subprocess

    if shutil.which("javac") is None:
        import pytest
        pytest.skip("javac no esta en el PATH")

    clases = tmp_path / "clases"
    fuente = pathlib.Path(__file__).resolve().parent / "fixtures" / "java" / "Ejemplo.java"
    subprocess.run(["javac", "--release", "17", "-d", str(clases), str(fuente)],
                   check=True, capture_output=True)

    indice = tmp_path / "indice.json"
    indice.write_text(__import__("json").dumps(INDICE), encoding="utf-8")
    destino = tmp_path / "cualquier" / "sitio" / "inventario-api.json"

    # El cwd se mueve a otro sitio a proposito: si la ruta siguiera siendo
    # relativa al cwd, el fichero apareceria aqui y no en `destino`.
    cwd_ajeno = tmp_path / "cwd-ajeno"
    cwd_ajeno.mkdir()
    monkeypatch.chdir(cwd_ajeno)
    monkeypatch.setattr(
        "sys.argv",
        ["verificar_superficie.py", str(clases), str(indice), "--inventario", str(destino)],
    )

    assert vs.main() == 0
    assert destino.is_file(), "el inventario no aparecio donde lo pidio quien invoca"
    assert not (cwd_ajeno / "build").exists(), "siguio escribiendo relativo al cwd"
