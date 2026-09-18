
import generar_indice_tipos as gen

# Muestra real abreviada: el fichero del buscador es un array JSON con cola.
JS_TIPOS = (
    'typeSearchIndex = [{"l":"All Classes and Interfaces","u":"allclasses-index.html"},'
    '{"p":"com.appiancorp.suiteapi.process.framework","l":"AppianSmartService"},'
    '{"p":"com.appiancorp.suiteapi.servlet","l":"AppianServlet"}];'
    "updateSearchResults();"
)
JS_PAQUETES = (
    'packageSearchIndex = [{"l":"All Packages","u":"allpackages-index.html"},'
    '{"l":"com.appiancorp.suiteapi.process.framework"},'
    '{"l":"com.appiancorp.suiteapi.servlet"}];'
)


def test_parsea_pese_a_la_cola_del_fichero():
    entradas = gen.parsear_indice_js(JS_TIPOS)
    assert len(entradas) == 3


def test_construye_nombres_cualificados_y_descarta_la_entrada_sintetica():
    snapshot = gen.construir("26.3", JS_TIPOS, JS_PAQUETES)
    assert "com.appiancorp.suiteapi.process.framework.AppianSmartService" in snapshot["tipos"]
    assert "com.appiancorp.suiteapi.servlet.AppianServlet" in snapshot["tipos"]
    assert not any("All Classes" in t for t in snapshot["tipos"])
    assert "com.appiancorp.suiteapi.servlet" in snapshot["paquetes"]
    assert not any("All Packages" in p for p in snapshot["paquetes"])


def test_snapshot_lleva_version_fecha_y_hash():
    snapshot = gen.construir("26.3", JS_TIPOS, JS_PAQUETES)
    assert snapshot["version"] == "26.3"
    assert len(snapshot["hash_sha256"]) == 64
    assert snapshot["fecha"]


def test_version_se_deriva_de_la_coordenada_de_gradle():
    assert gen.version_desde_coordenada("com.appian:appian-plug-in-sdk:26.3") == "26.3"


def test_coordenada_invalida_da_error():
    try:
        gen.version_desde_coordenada("appian-plug-in-sdk")
    except ValueError:
        pass
    else:
        raise AssertionError("deberia haber lanzado ValueError")
