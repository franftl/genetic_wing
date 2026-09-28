"""Genera semillas válidas por topología: define una base común y afina
numéricamente cg_frac_mac (margen estático en banda) e incidencia de cola
(Cm en crucero ~ 0). Los valores que salen de acá se fijan en competencia.py."""
import json, sys
from optimizacion_avion.geometria_avion import (
    TOPOLOGIAS, BOUNDS_POR_TOPOLOGIA, clamp_to_bounds_avion, SM_BANDS)
from optimizacion_avion.mision_avion import analizar_mision_avion, evaluar_mision_avion

BASE = dict(
    envergadura=3.10,
    root_chord=0.40, chord_1=0.38, chord_2=0.34, chord_3=0.29, chord_4=0.21,
    le_offset_1=0.010, le_offset_2=0.025, le_offset_3=0.045, le_offset_4=0.070,
    twist_0=1.5, twist_1=1.0, twist_2=0.0, twist_3=-1.5, twist_4=-3.5,
    elev_1=0.010, elev_2=0.024, elev_3=0.042, elev_4=0.065,
    perfil_raiz=15.0, perfil_medio=13.0, perfil_punta=2.0, perfil_pos_medio=0.55,
    winglet_height=0.13, winglet_cant_deg=25.0, winglet_taper=0.55, winglet_sweep_deg=28.0,
    flap_cuerda_frac=0.27, flap_inicio_frac=0.06, flap_fin_frac=0.70, flap_defl_deg=34.0,
    fuselaje_largo=1.25, fuselaje_diametro=0.155,
    morro_largo_frac=0.22, morro_exp=0.62,
    boattail_largo_frac=0.32, boattail_radio_frac=0.25,
    ala_x_frac_fuselaje=0.28,
)
COLA_HV = dict(htail_span=0.72, htail_root_chord=0.21, htail_taper=0.70,
               htail_sweep_deg=6.0, htail_incidencia_deg=-1.0,
               vstab_altura=0.28, vstab_root_chord=0.20, vstab_taper=0.60,
               vstab_sweep_deg=25.0, cola_arm_frac=0.88)
EXTRA = {
    "convencional": dict(COLA_HV),
    "t_tail": dict(COLA_HV, htail_span=0.64, vstab_altura=0.26),
    "v_tail": dict(v_tail_span=0.88, v_tail_root_chord=0.23, v_tail_taper=0.65,
                   v_dihedral_deg=38.0, v_tail_sweep_deg=14.0,
                   v_tail_incidencia_deg=-1.0, v_tail_arm_frac=0.88),
    # fuselaje_diametro sube respecto de la versión anterior (0.155 -> 0.20-
    # 0.21): un fuselaje/góndola CORTO necesita engordar para alcanzar el
    # volumen útil mínimo (VOLUMEN_UTIL_MIN_L en mision_avion.py), ver
    # también el bound ampliado en BOUNDS_DOBLE_BOOM/BOUNDS_POD_BOOM.
    "doble_boom": dict(fuselaje_largo=0.75, fuselaje_diametro=0.20, boom_largo=0.90,
                       boom_lateral_frac=0.30, boom_diametro=0.045, htail_cuerda=0.18,
                       htail_incidencia_deg=-1.0, vstab_altura=0.25, vstab_cuerda=0.18,
                       vstab_taper=0.60),
    "pod_boom": dict(COLA_HV, fuselaje_largo=0.62, fuselaje_diametro=0.20,
                     boom_largo=1.00, boom_diametro=0.050),
}


def afinar(t, base, n=16):
    """cg primero (mueve SM), incidencia después (mueve Cm casi sin tocar SM).

    SIGNO de la incidencia: la cola va DETRÁS del CG, así que más incidencia
    = más sustentación de cola = más momento de PICADA = Cm baja. Entonces,
    si Cm > 0 (morro arriba) hay que SUBIR la incidencia."""
    lo_sm, hi_sm = SM_BANDS[t]
    obj = 0.5 * (lo_sm + hi_sm)
    lo, hi = BOUNDS_POR_TOPOLOGIA[t]["cg_frac_mac"]
    mid = 0.5 * (lo + hi)
    for _ in range(n):
        mid = 0.5 * (lo + hi)
        a = analizar_mision_avion(clamp_to_bounds_avion({**base, "cg_frac_mac": mid}, t), t)
        if a is None:
            hi = mid           # inválido hacia atrás -> el CG se fue muy atrás
            continue
        if a["SM"] > obj:
            lo = mid
        else:
            hi = mid
    base = {**base, "cg_frac_mac": mid}

    clave = "v_tail_incidencia_deg" if t == "v_tail" else "htail_incidencia_deg"
    lo_i, hi_i = BOUNDS_POR_TOPOLOGIA[t][clave]
    mid_i = 0.5 * (lo_i + hi_i)
    for _ in range(n):
        mid_i = 0.5 * (lo_i + hi_i)
        a = analizar_mision_avion(clamp_to_bounds_avion({**base, clave: mid_i}, t), t)
        if a is None:
            hi_i = mid_i
            continue
        if a["Cm_crucero"] > 0:
            lo_i = mid_i       # falta picada -> subir incidencia
        else:
            hi_i = mid_i
    return clamp_to_bounds_avion({**base, clave: mid_i}, t)


# Segunda semilla: ala MÁS CHICA y más esbelta, compensada con más flap.
# Sembrar variado importa -- BLX-alfa entre dos padres iguales en una
# dimensión devuelve siempre ese valor, así que una dimensión donde las dos
# semillas coinciden queda sin explorar. Las dos semillas están a propósito
# en lados opuestos del compromiso central de esta misión: superficie de ala
# grande (buena para 10 m/s, cara en crucero) contra chica (al revés).
BASE_B = dict(
    BASE,
    envergadura=2.85,
    root_chord=0.36, chord_1=0.34, chord_2=0.30, chord_3=0.25, chord_4=0.17,
    le_offset_1=0.005, le_offset_2=0.012, le_offset_3=0.022, le_offset_4=0.035,
    twist_0=1.0, twist_1=0.5, twist_2=-0.5, twist_3=-2.0, twist_4=-4.5,
    elev_1=0.0, elev_2=0.0, elev_3=0.0, elev_4=0.0,          # ala plana
    # Camber MODERADO a propósito, al revés que la semilla A. Con perfiles
    # muy cambados el flap casi no aporta (ver `_clmax_ala` en mision_avion:
    # el perfil de alta sustentación y el flap COMPITEN). Esta semilla
    # explora la estrategia opuesta: perfil más suave + flap que sí rinde.
    perfil_raiz=13.0, perfil_medio=12.0, perfil_punta=12.0, perfil_pos_medio=0.45,
    winglet_height=0.0, winglet_cant_deg=20.0, winglet_taper=0.60, winglet_sweep_deg=20.0,
    flap_cuerda_frac=0.32, flap_inicio_frac=0.04, flap_fin_frac=0.86, flap_defl_deg=30.0,
    # fuselaje_diametro sube de 0.135 a 0.15: el fuselaje mas esbelto (L/D
    # alto) de esta semilla no entraba el volumen util minimo (ver
    # VOLUMEN_UTIL_MIN_L en mision_avion.py).
    fuselaje_largo=1.55, fuselaje_diametro=0.15,
    morro_largo_frac=0.30, morro_exp=0.50,
    boattail_largo_frac=0.38, boattail_radio_frac=0.18,
    ala_x_frac_fuselaje=0.34,
)
EXTRA_B = {
    "convencional": dict(COLA_HV, htail_span=0.55, htail_root_chord=0.17, cola_arm_frac=0.92),
    "t_tail": dict(COLA_HV, htail_span=0.50, htail_root_chord=0.16, vstab_altura=0.22, cola_arm_frac=0.92),
    "v_tail": dict(v_tail_span=0.70, v_tail_root_chord=0.18, v_tail_taper=0.55,
                   v_dihedral_deg=44.0, v_tail_sweep_deg=18.0,
                   v_tail_incidencia_deg=-1.0, v_tail_arm_frac=0.92),
    "doble_boom": dict(fuselaje_largo=0.60, fuselaje_diametro=0.22, boom_largo=1.10,
                       boom_lateral_frac=0.40, boom_diametro=0.038, htail_cuerda=0.13,
                       htail_incidencia_deg=-1.0, vstab_altura=0.20, vstab_cuerda=0.13,
                       vstab_taper=0.55),
    "pod_boom": dict(COLA_HV, fuselaje_largo=0.45, fuselaje_diametro=0.26,
                     boom_largo=1.25, boom_diametro=0.042,
                     htail_span=0.55, htail_root_chord=0.17, cola_arm_frac=0.92),
}


if __name__ == "__main__":
    solo = sys.argv[1:] or list(TOPOLOGIAS)
    out = {}
    for t in solo:
        out[t] = []
        for etiqueta, base, extra in (("A", BASE, EXTRA), ("B", BASE_B, EXTRA_B)):
            p = afinar(t, {**base, **extra[t]})
            a = analizar_mision_avion(p, t)
            s = evaluar_mision_avion(p, t)
            out[t].append(p)
            if a is None:
                print(f"{t:<14} {etiqueta}  INVALIDO")
            else:
                print(f"{t:<14} {etiqueta}  score={s:6.3f} SM={100*a['SM']:5.1f}% "
                      f"Cm={a['Cm_crucero']:+.4f} L/D={a['LD_crucero']:5.2f} "
                      f"b={a['envergadura']:.2f} S={a['S']:.3f} vstall={a['v_stall']:.2f} "
                      f"V_H={a['V_H']:.2f} m={a['masa_total']:.2f}kg")
    with open("semillas_out.json", "w") as f:
        json.dump(out, f, indent=1)
    print("-> semillas_out.json")
