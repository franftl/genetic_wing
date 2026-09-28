"""
Modelo estructural de las topologías con cola.

==========================================================================
REVISIÓN 2026-09-17
==========================================================================
Acompaña la reescritura de `geometria_avion.py`. Cambios respecto de la
versión anterior:

- ALA MULTI-ESTACIÓN: el larguero se dimensiona sobre la distribución real
  de cuerdas y elevación de las 5 estaciones, no sobre un ahusamiento lineal
  raíz-punta.
- ENVERGADURA VARIABLE: ya no se importa `HALF_SPAN`. Esto es lo que hace
  que liberar la envergadura no sea gratis -- la flecha en punta va como
  b^3, así que el criterio de rigidez le pone precio solo.
- WINGLETS: masa de recubrimiento sobre su superficie (mismo criterio que
  el ala volante).
- FLAPS: masa del mecanismo, estimada abajo desde abajo hacia arriba.
- COLA EN T: factor de masa explícito sobre la deriva (ver `FACTOR_MASA_T`).
- VIGAS DE COLA: para `doble_boom` (dos) y `pod_boom` (una).

Lo que SIGUE reutilizándose tal cual de `optimizacion_ala.estructura`, por
ser propiedades de MATERIAL o de MISIÓN y no de geometría: RHO_LARGUERO,
SIGMA_ADM, MASA_AREAL_PIEL, E_LARGUERO, FLECHA_MAX_FRAC, FACTOR_DETALLES,
N_ULTIMO, MASA_PAYLOAD, MASA_SISTEMAS, G.

==========================================================================
LO QUE ESTE MODELO SIGUE SIN VER
==========================================================================
- Torsión y flameo (flutter) del ala. Con la envergadura ahora LIBRE esto
  importa más que antes: el criterio de rigidez en flexión frena el
  alargamiento, pero un ala muy esbelta puede ser inviable por torsión
  mucho antes, y este modelo no lo vería.
- Pandeo del recubrimiento.
- La masa de las vigas es DECLARADA (densidad lineal de tubo de carbono),
  no dimensionada por flexión: eso necesitaría el diámetro y el espesor de
  pared de la viga como variables de diseño. `boom_diametro` ya existe como
  variable geométrica (afecta la resistencia), pero no se usa para
  dimensionar: sería el próximo paso natural.
"""

from __future__ import annotations

import numpy as np

from optimizacion_ala.estructura import (
    E_LARGUERO, FACTOR_DETALLES, FLECHA_MAX_FRAC, G, MASA_AREAL_PIEL,
    MASA_PAYLOAD, MASA_SISTEMAS, N_ULTIMO, RHO_LARGUERO, SIGMA_ADM,
)

from .geometria_avion import (
    N_ESTACIONES, TOPOLOGIAS, WINGLET_MIN_H, geometria_flap, semi_envergadura,
)
from .perfiles_avion import perfil_en_fraccion_avion

_FRAC = np.linspace(0.0, 1.0, N_ESTACIONES)

# Densidad lineal de una viga de cola de fibra de carbono a esta escala.
# DECLARADA, no calculada -- ver "lo que este modelo sigue sin ver".
MASA_LINEAL_BOOM = 0.12       # [kg/m] por viga

# Cola en T: la deriva pasa de ser una superficie descargada a ser la viga
# que sostiene el horizontal, con flexión Y torsión en la raíz. Es la
# desventaja estructural clásica de la T, y si no se la cobra el GA elige la
# T por una ventaja aerodinámica que en la realidad no sale gratis. 1.6 es
# una estimación de predimensionamiento, no un cálculo.
FACTOR_MASA_T = 1.6

# --- Masa del mecanismo de flap -------------------------------------
# No existe dato publicado de fracción de masa de flaps para UAV de esta
# escala (se buscó). Se estima desde abajo: dos servos metálicos de esta
# clase (~15 g cada uno con su cableado y horn), más un refuerzo local del
# borde de fuga y las bisagras, proporcional a la superficie con flap.
MASA_SERVO_FLAP = 0.015       # [kg] por servo
N_SERVOS_FLAP = 2
MASA_AREAL_FLAP = 0.35        # [kg/m^2] de superficie de flap, EXTRA sobre la piel


def _distribucion_ala(params: dict, n: int = 40):
    """Cuerda y elevación interpoladas sobre la semi-envergadura real."""
    b2 = semi_envergadura(params)
    fr = np.linspace(0.0, 1.0, n)
    cuerdas_ctrl = [params["root_chord"]] + [params[f"chord_{i}"] for i in range(1, N_ESTACIONES)]
    elev_ctrl = [0.0] + [params[f"elev_{i}"] for i in range(1, N_ESTACIONES)]
    cuerda = np.interp(fr, _FRAC, cuerdas_ctrl)
    z = np.interp(fr, _FRAC, elev_ctrl) * b2
    return fr, fr * b2, cuerda, z


def _espesores(params: dict, fr):
    """Espesor relativo leído del PERFIL que va en cada estación -- no un
    parámetro declarado. Es lo que hace que elegir un perfil más grueso
    (p.ej. uno de alta sustentación) also gane altura de larguero."""
    try:
        return np.array([float(perfil_en_fraccion_avion(params, f).max_thickness()) for f in fr])
    except Exception:
        return np.full(len(fr), 0.10)


def _masa_ala(params: dict, masa_total_supuesta: float) -> dict | None:
    """Larguero por flexión + rigidez sobre la distribución multi-estación,
    más recubrimiento y winglets. Mismo método que `estructura.py`."""
    n = 40
    fr, y_proy, cuerda, z = _distribucion_ala(params, n)
    # Coordenada DESARROLLADA: con diedro el ala es más larga que su
    # proyección, y esa diferencia es material real que pesa.
    ds = np.sqrt(np.diff(y_proy) ** 2 + np.diff(z) ** 2)
    y = np.concatenate([[0.0], np.cumsum(ds)])
    trapz = getattr(np, "trapezoid", None) or np.trapz

    W_ult = N_ULTIMO * masa_total_supuesta * G
    integral_cuerda = float(trapz(cuerda, y))
    if integral_cuerda <= 0:
        return None
    carga_lineal = (W_ult / 2.0) * cuerda / integral_cuerda

    momento = np.array([
        float(trapz(carga_lineal[i:] * (y[i:] - y[i]), y[i:])) if i < n - 1 else 0.0
        for i in range(n)
    ])

    h = _espesores(params, fr) * cuerda
    area_res = np.maximum(momento / (SIGMA_ADM * np.maximum(h, 1e-6)), 1e-12)

    # Criterio de RIGIDEZ. Con la envergadura libre este criterio es el que
    # impide que el optimizador estire el ala indefinidamente: la flecha en
    # punta crece como b^3.
    inercia = area_res * h ** 2 / 2.0
    curvatura = (momento / 1.5) / (E_LARGUERO * np.maximum(inercia, 1e-16))
    giro = np.concatenate([[0.0], np.cumsum(0.5 * (curvatura[1:] + curvatura[:-1]) * np.diff(y))])
    flecha = np.concatenate([[0.0], np.cumsum(0.5 * (giro[1:] + giro[:-1]) * np.diff(y))])
    flecha_punta = float(flecha[-1])
    flecha_adm = FLECHA_MAX_FRAC * float(y[-1])
    factor_rigidez = max(1.0, flecha_punta / flecha_adm) if flecha_adm > 0 else 1.0
    area_cordon = area_res * factor_rigidez

    masa_larguero = 4.0 * RHO_LARGUERO * float(trapz(area_cordon, y))
    area_planta = 2.0 * float(trapz(cuerda, y))
    masa_piel = MASA_AREAL_PIEL * 2.05 * area_planta

    masa_winglet = 0.0
    h_wl = float(params.get("winglet_height", 0.0))
    if h_wl >= WINGLET_MIN_H:
        c_media_wl = 0.5 * float(cuerda[-1]) * (1.0 + float(params.get("winglet_taper", 1.0)))
        masa_winglet = MASA_AREAL_PIEL * 2.05 * (2.0 * h_wl * c_media_wl)

    fl = geometria_flap(params)
    masa_flap = 0.0
    if fl["tiene_flap"]:
        area_flap = fl["frac_superficie"] * area_planta * fl["cuerda_frac"]
        masa_flap = N_SERVOS_FLAP * MASA_SERVO_FLAP + MASA_AREAL_FLAP * area_flap

    return {
        "masa_larguero": masa_larguero, "masa_piel": masa_piel,
        "masa_winglet": masa_winglet, "masa_flap": masa_flap,
        "momento_raiz": float(momento[0]), "area_planta": area_planta,
        "flecha_punta_mm": 1000.0 * flecha_punta / max(factor_rigidez, 1e-9),
        "manda_rigidez": bool(factor_rigidez > 1.0),
    }


def _area_trapecio(span, root_c, taper):
    return float(span) * 0.5 * float(root_c) * (1.0 + float(taper))


def _masa_cola(params: dict, topologia: str) -> dict:
    """Superficies de cola: solo recubrimiento, sin larguero dimensionado --
    mismo criterio que los winglets del ala volante, y por la misma razón
    (son chicas y mucho menos cargadas que el ala principal)."""
    cola = TOPOLOGIAS[topologia]["cola"]
    if cola == "v":
        area = _area_trapecio(params["v_tail_span"], params["v_tail_root_chord"], params["v_tail_taper"])
        masa = MASA_AREAL_PIEL * 2.05 * area
    elif cola == "doble_boom":
        b2 = semi_envergadura(params)
        y_boom = float(params["boom_lateral_frac"]) * b2
        area_h = (2.0 * y_boom) * float(params["htail_cuerda"])
        area_v = 2.0 * _area_trapecio(params["vstab_altura"], params["vstab_cuerda"], params["vstab_taper"])
        area = area_h + area_v
        masa = MASA_AREAL_PIEL * 2.05 * area
    else:  # convencional o T
        area_h = _area_trapecio(params["htail_span"], params["htail_root_chord"], params["htail_taper"])
        area_v = _area_trapecio(params["vstab_altura"], params["vstab_root_chord"], params["vstab_taper"])
        area = area_h + area_v
        f_v = FACTOR_MASA_T if cola == "t" else 1.0
        masa = MASA_AREAL_PIEL * 2.05 * (area_h + f_v * area_v)
    return {"masa_cola": masa, "area_cola": area}


def _masa_fuselaje_y_vigas(params: dict, topologia: str) -> dict:
    """Recubrimiento del fuselaje (o góndola) más las vigas de cola.

    La superficie mojada del fuselaje se aproxima como un cilindro
    equivalente corregido por el afinamiento de morro y boat-tail: un
    cilindro pleno la sobreestimaría bastante ahora que el morro y la cola
    son formas de verdad y no un cono."""
    tipo = TOPOLOGIAS[topologia]["fuselaje"]
    L = float(params["fuselaje_largo"])
    D = float(params["fuselaje_diametro"])
    f_morro = float(params["morro_largo_frac"])
    f_boat = float(params["boattail_largo_frac"])
    # Factor de forma: el tramo recto aporta superficie completa, y los
    # tramos afinados aportan del orden del 60-70% de la de un cilindro.
    frac_efectiva = (1.0 - f_morro - f_boat) + 0.65 * (f_morro + f_boat)
    area_fus = np.pi * D * L * max(frac_efectiva, 0.4)
    masa_fus = MASA_AREAL_PIEL * area_fus

    masa_boom = 0.0
    if tipo == "pod_boom":
        masa_boom = MASA_LINEAL_BOOM * float(params["boom_largo"])
    elif TOPOLOGIAS[topologia]["cola"] == "doble_boom":
        masa_boom = 2.0 * MASA_LINEAL_BOOM * float(params["boom_largo"])

    return {"masa_fuselaje": masa_fus, "masa_boom": masa_boom, "area_fuselaje": float(area_fus)}


def masa_estructura_avion(params: dict, topologia: str, masa_total_supuesta: float) -> dict | None:
    ala = _masa_ala(params, masa_total_supuesta)
    if ala is None:
        return None
    cola = _masa_cola(params, topologia)
    resto = _masa_fuselaje_y_vigas(params, topologia)

    bruta = (ala["masa_larguero"] + ala["masa_piel"] + ala["masa_winglet"] + ala["masa_flap"]
             + cola["masa_cola"] + resto["masa_fuselaje"] + resto["masa_boom"])
    total = FACTOR_DETALLES * bruta

    return {
        "masa_estructura": total,
        "masa_larguero": FACTOR_DETALLES * ala["masa_larguero"],
        "masa_piel_ala": FACTOR_DETALLES * ala["masa_piel"],
        "masa_winglet": FACTOR_DETALLES * ala["masa_winglet"],
        "masa_flap": FACTOR_DETALLES * ala["masa_flap"],
        "masa_cola": FACTOR_DETALLES * cola["masa_cola"],
        "masa_fuselaje": FACTOR_DETALLES * resto["masa_fuselaje"],
        "masa_boom": FACTOR_DETALLES * resto["masa_boom"],
        "momento_raiz": ala["momento_raiz"],
        "area_planta_ala": ala["area_planta"],
        "area_cola": cola["area_cola"],
        "flecha_punta_mm": ala["flecha_punta_mm"],
        "manda_rigidez": ala["manda_rigidez"],
    }


def converger_masa_avion(params: dict, topologia: str, tol: float = 1e-4,
                         max_iter: int = 30) -> dict | None:
    """Punto fijo sobre la circularidad masa <-> carga."""
    m_total = MASA_PAYLOAD + MASA_SISTEMAS + 1.0
    for _ in range(max_iter):
        est = masa_estructura_avion(params, topologia, m_total)
        if est is None:
            return None
        nueva = MASA_PAYLOAD + MASA_SISTEMAS + est["masa_estructura"]
        if not np.isfinite(nueva) or nueva > 60.0:
            return None
        if abs(nueva - m_total) < tol:
            m_total = nueva
            break
        m_total = nueva
    else:
        return None

    est = masa_estructura_avion(params, topologia, m_total)
    if est is None:
        return None
    return {
        **est, "masa_total": m_total,
        "masa_payload": MASA_PAYLOAD, "masa_sistemas": MASA_SISTEMAS,
        "peso_total": m_total * G,
        "fraccion_estructural": est["masa_estructura"] / m_total,
    }
