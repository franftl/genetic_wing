"""
El viento en la MISIÓN: velocidad respecto del suelo, tiempo de ida y vuelta,
operabilidad, y el chequeo de ráfaga "rápido" (fórmula de FAR 23.341) con los
datos del sitio. No necesita la geometría: alcanza con los números que ya
calcula el optimizador (por ejemplo, el diccionario 'analisis' de
optimizacion_avion/ganadores.json).

Intuición: un viento de frente no se compensa con el mismo viento a favor a
la vuelta. Con V = 22 m/s y 15 m/s en contra, la ida tarda 3.1 veces más y la
vuelta solo 0.6 veces: el viaje completo tarda 1.9 veces más que sin viento.
"""
from __future__ import annotations

import numpy as np

G = 9.80665
RHO_0 = 1.225   # densidad que usa hoy el optimizador (asb.Atmosphere(altitude=0))


# ---------------------------------------------------------------------------
# Velocidad respecto del suelo
# ---------------------------------------------------------------------------
def velocidad_suelo(V: float, W: float, angulo_deg: float) -> float:
    """Velocidad respecto del suelo manteniendo la ruta.
    angulo_deg: ángulo entre la ruta y la dirección HACIA DONDE va el viento
    (0 = de cola, 180 = de frente, 90 = cruzado). Devuelve NaN si no avanza."""
    a = np.radians(angulo_deg)
    cruz = W * np.sin(a)
    if abs(cruz) >= V:
        return float("nan")
    gs = np.sqrt(V ** 2 - cruz ** 2) + W * np.cos(a)
    return float(gs) if gs > 0 else float("nan")


def factor_ida_vuelta(V: float, W: float, angulo_deg: float = 180.0) -> float:
    """t(ida+vuelta con viento) / t(sin viento). angulo_deg = 180: peor caso,
    viento alineado con la ruta (de frente a la ida)."""
    ida = velocidad_suelo(V, W, angulo_deg)
    vuelta = velocidad_suelo(V, W, angulo_deg + 180.0)
    if not (np.isfinite(ida) and np.isfinite(vuelta)):
        return float("inf")
    return 0.5 * V * (1.0 / ida + 1.0 / vuelta)


def factor_ida_vuelta_promedio_rumbos(V: float, W: float, n: int = 72) -> float:
    """Igual que factor_ida_vuelta pero promediado sobre todos los rumbos
    (ruta con orientación cualquiera respecto del viento)."""
    fs = [factor_ida_vuelta(V, W, a) for a in np.linspace(0, 180, n)]
    return float(np.mean(fs))


# ---------------------------------------------------------------------------
# Operabilidad con la estadística del sitio
# ---------------------------------------------------------------------------
def operabilidad(ficha, V: float, factor_max: float = 1.5, corregido: bool = False,
                 solo_dia: bool = True, peor_caso: bool = True) -> dict:
    """Fracción de horas en que un viaje de ida y vuelta tarda como máximo
    `factor_max` veces lo que tardaría sin viento.

    ficha     : FichaViento (viento_uav.cargar_ficha)
    V         : velocidad de crucero respecto del aire [m/s]
    corregido : aplica el factor de cola del sitio (ERA5 subestima los vientos fuertes)
    peor_caso : True -> viento alineado con la ruta; False -> promedio sobre rumbos
    Devuelve: fraccion_operable, fraccion_sin_avance, factor_medio, y la
    energía relativa media (a potencia constante, energía ∝ tiempo).
    """
    Wb, n = ficha.histograma_120(solo_dia)
    if corregido:
        Wb = Wb * ficha.factor_cola
    f = np.array([factor_ida_vuelta(V, w) if peor_caso else factor_ida_vuelta_promedio_rumbos(V, w, 36)
                  for w in Wb])
    tot = n.sum()
    ok = f <= factor_max
    avanza = np.isfinite(f)
    return {
        "V": V,
        "fraccion_operable": float(n[ok].sum() / tot),
        "fraccion_sin_avance": float(n[~avanza].sum() / tot),
        "factor_tiempo_medio_operable": float((n[ok] * f[ok]).sum() / max(n[ok].sum(), 1)),
    }


def alcance_efectivo(R_aire_km: float, V: float, W: float) -> float:
    """Distancia máxima ida y vuelta que se puede cubrir, a la base y de
    vuelta, con un alcance en aire quieto R_aire_km (peor caso, viento alineado).
    Radio de acción = R / (2 * factor)."""
    f = factor_ida_vuelta(V, W)
    return float(R_aire_km / (2.0 * f)) if np.isfinite(f) else 0.0


# ---------------------------------------------------------------------------
# Ráfaga rápida (FAR 23.341), con la densidad y la ráfaga del sitio
# ---------------------------------------------------------------------------
def chequeo_rafaga(W: float, S: float, c_media: float, CL_alpha_por_grado: float,
                   CL_max: float, V: float, U_ds: float, rho: float) -> dict:
    """Ráfaga vertical cuasi-estática con factor de alivio Kg.

    Es la misma cuenta que hace hoy mision_avion.py (sección 4), pero con la
    amplitud de ráfaga y la densidad como argumentos, para poder usar las del
    sitio en lugar de 3 m/s y 1.225 kg/m3.
    """
    CL_alpha_rad = np.degrees(CL_alpha_por_grado)
    mu = 2.0 * (W / S) / (rho * c_media * CL_alpha_rad * G)
    Kg = 0.88 * mu / (5.3 + mu)
    q = 0.5 * rho * V ** 2
    CL_1g = W / (q * S)
    d_alpha = np.degrees(np.arctan(Kg * U_ds / V))
    dCL = CL_alpha_por_grado * d_alpha
    margen = (CL_max - (CL_1g + dCL)) / CL_max
    # Si la ráfaga llevaría el ala más allá de CL_max, la carga la limita la pérdida.
    n_max = min(1.0 + dCL * q * S / W, CL_max / CL_1g)
    return {"mu": mu, "Kg": Kg, "CL_1g": CL_1g, "d_alpha": d_alpha, "dCL": dCL,
            "dn": dCL * q * S / W, "n_max": n_max, "margen_perdida": margen,
            "entra_en_perdida": bool(margen <= 0.0),
            "n_limite_por_perdida": CL_max / CL_1g}


def chequeo_rafaga_desde_analisis(analisis: dict, ficha, V: float | None = None,
                                  criterio: str = "diseno", punto: str = "crucero") -> dict:
    """Atajo para el dict 'analisis' que guarda optimizacion_avion (ganadores.json).

    punto: 'crucero' (V_CRUCERO, CL_max limpio) o 'vmax' (V_MAX, CL_max limpio).
    Usa la densidad de diseño del sitio y la ráfaga del criterio elegido.
    """
    a = analisis
    if punto == "crucero":
        CL_max = a["CL_max_crucero"]
        if V is None:
            V = (2 * a["peso"] / (RHO_0 * a["S"] * a["CL_crucero"])) ** 0.5
    elif punto == "vmax":
        CL_max = a["CL_max_vmax"]
        if V is None:
            V = (2 * a["peso"] / (RHO_0 * a["S"] * a["CL_vmax"])) ** 0.5
    else:
        raise ValueError("punto debe ser 'crucero' o 'vmax'")
    return chequeo_rafaga(W=a["peso"], S=a["S"], c_media=a["MAC"],
                          CL_alpha_por_grado=a["CL_alpha_por_grado"], CL_max=CL_max,
                          V=V, U_ds=ficha.U_ds(criterio), rho=ficha.rho_diseno)


def CL_crucero_en_sitio(analisis: dict, ficha) -> float:
    """El optimizador calcula CL de crucero con rho = 1.225. En el sitio, con
    aire más liviano, el ala tiene que trabajar a un CL mayor."""
    return float(analisis["CL_crucero"] * RHO_0 / ficha.rho_diseno)
