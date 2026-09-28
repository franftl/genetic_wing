"""
Loop evolutivo para UNA topología con cola, corriendo sobre su propia
subpoblación. Es un calco de `optimizacion_ala.evolucion` -- misma
estructura de estado explícito, mismo criterio de parada, mismo modo
paso-a-paso vs. batch -- adaptado para que los candidatos sean
`CandidateAvion` (topología + dict de params) en vez del dataclass plano
del ala volante.

Por qué un módulo aparte y no generalizar `evolucion.py` para que acepte
cualquier tipo de Candidate: la única diferencia real es cómo se
construye un Candidate a partir de un dict de params (`Candidate(**p)`
para el ala volante vs. `CandidateAvion(topologia=..., params=p)` acá), y
forzar esa diferencia dentro de `evolucion.py` con un parámetro extra
hubiera complicado el módulo que ya funciona y está en uso. `deberia_parar`
SÍ se reutiliza tal cual (ver el import): solo mira `generation` y
`non_improving_streak`, que son campos idénticos en los dos estados.

La pieza que hace posible que varias topologías "compitan" vive en
`competencia.py`, no acá: este módulo corre una única subpoblación de
principio a fin. `competencia.py` es el que llama a esto una vez por
topología y compara los resultados finales."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from optimizacion_ala.evolucion import deberia_parar  # reutilizado tal cual, ver encabezado

from .geometria_avion import CandidateAvion

GenerarHijosFn = Callable[[CandidateAvion, CandidateAvion, int, int], List[dict]]
ObjetivoFn = Callable[[dict], float]

TOLERANCIA_MEJORA = 1e-9


@dataclass
class EstadoEvolucionAvion:
    """Mismo rol que `evolucion.EstadoEvolucion`, con la topología
    explícita en el estado (así `guardar_checkpoint`/`cargar_checkpoint`
    saben qué BOUNDS y qué función objetivo corresponden al recargar)."""

    topologia: str
    parents: List[CandidateAvion]
    generation: int = 0
    non_improving_streak: int = 0
    historial: List[dict] = field(default_factory=list)

    def mejor(self) -> CandidateAvion:
        return max(self.parents, key=lambda c: c.score)


def iniciar_evolucion_avion(
    seed_population: List[dict], topologia: str, objetivo_fn: ObjetivoFn
) -> EstadoEvolucionAvion:
    """`objetivo_fn` ya viene con la topología fijada (ver
    `competencia.optimizar_topologia`, que arma este closure) -- acá adentro
    solo se llama como `objetivo_fn(params)`, igual que en el ala volante."""
    scored = [CandidateAvion(topologia=topologia, params=p, score=objetivo_fn(p)) for p in seed_population]
    scored.sort(key=lambda c: c.score, reverse=True)
    estado = EstadoEvolucionAvion(topologia=topologia, parents=scored[:2])
    estado.historial.append({
        "generation": 0,
        "status": "seeded",
        "parent_scores": [c.score for c in estado.parents],
    })
    return estado


def correr_generacion_avion(
    estado: EstadoEvolucionAvion,
    generar_hijos_fn: GenerarHijosFn,
    objetivo_fn: ObjetivoFn,
    n_crossbred: int = 7,
    n_wildcard: int = 3,
) -> "tuple[EstadoEvolucionAvion, list[dict]]":
    parent_a, parent_b = estado.parents
    children_raw = generar_hijos_fn(parent_a, parent_b, n_crossbred, n_wildcard)

    children = [
        {**c, "candidate": CandidateAvion(topologia=estado.topologia, params=c["params"], score=objetivo_fn(c["params"]))}
        for c in children_raw
    ]

    best_child_score = max((c["candidate"].score for c in children), default=float("-inf"))
    mejor_antes = max(c.score for c in estado.parents)

    pool = list(estado.parents) + [c["candidate"] for c in children]
    pool.sort(key=lambda c: c.score, reverse=True)
    nuevos_padres = pool[:2]

    mejor_despues = max(c.score for c in nuevos_padres)
    mejoro = mejor_despues > mejor_antes + TOLERANCIA_MEJORA
    nueva_racha = 0 if mejoro else estado.non_improving_streak + 1

    nuevo_estado = EstadoEvolucionAvion(
        topologia=estado.topologia,
        parents=nuevos_padres,
        generation=estado.generation + 1,
        non_improving_streak=nueva_racha,
        historial=estado.historial + [{
            "generation": estado.generation + 1,
            "status": "in_progress",
            "parent_scores": [c.score for c in nuevos_padres],
            "best_child_score": best_child_score,
            "mejoro": mejoro,
        }],
    )
    return nuevo_estado, children


def guardar_checkpoint(estado: EstadoEvolucionAvion, ruta: Path) -> None:
    with open(ruta, "w") as f:
        json.dump({
            "topologia": estado.topologia,
            "generation": estado.generation,
            "non_improving_streak": estado.non_improving_streak,
            "parents": [asdict(p) for p in estado.parents],
            "historial": estado.historial,
        }, f, indent=2)


def cargar_checkpoint(ruta: Path) -> Optional[EstadoEvolucionAvion]:
    if not Path(ruta).exists():
        return None
    with open(ruta) as f:
        data = json.load(f)
    return EstadoEvolucionAvion(
        topologia=data["topologia"],
        parents=[CandidateAvion(**p) for p in data["parents"]],
        generation=data["generation"],
        non_improving_streak=data["non_improving_streak"],
        historial=data.get("historial", []),
    )


def correr_evolucion_completa_avion(
    seed_population: List[dict],
    topologia: str,
    generar_hijos_fn: GenerarHijosFn,
    objetivo_fn: ObjetivoFn,
    n_crossbred: int = 7,
    n_wildcard: int = 3,
    paciencia: int = 8,
    max_generaciones: int = 80,
    checkpoint_path: Optional[Path] = None,
    verbose: bool = True,
) -> EstadoEvolucionAvion:
    """Modo batch, igual que `evolucion.correr_evolucion_completa`, para
    UNA topología. `competencia.correr_competencia` llama a esto una vez
    por topología con seeds y checkpoint distintos."""
    estado = iniciar_evolucion_avion(seed_population, topologia, objetivo_fn)
    if checkpoint_path:
        guardar_checkpoint(estado, checkpoint_path)
    if verbose:
        print(f"[{topologia}] Población semilla: {len(estado.parents)} candidatos elite")
        for c in estado.parents:
            print(f"  score={c.score:.4f}")

    while not deberia_parar(estado, paciencia, max_generaciones):
        try:
            estado, hijos = correr_generacion_avion(
                estado, generar_hijos_fn, objetivo_fn, n_crossbred, n_wildcard
            )
        except Exception as e:
            if verbose:
                print(f"\n[{topologia}] Falló la generación {estado.generation + 1}: {e}")
                print(f"[{topologia}] Deteniendo. Mejor score hasta ahora: {estado.mejor().score:.4f}")
            if checkpoint_path:
                guardar_checkpoint(estado, checkpoint_path)
            return estado

        if checkpoint_path:
            guardar_checkpoint(estado, checkpoint_path)
        if verbose:
            print(f"[{topologia}] Generación {estado.generation}: "
                  f"mejor hijo={max((h['candidate'].score for h in hijos), default=float('-inf')):.4f}  "
                  f"padres={[round(c.score, 4) for c in estado.parents]}")

    if verbose:
        print(f"[{topologia}] Detenido en la generación {estado.generation}. Mejor score: {estado.mejor().score:.4f}")
    return estado
