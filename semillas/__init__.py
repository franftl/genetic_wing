"""
Biblioteca de sets de semillas para el optimizador de avión.

Cada set es un JSON con el mismo formato que optimizacion_avion/semillas.json:

    {"convencional": [params, params, ...], "t_tail": [...], ...}

con al menos DOS aviones por topología (el GA arranca con los dos mejores, y
BLX-alfa entre dos padres iguales no explora). Qué es cada set y con qué
modelo de misión es válido está en semillas/LEEME.md.

Uso, desde la carpeta genetic_wing (por ejemplo en una celda del notebook):

    import semillas
    semillas.listar()                               # nombres disponibles
    av.SEEDS_POR_TOPOLOGIA.update(semillas.cargar("bateria_350km"))

Para guardar los aviones de una corrida como set nuevo: guardar_semillas.py.
"""
from __future__ import annotations

import json
from pathlib import Path

CARPETA = Path(__file__).resolve().parent


def listar() -> list[str]:
    """Nombres de los sets disponibles (sin la extensión .json)."""
    return sorted(p.stem for p in CARPETA.glob("*.json"))


def cargar(nombre: str, clamp: bool = True) -> dict:
    """Devuelve {topologia: [params, ...]} del set `nombre`.

    Con clamp=True cada avión se pasa por clamp_to_bounds_avion, igual que
    hace competencia.py con semillas.json: si los bounds cambiaron desde que
    se guardó el set, el avión entra igual como diseño fabricable."""
    ruta = CARPETA / f"{nombre}.json"
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el set '{nombre}'. Disponibles: {', '.join(listar())}")
    crudas = json.loads(ruta.read_text(encoding="utf-8"))
    if not clamp:
        return crudas
    from optimizacion_avion.geometria_avion import clamp_to_bounds_avion
    return {t: [clamp_to_bounds_avion(p, t) for p in lista] for t, lista in crudas.items()}
