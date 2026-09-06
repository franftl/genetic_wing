"""
Backend de generación de hijos por GA numérico (SIN llamadas a ningún
modelo de IA -- no consume créditos ni depende de tener Claude Code
logueado). Reemplaza a `cruzamiento_ia.py` como backend activo del
notebook, siguiendo la recomendación de la Research Note 11/estado del
proyecto: es más fiel al método de Tran et al. (el antecedente
académico citado en el proyecto), determinístico si fijás la semilla
de `random`, y muchísimo más barato de correr a escala.

Misma firma que cruzamiento_ia.generar_hijos(), así que es un reemplazo
directo en `correr_generacion()` -- no hace falta tocar evolucion.py
ni el resto del pipeline.

Operadores usados (estándar en la literatura de GA de codificación
real, no inventados para este proyecto):

- Crossover: BLX-alfa (blend crossover). Para cada parámetro, el hijo
  se muestrea uniformemente en un rango que va un poco más allá del
  menor y el mayor valor de los dos padres (controlado por `alpha`),
  permitiendo explorar ligeramente afuera del segmento que conecta a
  ambos padres, no solo interpolar entre ellos.
- Mutación: ruido gaussiano aditivo con probabilidad `prob_mutacion`
  por gen, escalado al rango de BOUNDS de cada parámetro.
- Wildcards: muestreo uniforme independiente dentro de BOUNDS (mismo
  rol que cumplían los "wildcard" del backend de IA: inyectar
  diversidad que los padres no representan).

Nota de honestidad académica: esto sigue usando la misma arquitectura
de "2 padres elite + N hijos por generación, reemplazo elitista" que
ya estaba en evolucion.py -- en la práctica es más una estrategia
evolutiva (2+lambda) que un GA poblacional clásico de cientos de
individuos con selección por torneo. Si en algún momento quieren
replicar el método de Tran et al. de forma más literal (población
grande, selección por torneo/ruleta), es un cambio de evolucion.py
más profundo, no solo de este archivo -- avisen si lo quieren armar.
"""

from __future__ import annotations

import random
from typing import List

from .geometria import BOUNDS, Candidate, clamp_to_bounds


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


def _hijo_crossbred(parent_a: Candidate, parent_b: Candidate, alpha: float, prob_mutacion: float, sigma_frac: float) -> dict:
    pa, pb = parent_a.params(), parent_b.params()
    hijo = {}
    for key, (lo, hi) in BOUNDS.items():
        val = _blx_alpha_gen(pa[key], pb[key], lo, hi, alpha)
        val = _mutar(val, lo, hi, prob_mutacion, sigma_frac)
        hijo[key] = val
    return hijo


def _hijo_wildcard() -> dict:
    return {key: random.uniform(lo, hi) for key, (lo, hi) in BOUNDS.items()}


def generar_hijos(
    parent_a: Candidate,
    parent_b: Candidate,
    n_crossbred: int = 7,
    n_wildcard: int = 3,
    alpha: float = 0.5,
    prob_mutacion: float = 0.3,
    sigma_frac: float = 0.08,
) -> List[dict]:
    """Genera `n_crossbred` hijos por BLX-alfa + mutación gaussiana a
    partir de los dos padres, y `n_wildcard` hijos por muestreo
    uniforme independiente en BOUNDS. Misma forma de salida que el
    backend de IA (lista de dicts con "params", "origin", "rationale")
    para que el resto del pipeline (incluida la tabla que arma el
    notebook) no tenga que distinguir de qué backend vinieron.

    `alpha` controla cuánto se permite explorar más allá del rango de
    los padres (0 = nunca sale del segmento entre ambos, valores
    típicos 0.3-0.5). `prob_mutacion` y `sigma_frac` controlan la
    mutación gaussiana por gen (sigma como fracción del rango de
    BOUNDS de ese parámetro)."""
    hijos = []
    for _ in range(n_crossbred):
        params = clamp_to_bounds(_hijo_crossbred(parent_a, parent_b, alpha, prob_mutacion, sigma_frac))
        hijos.append({
            "params": params,
            "origin": "crossbred",
            "rationale": f"BLX-alfa (alpha={alpha}) entre los dos padres + mutación gaussiana",
        })
    for _ in range(n_wildcard):
        params = clamp_to_bounds(_hijo_wildcard())
        hijos.append({
            "params": params,
            "origin": "wildcard",
            "rationale": "muestreo uniforme independiente dentro de BOUNDS",
        })
    return hijos
