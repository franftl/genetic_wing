"""
Grafica los resultados de la noche CFD (recinto grande) contra AeroBuildup y contra la CFD vieja (recinto chico).

Uso (Python del proyecto, desde la raiz del repo):
    python herramientas/graficar_hallazgos_noche.py
Salida: Ansys noche/comparacion_cfd_aerobuildup.png y Ansys noche/tabla_cfd_aerobuildup.csv
Los puntos que no convergieron se dibujan huecos.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "herramientas"))
from calibrar_cfd_aerobuildup import curva_aerobuildup  # noqa: E402

CSV = RAIZ / "resultados" / "cfd_run" / "noche" / "noche_grande" / "resultados.csv"
VIEJA = RAIZ / "resultados" / "cfd_run" / "barrido_v5_total.json"
SALIDA = RAIZ / "Ansys noche"

NOMBRES = {"transicion": "Transition SST, recinto grande", "sst": "k-ω SST, recinto grande"}
COLOR = {"transicion": "#1b6ca8", "sst": "#d9822b", "vieja": "#7f7f7f", "ab": "#111111"}


def main():
    with CSV.open(newline="") as f:
        filas = [{"modelo": r["modelo"], "alfa": float(r["alfa_deg"]), "CL": float(r["CL"]), "CD": float(r["CD"]),
                  "conv": r["convergio"] == "1", "it": int(r["iteraciones"])} for r in csv.DictReader(f)]
    vieja = json.loads(VIEJA.read_text())["resultados"]

    alfas = np.arange(-2, 10.01, 0.5)
    puntos = sorted({r["alfa"] for r in filas} | {v["alfa_deg"] for v in vieja})
    todos = np.array(sorted(set(alfas) | set(puntos)))
    ab = dict(zip(todos, curva_aerobuildup(todos)))
    curva = np.array([ab[a] for a in alfas])

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, ax = plt.subplots(2, 2, figsize=(13, 9))
    ax = ax.ravel()
    ax[0].plot(alfas, curva[:, 0], "-", color=COLOR["ab"], lw=2, label="AeroBuildup (modelo)")
    ax[1].plot(alfas, curva[:, 1], "-", color=COLOR["ab"], lw=2)
    ax[2].plot(curva[:, 1], curva[:, 0], "-", color=COLOR["ab"], lw=2)
    ax[3].plot(alfas, curva[:, 0] / curva[:, 1], "-", color=COLOR["ab"], lw=2)

    va = np.array([v["alfa_deg"] for v in vieja])
    vcl, vcd = np.array([v["CL"] for v in vieja]), np.array([v["CD"] for v in vieja])
    for x, (xs, ys) in zip(ax, [(va, vcl), (va, vcd), (vcd, vcl), (va, vcl / vcd)]):
        x.plot(xs, ys, "s", color=COLOR["vieja"], ms=4, label="CFD vieja (k-ω SST, recinto chico, tendencia)" if x is ax[0] else None)

    usada = set()
    for r in filas:
        c = COLOR[r["modelo"]]
        etq = None
        if r["modelo"] not in usada:  # leyenda con marcador relleno aunque el primer punto sea hueco
            ax[0].plot([], [], "o-", color=c, ms=5, lw=1.2, label=NOMBRES[r["modelo"]] + " (tendencia)")
            usada.add(r["modelo"])
        kw = dict(marker="o", ms=5, color=c, mfc=c if r["conv"] else "white", mew=1.3, ls="none")
        ax[0].plot(r["alfa"], r["CL"], label=etq, **kw)
        ax[1].plot(r["alfa"], r["CD"], **kw)
        ax[2].plot(r["CD"], r["CL"], **kw)
        ax[3].plot(r["alfa"], r["CL"] / r["CD"], **kw)

    def tendencia(al, cl, cd, color):
        """CL lineal en α y CD = CD0 + k·CL² (por minimos cuadrados), solo con puntos convergidos; en el rango de los puntos."""
        if len(al) < 2:
            return
        a = np.linspace(min(al), max(al), 60)
        pcl = np.polyfit(al, cl, 1)
        A = np.vstack([np.ones(len(cl)), np.asarray(cl) ** 2]).T
        (cd0, k), *_ = np.linalg.lstsq(A, cd, rcond=None)
        cl_t = np.polyval(pcl, a)
        cd_t = cd0 + k * cl_t ** 2
        kw = dict(color=color, lw=1.2, ls="--")
        ax[0].plot(a, cl_t, **kw)
        ax[1].plot(a, cd_t, **kw)
        ax[2].plot(cd_t, cl_t, **kw)
        ax[3].plot(a, cl_t / cd_t, **kw)

    tendencia(va, vcl, vcd, COLOR["vieja"])
    for modelo in NOMBRES:
        pts = [r for r in filas if r["modelo"] == modelo and r["conv"]]
        tendencia([r["alfa"] for r in pts], [r["CL"] for r in pts], [r["CD"] for r in pts], COLOR[modelo])
    ax[0].plot([], [], "o", mfc="white", color="#555", mew=1.3, ms=5, label="hueco = no convergió")

    for x, (xl, yl, t) in zip(ax, [("α [°]", "CL", "Sustentación"), ("α [°]", "CD", "Resistencia"),
                                   ("CD", "CL", "Polar"), ("α [°]", "CL/CD", "Eficiencia")]):
        x.set(xlabel=xl, ylabel=yl, title=t)
        x.grid(alpha=0.3)
    ax[0].legend(fontsize=8, loc="upper left")
    fig.suptitle("Avión v_tail, 22.22 m/s — CFD (Fluent 24.1) vs AeroBuildup  (trazos: tendencia de la CFD con puntos convergidos)", fontsize=13)
    fig.tight_layout()
    fig.savefig(SALIDA / "comparacion_cfd_aerobuildup.png", dpi=140)

    # tabla
    with (SALIDA / "tabla_cfd_aerobuildup.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["serie", "alfa", "convergio", "CL_cfd", "CD_cfd", "CL_ab", "CD_ab", "dCL_pct", "CD_cfd/CD_ab"])
        for r in filas:
            cl_ab, cd_ab = ab[r["alfa"]]
            w.writerow([r["modelo"], r["alfa"], int(r["conv"]), "%.4f" % r["CL"], "%.5f" % r["CD"], "%.4f" % cl_ab,
                        "%.5f" % cd_ab, "%.1f" % (100 * (r["CL"] / cl_ab - 1)), "%.2f" % (r["CD"] / cd_ab)])
        for v in vieja:
            cl_ab, cd_ab = ab[v["alfa_deg"]]
            w.writerow(["vieja_sst_recinto_chico", v["alfa_deg"], 1, "%.4f" % v["CL"], "%.5f" % v["CD"], "%.4f" % cl_ab,
                        "%.5f" % cd_ab, "%.1f" % (100 * (v["CL"] / cl_ab - 1)), "%.2f" % (v["CD"] / cd_ab)])
    print("escrito en", SALIDA)


if __name__ == "__main__":
    main()
