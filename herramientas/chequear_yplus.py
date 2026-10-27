"""
Mide el y+ real de una malla: lee el .msh.h5 en el solver de Fluent 24.1, k-omega SST, entrada de 22.22 m/s,
itera unas pocas veces y calcula estadisticas de y+ sobre la zona m_plane (el avion).

Uso (desde la raiz del repo):
    C:\\Users\\felip\\venv_pyfluent\\Scripts\\python.exe -u herramientas\\chequear_yplus.py [malla] [--iter 45]

Es solo una verificacion de la malla: con 45 iteraciones desde inicializacion hibrida la solucion no esta convergida
(continuidad ~6e-3), pero el esfuerzo de pared ya es representativo. Tarda ~9 s por iteracion con 2.6 M celdas y 8 nucleos.
Los campos se piden con field_data (surface_integrals.facet_* devuelve 1 para cualquier campo sobre una zona de pared).
"""
from __future__ import annotations

import argparse
import atexit
import time
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
T0 = time.time()


def log(*a):
    print("[%6.1fs]" % (time.time() - T0), *a, flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("malla", nargs="?", type=Path, default=RAIZ / "resultados" / "cfd_run" / "malla_v5.msh.h5")
    ap.add_argument("--iter", type=int, default=45)
    ap.add_argument("--velocidad", type=float, default=22.22)
    ap.add_argument("--procesos", type=int, default=8)
    args = ap.parse_args()

    import ansys.fluent.core as pyfluent

    s = pyfluent.launch_fluent(product_version="24.1.0", mode="solver", precision="double", dimension=3,
                               processor_count=args.procesos, start_timeout=240, ui_mode="no_gui",
                               cwd=str(args.malla.parent))

    def cerrar():
        for fn in (s.exit, s.force_exit):
            try:
                fn()
            except Exception:  # noqa: BLE001
                pass

    atexit.register(cerrar)
    s.tui.file.read_case('"%s"' % args.malla.as_posix())
    log("malla leida")
    vi = s.setup.models.viscous
    vi.model = "k-omega"
    vi.k_omega_model = "sst"
    aire = s.setup.materials.fluid["air"]
    aire.density.value = 1.056
    aire.viscosity.value = 1.7433e-5
    entrada = s.setup.boundary_conditions.velocity_inlet["m_inlet"]
    entrada.momentum.velocity_specification_method = "Magnitude, Normal to Boundary"
    entrada.momentum.velocity.value = args.velocidad
    s.tui.solve.initialize.hyb_initialization()
    s.tui.solve.iterate(args.iter)
    log("iteraciones hechas")

    for campo in ("y-plus", "wall-shear"):
        r = s.field_data.get_scalar_field_data(field_name=campo, surfaces=["m_plane"], node_value=False,
                                               boundary_value=True)
        v = r["m_plane"] if isinstance(r, dict) else r
        a = np.asarray(getattr(v, "scalar_data", v), dtype=float).ravel()
        log("%-10s n=%d  min %.3g  mediana %.3g  media %.3g  p95 %.3g  max %.3g" %
            (campo, a.size, a.min(), np.median(a), a.mean(), np.percentile(a, 95), a.max()))


if __name__ == "__main__":
    main()
