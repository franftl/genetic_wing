"""
Pipeline de CFD con PyFluent: chequeo del dominio -> malla -> solver -> L y D en ejes del viento.

BORRADOR SIN PROBAR. Se escribio sin poder ejecutar Ansys, asi que la primera corrida va a pedir
ajustes de nombres de comandos segun la version de Ansys/PyFluent (se corrige iterando con el error).
Lo unico verificado es `--solo-chequeo` (no necesita Ansys).

Uso (PowerShell, desde la raiz del repo):
    pip install ansys-fluent-core
    python herramientas\\fluent_pipeline.py --solo-chequeo                 # revisa el dominio del STEP
    python herramientas\\fluent_pipeline.py --alpha 1.21                   # malla + calculo
    python herramientas\\fluent_pipeline.py --alpha 0 1.21 4 --sin-malla   # barrido, reusa la malla

Entradas : STEP con el dominio fluido (medio modelo, plano de simetria en y = 0), en mm.
           Ejes del modelo: x hacia atras, y a la derecha, z hacia arriba.
Salidas  : resultados/cfd_run/ (malla .msh.h5, caso .cas.h5, resultados.json)

POR QUE EXISTE EL CHEQUEO DE DOMINIO. El encl_red.step original mide 8.3 x 2.5 x 1.0 m (20.7 m3):
el ala queda a ~0.4 m de las tapas superior e inferior (menos de una cuerda). Con fronteras tan cerca
las fuerzas dependen del dominio, no del avion. Ver DOMINIO_MIN.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
STEP_POR_DEFECTO = RAIZ / "encl_red.step"
SALIDA = RAIZ / "resultados" / "cfd_run"

# --- Condiciones (de resultados/cfd_v_tail/v_tail_caso_cfd.md, V53, escenario viento ON, bateria ON) ---
V = 22.2222            # m/s
RHO = 1.056            # kg/m3
MU = 1.7433e-5         # Pa.s
S_REF_COMPLETA = 1.2134    # m2 (avion completo; el medio modelo usa la mitad)
C_REF = 0.3859         # m (MAC)
CG = (0.6343, 0.0, 0.0)    # m, centro de momentos
TURB_INTENSIDAD = 0.1  # % (aire libre; 5 % es de tunel de viento y arruina la transicion)
VISC_RATIO = 10.0

# --- Avion (m) para chequear el dominio ---
SEMIENVERGADURA = 1.68
LARGO = 1.79
# Distancias minimas del avion a las fronteras (m). Criterio ingenieril conservador para fuerzas.
DOMINIO_MIN = {"aguas_arriba": 5.0, "aguas_abajo": 10.0, "lateral": 5.0, "vertical": 5.0}

# --- Malla de pared (para Transition SST: y+ ~ 1) ---
PRIMERA_CAPA_MM = 0.015
CRECIMIENTO = 1.2
N_CAPAS = 30
TAMANO_SUPERFICIE_MM = {"min": 0.5, "max_avion": 4.0, "max_dominio": 600.0}


# =============================================================================
# Chequeo de dominio (python puro)
# =============================================================================
def bbox_step(ruta: Path):
    """Caja contenedora (mm) a partir de los CARTESIAN_POINT del STEP. Aproximada pero suficiente."""
    txt = ruta.read_text(errors="ignore")
    pts = re.findall(r"CARTESIAN_POINT\('[^']*',\(([-\d.eE+, ]+)\)\)", txt)
    xs, ys, zs = [], [], []
    for p in pts:
        v = p.split(",")
        if len(v) == 3:
            x, y, z = (float(t) for t in v)
            xs.append(x); ys.append(y); zs.append(z)
    if not xs:
        raise RuntimeError("no encontre puntos en el STEP: %s" % ruta)
    return (min(xs), max(xs)), (min(ys), max(ys)), (min(zs), max(zs))


def chequear_dominio(ruta: Path) -> bool:
    (x0, x1), (y0, y1), (z0, z1) = (tuple(t / 1000.0 for t in r) for r in bbox_step(ruta))
    vol = (x1 - x0) * (y1 - max(y0, 0.0)) * (z1 - z0)
    print("Dominio (m): x [%.2f, %.2f]  y [%.2f, %.2f]  z [%.2f, %.2f]   ~%.0f m3" % (x0, x1, y0, y1, z0, z1, vol))
    # el avion ocupa x in [0, LARGO], y in [0, SEMIENVERGADURA], z en [-0.08, +0.33]
    d = {
        "aguas_arriba": 0.0 - x0,
        "aguas_abajo": x1 - LARGO,
        "lateral": y1 - SEMIENVERGADURA,
        "vertical": min(z1 - 0.33, -0.08 - z0),
    }
    ok = True
    for k, minimo in DOMINIO_MIN.items():
        estado = "OK " if d[k] >= minimo else "CHICO"
        ok &= d[k] >= minimo
        print("  %-13s %6.2f m   (minimo %.1f m)  %s" % (k, d[k], minimo, estado))
    if not ok:
        print("\n=> El dominio es demasiado chico para confiar en L y D. Armar uno nuevo con al menos:")
        print("   x [%.1f, %.1f]  y [0, %.1f]  z [%.1f, %.1f]  (m, medio modelo)" % (
            -DOMINIO_MIN["aguas_arriba"], LARGO + DOMINIO_MIN["aguas_abajo"],
            SEMIENVERGADURA + DOMINIO_MIN["lateral"],
            -0.08 - DOMINIO_MIN["vertical"], 0.33 + DOMINIO_MIN["vertical"]))
    return ok


# =============================================================================
# Fluent (requiere Ansys + ansys-fluent-core). Comandos segun PyFluent 0.2x; ajustar a la version.
# =============================================================================
def mallar(step: Path, salida: Path, n_proc: int, gui: bool):
    import ansys.fluent.core as pyfluent

    meshing = pyfluent.launch_fluent(mode="meshing", precision="double", processor_count=n_proc,
                                     dimension=3, ui_mode="gui" if gui else "no_gui")
    wf = meshing.workflow
    wf.InitializeWorkflow(WorkflowType="Watertight Geometry")
    t = wf.TaskObject

    t["Import Geometry"].Arguments = {"FileName": str(step), "LengthUnit": "mm"}
    t["Import Geometry"].Execute()

    # Tamano de superficie. El ala necesita ~4 mm; el borde de fuga de 2 mm, al menos 3-4 celdas en el espesor.
    t["Generate the Surface Mesh"].Arguments = {"CFDSurfaceMeshControls": {
        "MinSize": TAMANO_SUPERFICIE_MM["min"], "MaxSize": TAMANO_SUPERFICIE_MM["max_dominio"],
        "GrowthRate": 1.2, "SizeFunctions": "Curvature", "CurvatureNormalAngle": 12}}
    t["Generate the Surface Mesh"].Execute()

    t["Describe Geometry"].UpdateChildTasks(SetupTypeChanged=False)
    t["Describe Geometry"].Arguments = {"SetupType": "The geometry consists of only fluid regions with no voids"}
    t["Describe Geometry"].UpdateChildTasks(SetupTypeChanged=True)
    t["Describe Geometry"].Execute()
    t["Update Boundaries"].Execute()
    t["Update Regions"].Execute()

    # Capas limite sobre el avion (zona 'plane'): y+ ~ 1.
    t["Add Boundary Layers"].AddChildToTask()
    t["Add Boundary Layers"].Arguments = {
        "BLControlName": "bl-avion", "OffsetMethodType": "uniform", "NumberOfLayers": N_CAPAS,
        "FirstHeight": PRIMERA_CAPA_MM, "GrowthRate": CRECIMIENTO, "FaceScope": {"GrowthMethod": "uniform"}}
    t["Add Boundary Layers"].InsertCompoundChildTask()
    t["add-boundary-layers-child-1"].Arguments = {
        "BLControlName": "bl-avion", "FaceScope": {"GrowthMethod": "uniform"}, "ZoneSelectionList": ["plane"]}
    t["add-boundary-layers-child-1"].Execute()

    t["Generate the Volume Mesh"].Arguments = {"VolumeFill": "poly-hexcore", "VolumeFillControls": {"GrowthRate": 1.2}}
    t["Generate the Volume Mesh"].Execute()

    salida.mkdir(parents=True, exist_ok=True)
    meshing.tui.file.write_mesh(str(salida / "malla.msh.h5"))
    solver = meshing.switch_to_solver()
    return solver


def configurar_y_resolver(solver, alpha_deg: float, iteraciones: int, salida: Path) -> dict:
    a = math.radians(alpha_deg)
    ca, sa = math.cos(a), math.sin(a)
    st = solver.settings

    st.setup.general.solver.type = "pressure-based"
    st.setup.general.solver.time = "steady"
    st.setup.models.energy.enabled = False
    st.setup.models.viscous.model = "transition-sst"
    st.setup.materials.fluid["air"].density.value = RHO
    st.setup.materials.fluid["air"].viscosity.value = MU

    inlet = st.setup.boundary_conditions.velocity_inlet["inlet"]
    inlet.momentum.velocity_specification_method = "Magnitude and Direction"
    inlet.momentum.velocity.value = V
    inlet.momentum.flow_direction[0].value = ca
    inlet.momentum.flow_direction[1].value = 0.0
    inlet.momentum.flow_direction[2].value = sa      # viento hacia atras y hacia arriba: alpha > 0
    inlet.turbulence.turbulent_intensity = TURB_INTENSIDAD / 100.0
    inlet.turbulence.turbulent_viscosity_ratio = VISC_RATIO

    # Valores de referencia (medio modelo)
    ref = st.setup.reference_values
    ref.area = S_REF_COMPLETA / 2.0
    ref.length = C_REF
    ref.density = RHO
    ref.velocity = V

    # Reportes en ejes del VIENTO
    rd = st.solution.report_definitions
    rd.drag["drag"] = {"zones": ["plane"], "force_vector": [ca, 0.0, sa]}
    rd.lift["lift"] = {"zones": ["plane"], "force_vector": [-sa, 0.0, ca]}

    st.solution.initialization.hybrid_initialize()
    st.solution.run_calculation.iterate(iter_count=iteraciones)

    L_medio = solver.settings.solution.report_definitions.lift["lift"].compute()  # puede variar segun version
    D_medio = solver.settings.solution.report_definitions.drag["drag"].compute()
    L, D = 2.0 * float(L_medio), 2.0 * float(D_medio)       # medio modelo -> avion completo
    q = 0.5 * RHO * V * V
    res = {"alpha_deg": alpha_deg, "L_N": L, "D_N": D, "CL": L / (q * S_REF_COMPLETA),
           "CD": D / (q * S_REF_COMPLETA), "L_sobre_D": L / D}
    salida.mkdir(parents=True, exist_ok=True)
    solver.tui.file.write_case_data(str(salida / ("caso_alpha_%.2f.cas.h5" % alpha_deg)))
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--step", type=Path, default=STEP_POR_DEFECTO)
    ap.add_argument("--alpha", type=float, nargs="+", default=[1.21])
    ap.add_argument("--iteraciones", type=int, default=1500)
    ap.add_argument("--procesos", type=int, default=8)
    ap.add_argument("--solo-chequeo", action="store_true", help="solo revisa el dominio del STEP (no usa Ansys)")
    ap.add_argument("--sin-malla", action="store_true", help="reusa resultados/cfd_run/malla.msh.h5")
    ap.add_argument("--gui", action="store_true", help="abre Fluent con ventana")
    args = ap.parse_args()

    ok = chequear_dominio(args.step)
    if args.solo_chequeo:
        sys.exit(0 if ok else 1)
    if not ok:
        print("\nSigo igual porque no pasaste --solo-chequeo, pero los resultados NO son confiables.\n")

    if args.sin_malla:
        import ansys.fluent.core as pyfluent
        solver = pyfluent.launch_fluent(mode="solver", precision="double", processor_count=args.procesos,
                                        dimension=3, ui_mode="gui" if args.gui else "no_gui")
        solver.tui.file.read_mesh(str(SALIDA / "malla.msh.h5"))
    else:
        solver = mallar(args.step, SALIDA, args.procesos, args.gui)

    resultados = []
    for a in args.alpha:
        r = configurar_y_resolver(solver, a, args.iteraciones, SALIDA)
        resultados.append(r)
        print("alpha %.2f  L %.2f N  D %.2f N  CL %.4f  CD %.5f  L/D %.2f" % (
            a, r["L_N"], r["D_N"], r["CL"], r["CD"], r["L_sobre_D"]))
    (SALIDA / "resultados.json").write_text(json.dumps(resultados, indent=2), encoding="utf-8")
    solver.exit()


if __name__ == "__main__":
    main()
