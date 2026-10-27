"""
Malla el dominio fluido (STEP con el avion como cavidad, medio modelo) en Fluent Meshing, via PyFluent.

Pensado para Fluent 2024 R1 (24.1): PyFluent >= 0.30 NO lo soporta, hay que usar 0.27. Entorno aparte:
    py -3.13 -m venv C:\\Users\\felip\\venv_pyfluent
    C:\\Users\\felip\\venv_pyfluent\\Scripts\\python.exe -m pip install ansys-fluent-core==0.27.0

Uso (desde la raiz del repo):
    C:\\Users\\felip\\venv_pyfluent\\Scripts\\python.exe -u herramientas\\mallar_fluent.py
    ... --step encl_red_v2.step --procesos 8 --hasta superficie     # para mirar la malla de superficie sola
    ... --capas 24 --crecimiento 1.2 --primera-capa 0.025 --tam-avion 8 --tam-min 1.0

El STEP no trae nombres de caras: sale una sola zona. Se separa por angulo (45 grados: las aristas de la caja
son de 90, el avion es suave) y cada zona se clasifica por su caja contenedora:
    x = x_min -> inlet      x = x_max -> outlet      y = 0 -> symmetry      y = y_max, z = +-z_max -> walls
    todo lo demas (el avion) -> plane
Las tapas 'walls' quedan como symmetry (deslizamiento libre), no como pared no-slip.

Salidas en resultados/cfd_run/: malla_<etiqueta>.msh.h5 y malla_<etiqueta>.json (celdas, capas, parametros).
"""
from __future__ import annotations

import argparse
import atexit
import itertools
import json
import re
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "resultados" / "cfd_run"
# Ruta SIN espacios para los transcripts de TUI (el TUI parte los argumentos por espacios).
TMP = Path("C:/Users/felip/AppData/Local/Temp")
TOL = 1.0  # mm
T0 = time.time()
_CONTADOR = itertools.count()


def _cerrar(m):
    for fn in (m.exit, m.force_exit):  # exit() no siempre mata fluent.exe si el script fallo a medias
        try:
            fn()
        except Exception:  # noqa: BLE001
            pass


def log(*a):
    print("[%6.1fs]" % (time.time() - T0), *a, flush=True)


def tui_texto(m, tui_fn, *args, espera=0.0):
    """Corre un comando TUI y devuelve lo que imprimio (via transcript)."""
    # un archivo nuevo por llamada: si existe, Fluent pregunta si sobrescribe y el comando siguiente se pierde
    tr = TMP / ("tr_mallar_%d_%d.txt" % (int(T0), next(_CONTADOR)))
    m.tui.file.start_transcript(tr.as_posix())
    try:
        tui_fn(*args)
        if espera:  # algunos comandos (objects.list) imprimen despues de volver
            time.sleep(espera)
    finally:
        m.tui.file.stop_transcript()
    txt = tr.read_text(errors="ignore") if tr.exists() else ""
    for _ in range(20 if espera else 0):  # Fluent a veces vuelca el transcript despues de cerrarlo
        if txt.strip():
            break
        time.sleep(0.25)
        txt = tr.read_text(errors="ignore") if tr.exists() else ""
    return txt


def lista_zonas(m):
    """[(id, nombre, n_caras)] de las zonas de cara."""
    txt = tui_texto(m, m.tui.boundary.manage.list)
    zonas = []
    for linea in txt.splitlines():
        r = re.match(r"\s*(\d+)\s+(\S+)\s+(\S+)\s+(\d+)\s+\d+\s+\d+\s*$", linea)
        if r:
            zonas.append((int(r.group(1)), r.group(2), int(r.group(4))))
    return zonas


def caja_zona(m, zid):
    txt = tui_texto(m, m.tui.boundary.compute_bounding_box, [str(zid)])
    r = re.search(r"bounding box dimensions \(\(([^)]*)\) \(([^)]*)\)\)", txt)
    lo = [float(v) for v in r.group(1).split()]
    hi = [float(v) for v in r.group(2).split()]
    return lo, hi


def clasificar(m, zona_inicial, ignorar=()):
    """Separa por angulo y devuelve ({rol: [ids]}, dominio); rol in inlet/outlet/symmetry/walls/plane.
    `ignorar`: ids de zonas que ya existian y no hay que tocar (p. ej. las de la geometria cuando se clasifica la malla)."""
    m.tui.boundary.separate.sep_face_zone_by_angle([zona_inicial], 45)
    zonas = [z for z in lista_zonas(m) if z[0] not in ignorar]
    log("zonas tras separar por angulo:", len(zonas))
    cajas = {zid: caja_zona(m, zid) for zid, _, _ in zonas}
    xmin = min(c[0][0] for c in cajas.values())
    xmax = max(c[1][0] for c in cajas.values())
    ymax = max(c[1][1] for c in cajas.values())
    zmax = max(c[1][2] for c in cajas.values())
    zmin = min(c[0][2] for c in cajas.values())
    log("dominio (mm): x [%g, %g]  y [0, %g]  z [%g, %g]" % (xmin, xmax, ymax, zmin, zmax))

    dom = (xmin, xmax, ymax, zmin, zmax)
    roles = {"inlet": [], "outlet": [], "symmetry": [], "walls": [], "plane": []}
    for zid, nombre, n in zonas:
        roles[rol_de_caja(*cajas[zid], dom)].append(zid)
    for k, v in roles.items():
        caras = sum(n for zid, _, n in zonas if zid in v)
        log("  %-9s %3d zonas  %6d caras" % (k, len(v), caras))
    for k in ("inlet", "outlet", "symmetry", "walls", "plane"):
        if not roles[k]:
            raise RuntimeError("no encontre ninguna zona para '%s'" % k)
    return roles, dom


def rol_de_caja(lo, hi, dom):
    xmin, xmax, ymax, zmin, zmax = dom
    plana = lambda i, v: abs(lo[i] - v) < TOL and abs(hi[i] - v) < TOL  # noqa: E731
    if plana(0, xmin):
        return "inlet"
    if plana(0, xmax):
        return "outlet"
    if plana(1, 0.0):
        return "symmetry"
    if plana(1, ymax) or plana(2, zmax) or plana(2, zmin):
        return "walls"
    return "plane"


def nombrar(m, roles, dom, prefijo="", ignorar=()):
    """Une las zonas de cada rol en una sola y le pone el nombre del rol (con `prefijo`)."""
    propias = lambda: [z for z in lista_zonas(m) if z[0] not in ignorar]  # noqa: E731
    antes = propias()
    caras_rol = {rol: sum(n for zid, _, n in antes if zid in ids) for rol, ids in roles.items()}
    for rol, ids in roles.items():
        if len(ids) > 1:
            m.tui.boundary.manage.merge([str(i) for i in ids])
    for zid, _, n in propias():
        lo, hi = caja_zona(m, zid)
        rol = rol_de_caja(lo, hi, dom)
        if rol == "plane":  # las zonas unidas ya no son planas (tapas, avion): se distinguen por cantidad de caras
            rol = next(r for r in ("walls", "plane") if caras_rol[r] == n)
        m.tui.boundary.manage.name(str(zid), prefijo + rol)
    zonas = propias()
    log("zonas renombradas:", zonas)
    nombres = sorted(n for _, n, _ in zonas)
    if nombres != sorted(prefijo + r for r in roles):
        raise RuntimeError("tras unir esperaba %s y hay %s" % (sorted(roles), nombres))
    return zonas


def guardar(m, ruta: Path):
    """write-mesh del TUI: la ruta lleva comillas porque el repo tiene espacios."""
    m.tui.file.write_mesh('"%s"' % ruta.as_posix())
    log("guardado", ruta)


def informe(m, args):
    """Celdas, calidad y espesor de capas del volumen; deja todo en malla_<etiqueta>.json."""
    calidad = tui_texto(m, m.tui.mesh.check_quality, espera=1.0)
    zonas = tui_texto(m, m.tui.mesh.manage.list, espera=1.0)
    print(calidad[-600:], zonas[-900:], flush=True)
    num = lambda pat, txt: float(re.findall(pat, txt)[-1]) if re.findall(pat, txt) else None  # noqa: E731
    f = re.findall(r"fluid\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", zonas)
    tipos = dict(zip(("tet", "hex", "pyramid", "wedge", "poly", "poly_prism", "hex_prism"), map(int, f[-1][1:]))) if f else {}
    datos = {"parametros": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
             "celdas": int(f[-1][0]) if f else None, "tipos": tipos,
             "ortogonalidad_minima": num(r"Minimum Orthogonal Quality =\s*([\d.eE+-]+)", calidad),
             "razon_aspecto_maxima": num(r"Maximum Aspect Ratio =\s*([\d.eE+-]+)", calidad),
             "tiempo_s": round(time.time() - T0, 1)}
    (SALIDA / ("malla_%s.json" % args.etiqueta)).write_text(json.dumps(datos, indent=2), encoding="utf-8")
    log("informe:", {k: v for k, v in datos.items() if k != "parametros"})


def agregar_estela(m, t, args, geom_ids):
    """EXPERIMENTAL / SIN PROBAR. Importa una caja como cuerpo de influencia y le pone tamano local de celda.
    Si algo falla, avisa y sigue sin refinar (la malla sale igual). Devuelve los ids de zona del cuerpo (hay que ignorarlos)."""
    antes = {z[0] for z in lista_zonas(m)}
    try:
        t["Import Geometry"].InsertNextTask(CommandName="ImportBodyOfInfluenceGeometry")
        ib = t["Import Body of Influence Geometry"]
        for clave in ("GeometryFileName", "FileName"):
            try:
                ib.Arguments = {"Type": "CAD", clave: str(args.estela), "LengthUnit": "mm"}
                ib.Execute()
                break
            except Exception as e:  # noqa: BLE001
                log("BOI con %s fallo: %r" % (clave, e))
        nuevas = [z for z in lista_zonas(m) if z[0] not in antes]
        if not nuevas:
            raise RuntimeError("la caja de la estela no agrego zonas")
        objeto = nuevas[0][1].rsplit(":", 1)[0]
        m.tui.objects.labels.create_label_per_zone(objeto)
        ls = t["Add Local Sizing"]
        ls.Arguments = {"AddChild": "yes", "BOIControlName": "estela", "BOIExecution": "Body Of Influence",
                        "BOIZoneorLabel": "label", "BOIFaceLabelList": [z[1] for z in nuevas],
                        "BOISize": args.tam_estela, "BOIGrowthRate": 1.2}
        ls.AddChildToTask()
        ls.Execute()
        log("estela: cuerpo de influencia %s con celda %g mm (zonas %s)" % (objeto, args.tam_estela, [z[1] for z in nuevas]))
        return {z[0] for z in nuevas}
    except Exception as e:  # noqa: BLE001
        log("AVISO: no pude armar la estela (%r). La malla sale SIN refinamiento de estela." % e)
        return set()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--step", type=Path, default=RAIZ / "encl_red_v2.step")
    ap.add_argument("--procesos", type=int, default=8)
    ap.add_argument("--primera-capa", type=float, default=0.025, help="mm; y+ ~ 0.8 en el centro de la primera celda (u_tau ~ 1.05 m/s a 22.2 m/s, Cf ~ 0.0045)")
    ap.add_argument("--crecimiento", type=float, default=1.2)
    ap.add_argument("--capas", type=int, default=24, help="24 capas x 1.2 desde 0.025 mm = 9.8 mm (capa limite turbulenta en la raiz ~ 9-11 mm)")
    ap.add_argument("--tam-avion", type=float, default=8.0, help="mm, tamano maximo de superficie sobre el avion")
    ap.add_argument("--tam-min", type=float, default=1.0, help="mm, minimo (borde de fuga de 2 mm)")
    ap.add_argument("--tam-max", type=float, default=600.0, help="mm, maximo del dominio")
    ap.add_argument("--estela", type=Path, default=None,
                    help="EXPERIMENTAL: STEP de una caja (zona_estela.step) usada como cuerpo de influencia para refinar la estela")
    ap.add_argument("--tam-estela", type=float, default=200.0, help="mm, tamano de celda dentro de la caja --estela")
    ap.add_argument("--hasta", choices=["zonas", "superficie", "capas", "volumen"], default="volumen")
    ap.add_argument("--etiqueta", default="v2")
    ap.add_argument("--gui", action="store_true")
    args = ap.parse_args()

    import ansys.fluent.core as pyfluent

    SALIDA.mkdir(parents=True, exist_ok=True)
    m = pyfluent.launch_fluent(product_version="24.1.0", mode="meshing", precision="double",
                               processor_count=args.procesos, dimension=3, start_timeout=240,
                               ui_mode="gui" if args.gui else "no_gui", cwd=str(SALIDA))
    atexit.register(lambda: _cerrar(m))  # si el script falla, Fluent queda huerfano (mpiexec/fluent.exe)
    log("Fluent", m.get_fluent_version())
    w = m.workflow
    w.InitializeWorkflow(WorkflowType="Watertight Geometry")
    t = w.TaskObject

    t["Import Geometry"].Arguments = {"FileName": str(args.step), "LengthUnit": "mm", "FileFormat": "CAD"}
    t["Import Geometry"].Execute()
    log("STEP importado")

    zonas = lista_zonas(m)
    if len(zonas) != 1:
        raise RuntimeError("esperaba 1 zona tras importar, hay %d" % len(zonas))
    roles, dom = clasificar(m, zonas[0][1])
    geom_ids = {z[0] for z in nombrar(m, roles, dom)}
    log("zonas clasificadas y nombradas")
    if args.hasta == "zonas":
        m.exit()
        return

    if args.estela:
        geom_ids |= agregar_estela(m, t, args, geom_ids)

    objeto = "origin-avion-optimizado--v_tail--body16"
    m.tui.objects.labels.create_label_per_zone(objeto)
    log("etiquetas por zona creadas")

    # --- tamanos de superficie sobre el avion ---
    ls = t["Add Local Sizing"]
    ls.Arguments = {"AddChild": "yes", "BOIControlName": "avion_tam", "BOIExecution": "Face Size",
                    "BOIZoneorLabel": "label", "BOIFaceLabelList": ["plane"],
                    "BOISize": args.tam_avion, "BOIGrowthRate": 1.2}
    ls.AddChildToTask()
    ls.Execute()
    ls.Arguments = {"AddChild": "yes", "BOIControlName": "avion_curv", "BOIExecution": "Curvature",
                    "BOIZoneorLabel": "label", "BOIFaceLabelList": ["plane"],
                    "BOIMinSize": args.tam_min, "BOIMaxSize": args.tam_avion,
                    "BOICurvatureNormalAngle": 12, "BOIGrowthRate": 1.2}
    ls.AddChildToTask()
    ls.Execute()
    log("tamanos locales creados")

    sm = t["Generate the Surface Mesh"]
    sm.Arguments = {"CFDSurfaceMeshControls": {"MinSize": args.tam_min, "MaxSize": args.tam_max,
                                               "GrowthRate": 1.2, "SizeFunctions": "Curvature",
                                               "CurvatureNormalAngle": 18}}
    sm.Execute()
    log("malla de superficie generada")
    # La malla de superficie sale como UNA sola zona que hereda todas las etiquetas: sin separarla, las fronteras
    # (entrada, salida, simetria, tapas) quedan como pared y las capas de inflacion crecen sobre todo el recinto.
    propias = [z for z in lista_zonas(m) if z[0] not in geom_ids]
    objeto_malla = propias[0][1].rsplit(":", 1)[0]  # la zona se llama '<objeto>:1'
    roles_m, dom_m = clasificar(m, propias[0][1], ignorar=geom_ids)
    nombrar(m, roles_m, dom_m, prefijo="m_", ignorar=geom_ids)
    m.tui.objects.labels.create_label_per_zone(objeto_malla)
    log("zonas de la malla separadas y etiquetadas (m_*) en", objeto_malla)
    print(tui_texto(m, m.tui.boundary.manage.list), flush=True)
    if args.hasta == "zonas":
        m.exit()
        return
    if args.hasta == "superficie":
        guardar(m, SALIDA / ("superficie_%s.msh.h5" % args.etiqueta))
        m.exit()
        return

    # --- fluido, tipos de frontera, regiones ---
    dg = t["Describe Geometry"]
    dg.UpdateChildTasks(SetupTypeChanged=False)
    dg.Arguments = {"SetupType": "The geometry consists of only fluid regions with no voids"}
    dg.UpdateChildTasks(SetupTypeChanged=True)
    dg.Execute()
    log("geometria descrita")

    ub = t["Update Boundaries"]
    etiquetas = ["m_inlet", "m_outlet", "m_symmetry", "m_walls", "m_plane"]
    ub.Arguments = {"BoundaryLabelList": etiquetas[:4],
                    "BoundaryLabelTypeList": ["velocity-inlet", "pressure-outlet", "symmetry", "symmetry"],
                    "OldBoundaryLabelList": etiquetas[:4], "OldBoundaryLabelTypeList": ["wall"] * 4}
    ub.Execute()
    t["Update Regions"].Execute()
    log("fronteras y regiones listas")

    # --- capas de inflacion sobre el avion (y+ ~ 1) ---
    # Alcance por etiqueta (m_plane, creada sobre la zona de MALLA). RegionScope/RegionsType se dejan por defecto:
    # tocarlos deja el alcance vacio. Con 'only-walls' tambien crecerian capas en las tapas (m_walls queda como pared).
    bl = t["Add Boundary Layers"]
    bl.Arguments = {"BLControlName": "capas_avion", "OffsetMethodType": "uniform"}
    bl.AddChildToTask()
    bl.InsertCompoundChildTask()
    t["capas_avion"].Arguments = {
        "BLControlName": "capas_avion", "OffsetMethodType": "uniform",
        "NumberOfLayers": args.capas, "FirstHeight": args.primera_capa, "Rate": args.crecimiento,
        "FaceScope": {"GrowOn": "selected-zones"}, "ZoneSelectionList": ["m_plane"]}
    t["capas_avion"].Execute()
    log("capas creadas:", t["capas_avion"].Arguments())
    if args.hasta == "capas":
        m.exit()
        return

    vm = t["Generate the Volume Mesh"]
    vm.Arguments = {"VolumeFill": "poly-hexcore",
                    "VolumeFillControls": {"GrowthRate": 1.2, "HexMaxCellLength": args.tam_max}}
    vm.Execute()
    log("malla de volumen generada")
    # Update Boundaries no tipa las tapas del recinto: quedan como pared (no-slip) salvo que se corrija aca.
    m.tui.boundary.manage.type(["m_walls"], "symmetry")
    guardar(m, SALIDA / ("malla_%s.msh.h5" % args.etiqueta))
    informe(m, args)
    m.exit()


if __name__ == "__main__":
    main()
