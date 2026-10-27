"""
Superpone el barrido de alpha de la CFD (Fluent, barrido_*.json) con el modelo del optimizador (AeroBuildup) y con un VLM
puro (asb.VortexLatticeMethod, no viscoso) para la MISMA geometria, y estima si la diferencia es una distorsion de
pendiente (factor sobre alpha) o un offset de resistencia.

Uso (Python del proyecto, desde la raiz):
    python herramientas/comparar_cfd_modelo.py [resultados/cfd_run/barrido_v5_total.json]
Salida: resultados/cfd_run/comparacion_cfd_modelo.png y .json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "herramientas"))

import aerosandbox as asb  # noqa: E402
from exportar_cfd_avion import cargar_params  # noqa: E402
from optimizacion_avion import mision_avion as ma  # noqa: E402
from optimizacion_avion.geometria_avion import construir_avion  # noqa: E402

SALIDA = RAIZ / "resultados" / "cfd_run"


def _f(x) -> float:
    return float(np.atleast_1d(x)[0])


def curvas_modelo(avion, alphas):
    atm, V = ma._atmosfera(), float(ma.V_CRUCERO)
    ab, vlm = [], []
    for al in alphas:
        op = asb.OperatingPoint(atmosphere=atm, velocity=V, alpha=float(al))
        r = asb.AeroBuildup(airplane=avion, op_point=op).run()
        ab.append((_f(r["CL"]), _f(r["CD"])))
        v = asb.VortexLatticeMethod(airplane=avion, op_point=op, spanwise_resolution=8, chordwise_resolution=6).run()
        vlm.append((_f(v["CL"]), _f(v["CD"])))
    return np.array(ab), np.array(vlm)


def main():
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else SALIDA / "barrido_v5_total.json"
    cfd = json.loads(ruta.read_text())["resultados"]
    a_cfd = np.array([r["alfa_deg"] for r in cfd])
    cl_cfd = np.array([r["CL"] for r in cfd])
    cd_cfd = np.array([r["CD"] for r in cfd])

    params, top = cargar_params(RAIZ / "resultados" / "avion_design_params_v_tail.json", "v_tail")
    avion = construir_avion(params, top)
    alphas = np.arange(-4, 12.01, 1.0)
    ab, vlm = curvas_modelo(avion, alphas)

    # modelo (AeroBuildup) a los alphas de la CFD
    ab_c, vlm_c = curvas_modelo(avion, a_cfd)

    # 1) pendiente: dCL_cfd/dCL_modelo respecto de alpha = 0
    dcl_c, dcl_m = cl_cfd - cl_cfd[a_cfd == 0][0], ab_c[:, 0] - ab_c[a_cfd == 0, 0][0]
    k = float(np.sum(dcl_c * dcl_m) / np.sum(dcl_m ** 2))          # CFD ~ k * modelo (mismo alpha)
    dcl_v = vlm_c[:, 0] - vlm_c[a_cfd == 0, 0][0]
    k_vlm = float(np.sum(dcl_c * dcl_v) / np.sum(dcl_v ** 2))
    cl_corr = ab_c[a_cfd == 0, 0][0] + dcl_c / k                    # CFD "des-distorsionado" al alpha del modelo

    # 2) resistencia a igual CL: CD_modelo(CL) por interpolacion de la polar del modelo
    o = np.argsort(ab[:, 0])
    cd_mod_en_cl = np.interp(cl_cfd, ab[o, 0], ab[o, 1])
    d_cd = cd_cfd - cd_mod_en_cl

    res = {"factor_pendiente_CFD_sobre_AeroBuildup": k, "factor_pendiente_CFD_sobre_VLM": k_vlm,
           "alfa_cfd_deg": a_cfd.tolist(), "CL_cfd": cl_cfd.tolist(), "CL_aerobuildup_mismo_alfa": ab_c[:, 0].tolist(),
           "CL_vlm_mismo_alfa": vlm_c[:, 0].tolist(), "CD_cfd": cd_cfd.tolist(),
           "CD_aerobuildup_mismo_CL": cd_mod_en_cl.tolist(), "CD_cfd_menos_modelo_mismo_CL": d_cd.tolist()}
    (SALIDA / "comparacion_cfd_modelo.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 4, figsize=(17, 4))
    ax[0].plot(alphas, ab[:, 0], "-", label="AeroBuildup (modelo)")
    ax[0].plot(alphas, vlm[:, 0], "--", label="VLM puro")
    ax[0].plot(a_cfd, cl_cfd, "ko", label="CFD (v5)")
    ax[0].plot(a_cfd, cl_cfd[a_cfd == 0][0] + (ab_c[:, 0] - ab_c[a_cfd == 0, 0][0]) * k, "r:",
               label="modelo con pendiente x%.2f" % k)
    ax[0].set(xlabel="alfa [deg]", ylabel="CL", title="Sustentacion")
    ax[1].plot(ab[:, 1], ab[:, 0], "-", label="AeroBuildup")
    ax[1].plot(vlm[:, 1], vlm[:, 0], "--", label="VLM puro (solo inducida)")
    ax[1].plot(cd_cfd, cl_cfd, "ko", label="CFD")
    ax[1].set(xlabel="CD", ylabel="CL", title="Polar")
    ax[2].plot(alphas, ab[:, 0] / ab[:, 1], "-", label="AeroBuildup")
    ax[2].plot(a_cfd, cl_cfd / cd_cfd, "ko", label="CFD")
    ax[2].set(xlabel="alfa [deg]", ylabel="L/D", title="Eficiencia")
    ax[3].plot(a_cfd, d_cd * 1e4, "ko-")
    ax[3].axhline(0, color="gray", lw=0.8)
    ax[3].set(xlabel="alfa [deg]", ylabel="CD_CFD - CD_modelo a igual CL  [cuentas de drag x1e-4]",
              title="Exceso de resistencia")
    for x in ax:
        x.grid(alpha=0.3)
        if x.get_legend_handles_labels()[0]:
            x.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(SALIDA / "comparacion_cfd_modelo.png", dpi=140)


if __name__ == "__main__":
    main()
