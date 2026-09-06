"""
Loop evolutivo -- reestructurado para poder correrse GENERACIÓN POR
GENERACIÓN desde una notebook, en vez de quedar encerrado dentro de un
único `while` que corre de punta a punta sin poder pausarse a mirar
resultados intermedios.

Esto es intencional: es la diferencia concreta entre "un script que
corrés y esperás" y "un panel de control donde ves cada generación,
el razonamiento de cada hijo propuesto, y decidís vos si seguir".

Backend-agnóstico: `correr_generacion()` recibe la función de
generación de hijos como parámetro (`generar_hijos_fn`), no la importa
por nombre fijo. Así, cambiar de backend (IA -> GA numérico -> asb.Opti)
es pasar una función distinta, no reescribir este archivo.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from .geometria import Candidate

GenerarHijosFn = Callable[[Candidate, Candidate, int, int], List[dict]]
ObjetivoFn = Callable[[dict], float]

CHECKPOINT_PATH = Path("evolution_checkpoint.json")

# Mejora mínima para que una generación cuente como "mejoró" y resetee la
# racha. Existe para que el ruido de punto flotante (o una mejora de
# 1e-12) no resetee el contador y el criterio de parada nunca dispare.
TOLERANCIA_MEJORA = 1e-9


@dataclass
class EstadoEvolucion:
    """Todo el estado del loop evolutivo en un solo objeto explícito --
    nada vive en variables globales ni en el estado interno de una
    función. Eso es lo que permite pausar entre generaciones: el estado
    completo cabe en esta clase y se puede inspeccionar, guardar, o
    incluso editar a mano entre una celda y la siguiente."""

    parents: List[Candidate]
    generation: int = 0
    non_improving_streak: int = 0
    historial: List[dict] = field(default_factory=list)  # un dict resumen por generación

    def mejor(self) -> Candidate:
        return max(self.parents, key=lambda c: c.score)


def iniciar_evolucion(seed_population: List[dict], objetivo_fn: ObjetivoFn) -> EstadoEvolucion:
    """Evalúa la población semilla y arma el estado inicial (los 2
    mejores como padres)."""
    scored = [Candidate(**p, score=objetivo_fn(p)) for p in seed_population]
    scored.sort(key=lambda c: c.score, reverse=True)
    estado = EstadoEvolucion(parents=scored[:2])
    estado.historial.append(
        {
            "generation": 0,
            "status": "seeded",
            "parent_scores": [c.score for c in estado.parents],
        }
    )
    return estado


def correr_generacion(
    estado: EstadoEvolucion,
    generar_hijos_fn: GenerarHijosFn,
    objetivo_fn: ObjetivoFn,
    n_crossbred: int = 7,
    n_wildcard: int = 3,
) -> "tuple[EstadoEvolucion, list[dict]]":
    """Corre UNA generación: genera hijos, los evalúa, actualiza los
    padres por elitismo. Devuelve el estado actualizado Y la lista de
    hijos de esta generación (cada uno con su score, origin y
    rationale si el backend los da) -- para que la notebook los pueda
    mostrar/graficar antes de decidir si seguir.

    No muta `estado` in-place; devuelve uno nuevo, para que si algo
    sale mal en una celda se pueda volver a correr sin efectos
    colaterales sobre el estado anterior."""
    parent_a, parent_b = estado.parents
    children_raw = generar_hijos_fn(parent_a, parent_b, n_crossbred, n_wildcard)

    children = [
        {**c, "candidate": Candidate(**c["params"], score=objetivo_fn(c["params"]))}
        for c in children_raw
    ]

    best_child_score = max((c["candidate"].score for c in children), default=float("-inf"))
    mejor_antes = max(c.score for c in estado.parents)

    pool = list(estado.parents) + [c["candidate"] for c in children]
    pool.sort(key=lambda c: c.score, reverse=True)
    nuevos_padres = pool[:2]

    mejor_despues = max(c.score for c in nuevos_padres)

    # La racha cuenta generaciones en las que EL MEJOR SCORE no mejoró.
    #
    # OJO -- esto cambió (2026-08-26). Antes la racha se reseteaba cuando
    # cualquier hijo superaba al PEOR de los dos padres, lo cual resetea
    # el contador aunque el mejor score se haya quedado clavado: en una
    # prueba real el mejor score no se movió durante 3 generaciones
    # seguidas y la racha seguía en 0, así que el criterio de parada no
    # llegaba a dispararse nunca por estancamiento. Ahora compara el
    # mejor score antes vs. después, que es lo que uno espera cuando dice
    # "parar si no mejora en N generaciones".
    mejoro = mejor_despues > mejor_antes + TOLERANCIA_MEJORA
    nueva_racha = 0 if mejoro else estado.non_improving_streak + 1

    nuevo_estado = EstadoEvolucion(
        parents=nuevos_padres,
        generation=estado.generation + 1,
        non_improving_streak=nueva_racha,
        historial=estado.historial
        + [
            {
                "generation": estado.generation + 1,
                "status": "in_progress",
                "parent_scores": [c.score for c in nuevos_padres],
                "best_child_score": best_child_score,
                "mejoro": mejoro,
            }
        ],
    )
    return nuevo_estado, children


def deberia_parar(estado: EstadoEvolucion, paciencia: int = 8, max_generaciones: int = 80) -> bool:
    """Criterio de parada, expuesto como función aparte (en vez de
    quedar hardcodeado dentro del loop) para poder ajustar `paciencia`
    sin tocar correr_generacion.

    `paciencia` = cuántas generaciones seguidas sin mejorar el mejor score
    se toleran antes de parar.

    Default 8, subido desde 3 el 2026-08-26 junto con el espacio de 27
    parámetros. Medido sobre 2 semillas:
        paciencia 3 -> 12 y 9 generaciones, scores 1.454 / 1.397 (media 1.425)
        paciencia 8 -> 45 y 26 generaciones, scores 1.557 / 1.477 (media 1.517)
    Mejora ~6.5% en ambas semillas.

    (También se probó mutación adaptativa -- agrandar sigma al estancarse --
    y resultó CONTRAPRODUCENTE: media 1.309, peor que el baseline. Las
    mutaciones grandes dan hijos peores, la racha crece más rápido y el loop
    corta antes. Se descartó; no está en el código.)

    `max_generaciones` = tope duro, para que el loop no quede corriendo
    indefinidamente si el score mejora de a migajas para siempre."""
    return estado.non_improving_streak >= paciencia or estado.generation >= max_generaciones


def guardar_checkpoint(estado: EstadoEvolucion, ruta: Path = CHECKPOINT_PATH) -> None:
    """Guarda el estado actual a disco. Llamar después de cada
    generación (o cuando se quiera) para no perder progreso si se corta
    la sesión."""
    with open(ruta, "w") as f:
        json.dump(
            {
                "generation": estado.generation,
                "non_improving_streak": estado.non_improving_streak,
                "parents": [asdict(p) for p in estado.parents],
                "historial": estado.historial,
            },
            f,
            indent=2,
        )


def cargar_checkpoint(ruta: Path = CHECKPOINT_PATH) -> Optional[EstadoEvolucion]:
    """Recupera un estado guardado, por si se quiere retomar una
    corrida sin empezar de cero."""
    if not Path(ruta).exists():
        return None
    with open(ruta) as f:
        data = json.load(f)
    return EstadoEvolucion(
        parents=[Candidate(**p) for p in data["parents"]],
        generation=data["generation"],
        non_improving_streak=data["non_improving_streak"],
        historial=data.get("historial", []),
    )


def correr_evolucion_completa(
    seed_population: List[dict],
    generar_hijos_fn: GenerarHijosFn,
    objetivo_fn: ObjetivoFn,
    n_crossbred: int = 7,
    n_wildcard: int = 3,
    paciencia: int = 8,
    max_generaciones: int = 80,
    verbose: bool = True,
) -> EstadoEvolucion:
    """Modo "batch": corre generaciones hasta el criterio de parada sin
    pausar, para cuando ya no hace falta inspeccionar cada paso a mano
    (ej. una vez que el objetivo real ya está validado y solo se quiere
    dejarlo correr). Construida sobre las mismas piezas que el modo
    paso a paso -- no hay lógica duplicada."""
    estado = iniciar_evolucion(seed_population, objetivo_fn)
    guardar_checkpoint(estado)
    if verbose:
        print(f"Población semilla: {len(estado.parents)} candidatos elite")
        for c in estado.parents:
            print(f"  score={c.score:.4f}  {c.params()}")

    while not deberia_parar(estado, paciencia, max_generaciones):
        try:
            estado, hijos = correr_generacion(
                estado, generar_hijos_fn, objetivo_fn, n_crossbred, n_wildcard
            )
        except Exception as e:
            if verbose:
                print(f"\nFalló la generación {estado.generation + 1}: {e}")
                print(f"Deteniendo. Mejor diseño hasta ahora: score={estado.mejor().score:.4f}")
            guardar_checkpoint(estado)
            return estado

        guardar_checkpoint(estado)
        if verbose:
            print(f"\n=== Generación {estado.generation} ===")
            for h in hijos:
                print(f"  [{h.get('origin', '?')}] score={h['candidate'].score:.4f}  ({h.get('rationale', '')})")

    if verbose:
        print(f"\nDetenido en la generación {estado.generation}. Mejor score: {estado.mejor().score:.4f}")
    return estado
