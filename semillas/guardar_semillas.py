"""
Guarda los aviones de una corrida como un set de semillas nuevo.

    python semillas/guardar_semillas.py checkpoint_avion_*.json --nombre v51_bateria_viento
    python semillas/guardar_semillas.py optimizacion_avion/ganadores.json optimizacion_avion/ganadores_viento.json --nombre mezcla

Acepta, mezclados:
  - checkpoints del notebook (checkpoint_avion_<topologia>.json): aporta los dos padres finales;
  - archivos de ganadores (ganadores*.json, {topologia: {score, params, ...}}): aporta el ganador;
  - ganadores sueltos de viento (ganador_viento_<topologia>.json): aporta el ganador.

Por topología se quedan los --por-topologia mejores por score (default 2). Se
avisa si una topología queda con menos de 2: el GA necesita dos padres.
Escribe semillas/<nombre>.json y agrega una fila a la tabla de semillas/LEEME.md.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

CARPETA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARPETA.parent))

from optimizacion_avion.geometria_avion import TOPOLOGIAS  # noqa: E402


def _aviones(ruta: Path) -> list[tuple[str, float, dict]]:
    """(topologia, score, params) de cada avión que trae el archivo."""
    d = json.loads(ruta.read_text(encoding="utf-8"))
    if "parents" in d and "topologia" in d:                      # checkpoint del notebook
        return [(d["topologia"], p["score"], p["params"]) for p in d["parents"]]
    if "params" in d and ruta.stem.startswith("ganador_viento_"):  # ganador suelto
        return [(ruta.stem.removeprefix("ganador_viento_"), d.get("score", float("-inf")), d["params"])]
    if all(t in TOPOLOGIAS for t in d):                           # {topologia: {score, params}}
        return [(t, v.get("score", float("-inf")), v["params"]) for t, v in d.items()]
    raise ValueError(f"{ruta}: formato no reconocido")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("archivos", nargs="+", type=Path)
    ap.add_argument("--nombre", required=True, help="nombre del set (queda semillas/<nombre>.json)")
    ap.add_argument("--por-topologia", type=int, default=2)
    ap.add_argument("--descripcion", default="", help="una línea para la tabla del LEEME")
    ap.add_argument("--pisar", action="store_true", help="reemplazar un set que ya existe")
    a = ap.parse_args()

    destino = CARPETA / f"{a.nombre}.json"
    if destino.exists() and not a.pisar:
        sys.exit(f"Ya existe {destino.name}. Elegí otro --nombre o pasá --pisar.")

    por_top: dict[str, list[tuple[float, dict]]] = {}
    for ruta in a.archivos:
        for top, score, params in _aviones(ruta):
            por_top.setdefault(top, []).append((score, params))

    salida = {}
    for top in TOPOLOGIAS:
        if top not in por_top:
            continue
        mejores = sorted(por_top[top], key=lambda sp: sp[0], reverse=True)[: a.por_topologia]
        salida[top] = [p for _, p in mejores]
        aviso = "   <-- OJO: menos de 2, el GA necesita dos padres" if len(mejores) < 2 else ""
        if any(s == float("-inf") for s, _ in mejores):
            aviso += "   <-- OJO: aviones INVALIDOS en esa corrida (score -inf)"
        print(f"  {top:<14} {len(mejores)} aviones, scores {[round(s, 3) for s, _ in mejores]}{aviso}")

    destino.write_text(json.dumps(salida, indent=2, default=float), encoding="utf-8")

    fuentes = ", ".join(f"`{r.name}`" for r in a.archivos)
    fila = (f"| `{a.nombre}` | {dt.date.today().isoformat()} | {a.descripcion or '—'} | {fuentes} |"
            f" correr `python semillas/validar_semillas.py {a.nombre}` |\n")
    with open(CARPETA / "LEEME.md", "a", encoding="utf-8") as f:
        f.write(fila)
    print(f"Guardado {destino}  (y anotado en semillas/LEEME.md)")


if __name__ == "__main__":
    main()
