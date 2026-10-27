"""
Pipeline de CFD con PyFluent: chequeo del dominio -> malla -> solver -> L y D en ejes del viento.

BORRADOR SIN PROBAR. Se escribio sin poder ejecutar Ansys, asi que la primera corrida va a pedir
ajustes de nombres de comandos segun la version de Ansys/PyFluent (se corrige iterando con el error).
Lo unico verificado es `--solo-chequeo` y `--revisar-set` (no necesitan Ansys).

Uso (PowerShell, desde la raiz del repo):
    pip install ansys-fluent-core
    python herramientas\\fluent_pipeline.py --solo-chequeo                 # revisa el dominio del STEP
    python herramientas\\fluent_pipeline.py --revisar-set Encl_test_files\\dp0\\FFF\\Fluent\\FFF.set   # revisa un caso a mano
    python herramientas\\fluent_pipeline.py --alpha 1.21                   # malla + calculo
    python herramientas\\fluent_pipeline.py --alpha 0 1.21 4 --sin-malla   # barrido, reusa la malla
    python herramientas\\fluent_pipeline.py --alpha 1.21 --sin-malla --modelo k-omega   # mismo caso con SST puro

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

# --- Avion (m) para chequear el dominio (medido en encl_red.step: x [0, 1.849], y [0, 1.674], z [-0.073, 0.317]) ---
SEMIENVERGADURA = 1.674
LARGO = 1.849
Z_AVION = (-0.073, 0.317)
# Distancias minimas del avion a las fronteras (m). Criterio ingenieril conservador para fuerzas.
DOMINIO_MIN = {"aguas_arriba": 5.0, "aguas_abajo": 10.0, "lateral": 5.0, "vertical": 5.0}

# --- Malla de pared (para Transition SST: y+ ~ 1) ---
# Dos perfiles de malla. "rapida" = primera prueba del pipeline (~4-6 M celdas); "fina" = la de verdad (~10-15 M).
PERFILES_MALLA = {
    "rapida": {"primera_capa_mm": 0.015, "crecimiento": 1.2, "n_capas": 25, "avion_mm": 8.0, "min_mm": 1.0, "max_mm": 600.0},
    "fina":   {"primera_capa_mm": 0.015, "crecimiento": 1.2, "n_capas": 30, "avion_mm": 4.0, "min_mm": 0.5, "max_mm": 600.0},
}


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
    # el avion ocupa x in [0, LARGO], y in [0, SEMIENVERGADURA], z in Z_AVION
    d = {
        "aguas_arriba": 0.0 - x0,
        "aguas_abajo": x1 - LARGO,
        "lateral": y1 - SEMIENVERGADURA,
        "vertical": min(z1 - Z_AVION[1], Z_AVION[0] - z0),
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
            Z_AVION[0] - DOMINIO_MIN["vertical"], Z_AVION[1] + DOMINIO_MIN["vertical"]))
    return ok


# =============================================================================
# Revision de un caso armado a mano (python puro): lee el .set que exporta Fluent
# (File > Export > Case Settings, o el FFF.set de Workbench) y marca lo que no cuadra.
# =============================================================================
def revisar_set(ruta: Path) -> bool:
    t = ruta.read_text(errors="ignore")
    problemas, avisos = [], []

    def num(patron):
        m = re.search(patron, t, re.S)
        return float(m.group(1)) if m else None

    # Reportes de fuerza sobre el avion: la sustentacion tiene que ir en z (y es la envergadura).
    for m in re.finditer(r'\(report-definition (lift|drag) \(force-vector ([-\d.eE+]+) ([-\d.eE+]+) ([-\d.eE+]+)\)'
                         r'.{0,400}?name "([^"]+)"', t, re.S):
        tipo, fx, fy, fz, nombre = m.group(1), float(m.group(2)), float(m.group(3)), float(m.group(4)), m.group(5)
        print("  reporte %-14s %-5s vector (%.4f, %.4f, %.4f)" % (nombre, tipo, fx, fy, fz))
        if abs(fy) > 0.5:
            problemas.append("'%s' (%s) apunta en y: eso es fuerza LATERAL (y = envergadura). Lift = (-sin a, 0, cos a), "
                             "drag = (cos a, 0, sin a)." % (nombre, tipo))
        elif tipo == "lift" and abs(fz) < 0.5:
            problemas.append("'%s' (lift) no apunta en z." % nombre)

    # Paredes del dominio: shear-bc 0 = no-slip (tunel de viento con capa limite propia).
    for m in re.finditer(r'\(bc \((\S+) wall mixture\) \(\s*\(motion-bc \. \d+\)\s*\(shear-bc \. (\d+)\)', t):
        zona, shear = m.group(1), int(m.group(2))
        if zona != "plane" and shear == 0:
            problemas.append("la zona '%s' es pared NO-SLIP: el dominio se vuelve un tunel. Cambiarla a symmetry "
                             "(o pressure-far-field)." % zona)

    if re.search(r'\(rp-trans-sst\? #f\)', t):
        avisos.append("sin modelo de transicion (SST totalmente turbulento): da mas drag de perfil que NeuralFoil.")
    ti = num(r'\(turb-intensity \. ([\d.eE+-]+)\)')
    if ti is not None and ti > 0.005:
        avisos.append("intensidad de turbulencia de entrada %.1f %% (aire libre ~0.1 %%)." % (100 * ti))
    if re.search(r'\(velocity-spec \. 0\)', t):
        avisos.append("velocidad de entrada 'normal a la frontera': alpha = 0 (para otro alpha usar Magnitude and Direction).")
    for clave, esperado, patron in (("velocidad", V, r'velocity-inlet mixture\) \(.{0,200}?\(vmag \(constant \. ([\d.eE+-]+)\)'),
                                    ("densidad", RHO, r'\(density \(constant \. (1\.[\d]+)\)'),
                                    ("viscosidad", MU, r'\(viscosity \(constant \. ([\d.eE+-]+)\)'),
                                    ("area de referencia", S_REF_COMPLETA / 2.0, r'\(reference-area ([\d.eE+-]+)\)'),
                                    ("velocidad de referencia", V, r'\(reference-velocity ([\d.eE+-]+)\)')):
        v = num(patron)
        if v is not None and abs(v / esperado - 1.0) > 0.005:
            avisos.append("%s = %.5g (caso del modelo: %.5g)." % (clave, v, esperado))

    for p in problemas:
        print("  PROBLEMA: " + p)
    for a in avisos:
        print("  aviso   : " + a)
    if not problemas and not avisos:
        print("  sin observaciones.")
    return not problemas


# =============================================================================
# Fluent (requiere Ansys + ansys-fluent-core). Comandos segun PyFluent 0.2x; ajustar a la version.
# =============================================================================
def mallar(step: Path, salida: Path, n_proc: int, gui: bool, perfil: dict):
    import ansys.fluent.core as pyfluent

    meshing = pyfluent.launch_fluent(mode="meshing", precision="double", processor_count=n_proc,
                                     dimension=3, ui_mode="gui" if gui else "no_gui")
    wf = meshing.workflow
    wf.InitializeWorkflow(WorkflowType="Watertight Geometry")
    t = wf.TaskObject

    t["Import Geometry"].Arguments = {"FileName": str(step), "LengthUnit": "mm"}
    t["Import Geometry"].Execute()

    # Tamano de superficie. El ala necesita ~4 mm; el borde de fuga de 2 mm, al menos 3-4 celdas en el espesor.
    # Tamano local sobre el avion (zona 'plane'). SIN PROBAR: depende de que el STEP conserve ese nombre como label.
    try:
        t["Add Local Sizing"].AddChildToTask()
        t["Add Local Sizing"].Arguments = {"AddChild": "yes", "BOIControlName": "avion", "BOIExecution": "Face Size",
                                           "BOIFaceLabelList": ["plane"], "BOISize": perfil["avion_mm"], "BOIGrowthRate": 1.2}
        t["Add Local Sizing"].Execute()
    except Exception as e:  # noqa: BLE001
        print("AVISO: no pude crear el tamano local del avion (%s); sigo con el global." % e)

    t["Generate the Surface Mesh"].Arguments = {"CFDSurfaceMeshControls": {
        "MinSize": perfil["min_mm"], "MaxSize": perfil["max_mm"],
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
        "BLControlName": "bl-avion", "OffsetMethodType": "uniform", "NumberOfLayers": perfil["n_capas"],
        "FirstHeight": perfil["primera_capa_mm"], "GrowthRate": perfil["crecimiento"], "FaceScope": {"GrowthMethod": "uniform"}}
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


def configurar_y_resolver(solver, alpha_deg: float, iteraciones: int, salida: Path, modelo: str) -> dict:
    a = math.radians(alpha_deg)
    ca, sa = math.cos(a), math.sin(a)
    st = solver.settings

    st.setup.general.solver.type = "pressure-based"
    st.setup.general.solver.time = "steady"
    st.setup.models.energy.enabled = False
    st.setup.models.viscous.model = modelo     # "transition-sst" o "k-omega" (SST) para comparar
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

    # Las tapas laterales/superior/inferior del dominio salen del STEP como pared no-slip: deslizamiento libre.
    solver.tui.define.boundary_conditions.zone_type("walls", "symmetry")

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
    ap.add_argument("--revisar-set", type=Path, help="revisa un caso armado a mano (.set de Fluent) y sale (no usa Ansys)")
    ap.add_argument("--sin-malla", action="store_true", help="reusa resultados/cfd_run/malla.msh.h5")
    ap.add_argument("--malla", choices=list(PERFILES_MALLA), default="rapida", help="rapida = prueba del pipeline; fina = definitiva")
    ap.add_argument("--modelo", choices=["transition-sst", "k-omega"], default="transition-sst")
    ap.add_argument("--gui", action="store_true", help="abre Fluent con ventana")
    args = ap.parse_args()

    if args.revisar_set:
        print("Caso %s:" % args.revisar_set)
        sys.exit(0 if revisar_set(args.revisar_set) else 1)

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
        solver = mallar(args.step, SALIDA, args.procesos, args.gui, PERFILES_MALLA[args.malla])

    resultados = []
    for a in args.alpha:
        r = configurar_y_resolver(solver, a, args.iteraciones, SALIDA, args.modelo)
        resultados.append(r)
        print("alpha %.2f  L %.2f N  D %.2f N  CL %.4f  CD %.5f  L/D %.2f" % (
            a, r["L_N"], r["D_N"], r["CL"], r["CD"], r["L_sobre_D"]))
    (SALIDA / "resultados.json").write_text(json.dumps(resultados, indent=2), encoding="utf-8")
    solver.exit()


if __name__ == "__main__":
    main()
