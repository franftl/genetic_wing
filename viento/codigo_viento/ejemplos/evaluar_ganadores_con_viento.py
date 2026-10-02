"""
Evalúa los diseños ganadores del optimizador (optimizacion_avion/ganadores.json)
con el viento real de Cañadón León y Puesto Hernández.

NO modifica nada del repositorio genetic_wing: solo LEE ganadores.json y usa
construir_avion() para armar la geometría. Todo lo que escribe va a la carpeta
de salida de este script.

Uso (desde la carpeta codigo_viento):
    python ejemplos/evaluar_ganadores_con_viento.py --repo "C:/ruta/a/genetic_wing"
    python ejemplos/evaluar_ganadores_con_viento.py --repo ... --sin-vlm   (rápido, sin AeroSandbox)

Qué calcula, para cada topología y cada sitio:
  1. Operabilidad a la velocidad de crucero del optimizador (80 km/h) y a V_MAX.
  2. CL de crucero con la densidad del sitio (el optimizador usa 1.225 kg/m3).
  3. Ráfaga rápida (FAR 23.341, misma cuenta que mision_avion.py) con la
     ráfaga de diseño del sitio en lugar de 3 m/s.
  4. (con VLM) Ráfaga 1-coseno barriendo la longitud H, con el avión libre de
     subir y el retardo de la sustentación: factor de carga y momento flector
     en la raíz del ala, como insumo para la estructura.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
import viento_uav as vu  # noqa: E402

# Valores de la misión de genetic_wing (optimizacion_avion/mision_avion.py, 28/09/2026).
# Se COPIAN acá en lugar de importarlos para no depender de que ese módulo cargue.
V_CRUCERO = 80.0 / 3.6
V_MAX = 120.0 / 3.6
RAFAGA_ACTUAL = 3.0
N_LIMITE_ESTRUCTURA = 3.0      # optimizacion_ala/estructura.py: N_LIMITE (N_ULTIMO = 4.5)


def buscar_repo(arg: str | None) -> Path:
    candidatos = [Path(arg)] if arg else []
    # Primero: el repo que contiene esta carpeta (genetic_wing/viento/codigo_viento/ejemplos).
    candidatos += [AQUI.parents[2], AQUI.parents[2] / "genetic_wing", AQUI.parents[3] / "genetic_wing",
                   Path.home() / "Documents" / "GitHub" / "genetic_wing"]
    for c in candidatos:
        if (c / "optimizacion_avion" / "ganadores.json").exists():
            return c
    raise SystemExit("No encuentro genetic_wing. Pasá la ruta con --repo \"...\\genetic_wing\"")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", help="carpeta del repositorio genetic_wing")
    ap.add_argument("--salida", default=str(AQUI.parent / "resultados"))
    ap.add_argument("--sin-vlm", action="store_true", help="saltea el análisis VLM (rápido)")
    args = ap.parse_args()

    repo = buscar_repo(args.repo)
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    ganadores = json.loads((repo / "optimizacion_avion" / "ganadores.json").read_text(encoding="utf-8"))
    fichas = {s: vu.cargar_ficha(s) for s in vu.SITIOS}
    print(f"Repositorio: {repo}\nTopologías: {', '.join(ganadores)}\n")

    # ---------------------------------------------------------------- 1-3: sin geometría
    filas = []
    for top, g in ganadores.items():
        a = g["analisis"]
        for s, f in fichas.items():
            op_c = vu.operabilidad(f, V_CRUCERO)
            op_cc = vu.operabilidad(f, V_CRUCERO, corregido=True)
            op_m = vu.operabilidad(f, V_MAX, corregido=True)
            r_act = vu.chequeo_rafaga_desde_analisis(a, f, criterio="operacion")
            r_dis = vu.chequeo_rafaga_desde_analisis(a, f, criterio="diseno")
            r_vmax_op = vu.chequeo_rafaga_desde_analisis(a, f, V=V_MAX, criterio="operacion", punto="vmax")
            r_vmax_dis = vu.chequeo_rafaga_desde_analisis(a, f, V=V_MAX, criterio="diseno", punto="vmax")
            filas.append({
                "topologia": top, "sitio": s,
                "masa_kg": round(a["masa_total"], 2), "carga_alar_N_m2": round(a["carga_alar"], 1),
                "operable_80kmh_%": round(100 * op_c["fraccion_operable"], 1),
                "operable_80kmh_corr_%": round(100 * op_cc["fraccion_operable"], 1),
                "sin_avance_80kmh_corr_%": round(100 * op_cc["fraccion_sin_avance"], 1),
                "operable_120kmh_corr_%": round(100 * op_m["fraccion_operable"], 1),
                "CL_crucero_opt": round(a["CL_crucero"], 3),
                "CL_crucero_sitio": round(vu.CL_crucero_en_sitio(a, f), 3),
                "Kg_sitio": round(r_dis["Kg"], 3),
                "dalpha_rafaga_3.1_deg": round(r_act["d_alpha"], 2),
                "dalpha_rafaga_4.6_deg": round(r_dis["d_alpha"], 2),
                "n_rafaga_4.6": round(r_dis["n_max"], 2),
                "margen_perdida_4.6_%": round(100 * r_dis["margen_perdida"], 1),
                "n_limite_por_perdida": round(r_dis["n_limite_por_perdida"], 2),
                "n_rafaga_3.1_a_120kmh": round(r_vmax_op["n_max"], 2),
                "n_rafaga_4.6_a_120kmh": round(r_vmax_dis["n_max"], 2),
                "n_limite_estructura_opt": N_LIMITE_ESTRUCTURA,
                "margen_perdida_opt_%": round(100 * a["margen_perdida"], 1),
            })
    ruta = salida / "evaluacion_ganadores_viento.csv"
    with open(ruta, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0]))
        w.writeheader(); w.writerows(filas)
    print(f"-> {ruta}")
    for r in filas:
        print(f"{r['topologia']:12s} {r['sitio']:17s} operable {r['operable_80kmh_corr_%']:5.1f}%  "
              f"n(4.6 m/s) {r['n_rafaga_4.6']:4.2f}  margen pérdida {r['margen_perdida_4.6_%']:5.1f}%")

    # ---------------------------------------------------------------- figura operabilidad vs V
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    Vs = np.linspace(12, 36, 49)
    fig, ax = plt.subplots(figsize=(7, 4))
    for s, f, c in (("canadon_leon", fichas["canadon_leon"], "#2a78d6"),
                    ("puesto_hernandez", fichas["puesto_hernandez"], "#eb6834")):
        ax.plot(Vs, [100 * vu.operabilidad(f, v)["fraccion_operable"] for v in Vs], color=c, lw=2, label=f.nombre.split(" (")[0])
        ax.plot(Vs, [100 * vu.operabilidad(f, v, corregido=True)["fraccion_operable"] for v in Vs], color=c, lw=1.2, ls="--")
    for v, txt in ((V_CRUCERO, "crucero 80 km/h"), (V_MAX, "V_max 120 km/h")):
        ax.axvline(v, color="#3d3d3a", ls=":", lw=1)
        ax.text(v + 0.3, 5, txt, fontsize=8, rotation=90, va="bottom")
    ax.set(xlabel="Velocidad respecto del aire [m/s]", ylabel="% de horas diurnas operables",
           title="Operabilidad (ida y vuelta ≤ 1,5× el tiempo sin viento)", ylim=(0, 100))
    ax.grid(alpha=0.3); ax.legend(frameon=False, fontsize=8, loc="center right")
    ax.text(35.8, 2, "línea punteada: con corrección de cola", fontsize=7, color="#5f5e5a", ha="right")
    fig.tight_layout(); fig.savefig(salida / "operabilidad_vs_velocidad.png", dpi=150); plt.close(fig)

    if args.sin_vlm:
        return

    # ---------------------------------------------------------------- 4: VLM
    sys.path.insert(0, str(repo))
    from optimizacion_avion.geometria_avion import construir_avion   # solo lectura
    from viento_uav import vlm_viento as vv

    f = fichas["canadon_leon"]           # mayor densidad -> mayores cargas de ráfaga
    U = f.U_ds("diseno")
    filas_vlm, curvas = [], {}
    for top, g in ganadores.items():
        a = g["analisis"]
        avion = construir_avion(g["params"], top)
        c = a["MAC"]
        H_lista = [round(6.25 * c, 2), round(12.5 * c, 2), 10.0, 20.0, 40.0, 80.0]
        print(f"VLM {top}: barrido de H = {H_lista} m ...")
        alpha = vv.alpha_de_trim_vlm(avion, V_CRUCERO, f.rho_diseno, a["peso"])
        res = vv.barrido_H(avion, V_CRUCERO, f.rho_diseno, a["peso"], U, H_lista,
                           n_muestras_vlm=30, alpha=alpha, dinamico=True)
        cuasi = vv.barrido_H(avion, V_CRUCERO, f.rho_diseno, a["peso"], U, [20.0],
                             n_muestras_vlm=25, alpha=alpha, dinamico=False)[0]
        r_kg = vu.chequeo_rafaga_desde_analisis(a, f, criterio="diseno")
        for r in res:
            filas_vlm.append({"topologia": top, "H_m": r["H"], "H_en_cuerdas": round(r["H"] / c, 1),
                              "n_max_dinamico": round(r["n_max"], 3),
                              "M_raiz_1g_Nm": round(r["M_raiz_1g"], 2), "M_raiz_max_Nm": round(r["M_raiz_max"], 2),
                              "relacion_M_raiz": round(r["relacion_M_raiz"], 3),
                              "CL_max_alcanzado": round(r["CL_max_alcanzado"], 3),
                              "CL_max_ala_opt": round(a["CL_max_crucero"], 3),
                              "n_max_Kg_FAR23": round(r_kg["n_max"], 3),
                              "n_max_cuasiestatico_cota": round(cuasi["n_max"], 3)})
        curvas[top] = res
    ruta = salida / "rafaga_vlm_barrido_H.csv"
    with open(ruta, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas_vlm[0]))
        w.writeheader(); w.writerows(filas_vlm)
    print(f"-> {ruta}")

    fig, ax = plt.subplots(figsize=(7, 4))
    paleta = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
    for (top, res), col in zip(curvas.items(), paleta):
        ax.plot([r["H"] for r in res], [r["n_max"] for r in res], marker="o", ms=4, lw=2, color=col, label=top)
    ax.set_xscale("log")
    ax.set(xlabel="Semilongitud de ráfaga H [m]", ylabel="Factor de carga máximo n",
           title=f"Ráfaga 1−coseno de {U:.1f} m/s a 80 km/h — Cañadón León\n(VLM + avión libre de subir + retardo de Küssner/Wagner)")
    ax.grid(alpha=0.3, which="both"); ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(salida / "rafaga_vlm_barrido_H.png", dpi=150); plt.close(fig)
    print("listo")


if __name__ == "__main__":
    main()
