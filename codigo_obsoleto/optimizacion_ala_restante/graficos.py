"""
Gráficos de la geometría y la performance del diseño final.

Todo lo de acá es para MIRAR un diseño ya elegido, no para optimizar: son
funciones caras (barren el ángulo de ataque, evalúan decenas de puntos) que no
tienen que estar en el loop.

Nada de esto usa el punto de operación fijo del objetivo. Las curvas de
performance se calculan sobre un barrido completo, que es lo que permite ver
la entrada en pérdida y la velocidad de mínima resistencia.
"""

from __future__ import annotations

import aerosandbox as asb
import matplotlib.pyplot as plt
import numpy as np

from .estructura import converger_masa
from .geometria import (
    MASA_TOTAL,
    WINGLET_MIN_H,
    _CAMBER_X,
    _N_ESTACIONES,
    _STATION_FRACTIONS,
    HALF_SPAN,
    construir_avion,
    distribucion_envergadura,
    linea_de_curvatura,
)

G = 9.81  # [m/s^2]


# =====================================================================
# 1. Geometría en 2D
# =====================================================================
def plot_geometria_2d(params: dict, figsize=(13, 12)):
    """Seis vistas del diseño: planta, perfil, frontal, lateral, y las
    distribuciones de cuerda y torsión a lo largo de la envergadura.

    Las curvas se dibujan con 80 estaciones interpoladas (no las 11 que usa el
    solver ni las 6 de control) para que se vea la forma real y suave; los
    puntos rojos marcan las 6 estaciones que SÍ son variables de diseño.

    Solo la planta y el perfil llevan escala 1:1. Las vistas frontal y lateral
    NO: son franjas de 2.2 m de ancho por unos centímetros de alto, y con
    escala igual quedarían como una raya ilegible."""
    from .geometria import construir_perfil

    y, cuerda, x_le, torsion = distribucion_envergadura(params, n=80)
    x_te = x_le + cuerda
    yc, cc, xc_le, tc = distribucion_envergadura(params, n=_N_ESTACIONES)

    hay_wl = params["winglet_height"] >= WINGLET_MIN_H
    h = params["winglet_height"]
    cant = np.radians(params["winglet_cant_deg"])
    swp = np.radians(params["winglet_sweep_deg"])

    fig, ax = plt.subplots(3, 2, figsize=figsize)

    # --- (0,0) VISTA SUPERIOR (planta) ---
    a = ax[0, 0]
    for s_ in (1, -1):
        a.plot(s_ * y, x_le, "b-", lw=1.6)
        a.plot(s_ * y, x_te, "b-", lw=1.6)
        a.plot(s_ * yc, xc_le, "ro", ms=5, zorder=5)
        a.plot([s_ * y[-1], s_ * y[-1]], [x_le[-1], x_te[-1]], "b-", lw=1.6)
    a.plot([-y[0], y[0]], [x_le[0], x_le[0]], "b-", lw=1.6)
    a.plot([-y[0], y[0]], [x_te[0], x_te[0]], "b-", lw=1.6)
    a.set_title("Vista superior (planta)", fontsize=10, weight="bold")
    a.set_xlabel("envergadura y [m]"); a.set_ylabel("x [m]")
    a.invert_yaxis(); a.set_aspect("equal"); a.grid(alpha=.3)

    # --- (0,1) PERFIL ---
    # Los TRES perfiles ancla, superpuestos. Ya no hay puntos de control que
    # dibujar: el perfil no se diseña, se elige del catálogo.
    a = ax[0, 1]
    from .geometria import perfil_en_fraccion
    from .perfiles import perfiles_del_diseno
    info = perfiles_del_diseno(params)
    anclas = [(0.0, info["raiz"], "k-", "raíz"),
              (info["pos_medio"], info["medio"], "b-", f"medio (y/b={info['pos_medio']:.2f})"),
              (1.0, info["punta"], "g-", "punta")]
    for frac, nombre, estilo, etiqueta in anclas:
        co = perfil_en_fraccion(params, frac).coordinates
        a.plot(co[:, 0], co[:, 1], estilo, lw=1.5, label=f"{etiqueta}: {nombre}")
    a.axhline(0, color="gray", lw=.5)
    a.set_title("Perfiles ancla (reales, del catálogo UIUC)", fontsize=10, weight="bold")
    a.set_xlabel("x/c"); a.set_aspect("equal"); a.grid(alpha=.3); a.legend(fontsize=7, loc="upper right")

    # --- (1,0) VISTA FRONTAL ---
    a = ax[1, 0]
    # El winglet se dibuja con su camino real (arco de transición incluido),
    # con 24 puntos en vez de las 3 secciones que ve el solver.
    from .geometria import camino_winglet, elevacion_envergadura
    z_elev = elevacion_envergadura(params, n=len(y))
    cam_wl = camino_winglet(params, (x_le[-1], y[-1], float(z_elev[-1])), n_filete=24)
    for s_ in (1, -1):
        a.plot(s_ * y, z_elev, "b-", lw=3)
        if cam_wl:
            a.plot([s_ * y[-1]] + [s_ * p_[1] for p_ in cam_wl],
                   [float(z_elev[-1])] + [p_[2] for p_ in cam_wl], "g-", lw=3)
    a.set_title("Vista frontal: diedro (escala vertical exagerada)", fontsize=10, weight="bold")
    a.set_xlabel("envergadura y [m]"); a.set_ylabel("z [m]"); a.grid(alpha=.3)
    # Ángulo de diedro equivalente: el de la recta raíz-punta.
    diedro_eq = np.degrees(np.arctan2(float(z_elev[-1]), float(y[-1])))
    a.text(0.02, 0.93,
           f"diedro equivalente {diedro_eq:+.1f}°  (punta {1000*float(z_elev[-1]):+.0f} mm)\n" +
           ((f"winglet {1000*h:.0f} mm, cant {np.degrees(cant):.0f}°, "
             f"radio {100*params.get('winglet_radio', 0.0):.0f}% de h") if hay_wl else "sin winglet"),
           transform=a.transAxes, fontsize=8, va="top", color="black")

    # --- (1,1) VISTA LATERAL ---
    a = ax[1, 1]
    a.plot(x_le, np.zeros_like(x_le), "b-", lw=2, label="borde de ataque")
    a.plot(x_te, np.zeros_like(x_te), "c-", lw=2, label="borde de fuga")
    if cam_wl:
        a.plot([x_le[-1]] + [p_[0] for p_ in cam_wl],
               [float(z_elev[-1])] + [p_[2] for p_ in cam_wl], "g-", lw=3, label="winglet")
    a.set_title("Vista lateral (escala vertical exagerada)", fontsize=10, weight="bold")
    a.set_xlabel("x [m]"); a.set_ylabel("z [m]"); a.grid(alpha=.3); a.legend(fontsize=7)

    # --- (2,0) DISTRIBUCIÓN DE CUERDA ---
    a = ax[2, 0]
    a.plot(y, 1000 * cuerda, "b-", lw=1.8)
    a.plot(yc, 1000 * cc, "ro", ms=6, label="estaciones de control (variables de diseño)")
    a.set_title("Cuerda a lo largo de la envergadura", fontsize=10, weight="bold")
    a.set_xlabel("y [m]"); a.set_ylabel("cuerda [mm]"); a.grid(alpha=.3); a.legend(fontsize=7)

    # --- (2,1) DISTRIBUCIÓN DE TORSIÓN ---
    a = ax[2, 1]
    a.plot(y, torsion, "b-", lw=1.8)
    a.plot(yc, tc, "ro", ms=6, label="estaciones de control (variables de diseño)")
    a.axhline(0, color="gray", lw=.5)
    a.set_title("Torsión a lo largo de la envergadura", fontsize=10, weight="bold")
    a.set_xlabel("y [m]"); a.set_ylabel("torsión [°]"); a.grid(alpha=.3); a.legend(fontsize=7)

    fig.suptitle("Geometría del diseño final", fontsize=13, weight="bold")
    fig.tight_layout()
    return fig


# =====================================================================
# 2. Barrido aerodinámico, pérdida y curvas de vuelo
# =====================================================================
def barrido_alpha(params: dict, alpha_min=-4.0, alpha_max=20.0, n=25, velocidad=20.0):
    """Corre AeroBuildup en un barrido de ángulo de ataque. Devuelve un dict
    con alpha, CL, CD y los datos de entrada en pérdida.

    La pérdida se detecta como el máximo de la curva CL(alpha). NeuralFoil,
    que es lo que AeroBuildup usa por debajo, sí modela la caída de
    sustentación tras la pérdida -- por eso este barrido tiene sentido y no da
    una recta infinita como daría un método puramente potencial."""
    alphas = np.linspace(alpha_min, alpha_max, n)
    avion = construir_avion(params)
    CL, CD = [], []
    for al in alphas:
        r = asb.AeroBuildup(airplane=avion, op_point=asb.OperatingPoint(velocity=velocidad, alpha=al)).run()
        CL.append(float(np.atleast_1d(r["CL"])[0]))
        CD.append(float(np.atleast_1d(r["CD"])[0]))
    CL, CD = np.array(CL), np.array(CD)

    i_stall = int(np.argmax(CL))
    CL_max = float(CL[i_stall])
    alpha_stall = float(alphas[i_stall])

    rho = asb.Atmosphere(altitude=0).density()
    S = avion.s_ref

    # MASA: se usa la CALCULADA por el modelo estructural (estructura.py), no
    # la constante MASA_TOTAL de geometria.py. Si no fuera así, la velocidad de
    # pérdida que reporta este gráfico contradiría a la que sale del análisis
    # de misión, que sí pesa el avión de verdad. MASA_TOTAL queda solo como
    # respaldo por si el modelo estructural no cierra para esta geometría.
    est = converger_masa(params)
    masa = est["masa_total"] if est is not None else MASA_TOTAL
    W = masa * G
    V_stall = float(np.sqrt(2 * W / (rho * S * CL_max))) if CL_max > 0 else float("nan")

    return {
        "alpha": alphas, "CL": CL, "CD": CD,
        "CL_max": CL_max, "alpha_stall": alpha_stall, "V_stall": V_stall,
        "rho": float(rho), "S": float(S), "W": float(W),
        "masa": float(masa), "masa_calculada": est is not None,
        "stall_en_el_borde": i_stall >= n - 1,
    }


def plot_performance(params: dict, figsize=(15, 4.5)):
    """Tres paneles: sustentación y resistencia contra velocidad a ángulo de
    ataque fijo, resistencia en vuelo nivelado, y la curva CL(alpha) con la
    pérdida marcada.

    La distinción entre los dos primeros importa:

    - A ALPHA FIJO, L y D crecen con V^2 -- LAS DOS, exactamente igual, porque
      salen de la misma fórmula (1/2 rho V^2 S) cambiando solo el
      coeficiente. Es la ley física desnuda, pero no corresponde a ningún
      vuelo real: si mantenés alpha y acelerás, subís. Las dos curvas van en
      un mismo eje: como L/D ~ 25, la de D queda cerca del piso y parece una
      recta, pero es cuadrática igual (verificado: al duplicar V las dos se
      multiplican por 4). Hay una nota en el gráfico aclarándolo.
    - En VUELO NIVELADO la sustentación está fija (L = peso) y es el ángulo de
      ataque el que se ajusta a cada velocidad. Ahí la resistencia tiene un
      MÍNIMO: a baja velocidad domina la inducida (mucho CL), a alta velocidad
      domina la de perfil (mucha presión dinámica). Esa curva es la que sirve
      para elegir velocidad de crucero y estimar autonomía."""
    b = barrido_alpha(params)
    rho, S, W = b["rho"], b["S"], b["W"]

    fig, ax = plt.subplots(1, 3, figsize=figsize)

    # --- (0) alpha fijo ---
    #
    # UN SOLO EJE vertical, sin anotaciones. Es la version original y la que
    # prefiere Felipe.
    #
    # Nota para quien lea el codigo (no va al grafico): L = 1/2 rho V^2 S CL y
    # D = 1/2 rho V^2 S CD son la MISMA formula cambiando solo el coeficiente,
    # asi que las dos crecen con V^2 exactamente -- al duplicar V, las dos se
    # multiplican por 4. Pero como L/D ~ 25, D es ~25 veces mas chica y en un
    # eje compartido queda cerca del piso, pareciendo una recta. NO es un error
    # de cuenta, es escala.
    a = ax[0]
    alpha_fijo = 4.0
    i = int(np.argmin(np.abs(b["alpha"] - alpha_fijo)))
    V = np.linspace(5, 35, 60)
    q = 0.5 * rho * V**2

    a.plot(V, q * S * b["CL"][i], "b-", lw=1.8, label=f"L  (α={b['alpha'][i]:.0f}°)")
    a.plot(V, q * S * b["CD"][i], "r-", lw=1.8, label=f"D  (α={b['alpha'][i]:.0f}°)")
    a.axhline(W, color="k", ls=":", lw=1.2, label=f"peso = {W:.1f} N ({b['masa']:.2f} kg)")
    a.set_title("L y D vs velocidad, a α fijo", fontsize=10, weight="bold")
    a.set_xlabel("velocidad [m/s]"); a.set_ylabel("fuerza [N]")
    a.grid(alpha=.3); a.legend(fontsize=8)

    # --- (1) vuelo nivelado ---
    a = ax[1]
    CL_asc = b["CL"][: int(np.argmax(b["CL"])) + 1]
    CD_asc = b["CD"][: int(np.argmax(b["CL"])) + 1]
    Vn = np.linspace(b["V_stall"], 35, 80)
    CL_req = 2 * W / (rho * Vn**2 * S)
    ok = CL_req <= b["CL_max"]
    CD_req = np.interp(CL_req[ok], CL_asc, CD_asc)
    D_niv = 0.5 * rho * Vn[ok] ** 2 * S * CD_req
    a.plot(Vn[ok], D_niv, "r-", lw=2, label="D en vuelo nivelado")
    a.axhline(W, color="k", ls=":", lw=1.2, label=f"L = peso = {W:.1f} N")
    j = int(np.argmin(D_niv))
    a.plot(Vn[ok][j], D_niv[j], "go", ms=9, zorder=5,
           label=f"D mínima: {Vn[ok][j]:.1f} m/s  (L/D={W/D_niv[j]:.1f})")
    a.axvline(b["V_stall"], color="orange", ls="--", lw=1.5,
              label=f"pérdida: {b['V_stall']:.1f} m/s")
    a.set_title("Vuelo nivelado: D vs velocidad", fontsize=10, weight="bold")
    a.set_xlabel("velocidad [m/s]"); a.set_ylabel("fuerza [N]")
    a.grid(alpha=.3); a.legend(fontsize=8)

    # --- (2) CL vs alpha ---
    a = ax[2]
    a.plot(b["alpha"], b["CL"], "b-", lw=1.8)
    a.plot(b["alpha_stall"], b["CL_max"], "o", color="orange", ms=10, zorder=5,
           label=f"pérdida: α={b['alpha_stall']:.1f}°, CLmax={b['CL_max']:.3f}")
    a.axhline(0, color="gray", lw=.5)
    a.set_title("CL vs ángulo de ataque", fontsize=10, weight="bold")
    a.set_xlabel("α [°]"); a.set_ylabel("CL"); a.grid(alpha=.3); a.legend(fontsize=8)

    fig.suptitle(
        f"Performance — masa {b['masa']:.2f} kg"
        f"{' (calculada)' if b['masa_calculada'] else ' (declarada)'}, S = {S:.3f} m², "
        f"velocidad de pérdida {b['V_stall']:.1f} m/s ({3.6*b['V_stall']:.0f} km/h)",
        fontsize=11, weight="bold")
    fig.tight_layout()
    return fig, b
