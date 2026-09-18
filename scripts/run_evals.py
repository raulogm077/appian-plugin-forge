"""Evals de la propia skill: nivel 1 (estructural) y nivel 2 (disparo).

Regla antitrampa (spec §7): los prompts de prueba parafrasean COMO HABLA LA
GENTE. Copiar la descripcion dentro del prompt falsea el eval y no informa de
nada, asi que se detecta y se marca.
"""

from __future__ import annotations

import json
import math
import pathlib
import re

UMBRAL_SOLAPE_TRAMPA = 0.6

# Ganar no basta: hay que ganar POR EL CONTENIDO. El caso del endpoint HTTP
# ganaba con un margen de 0.0242 cuando todos los demas pasan de 0.4458, y su
# unica palanca era repetir «appian» — borrando toda mencion a «servlet» de la
# descripcion, la puntuacion no se movia ni una milesima. Un caso asi no
# informa de nada y no puede constar como acierto.
#
# El umbral separa con holgura: 18 veces por encima del caso degenerado y
# cuatro veces por debajo del siguiente mas flojo.
MARGEN_MINIMO = 0.10
PALABRAS_VACIAS = {
    "de", "la", "el", "un", "una", "y", "o", "que", "en", "para", "con", "por", "los", "las",
    "del", "al", "se", "es", "mi", "me", "lo", "a",
}


def tokenizar(texto: str) -> list[str]:
    return [t for t in re.findall(r"\w+", texto.lower()) if t not in PALABRAS_VACIAS and len(t) > 2]


def puntuar(prompt: str, skills: dict[str, str]) -> list[tuple[str, float]]:
    """Ranking determinista tipo BM25 simplificado (IDF x frecuencia acotada)."""
    tokens_prompt = set(tokenizar(prompt))
    documentos = {n: tokenizar(d) for n, d in skills.items()}
    total = len(documentos) or 1

    resultados: list[tuple[str, float]] = []
    for nombre, tokens in documentos.items():
        puntos = 0.0
        for t in tokens_prompt:
            apariciones = tokens.count(t)
            if not apariciones:
                continue
            documentos_con_t = sum(1 for d in documentos.values() if t in d)
            idf = math.log(1 + (total - documentos_con_t + 0.5) / (documentos_con_t + 0.5))
            puntos += idf * (apariciones / (apariciones + 1.2))
        resultados.append((nombre, round(puntos, 4)))

    resultados.sort(key=lambda par: (-par[1], par[0]))
    return resultados


def es_trampa(caso: dict, skills: dict[str, str]) -> bool:
    descripcion = skills.get(caso["esperada"], "")
    tokens_prompt = set(tokenizar(caso["prompt"]))
    tokens_desc = set(tokenizar(descripcion))
    if not tokens_prompt:
        return False
    return len(tokens_prompt & tokens_desc) / len(tokens_prompt) >= UMBRAL_SOLAPE_TRAMPA


def margen(ranking: list[tuple[str, float]]) -> float:
    """Cuanto le saca la ganadora a la segunda. Es lo que distingue ganar por
    el contenido de ganar por un token generico que comparte todo el mundo."""
    if len(ranking) < 2:
        return ranking[0][1] if ranking else 0.0
    return round(ranking[0][1] - ranking[1][1], 4)


def ejecutar_casos(casos: list[dict], skills: dict[str, str]) -> list[dict]:
    resultados = []
    for caso in casos:
        ranking = puntuar(caso["prompt"], skills)
        ganadora = ranking[0][0] if ranking else ""
        acierto = ganadora == caso["esperada"]
        m = margen(ranking)
        resultados.append(
            {
                "prompt": caso["prompt"],
                "esperada": caso["esperada"],
                "ganadora": ganadora,
                "acierto": acierto,
                "margen": m,
                # Acertar por los pelos no es acertar: el caso no informa de
                # nada y no debe engordar el recuento de verdes.
                "acierto_limpio": acierto and m >= MARGEN_MINIMO,
                "trampa": es_trampa(caso, skills),
            }
        )
    return resultados


def main() -> int:
    import skill_lint

    raiz = pathlib.Path(__file__).resolve().parents[1]

    # Nivel 1 — estructural.
    skills_dir = raiz / "skills"
    conocidas = {d.name for d in skills_dir.iterdir() if d.is_dir()}
    errores_nivel1 = 0
    # El TAMANO del insumo, como toda puerta de este sistema. «0 errores» se
    # imprime igual sobre cero skills que sobre las de verdad, asi que sin esta
    # cuenta el nivel 1 es la unica linea del pipeline que puede dar un verde
    # sin decir sobre que. Levantado por el gate del ciclo 13 (OBS-1).
    corpus = [
        f
        for nombre in sorted(conocidas)
        for f in [skills_dir / nombre / "SKILL.md",
                  *sorted((skills_dir / nombre / "referencias").glob("*.md"))]
        if f.is_file()
    ]
    lineas_corpus = sum(len(f.read_text(encoding="utf-8").splitlines()) for f in corpus)
    for nombre in sorted(conocidas):
        resultado = skill_lint.lint_skill(nombre, skills_dir, conocidas)
        for e in resultado.errors:
            print(f"NIVEL1 ERROR {nombre}: {e}")
        errores_nivel1 += len(resultado.errors)

    # Nivel 2 — disparo.
    casos = json.loads((raiz / "evals" / "cases" / "disparo.json").read_text(encoding="utf-8"))
    skills = {}
    for nombre in sorted(conocidas):
        texto = (skills_dir / nombre / "SKILL.md").read_text(encoding="utf-8")
        campos, _ = skill_lint.parse_frontmatter(texto)
        skills[nombre] = campos.get("description", "")
    skills.update(casos.get("skills_competidoras", {}))

    resultados = ejecutar_casos(casos["casos"], skills)
    fallos = [r for r in resultados if not r["acierto"]]
    trampas = [r for r in resultados if r["trampa"]]
    # Acertar por los pelos no es acertar. Se cuentan aparte para que el
    # recuento de verdes no engorde con casos que no informan de nada.
    flojos = [r for r in resultados if r["acierto"] and not r["acierto_limpio"]]

    for r in resultados:
        marca = "OK  " if r["acierto_limpio"] else ("FLOJO" if r["acierto"] else "FALLO")
        aviso = "  <-- TRAMPA: el prompt copia la descripcion" if r["trampa"] else ""
        if r in flojos:
            aviso += (f"  <-- NO DISCRIMINANTE: gana por {r['margen']}, "
                      f"minimo {MARGEN_MINIMO}; no mide lo que dice medir")
        print(f"NIVEL2 {marca} «{r['prompt'][:50]}» -> {r['ganadora']} "
              f"(margen {r['margen']}){aviso}")

    limpios = len([r for r in resultados if r["acierto_limpio"]])
    print(f"\nNivel 1: {errores_nivel1} errores sobre {len(conocidas)} skill(s), "
          f"{len(corpus)} ficheros, {lineas_corpus} lineas. "
          f"Nivel 2: {limpios}/{len(resultados)} aciertos "
          f"limpios, {len(fallos)} fallos, {len(flojos)} no discriminantes, "
          f"{len(trampas)} prompts marcados como trampa.")
    if not corpus:
        # Un verde sobre un insumo vacio no cuenta como verde, aqui igual que en
        # las puertas del certificado.
        print("NIVEL1 ERROR: insumo vacio — no se linto ninguna skill")
    return 1 if (errores_nivel1 or fallos or trampas or flojos or not corpus) else 0


if __name__ == "__main__":
    raise SystemExit(main())
