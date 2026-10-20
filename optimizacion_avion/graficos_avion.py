"""
Gráficos del vuelo lento del avión ganador: sustentación vs ángulo de ataque
con y sin flap superpuestos, y velocidad de pérdida / de despegue.

Se usa el MISMO modelo que puntúa a los candidatos (`mision_avion`), no uno
aparte:

  * la pendiente y el CL a alpha = 0 del avión limpio salen de AeroBuildup al
    Reynolds del vuelo lento;
  * el flap suma un CL a alpha = 0 que se mide con NeuralFoil en la sección del
    medio del tramo con flap (perfil limpio vs deflectado), escalado por la
    fracción de superficie con flap -- el mismo método de
    `mision_avion._delta_clmax_flap`;
  * el CL máximo de cada curva es el que usa el optimizador
    (`mision_avion._clmax_ala`, con FACTOR_CLMAX_3D), no el pico de AeroBuildup.

La transición a la pérdida se dibuja con un mínimo suave entre la recta de
sustentación y el CL máximo. Es solo la forma de la curva: el modelo NO
predice el comportamiento post-pérdida, por eso el gráfico se corta pocos
grados después del CL máximo.
"""
from __future__ import annotations

import aerosandbox as asb
import matplotlib.pyplot as plt
import numpy as np

from . import mision_avion as ma
from .geometria_avion import construir_avion, geometria_flap
from .perfiles_avion import perfil_con_flap, perfil_en_fraccion_avion


def _soft_min(a, b, p=40.0):
    """Mínimo suave entre la recta (a) y el techo (b); donde a <= 0 queda a."""
    a = np.asarray(a, float)
    pos = np.maximum(a, 1e-9)
    menor, mayor = np.minimum(pos, b), np.maximum(pos, b)
    suave = menor * (1.0 + (menor / mayor) ** p) ** (-1.0 / p)
    return np.where(a > 0, suave, a)


def datos_vuelo_lento(params: dict, topologia: str) -> dict | None:
    """Todo lo que hace falta para graficar el vuelo lento de un diseño.
    None si el modelo declara inválido el diseño."""
    a = ma.analizar_mision_avion(params, topologia)
    if a is None:
        return None
    avion = construir_avion(params, topologia)
    atm = ma._atmosfera()
    rho = float(atm.density())
    V = float(ma.V_LENTO)
    W, S = float(a["peso"]), float(a["S"])
    Re = float(a["Re_lento"])

    # --- recta de sustentación del avión limpio (AeroBuildup, vuelo lento)
    al_lin = np.linspace(-2.0, 6.0, 9)
    cl_lin = np.array([float(np.atleast_1d(asb.AeroBuildup(
        airplane=avion, op_point=asb.OperatingPoint(atmosphere=atm, velocity=V, alpha=x)).run()["CL"])[0])
        for x in al_lin])
    pend, cl0 = np.polyfit(al_lin, cl_lin, 1)           # CL = pend * alpha + cl0

    # --- CL máximo limpio y con flap, tal como los usa el optimizador
    cl_max_limpio = ma._clmax_ala(params, Re, V, con_flap=False)
    cl_max_flap = ma._clmax_ala(params, Re, V, con_flap=True)

    # --- desplazamiento del CL a alpha = 0 por el flap
    fl = geometria_flap(params)
    d_cl0 = 0.0
    if fl["tiene_flap"]:
        frac = 0.5 * (float(params["flap_inicio_frac"]) + float(params["flap_fin_frac"]))
        af = perfil_en_fraccion_avion(params, frac)
        af_f = perfil_con_flap(af, fl["deflexion"], fl["cuerda_frac"])
        cl2d = lambda x: float(np.atleast_1d(x.get_aero_from_neuralfoil(alpha=0.0, Re=Re, mach=V / 340.0)["CL"])[0])
        d_cl0 = max(cl2d(af_f) - cl2d(af), 0.0) * fl["frac_superficie"]

    return {"a": a, "rho": rho, "V": V, "W": W, "S": S, "pend": float(pend), "cl0": float(cl0),
            "cl_max_limpio": float(cl_max_limpio), "cl_max_flap": float(cl_max_flap),
            "d_cl0_flap": float(d_cl0), "flap": fl}


def graficar_vuelo_lento(params: dict, topologia: str, titulo: str | None = None):
    """Dos paneles: CL(alpha) con y sin flap, y CL necesario vs velocidad con las
    velocidades de pérdida y de despegue. Devuelve (fig, tabla_resumen)."""
    d = datos_vuelo_lento(params, topologia)
    if d is None:
        raise ValueError("El modelo declara inválido este diseño con los interruptores actuales.")
    pend, cl0, rho, W, S = d["pend"], d["cl0"], d["rho"], d["W"], d["S"]
    margen = float(ma.MARGEN_SOBRE_PERDIDA)

    def curva(alphas, desplaz, cl_max):
        return _soft_min(pend * alphas + cl0 + desplaz, cl_max)

    def alpha_de(cl_max, desplaz):
        return (cl_max - cl0 - desplaz) / pend

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 4.8))

    # ---------------- panel 1: CL vs alpha
    a_fin = max(alpha_de(d["cl_max_limpio"], 0.0), alpha_de(d["cl_max_flap"], d["d_cl0_flap"])) + 2.0
    al = np.linspace(-4.0, a_fin, 300)
    ax1.plot(al, curva(al, 0.0, d["cl_max_limpio"]), color="tab:blue", lw=2, label="Flap retraído")
    if d["flap"]["tiene_flap"]:
        ax1.plot(al, curva(al, d["d_cl0_flap"], d["cl_max_flap"]), color="tab:red", lw=2,
                 label=f"Flap {d['flap']['deflexion']:.0f}° ({100 * d['flap']['cuerda_frac']:.0f}% de cuerda, "
                       f"{100 * d['flap']['frac_superficie']:.0f}% de la superficie)")
    ax1.plot([alpha_de(d["cl_max_limpio"], 0.0)], [d["cl_max_limpio"]], "o", color="tab:blue")
    if d["flap"]["tiene_flap"]:
        ax1.plot([alpha_de(d["cl_max_flap"], d["d_cl0_flap"])], [d["cl_max_flap"]], "o", color="tab:red")
    ax1.axhline(d["a"]["CL_lento"], color="gray", ls="--", lw=1)
    ax1.text(al[0] + 0.2, d["a"]["CL_lento"] + 0.03, f"CL necesario a {d['V']:.0f} m/s = {d['a']['CL_lento']:.2f}",
             fontsize=8, color="gray")
    ax1.set_xlabel("Ángulo de ataque [°]")
    ax1.set_ylabel("CL del avión (referido a S del ala)")
    ax1.set_title("Sustentación vs ángulo de ataque, vuelo lento")
    ax1.grid(alpha=0.3)
    ax1.legend(loc="lower right", fontsize=8)

    # ---------------- panel 2: CL necesario vs velocidad
    v = np.linspace(5.0, 16.0, 200)
    cl_req = 2.0 * W / (rho * v ** 2 * S)
    ax2.plot(v, cl_req, color="black", lw=2, label="CL necesario (L = W)")
    casos = [("Flap retraído", d["cl_max_limpio"], "tab:blue")]
    if d["flap"]["tiene_flap"]:
        casos.append((f"Flap {d['flap']['deflexion']:.0f}°", d["cl_max_flap"], "tab:red"))
    resumen = []
    for nombre, cl_max, color in casos:
        v_stall = float(np.sqrt(2.0 * W / (rho * S * cl_max)))
        v_to = margen * v_stall
        ax2.axhline(cl_max, color=color, ls="--", lw=1)
        ax2.axvline(v_stall, color=color, ls=":", lw=1.2)
        ax2.plot([v_stall], [cl_max], "o", color=color)
        ax2.axvline(v_to, color=color, ls="-.", lw=1.2)
        ax2.text(v_stall - 0.1, 0.08, f"V pérdida {v_stall:.1f}", rotation=90, color=color, fontsize=8,
                 ha="right", va="bottom")
        ax2.text(v_to + 0.1, 0.08, f"V despegue {v_to:.1f}", rotation=90, color=color, fontsize=8,
                 ha="left", va="bottom")
        resumen.append({"configuración": nombre, "CL_max": round(cl_max, 3),
                        "V_pérdida [m/s]": round(v_stall, 2),
                        f"V_despegue ({margen:.2f}·Vp) [m/s]": round(v_to, 2),
                        "V_pérdida [km/h]": round(3.6 * v_stall, 1)})
    ax2.axvline(d["V"], color="gray", lw=1)
    ax2.text(d["V"] + 0.1, ax2.get_ylim()[1] * 0.9, f"V lento {d['V']:.0f}", fontsize=8, color="gray")
    ax2.set_xlabel("Velocidad [m/s]")
    ax2.set_ylabel("CL")
    ax2.set_title(f"Pérdida y despegue (peso {W:.0f} N, S = {S:.2f} m²)")
    ax2.set_ylim(0, max(d["cl_max_flap"], d["cl_max_limpio"]) * 1.3)
    ax2.grid(alpha=0.3)
    ax2.legend(loc="upper right", fontsize=8)

    fig.suptitle(titulo or f"Vuelo lento — {topologia}", fontweight="bold")
    fig.subplots_adjust(left=0.07, right=0.98, bottom=0.12, top=0.86, wspace=0.22)
    return fig, resumen


# =====================================================================
# TABLA ÚNICA DE LA GEOMETRÍA GANADORA
# =====================================================================
def tabla_ganador(params: dict, topologia: str, score: float | None = None):
    """UNA sola tabla (Grupo | Magnitud | Valor | Unidad) con la geometría del
    diseño ganador y lo que el modelo dice de él: reemplaza a las tablas sueltas
    de misión, comparación y batería que mostraban información parecida."""
    import pandas as pd
    from .geometria_avion import TOPOLOGIAS
    from .perfiles_avion import indice_a_nombre_avion

    a = ma.analizar_mision_avion(params, topologia)
    if a is None:
        raise ValueError("El modelo declara inválido este diseño con los interruptores actuales.")
    p = params
    f = []

    def add(grupo, nombre, valor, unidad=""):
        f.append({"Grupo": grupo, "Magnitud": nombre, "Valor": valor, "Unidad": unidad})

    add("Diseño", "Topología", TOPOLOGIAS[topologia]["nombre"])
    if score is not None:
        add("Diseño", "Score", round(float(score), 4))

    g = "Ala"
    add(g, "Envergadura", round(a["envergadura"], 3), "m")
    add(g, "Superficie", round(a["S"], 3), "m²")
    add(g, "Alargamiento", round(a["AR"], 2))
    add(g, "Cuerda en la raíz", round(1000 * p["root_chord"]), "mm")
    add(g, "Cuerdas en 25/50/75/100 %", " / ".join(str(round(1000 * p[f"chord_{i}"])) for i in range(1, 5)), "mm")
    add(g, "Cuerda media aerodinámica", round(1000 * a["MAC"]), "mm")
    add(g, "Torsión en las 5 estaciones", " / ".join(f"{p[f'twist_{i}']:.1f}" for i in range(5)), "°")
    add(g, "Perfiles raíz / medio / punta",
        " / ".join(indice_a_nombre_avion(p[k]) for k in ("perfil_raiz", "perfil_medio", "perfil_punta")))
    add(g, "Winglet (altura / cant)", f"{1000 * p.get('winglet_height', 0):.0f} mm / {p.get('winglet_cant_deg', 0):.0f}°")
    if a["tiene_flap"]:
        add(g, "Flap", f"{100 * a['flap_cuerda_frac']:.0f} % de cuerda, {a['flap_deflexion']:.0f}°, "
                       f"{100 * a['flap_frac_superficie']:.0f} % de la superficie")
    else:
        add(g, "Flap", "sin flap")
    add(g, "Borde de fuga (manufactura)", 2.0, "mm")

    g = "Fuselaje y cola"
    add(g, "Largo / diámetro del fuselaje", f"{1000 * p['fuselaje_largo']:.0f} / {1000 * p['fuselaje_diametro']:.0f}", "mm")
    add(g, "Volumen útil / requerido", f"{a['vol_util_fuselaje_L']:.1f} / {a['vol_requerido_L']:.1f}", "L")
    etiquetas = {
        "v_tail_span": ("Cola: envergadura", 1000, "mm"), "v_tail_root_chord": ("Cola: cuerda en la raíz", 1000, "mm"),
        "v_tail_taper": ("Cola: estrechamiento", 1, ""), "v_tail_sweep_deg": ("Cola: flecha", 1, "°"),
        "v_dihedral_deg": ("Cola en V: diedro", 1, "°"), "v_tail_incidencia_deg": ("Cola: incidencia", 1, "°"),
        "v_tail_arm_frac": ("Cola: brazo (fracción del fuselaje)", 1, ""),
        "htail_span": ("Horizontal: envergadura", 1000, "mm"), "htail_root_chord": ("Horizontal: cuerda raíz", 1000, "mm"),
        "htail_cuerda": ("Horizontal: cuerda", 1000, "mm"), "htail_taper": ("Horizontal: estrechamiento", 1, ""),
        "htail_sweep_deg": ("Horizontal: flecha", 1, "°"), "htail_incidencia_deg": ("Horizontal: incidencia", 1, "°"),
        "vstab_altura": ("Deriva: altura", 1000, "mm"), "vstab_root_chord": ("Deriva: cuerda raíz", 1000, "mm"),
        "vstab_cuerda": ("Deriva: cuerda", 1000, "mm"), "vstab_taper": ("Deriva: estrechamiento", 1, ""),
        "vstab_sweep_deg": ("Deriva: flecha", 1, "°"), "cola_arm_frac": ("Cola: brazo (fracción del fuselaje)", 1, ""),
        "boom_largo": ("Viga: largo", 1000, "mm"), "boom_diametro": ("Viga: diámetro", 1000, "mm"),
        "boom_lateral_frac": ("Vigas: posición en la semi-envergadura", 1, ""),
    }
    for k in sorted(p):
        if k in etiquetas:
            nombre, esc, un = etiquetas[k]
            v = float(p[k]) * esc
            add(g, nombre, round(v) if esc == 1000 else round(v, 3), un)
    add(g, "Volumen de cola V_H / V_V", f"{a['V_H']:.2f} / {a['V_V']:.3f}")

    g = "Masa"
    add(g, "Masa total", round(a["masa_total"], 2), "kg")
    add(g, "Estructura (fracción)", round(100 * a["fraccion_estructural"], 1), "%")
    add(g, "Batería", round(a["masa_bateria"], 2), "kg")
    add(g, "Carga alar", round(a["carga_alar"], 1), "N/m²")

    g = "Crucero"
    add(g, "L/D", round(a["LD_crucero"], 1))
    add(g, "Resistencia", round(a["D_crucero"], 2), "N")
    add(g, "Potencia", round(a["potencia_W"]), "W")
    add(g, "Ángulo de ataque / CL", f"{a['alpha_crucero']:.2f}° / {a['CL_crucero']:.3f}")

    g = "Vuelo lento"
    add(g, "CL máx con flap", round(a["CL_max_lento"], 3))
    add(g, "Velocidad de pérdida", round(a["v_stall"], 2), "m/s")
    add(g, "Margen de vuelo lento", round(100 * a["margen_lento"], 1), "%")

    g = "Estabilidad"
    add(g, "Margen estático", round(100 * a["SM"], 1), "%")
    add(g, "Cm en crucero", round(a["Cm_crucero"], 4))
    add(g, "Cn_β / Cl_β", f"{a['Cn_beta']:.3f} / {a['Cl_beta']:.3f}")
    add(g, "Cn_r (amortiguación de guiñada)", round(a["Cn_r"], 3))

    b = a.get("bateria")
    if b:
        pk = b["pack"]
        g = "Batería"
        add(g, "Pack", f"{pk['S']}S{pk['P']}P, {pk['capacidad_Ah']:.1f} Ah")
        add(g, "Energía / alcance", f"{b['energia_requerida_wh']:.0f} Wh / {b['alcance_logrado_km']:.0f} km")
        add(g, "Corriente crucero / despegue", f"{b['corriente_crucero_A']:.0f} A / {b['despegue']['corriente_A']:.0f} A")

    return pd.DataFrame(f)
