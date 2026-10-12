"""
Corre la competencia de topologías en el escenario que se elija con DOS
interruptores independientes:

    --viento   on|off    viento de los sitios (lo de imarzeniuk), mision_avion.VIENTO_ACTIVO
    --bateria  on|off    batería dimensionada por 350 km, mision_avion.BATERIA_ACTIVA

La penalización de envergadura > 2 m, el sweep monótono y las 11 estaciones
del ala están siempre activas en esta rama (se pueden mover en
mision_avion.py: ENVERGADURA_MANUFACTURA_MAX / _TOL / PESO_ENVERGADURA).

Ejemplos (desde la raíz del repo):

    python evaluacion_bateria_350km/correr_escenarios.py --viento on --bateria on
    python evaluacion_bateria_350km/correr_escenarios.py --viento off --bateria on --topologias v_tail pod_boom
    python evaluacion_bateria_350km/correr_escenarios.py --viento on --bateria on --paciencia 4 --max-gen 15   # corrida corta

Salida: evaluacion_bateria_350km/resultados/ganadores_viento-<on|off>_bateria-<on|off>.json
        y una tabla en .md al lado. La semilla del azar es fija.

Semillas: con batería hacen falta semillas más grandes (11 kg, 1.5 L de batería):
se usan las de semillas_bateria.json (generadas por reparar_semillas.py). Sin
batería y con viento se usa ganadores_viento.json (semillas.json no vuela a
10 m/s con aire de 1.056 kg/m3).
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
REPO = AQUI.parent
sys.path.insert(0, str(REPO))

from optimizacion_avion import mision_avion as ma                      # noqa: E402
from optimizacion_avion import competencia                              # noqa: E402
from optimizacion_avion.geometria_avion import TOPOLOGIAS, clamp_to_bounds_avion  # noqa: E402

SALIDA = AQUI / "resultados"


def _onoff(v: str) -> bool:
    return v.lower() in ("on", "true", "1", "si", "sí")


def semillas(top: str, viento: bool, bateria: bool) -> list:
    if bateria:
        ruta = AQUI / "semillas_bateria.json"
        if not ruta.exists():
            sys.exit("Falta semillas_bateria.json: correr reparar_semillas.py primero.")
        crudas = json.load(open(ruta))[top]
    elif viento:
        crudas = [json.load(open(REPO / "optimizacion_avion" / "ganadores_viento.json"))[top]["params"]]
    else:
        crudas = json.load(open(REPO / "optimizacion_avion" / "semillas.json"))[top]
    return [clamp_to_bounds_avion(p, top) for p in crudas]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--viento", default="on")
    ap.add_argument("--bateria", default="on")
    ap.add_argument("--topologias", nargs="*", default=list(TOPOLOGIAS))
    ap.add_argument("--paciencia", type=int, default=10)
    ap.add_argument("--max-gen", type=int, default=60)
    ap.add_argument("--semilla", type=int, default=2026)
    ap.add_argument("--sufijo", default="", help="agrega un sufijo al nombre del archivo de salida")
    args = ap.parse_args()

    ma.VIENTO_ACTIVO = _onoff(args.viento)
    ma.BATERIA_ACTIVA = _onoff(args.bateria)
    etiqueta = f"viento-{'on' if ma.VIENTO_ACTIVO else 'off'}_bateria-{'on' if ma.BATERIA_ACTIVA else 'off'}{args.sufijo}"
    SALIDA.mkdir(exist_ok=True)
    ruta_json = SALIDA / f"ganadores_{etiqueta}.json"
    res = json.load(open(ruta_json)) if ruta_json.exists() else {}

    todas = list(TOPOLOGIAS)
    for top in args.topologias:
        random.seed(args.semilla + todas.index(top))
        est = competencia.optimizar_topologia(top, seed_population=semillas(top, ma.VIENTO_ACTIVO, ma.BATERIA_ACTIVA),
                                              paciencia=args.paciencia, max_generaciones=args.max_gen)
        mejor = est.mejor()
        res[top] = {"score": mejor.score, "generaciones": est.generation, "params": mejor.params,
                    "analisis": ma.analizar_mision_avion(mejor.params, top)}
        json.dump(res, open(ruta_json, "w"), indent=2, default=float, ensure_ascii=False)
        print(f"[{top}] listo: score {mejor.score:.4f} en {est.generation} generaciones", flush=True)

    # tabla
    L = [f"# Escenario {etiqueta}", "",
         "| Topología | Score | b [m] | S [m²] | AR | Masa [kg] | Batería [kg] | Alcance [km] | L/D | V pérdida [m/s] |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for top, r in sorted(res.items(), key=lambda kv: -kv[1]["score"]):
        a = r["analisis"]
        bat = a.get("bateria")
        L.append(f"| {top} | {r['score']:.3f} | {a['envergadura']:.2f} | {a['S']:.3f} | {a['AR']:.1f} | "
                 f"{a['masa_total']:.2f} | {a.get('masa_bateria', 0) or 0:.2f} | "
                 f"{bat['alcance_logrado_km']:.0f} | {a['LD_crucero']:.1f} | {a['v_stall']:.2f} |"
                 if bat else
                 f"| {top} | {r['score']:.3f} | {a['envergadura']:.2f} | {a['S']:.3f} | {a['AR']:.1f} | "
                 f"{a['masa_total']:.2f} | - | - | {a['LD_crucero']:.1f} | {a['v_stall']:.2f} |")
    (SALIDA / f"tabla_{etiqueta}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
