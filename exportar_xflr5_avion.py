"""
Exporta un avión a XFLR5 (XML del avión + perfiles .dat + condiciones de crucero).

USO (desde la carpeta genetic_wing, con el venv):

    python exportar_xflr5_avion.py --params "<resultados>/<corrida>/ganadores.json" --topologia v_tail
    python exportar_xflr5_avion.py --params avion_design_params_v_tail.json --viento on --bateria on

Acepta lo mismo que exportar_cad_avion.py: un ganadores.json de una carpeta de resultados,
lo que exporta el notebook (sección 11) o un dict de parámetros. Escribe en
`--salida` (por defecto xflr5_<topologia>/ al lado de este script):

    <topologia>_avion.xml   perfiles/*.dat   condiciones.txt   LEEME.txt

Ver optimizacion_avion/xflr5.py para qué se exporta y qué no (sin fuselaje; masa en el CG).
Cada corrida guardada con guardar_resultados ya trae esto en su carpeta xflr5/<familia>/.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

from optimizacion_avion import mision_avion as ma                       # noqa: E402
from optimizacion_avion.geometria_avion import TOPOLOGIAS, clamp_to_bounds_avion  # noqa: E402
from optimizacion_avion.xflr5 import exportar_xflr5                       # noqa: E402
import exportar_cfd_avion as ecfd                                         # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Exporta un avión a XFLR5.")
    ap.add_argument("--params", required=True, type=Path)
    ap.add_argument("--topologia", choices=list(TOPOLOGIAS))
    ap.add_argument("--salida", type=Path)
    ap.add_argument("--viento", choices=("on", "off"), default=None)
    ap.add_argument("--bateria", choices=("on", "off"), default=None)
    args = ap.parse_args()
    if args.viento:
        ma.VIENTO_ACTIVO = args.viento == "on"
    if args.bateria:
        ma.BATERIA_ACTIVA = args.bateria == "on"
    params, top = ecfd.cargar_params(args.params, args.topologia)
    params = clamp_to_bounds_avion(params, top)
    ruta = exportar_xflr5(params, top, args.salida or RAIZ / f"xflr5_{top}")
    print(f"XFLR5: {ruta}")
    print((ruta.parent / "LEEME.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
