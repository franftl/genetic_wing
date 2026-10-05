"""
Corre la competencia de topologías CON el viento de los sitios y la compara
con la corrida sin viento del 18/09 (optimizacion_avion/ganadores.json).

    python viento/optimizar_con_viento.py                 # corre todo y compara (~20 min)
    python viento/optimizar_con_viento.py --solo-comparar # rearma tabla y gráficos

Salidas:
    optimizacion_avion/ganadores_viento.json   ganadores con viento (mismo formato que ganadores.json)
    viento/resultados_optimizacion/            tabla comparativa (CSV y Markdown) y gráficos

El viento entra por mision_avion.VIENTO_ACTIVO (ver Research Note 16).
La semilla del azar es fija: correr dos veces da el mismo resultado.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from optimizacion_avion import mision_avion as ma          # noqa: E402
from optimizacion_avion import competencia                  # noqa: E402
from optimizacion_avion.geometria_avion import TOPOLOGIAS   # noqa: E402

SALIDA = REPO / "viento" / "resultados_optimizacion"
RUTA_SIN_VIENTO = REPO / "optimizacion_avion" / "ganadores.json"
RUTA_CON_VIENTO = REPO / "optimizacion_avion" / "ganadores_viento.json"
TOPS = list(TOPOLOGIAS.keys())


def _json(obj) -> str:
    return json.dumps(obj, indent=2, default=float, ensure_ascii=False)


def optimizar(topologias, paciencia, max_gen, semilla):
    ma.VIENTO_ACTIVO = True
    SALIDA.mkdir(parents=True, exist_ok=True)
    for top in topologias:
        random.seed(semilla + TOPS.index(top))        # misma secuencia de azar por topología
        est = competencia.optimizar_topologia(top, seed_population=competencia.SEEDS_POR_TOPOLOGIA[top],
                                              paciencia=paciencia, max_generaciones=max_gen)
        mejor = est.mejor()
        res = {"score": mejor.score, "generaciones": est.generation, "params": mejor.params,
               "analisis": ma.analizar_mision_avion(mejor.params, top), "historial": est.historial}
        (SALIDA / f"ganador_viento_{top}.json").write_text(_json(res), encoding="utf-8")
        print(f"[{top}] listo: score con viento {mejor.score:.4f} en {est.generation} generaciones")


def _evaluar(params, top, viento: bool):
    ma.VIENTO_ACTIVO = viento
    try:
        a = ma.analizar_mision_avion(params, top)
        s = sum(w * f for _, w, f in ma._terminos(a)) if a else float("-inf")
        return s, a
    finally:
        ma.VIENTO_ACTIVO = True


def comparar():
    sin = json.loads(RUTA_SIN_VIENTO.read_text(encoding="utf-8"))
    con = {}
    for top in TOPS:
        ruta = SALIDA / f"ganador_viento_{top}.json"
        if ruta.exists():
            con[top] = json.loads(ruta.read_text(encoding="utf-8"))
    RUTA_CON_VIENTO.write_text(_json({t: {k: v[k] for k in ("score", "generaciones", "params", "analisis")}
                                      for t, v in con.items()}), encoding="utf-8")

    filas = []
    for top in TOPS:
        if top not in con:
            continue
        s_f_viento, a_f = _evaluar(sin[top]["params"], top, True)     # diseño de Felipe, en el sitio
        s_v, a_v = _evaluar(con[top]["params"], top, True)             # diseño con viento, en el sitio
        for nombre, s, a in (("sin viento (18/09)", s_f_viento, a_f), ("con viento", s_v, a_v)):
            filas.append({
                "topologia": top, "diseno": nombre, "score_en_el_sitio": s,
                "envergadura_m": a["envergadura"], "superficie_m2": a["S"], "alargamiento": a["AR"],
                "carga_alar_N_m2": a["carga_alar"], "masa_kg": a["masa_total"],
                "LD_crucero": a["LD_crucero"], "D_crucero_N": a["D_crucero"],
                "turbulencia_extra_pct": 100 * a["extra_turbulencia"], "D_turbulento_N": a["D_turbulento"],
                "v_perdida_ms": a["v_stall"], "margen_vuelo_lento_pct": 100 * a["margen_lento"],
                "n_rafaga": a["n_con_rafaga"], "margen_perdida_rafaga_pct": 100 * a["margen_perdida"],
                "margen_estatico_pct": 100 * a["SM"],
            })

    with open(SALIDA / "comparacion_sin_vs_con_viento.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)

    cols = [("topologia", "Topología", "{}"), ("diseno", "Diseño", "{}"), ("score_en_el_sitio", "Score en el sitio", "{:.3f}"),
            ("envergadura_m", "b [m]", "{:.2f}"), ("superficie_m2", "S [m²]", "{:.3f}"), ("alargamiento", "AR", "{:.1f}"),
            ("carga_alar_N_m2", "W/S [N/m²]", "{:.1f}"), ("masa_kg", "Masa [kg]", "{:.2f}"), ("LD_crucero", "L/D", "{:.2f}"),
            ("turbulencia_extra_pct", "Turb. [%]", "+{:.1f}"), ("v_perdida_ms", "V pérdida [m/s]", "{:.2f}"),
            ("n_rafaga", "n ráfaga", "{:.2f}")]
    md = ["| " + " | ".join(c[1] for c in cols) + " |", "|" + "---|" * len(cols)]
    for fl in filas:
        md.append("| " + " | ".join(fmt.format(fl[k]) for k, _, fmt in cols) + " |")
    orden = sorted({fl["topologia"] for fl in filas},
                   key=lambda t: -max(fl["score_en_el_sitio"] for fl in filas if fl["topologia"] == t and fl["diseno"] == "con viento"))
    md += ["", "Ranking con viento: " + " > ".join(orden)]
    (SALIDA / "comparacion_sin_vs_con_viento.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    _graficos(filas, con)


def _graficos(filas, con):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    tops = [t for t in TOPS if any(f["topologia"] == t for f in filas)]
    get = lambda t, d, k: next(f[k] for f in filas if f["topologia"] == t and f["diseno"] == d)  # noqa: E731
    x = np.arange(len(tops))
    fig, axs = plt.subplots(1, 4, figsize=(17, 4.2))
    for ax, (k, titulo) in zip(axs, [("score_en_el_sitio", "Score en el sitio"), ("superficie_m2", "Superficie alar [m²]"),
                                     ("v_perdida_ms", "Velocidad de pérdida [m/s]"), ("LD_crucero", "L/D en crucero")]):
        ax.bar(x - 0.2, [get(t, "sin viento (18/09)", k) for t in tops], 0.4, label="diseño sin viento (18/09)", color="#9aa5b1")
        ax.bar(x + 0.2, [get(t, "con viento", k) for t in tops], 0.4, label="diseño con viento", color="#2f6fb0")
        ax.set_xticks(x, tops, rotation=30, ha="right")
        ax.set_title(titulo)
        if k == "v_perdida_ms":
            ax.axhline(ma.V_LENTO, color="#c0392b", lw=1, ls="--")
            ax.set_ylim(7, 10.5)
    axs[0].legend(fontsize=8, loc="lower left")
    fig.suptitle("Diseño sin viento vs con viento, ambos evaluados con el viento del sitio")
    fig.tight_layout()
    fig.savefig(SALIDA / "comparacion_sin_vs_con_viento.png", dpi=150)

    fig, ax = plt.subplots(figsize=(7, 4))
    for t in tops:
        h = con[t]["historial"]
        ax.plot([g["generation"] for g in h], [max(g["parent_scores"]) for g in h], label=t)
    ax.set_xlabel("generación")
    ax.set_ylabel("mejor score (con viento)")
    ax.set_title("Convergencia con viento")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(SALIDA / "convergencia_con_viento.png", dpi=150)
    print(f"\nGráficos en {SALIDA}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--topologias", nargs="*", default=TOPS)
    ap.add_argument("--paciencia", type=int, default=8)          # igual que la corrida del 18/09
    ap.add_argument("--max-generaciones", type=int, default=35)
    ap.add_argument("--semilla", type=int, default=2026)
    ap.add_argument("--solo-comparar", action="store_true")
    ap.add_argument("--sin-comparar", action="store_true")
    a = ap.parse_args()
    if not a.solo_comparar:
        optimizar(a.topologias, a.paciencia, a.max_generaciones, a.semilla)
    if not a.sin_comparar:
        comparar()


if __name__ == "__main__":
    main()
