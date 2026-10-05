"""
Viento de los sitios de operación, para que entre en la optimización.

Lo usa `mision_avion.py` cuando `VIENTO_ACTIVO = True`. Ver la Research Note 16
(documentos_de_decision) para el razonamiento completo.

==========================================================================
DE DÓNDE SALEN LOS NÚMEROS
==========================================================================
De las fichas de viento de los dos sitios candidatos (viento/fichas/*.yaml,
caracterización con ERA5 en viento/caracterizacion_viento.pdf). Se toma el
PEOR CASO de los dos, para que el avión sirva en cualquiera:

  densidad del aire ...... la más baja  -> Puesto Hernández (aire más liviano,
                                           el ala sostiene menos)
  ráfaga vertical ........ la más alta  -> 4.63 m/s (3 sigma, turbulencia
                                           moderada; igual en los dos sitios)
  viento medio / fuerte .. el más alto  -> Cañadón León
  turbulencia continua ... Dryden de baja altura (MIL-F-8785C) a 120 m,
                           turbulencia moderada

Si se actualizan las fichas, `condiciones_desde_fichas()` recalcula todo y
el test viento/codigo_viento/tests/test_optimizador_viento.py avisa si estas
constantes quedaron desactualizadas.

==========================================================================
TURBULENCIA: POR QUÉ CUESTA ENERGÍA
==========================================================================
En aire turbulento la sustentación sube y baja todo el tiempo. La resistencia
inducida crece con el CUADRADO de la sustentación, así que los picos para
arriba cuestan más de lo que ahorran los picos para abajo (como manejar por
un camino con pozos). Como en vuelo nivelado CL = n * CL_crucero:

    resistencia inducida extra / resistencia inducida = sigma_n^2

con sigma_n la desviación estándar del factor de carga. Las ráfagas
horizontales suman además (sigma_u / V)^2 de resistencia de perfil.

sigma_n sale de un modelo de 1 grado de libertad vertical: el avión SUBE Y
BAJA con las ráfagas. Las ráfagas largas las "acompaña" y casi no le cambian
la sustentación; las cortas lo agarran sin tiempo de reaccionar. La frontera
la marca tau = 2 (W/S) / (g rho V CL_alpha). Con más carga alar, la misma
ráfaga sacude menos.

No incluye el retardo aerodinámico (Küssner) ni el promedio de la ráfaga en
la envergadura (los dos reducen la respuesta, así que es conservador).
Verificado contra la simulación dinámica con VLM de viento/codigo_viento:
coinciden dentro de ~5 %.
"""
from __future__ import annotations

from pathlib import Path

import aerosandbox as asb
import numpy as np

G = 9.80665

# --- Condiciones de diseño: peor caso de Cañadón León y Puesto Hernández ---
RHO_SITIO = 1.056          # [kg/m3] densidad de diseño (Puesto Hernández, p05 de verano)
RAFAGA_VERTICAL_SITIO = 4.63   # [m/s] ráfaga discreta 1-coseno de diseño (3 sigma, moderada)
VIENTO_MEDIO_SITIO = 8.905     # [m/s] viento medio diurno a 120 m (Cañadón León)
VIENTO_FUERTE_SITIO = 20.37    # [m/s] p95 diurno a 120 m, corregido (Cañadón León)
SIGMA_U = 2.035            # [m/s] Dryden horizontal, 120 m, moderada
SIGMA_W = 1.543            # [m/s] Dryden vertical, 120 m, moderada
L_W = 120.0                # [m]   escala de Dryden vertical a 120 m


def atmosfera_con_densidad(rho: float) -> asb.Atmosphere:
    """Atmósfera estándar a la altitud que da la densidad pedida."""
    if abs(rho - float(asb.Atmosphere(altitude=0).density())) < 1e-6:
        return asb.Atmosphere(altitude=0)
    lo, hi = -2000.0, 12000.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if float(asb.Atmosphere(altitude=mid).density()) > rho:
            lo = mid
        else:
            hi = mid
    return asb.Atmosphere(altitude=0.5 * (lo + hi))


ATMOSFERA_SITIO = atmosfera_con_densidad(RHO_SITIO)


# --- Turbulencia ----------------------------------------------------------
def espectro_dryden_w(omega, sigma_w: float, Lw: float, V: float):
    """Espectro temporal unilateral (omega >= 0, rad/s) de la ráfaga vertical
    de Dryden. Integra a sigma_w^2."""
    x = Lw * omega / V
    return sigma_w ** 2 * Lw / (np.pi * V) * (1 + 3 * x ** 2) / (1 + x ** 2) ** 2


def sigma_n_turbulencia(carga_alar: float, CL_alpha_rad: float, rho: float, V: float,
                        sigma_w: float = SIGMA_W, Lw: float = L_W) -> float:
    """Desviación estándar del factor de carga en turbulencia continua."""
    tau = 2.0 * carga_alar / (G * rho * V * CL_alpha_rad)
    omega = np.logspace(np.log10(V / 1e5), np.log10(V / 1e-2), 4000)
    integrando = omega ** 2 / (1 + (tau * omega) ** 2) * espectro_dryden_w(omega, sigma_w, Lw, V)
    return float(np.sqrt(np.trapezoid(integrando, omega)) / G)


def resistencia_extra_turbulencia(frac_inducida: float, s_n: float, V: float,
                                  sigma_u: float = SIGMA_U) -> float:
    """Fracción de resistencia extra por turbulencia (0.02 = +2 %)."""
    return frac_inducida * s_n ** 2 + (1.0 - frac_inducida) * (sigma_u / V) ** 2


# --- Recalcular desde las fichas (opcional, necesita pyyaml) ---------------
def condiciones_desde_fichas(carpeta_viento: str | Path | None = None) -> dict:
    """Recalcula las constantes de arriba a partir de viento/fichas/*.yaml."""
    import sys
    carpeta = Path(carpeta_viento) if carpeta_viento else Path(__file__).resolve().parents[1] / "viento"
    sys.path.insert(0, str(carpeta / "codigo_viento"))
    import viento_uav as vu
    fichas = [vu.cargar_ficha(s, base=carpeta) for s in vu.SITIOS]
    dryden = [f.dryden(120.0, "moderada") for f in fichas]
    return {
        "RHO_SITIO": min(f.rho_diseno for f in fichas),
        "RAFAGA_VERTICAL_SITIO": max(f.U_ds("diseno") for f in fichas),
        "VIENTO_MEDIO_SITIO": max(f.viento_120("media") for f in fichas),
        "VIENTO_FUERTE_SITIO": max(f.viento_120("p95", corregido=True) for f in fichas),
        "SIGMA_U": max(d["sigma_u"] for d in dryden),
        "SIGMA_W": max(d["sigma_w"] for d in dryden),
        "L_W": dryden[0]["Lw"],
    }
