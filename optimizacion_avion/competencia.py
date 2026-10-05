"""
Hace competir las cinco topologías entre sí.

Cada una optimiza su PROPIA subpoblación de punta a punta, independiente, y
al final se comparan los mejores puntajes.

Por qué subpoblaciones separadas y no una sola población mixta: el `score`
de `evaluar_mision_avion` SÍ es comparable entre topologías (mismos nueve
términos, mismos pesos, mismas referencias de escala, misma misión), así que
competir por el mejor score final es válido. Lo que NO es válido es cruzar
(BLX-alfa) un padre con cola en V con uno de doble boom: sus vectores de
parámetros ni siquiera tienen la misma forma (uno tiene `v_tail_span`, el
otro `boom_largo`), así que "mezclarlos" no daría un diseño coherente de
ninguna de las dos familias. La competencia es "quién llega más alto", no un
crossover entre familias.

==========================================================================
SEMILLAS -- de dónde salen
==========================================================================
Están en `semillas.json`, al lado de este módulo, y las genera
`gen_semillas.py` (también incluido, para que el proceso sea reproducible y
no un número mágico). El procedimiento es:

1. Se define una base de ala + fuselaje + flap a mano, y una cola a mano por
   topología, con criterio de diseño pero sin pretensión de optimalidad.
2. Se AFINAN numéricamente dos parámetros por bisección:
   - `cg_frac_mac` hasta que el margen estático caiga en el medio de la
     banda de esa topología;
   - la incidencia del estabilizador hasta que el Cm en crucero sea ~0, o
     sea hasta que el avión quede TRIMADO sin elevador.
   Esos dos son los únicos que se afinan porque son los que deciden si el
   candidato es válido o no; el resto es trabajo del GA.

Hay DOS semillas por topología, y están a propósito en lados opuestos del
compromiso central de esta misión:

  A: ala grande (b ~ 3.1 m, S ~ 1.02 m2) con perfiles de ALTA SUSTENTACIÓN
     (fx63137 / naca6412). Vuela lento con holgura, pero en crucero a
     120 km/h anda por L/D ~ 7.3.
  B: ala más chica (b ~ 2.85 m, S ~ 0.82 m2) con perfiles de camber
     MODERADO (naca6412 / naca4412) y un flap que sí rinde. L/D ~ 10.4 en
     crucero -- bastante mejor -- y todavía vuela a 10 m/s.

Sembrar variado no es cosmético: BLX-alfa entre dos padres que tienen el
MISMO valor en una dimensión devuelve siempre ese valor, así que una
dimensión donde las dos semillas coinciden queda sin explorar.

Que la semilla B le gane a la A en L/D por 40% ya dice algo interesante
antes de optimizar: a 120 km/h el ala grande se paga caro, y el perfil de
alta sustentación no es gratis. Esa es la pelea que el GA tiene que resolver.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .evolucion_avion import EstadoEvolucionAvion, correr_evolucion_completa_avion
from .ga_numerico_avion import generar_hijos_avion
from .geometria_avion import TOPOLOGIAS, clamp_to_bounds_avion
from . import mision_avion
from .mision_avion import evaluar_mision_avion

_RUTA_SEMILLAS = Path(__file__).with_name("semillas.json")
# Con el viento del sitio (mision_avion.VIENTO_ACTIVO) las semillas de
# semillas.json no pueden volar a 10 m/s con el aire más liviano (pérdida a
# ~10.1-10.6 m/s), así que se arranca desde los ganadores SIN viento de la
# corrida del 18/09 (ganadores.json), que sí son válidos. Ver Research Note 16.
_RUTA_SEMILLAS_VIENTO = Path(__file__).with_name("semillas_viento.json")


def _cargar_semillas() -> dict:
    ruta = _RUTA_SEMILLAS_VIENTO if mision_avion.VIENTO_ACTIVO else _RUTA_SEMILLAS
    with open(ruta) as f:
        crudas = json.load(f)
    # Se vuelven a pasar por clamp: si alguien edita el JSON a mano, el
    # candidato entra igual al pipeline como diseño fabricable.
    return {t: [clamp_to_bounds_avion(p, t) for p in lista] for t, lista in crudas.items()}


SEEDS_POR_TOPOLOGIA = _cargar_semillas()


def optimizar_topologia(
    topologia: str,
    seed_population: Optional[list] = None,
    n_crossbred: int = 7,
    n_wildcard: int = 3,
    paciencia: int = 10,
    max_generaciones: int = 60,
    checkpoint_path: Optional[Path] = None,
    verbose: bool = True,
) -> EstadoEvolucionAvion:
    """Evolución completa de UNA topología.

    Los defaults de `paciencia` y `max_generaciones` subieron respecto de la
    versión anterior (8/40) porque el espacio de diseño creció bastante: de
    ~20 parámetros por topología a 46-51. Con más dimensiones, el GA
    necesita más generaciones para explotar una dirección buena antes de que
    la racha sin mejora lo corte."""
    seeds = seed_population if seed_population is not None else SEEDS_POR_TOPOLOGIA[topologia]

    def objetivo_fn(params: dict) -> float:
        return evaluar_mision_avion(params, topologia)

    def generar_hijos_fn(parent_a, parent_b, ncb, nw):
        return generar_hijos_avion(parent_a, parent_b, ncb, nw)

    return correr_evolucion_completa_avion(
        seeds, topologia, generar_hijos_fn, objetivo_fn,
        n_crossbred=n_crossbred, n_wildcard=n_wildcard,
        paciencia=paciencia, max_generaciones=max_generaciones,
        checkpoint_path=checkpoint_path, verbose=verbose,
    )


def correr_competencia(
    topologias: Optional[list] = None,
    n_crossbred: int = 7,
    n_wildcard: int = 3,
    paciencia: int = 10,
    max_generaciones: int = 60,
    checkpoint_dir: Optional[Path] = None,
    verbose: bool = True,
) -> dict:
    """Corre cada topología por separado y devuelve {topologia: estado}.
    No hay ningún intercambio entre topologías durante la corrida."""
    topologias = topologias if topologias is not None else list(TOPOLOGIAS.keys())
    resultados = {}
    for topologia in topologias:
        if verbose:
            print(f"\n{'=' * 70}\nOptimizando topologia: {topologia}\n{'=' * 70}")
        ckpt = Path(checkpoint_dir) / f"checkpoint_{topologia}.json" if checkpoint_dir else None
        resultados[topologia] = optimizar_topologia(
            topologia, n_crossbred=n_crossbred, n_wildcard=n_wildcard,
            paciencia=paciencia, max_generaciones=max_generaciones,
            checkpoint_path=ckpt, verbose=verbose)
    return resultados


def tabla_resultados(resultados: dict, extra: Optional[dict] = None) -> str:
    """Tabla comparativa final, ordenada de mayor a menor score.

    `extra` permite sumar entradas de puntaje ya conocido que no pasaron por
    este loop -- por ejemplo el mejor score del ala volante del notebook 01.
    OJO al comparar contra el ala volante: comparte pesos y referencias de
    escala, pero NO la misión (el ala volante está optimizada para crucero a
    60 km/h y sin requisito de vuelo lento), así que esa comparación solo
    vale si se vuelve a correr el notebook 01 con la misión nueva."""
    filas = [(t, e.mejor().score, e.generation) for t, e in resultados.items()]
    if extra:
        filas += [(n, s, None) for n, s in extra.items()]
    filas.sort(key=lambda f: f[1], reverse=True)

    ancho = max([len(str(f[0])) for f in filas] + [14])
    L = ["=== COMPETENCIA ENTRE TOPOLOGIAS ==="]
    for i, (nombre, score, gen) in enumerate(filas, start=1):
        g = f"  ({gen} generaciones)" if gen is not None else "  (externo)"
        marca = "  <-- GANA" if i == 1 else ""
        L.append(f"  {i}. {nombre:<{ancho}} score={score:8.4f}{g}{marca}")
    return "\n".join(L)
