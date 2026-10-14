"""
Corre la competencia de topologías CON el viento de los sitios y la compara
con la corrida sin viento del 18/09 (optimizacion_avion/ganadores.json).

    python viento/optimizar_con_viento.py                 # corre todo y compara (~1 h)
    python viento/optimizar_con_viento.py --solo-comparar # rearma tablas, gráficos y vistas 3D

Salidas:
    optimizacion_avion/ganadores_viento.json   ganadores con viento (mismo formato que ganadores.json)
    viento/resultados/                         todo lo demás, ordenado por tipo (ver su LEEME.md):
        ganadores/                             ganador_viento_<topologia>.json (con historial)
        tablas/                                comparacion_sin_vs_con_viento.csv y .md
        graficos/comparacion/                  barras: score, superficie, pérdida, L/D; y performance
        graficos/curvas_vuelo_nivelado/        empuje, potencia y L/D contra velocidad
        graficos/convergencia/                 mejor score por generación
        vistas_3d/                             un HTML interactivo por avión (sin y con viento)

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

# Todo lo que produce este script, ordenado por tipo (ver viento/resultados/LEEME.md).
SALIDA = REPO / "viento" / "resultados"
DIR_GANADORES = SALIDA / "ganadores"
DIR_TABLAS = SALIDA / "tablas"
DIR_COMPARACION = SALIDA / "graficos" / "comparacion"
DIR_CURVAS = SALIDA / "graficos" / "curvas_vuelo_nivelado"
DIR_CONVERGENCIA = SALIDA / "graficos" / "convergencia"
DIR_3D = SALIDA / "vistas_3d"


def _crear_carpetas():
    for d in (DIR_GANADORES, DIR_TABLAS, DIR_COMPARACION, DIR_CURVAS, DIR_CONVERGENCIA, DIR_3D):
        d.mkdir(parents=True, exist_ok=True)
RUTA_SIN_VIENTO = REPO / "optimizacion_avion" / "ganadores.json"
RUTA_CON_VIENTO = REPO / "optimizacion_avion" / "ganadores_viento.json"
TOPS = list(TOPOLOGIAS.keys())


def _json(obj) -> str:
    return json.dumps(obj, indent=2, default=float, ensure_ascii=False)


def optimizar(topologias, paciencia, max_gen, semilla):
    ma.VIENTO_ACTIVO = True
    _crear_carpetas()
    for top in topologias:
        random.seed(semilla + TOPS.index(top))        # misma secuencia de azar por topología
        est = competencia.optimizar_topologia(top, seed_population=competencia.SEEDS_POR_TOPOLOGIA[top],
                                              paciencia=paciencia, max_generaciones=max_gen)
        mejor = est.mejor()
        res = {"score": mejor.score, "generaciones": est.generation, "params": mejor.params,
               "analisis": ma.analizar_mision_avion(mejor.params, top), "historial": est.historial}
        (DIR_GANADORES / f"ganador_viento_{top}.json").write_text(_json(res), encoding="utf-8")
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
    _crear_carpetas()
    sin = json.loads(RUTA_SIN_VIENTO.read_text(encoding="utf-8"))
    con = {}
    for top in TOPS:
        ruta = DIR_GANADORES / f"ganador_viento_{top}.json"
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
                "potencia_crucero_W": a["potencia_W"], "D_vmax_N": a["D_vmax"],
                "potencia_vmax_W": a["D_vmax"] * ma.V_MAX,
            })

    with open(DIR_TABLAS / "comparacion_sin_vs_con_viento.csv", "w", newline="", encoding="utf-8") as f:
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
    (DIR_TABLAS / "comparacion_sin_vs_con_viento.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    _graficos(filas, con)
    _graficos_performance(filas, sin, con)
    _vistas_3d(sin, con)


def _vistas_3d(sin, con):
    """Una página HTML interactiva (plotly) por avión: el diseño sin viento de
    Felipe y el diseño con viento de cada topología. Se abren con doble clic
    en el navegador (rotar arrastrando, zoom con la rueda)."""
    from optimizacion_avion.geometria_avion import construir_avion

    for top in TOPS:
        if top not in con:
            continue
        for params, nombre in ((sin[top]["params"], "sin_viento_18-09"), (con[top]["params"], "con_viento")):
            fig = construir_avion(params, top).draw(backend="plotly", show=False)
            fig.update_layout(title=f"{top} — diseño {nombre.replace('_', ' ')}")
            fig.write_html(DIR_3D / f"{top}_{nombre}.html", include_plotlyjs="cdn")
    print(f"Vistas 3D en {DIR_3D}")


def _curvas_vuelo_nivelado(params, top, a, n=18):
    """Empuje requerido (= D), potencia requerida y L/D en vuelo nivelado,
    con el viento del sitio, desde poco arriba de la pérdida LIMPIA hasta
    V_MAX + 10 %. El ángulo de ataque de cada velocidad sale de la pendiente
    CL_alpha que midió analizar_mision_avion (lineal, como hace la misión
    para ubicar el punto de V_MAX)."""
    import aerosandbox as asb
    import numpy as np
    from optimizacion_avion.geometria_avion import construir_avion, geometria_flap

    ma.VIENTO_ACTIVO = True
    atm = ma._atmosfera()
    rho, S, W = a["rho"], a["S"], a["peso"]
    avion = construir_avion(params, top)
    fl = geometria_flap(params)
    penal = 1.0 + ma.PENAL_CD_FLAP * fl["frac_superficie"] if fl["tiene_flap"] else 1.0

    v_stall_limpio = np.sqrt(2 * W / (rho * S * a["CL_max_crucero"]))
    V = np.linspace(1.1 * v_stall_limpio, 1.1 * ma.V_MAX, n)
    D = []
    for v in V:
        CL_req = W / (0.5 * rho * v ** 2 * S)
        alpha = a["alpha_crucero"] + (CL_req - a["CL_crucero"]) / a["CL_alpha_por_grado"]
        r = asb.AeroBuildup(airplane=avion, op_point=asb.OperatingPoint(atmosphere=atm, velocity=v, alpha=alpha)).run()
        D.append(0.5 * rho * v ** 2 * S * ma._escalar(r["CD"]) * penal)
    D = np.array(D)
    return {"V": V, "D": D, "P": D * V, "LD": W / D, "v_stall_limpio": v_stall_limpio}


def _graficos_performance(filas, sin, con):
    """Curvas de empuje/potencia/L-D contra velocidad y barras de performance:
    diseño sin viento (Felipe, 18/09) contra diseño con viento, los dos
    evaluados con el viento del sitio."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from optimizacion_ala.estructura import N_LIMITE

    GRIS, AZUL = "#9aa5b1", "#2f6fb0"
    tops = [t for t in TOPS if any(f["topologia"] == t for f in filas)]
    get = lambda t, d, k: next(f[k] for f in filas if f["topologia"] == t and f["diseno"] == d)  # noqa: E731

    # --- Curvas en vuelo nivelado: una columna por topología ---
    fig, axs = plt.subplots(3, len(tops), figsize=(3.6 * len(tops), 9), sharex=True, squeeze=False)
    for j, top in enumerate(tops):
        for params, color, etiqueta in ((sin[top]["params"], GRIS, "sin viento (18/09)"),
                                        (con[top]["params"], AZUL, "con viento")):
            _, a = _evaluar(params, top, True)
            c = _curvas_vuelo_nivelado(params, top, a)
            axs[0, j].plot(c["V"] * 3.6, c["D"], color=color, lw=2, label=etiqueta)
            axs[1, j].plot(c["V"] * 3.6, c["P"], color=color, lw=2)
            axs[2, j].plot(c["V"] * 3.6, c["LD"], color=color, lw=2)
        axs[0, j].set_title(top)
        for i in range(3):
            for v, ls in ((ma.V_CRUCERO, "-"), (ma.V_MAX, "--")):
                axs[i, j].axvline(v * 3.6, color="#c0392b", lw=0.8, ls=ls, alpha=0.7)
            axs[i, j].grid(alpha=0.3)
        axs[2, j].set_xlabel("velocidad [km/h]")
    axs[0, 0].set_ylabel("empuje requerido = D [N]")
    axs[1, 0].set_ylabel("potencia requerida [W]")
    axs[2, 0].set_ylabel("L/D")
    axs[0, 0].legend(fontsize=8)
    fig.suptitle("Vuelo nivelado con el viento del sitio — línea llena: crucero 80 km/h, punteada: máxima 120 km/h\n"
                 "(potencia aerodinámica, sin rendimiento de hélice ni motor; desde 1.1 × pérdida sin flap)", fontsize=11)
    fig.tight_layout()
    fig.savefig(DIR_CURVAS / "curvas_empuje_potencia.png", dpi=150)
    plt.close(fig)

    # --- Barras de performance ---
    paneles = [("D_crucero_N", "Resistencia en crucero [N]"), ("potencia_crucero_W", "Potencia en crucero [W]"),
               ("D_vmax_N", "Resistencia a 120 km/h [N]"), ("potencia_vmax_W", "Potencia a 120 km/h [W]"),
               ("masa_kg", "Masa [kg]"), ("carga_alar_N_m2", "Carga alar [N/m²]"),
               ("n_rafaga", "Factor de carga con ráfaga [g]"), ("turbulencia_extra_pct", "Resistencia extra por turbulencia [%]")]
    x = np.arange(len(tops))
    fig, axs = plt.subplots(2, 4, figsize=(18, 8))
    for ax, (k, titulo) in zip(axs.flat, paneles):
        ax.bar(x - 0.2, [get(t, "sin viento (18/09)", k) for t in tops], 0.4, label="diseño sin viento (18/09)", color=GRIS)
        ax.bar(x + 0.2, [get(t, "con viento", k) for t in tops], 0.4, label="diseño con viento", color=AZUL)
        ax.set_xticks(x, tops, rotation=30, ha="right")
        ax.set_title(titulo, fontsize=10)
        if k == "n_rafaga":
            ax.axhline(N_LIMITE, color="#c0392b", lw=1.2, ls="--", label=f"N_LIMITE = {N_LIMITE:.1f}")
            ax.legend(fontsize=7, loc="lower right")
    axs[0, 0].legend(fontsize=8, loc="lower left")
    fig.suptitle("Performance: diseño sin viento vs con viento, ambos evaluados con el viento del sitio")
    fig.tight_layout()
    fig.savefig(DIR_COMPARACION / "comparacion_performance.png", dpi=150)
    plt.close(fig)
    print(f"Gráficos de performance en {SALIDA}")


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
    fig.savefig(DIR_COMPARACION / "comparacion_sin_vs_con_viento.png", dpi=150)

    fig, ax = plt.subplots(figsize=(7, 4))
    for t in tops:
        h = con[t]["historial"]
        ax.plot([g["generation"] for g in h], [max(g["parent_scores"]) for g in h], label=t)
    ax.set_xlabel("generación")
    ax.set_ylabel("mejor score (con viento)")
    ax.set_title("Convergencia con viento")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(DIR_CONVERGENCIA / "convergencia_con_viento.png", dpi=150)
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
