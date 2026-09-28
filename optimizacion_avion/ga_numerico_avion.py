"""
Backend de generación de hijos por GA numérico, para las topologías CON
COLA. MISMOS operadores que `optimizacion_ala.ga_numerico` (BLX-alfa +
mutación gaussiana + wildcards) -- ver ese módulo para la justificación
completa de por qué estos operadores y no otros.

Lo único que cambia es la firma: acá los padres son `CandidateAvion`
(topología + dict de params), no un dataclass plano por parámetro, así que
`generar_hijos_avion` recibe la topología explícita para saber contra qué
`BOUNDS_*` clampear -- los dos padres SIEMPRE tienen que ser de la MISMA
topología (ver `competencia.py`: cada topología evoluciona su propia
subpoblación, nunca se cruzan entre sí -- no tendría sentido cruzar un
parámetro que una topología tiene y la otra no)."""

from __future__ import annotations

import random
from typing import List

from .geometria_avion import BOUNDS_POR_TOPOLOGIA, CandidateAvion, clamp_to_bounds_avion


def _blx_alpha_gen(v1: float, v2: float, lo: float, hi: float, alpha: float) -> float:
    d = abs(v1 - v2)
    a = min(v1, v2) - alpha * d
    b = max(v1, v2) + alpha * d
    return random.uniform(a, b)


def _mutar(valor: float, lo: float, hi: float, prob_mutacion: float, sigma_frac: float) -> float:
    if random.random() < prob_mutacion:
        sigma = sigma_frac * (hi - lo)
        valor += random.gauss(0, sigma)
    return valor


def _hijo_crossbred(parent_a: CandidateAvion, parent_b: CandidateAvion, bounds: dict,
                     alpha: float, prob_mutacion: float, sigma_frac: float) -> dict:
    pa, pb = parent_a.params, parent_b.params
    hijo = {}
    for key, (lo, hi) in bounds.items():
        val = _blx_alpha_gen(pa[key], pb[key], lo, hi, alpha)
        val = _mutar(val, lo, hi, prob_mutacion, sigma_frac)
        hijo[key] = val
    return hijo


def _hijo_wildcard(bounds: dict) -> dict:
    return {key: random.uniform(lo, hi) for key, (lo, hi) in bounds.items()}


def generar_hijos_avion(
    parent_a: CandidateAvion,
    parent_b: CandidateAvion,
    n_crossbred: int = 7,
    n_wildcard: int = 3,
    alpha: float = 0.5,
    prob_mutacion: float = 0.3,
    sigma_frac: float = 0.08,
) -> List[dict]:
    """Misma forma de salida que `ga_numerico.generar_hijos`: lista de
    dicts con "params", "origin", "rationale". `parent_a.topologia` y
    `parent_b.topologia` tienen que coincidir -- lo asegura
    `competencia.py` al mantener una subpoblación por topología, pero se
    valida acá también para que un error de wiring falle fuerte y temprano
    en vez de producir un candidato con parámetros mezclados sin sentido."""
    if parent_a.topologia != parent_b.topologia:
        raise ValueError(
            f"No se puede cruzar entre topologías distintas "
            f"({parent_a.topologia!r} vs {parent_b.topologia!r}): "
            f"cada topología evoluciona su propia subpoblación (ver competencia.py)."
        )
    topologia = parent_a.topologia
    bounds = BOUNDS_POR_TOPOLOGIA[topologia]

    hijos = []
    for _ in range(n_crossbred):
        params = clamp_to_bounds_avion(
            _hijo_crossbred(parent_a, parent_b, bounds, alpha, prob_mutacion, sigma_frac), topologia
        )
        hijos.append({
            "params": params,
            "origin": "crossbred",
            "rationale": f"BLX-alfa (alpha={alpha}) entre los dos padres + mutación gaussiana",
        })
    for _ in range(n_wildcard):
        params = clamp_to_bounds_avion(_hijo_wildcard(bounds), topologia)
        hijos.append({
            "params": params,
            "origin": "wildcard",
            "rationale": "muestreo uniforme independiente dentro de BOUNDS",
        })
    return hijos
