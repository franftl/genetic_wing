"""
Barrido de angulo de ataque en Fluent 24.1 (PyFluent 0.27) sobre una malla con capa limite (malla_v5, malla_grande...).

Uso (desde la raiz del repo, con el Python de venv_pyfluent):
    # un modelo, varios angulos (arranque en caliente de uno a otro, orden creciente)
    ...\\python.exe -u herramientas\\correr_cfd_fluent.py --alfas 0 1.21 4 --transicion --etiqueta prueba
    # varios modelos y angulos, en orden de prioridad (lo que se hace de noche)
    ...\\python.exe -u herramientas\\correr_cfd_fluent.py --malla resultados\\cfd_run\\malla_grande.msh.h5 ^
        --plan "transicion:0,4;sst:4;transicion:1.21,8;sst:0,1.21,8" --limite 08:30 --etiqueta noche

Plan = grupos "modelo:alfa,alfa;modelo:alfa". Modelos: sst (k-omega SST totalmente turbulento) o transicion (Transition SST).
Cada grupo relee la malla (arranque limpio) y sus angulos corren en orden creciente con arranque en caliente.

Setup: medio modelo (simetria en y = 0), aire a 1.056 kg/m3 / 1.7433e-5 Pa.s, velocidad 22.22 m/s. Ejes de la malla:
x atras, y derecha, z arriba, por eso el viento va en (cos a, 0, sin a). Fluent reporta la mitad del avion: L y D se
multiplican por 2 y se rotan al viento. Coeficientes con S = 1.2134 m2 (completa) y q = 0.5 rho V^2.

PAREDES DEL RECINTO (--paredes). 'velocidad' (default) cambia m_walls (lateral, arriba, abajo) a velocity-inlet con el MISMO
vector de viento: el flujo libre inclinado entra por todas las tapas. Con 'simetria' las tapas de arriba/abajo obligan al
flujo a quedar horizontal y aplastan la pendiente de CL (la CFD en el recinto chico dio 0.285 x la pendiente del modelo).

CONVERGENCIA. Se itera en bloques (--bloque, 50). Se corta cuando, pasado --iter-min, L y D de los ultimos 3 bloques
varian menos de --tol-conv [%] (default 0.3), o al llegar a --iter-max. El criterio por residuales va apagado (con el
default Fluent corta a las 5-10 iteraciones).

Salida: resultados/cfd_run/noche/<etiqueta>/resultados.csv (una fila por caso, se agrega a medida que termina) y
resultados.json (con la historia de L y D por bloque). Si se vuelve a lanzar con la misma etiqueta, los casos ya hechos
se saltean (--no-retomar para repetirlos). Los casos no convergidos quedan marcados convergio=0: no son resultado.
"""
from __future__ import annotations

import argparse
import atexit
import csv
import json
import math
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "resultados" / "cfd_run"
T0 = time.time()
RHO, MU = 1.056, 1.7433e-5
S_REF = 1.2134174441842038  # m2, superficie alar completa (avion_geometry_cad.json)
MAC = 0.3859155228024745  # m
MODELOS = {"sst": "k-omega", "transicion": "transition-sst"}
COLUMNAS = ["modelo", "paredes", "malla", "alfa_deg", "L_N", "D_N", "CL", "CD", "L_D", "iteraciones", "convergio",
            "var_L_pct", "var_D_pct", "tiempo_s", "s_por_iter", "yplus_media", "yplus_max"]


def log(*a):
    print("[%6.1fs]" % (time.time() - T0), *a, flush=True)


def _valor(r):
    """compute() devuelve [{nombre: [valor, unidad]}] segun la version; se toma el primer numero."""
    while isinstance(r, (list, tuple, dict)):
        r = next(iter(r.values())) if isinstance(r, dict) else r[0]
    return float(r)


def _plan(args):
    """[(modelo, [alfas])] a partir de --plan, o de --alfas/--transicion."""
    if not args.plan:
        return [("transicion" if args.transicion else "sst", sorted(args.alfas))]
    grupos = []
    for g in args.plan.split(";"):
        g = g.strip()
        if not g:
            continue
        nombre, _, al = g.partition(":")
        nombre = nombre.strip().lower()
        if nombre not in MODELOS:
            raise SystemExit("modelo desconocido '%s' (usar sst o transicion)" % nombre)
        grupos.append((nombre, sorted(float(x) for x in al.split(","))))
    return grupos


def _hora_limite(txt):
    if not txt:
        return None
    h, m = map(int, txt.split(":"))
    ahora = time.localtime()
    t = time.mktime(ahora[:3] + (h, m, 0, 0, 0, -1))
    return t if t > time.time() else t + 86400


def _hechos(ruta_csv):
    if not ruta_csv.exists():
        return set()
    with ruta_csv.open(newline="") as f:
        return {(r["modelo"], round(float(r["alfa_deg"]), 3)) for r in csv.DictReader(f) if r["convergio"] in ("0", "1")}


def _yplus(s):
    """Media y maximo de y+ sobre m_plane (None si falla)."""
    try:
        import numpy as np
        r = s.field_data.get_scalar_field_data(field_name="y-plus", surfaces=["m_plane"], node_value=False,
                                               boundary_value=True)
        v = r["m_plane"] if isinstance(r, dict) else r
        a = np.asarray(getattr(v, "scalar_data", v), dtype=float).ravel()
        return float(a.mean()), float(a.max())
    except Exception as e:  # noqa: BLE001
        log("AVISO: no pude leer y+ (%s)" % e)
        return None, None


def _set_viento(zona, ux, uz, ti):
    zona.momentum.velocity_specification_method = "Components"
    zona.momentum.velocity_components.set_state([ux, 0.0, uz])
    zona.turbulence.turbulent_specification = "Intensity and Viscosity Ratio"
    zona.turbulence.turbulent_intensity = ti / 100.0
    try:  # el default de Fluent ya es 10; si el nombre cambia con el modelo no se pierde nada
        zona.turbulence.turbulent_viscosity_ratio = 10.0
    except Exception:  # noqa: BLE001
        pass


def _modelo_de_viscosidad(s, modelo):
    vi = s.setup.models.viscous
    if modelo == "sst":
        vi.model = "k-omega"
        vi.k_omega_model = "sst"
    else:
        try:
            vi.model = "transition-sst"
        except Exception as e:  # noqa: BLE001
            log("vi.model='transition-sst' fallo (%s); pruebo por TUI" % e)
            s.tui.define.models.viscous.transition_sst("yes")
    estado = vi.model.get_state() if hasattr(vi.model, "get_state") else str(vi.model)
    log("modelo de viscosidad en Fluent:", estado)
    esperado = MODELOS[modelo]
    if str(estado) != esperado:
        raise RuntimeError("el modelo quedo en '%s' y se pedia '%s'" % (estado, esperado))


def _paredes_a_velocidad(s):
    try:
        s.tui.define.boundary_conditions.zone_type("m_walls", "velocity-inlet")
    except Exception as e:  # noqa: BLE001
        log("zone_type con string fallo (%s); pruebo con lista" % e)
        s.tui.define.boundary_conditions.zone_type(["m_walls"], "velocity-inlet")
    if "m_walls" not in s.setup.boundary_conditions.velocity_inlet.keys():
        raise RuntimeError("m_walls no quedo como velocity-inlet")
    log("m_walls ahora es velocity-inlet")


def correr_grupo(args, modelo, alfas, hechos, fin, csv_path, json_path, acumulado):
    import ansys.fluent.core as pyfluent

    pendientes = [a for a in alfas if (modelo, round(a, 3)) not in hechos]
    if not pendientes:
        log("grupo %s ya estaba hecho: %s" % (modelo, alfas))
        return True
    s = pyfluent.launch_fluent(product_version="24.1.0", mode="solver", precision="double", dimension=3,
                               processor_count=args.procesos, start_timeout=240, ui_mode="no_gui",
                               cwd=str(args.malla.parent))

    def cerrar():
        for fn in (s.exit, s.force_exit):
            try:
                fn()
            except Exception:  # noqa: BLE001
                pass

    try:
        s.tui.file.read_case('"%s"' % args.malla.as_posix())
        log("[%s] malla leida: %s" % (modelo, args.malla.name))
        _modelo_de_viscosidad(s, modelo)
        aire = s.setup.materials.fluid["air"]
        aire.density.value = RHO
        aire.viscosity.value = MU
        if args.paredes == "velocidad":
            _paredes_a_velocidad(s)
        s.tui.solve.set.discretization_scheme("pressure", "12")  # second order
        s.tui.solve.set.discretization_scheme("mom", "1")
        s.tui.solve.monitors.residual.criterion_type("none")
        rd = s.solution.report_definitions
        bc = s.setup.boundary_conditions
        zonas_viento = [bc.velocity_inlet["m_inlet"]]
        if args.paredes == "velocidad":
            zonas_viento.append(bc.velocity_inlet["m_walls"])

        primera = True
        ultimo_s_it = None
        for alfa in pendientes:
            a = math.radians(alfa)
            ux, uz = args.velocidad * math.cos(a), args.velocidad * math.sin(a)
            for z in zonas_viento:
                _set_viento(z, ux, uz, args.ti)
            rd.drag["cd_x"] = {"zones": ["m_plane"], "force_vector": [math.cos(a), 0.0, math.sin(a)]}
            rd.lift["cl_x"] = {"zones": ["m_plane"], "force_vector": [-math.sin(a), 0.0, math.cos(a)]}
            if primera:
                s.tui.solve.initialize.hyb_initialization()
                primera = False
            it_max = args.iter_max_primera if not acumulado.get(("_ini", modelo)) else args.iter_max
            it_min = args.iter_min_primera if not acumulado.get(("_ini", modelo)) else args.iter_min
            acumulado[("_ini", modelo)] = True
            if fin and ultimo_s_it and time.time() + ultimo_s_it * it_min > fin:
                log("[%s] no alcanza el tiempo para alfa %.2f: se corta aca" % (modelo, alfa))
                return False
            t0 = time.time()
            hist, it, conv = [], 0, False
            while it < it_max:
                s.tui.solve.iterate(args.bloque)
                it += args.bloque
                L = _valor(rd.compute(report_defs=["cl_x"])) * 2.0
                D = _valor(rd.compute(report_defs=["cd_x"])) * 2.0
                hist.append({"it": it, "L_N": L, "D_N": D})
                log("[%s] alfa %.2f it %4d  L %.2f  D %.3f" % (modelo, alfa, it, L, D))
                if it >= it_min and len(hist) >= 3:
                    ult = hist[-3:]
                    vL = (max(h["L_N"] for h in ult) - min(h["L_N"] for h in ult)) / abs(L) * 100
                    vD = (max(h["D_N"] for h in ult) - min(h["D_N"] for h in ult)) / abs(D) * 100
                    if vL < args.tol_conv and vD < args.tol_conv:
                        conv = True
                        break
                if fin and time.time() > fin:
                    log("[%s] se acabo el tiempo en alfa %.2f (it %d)" % (modelo, alfa, it))
                    break
            dt = time.time() - t0
            ultimo_s_it = dt / max(it, 1)
            ult = hist[-3:]
            vL = (max(h["L_N"] for h in ult) - min(h["L_N"] for h in ult)) / abs(L) * 100 if len(ult) > 1 else float("nan")
            vD = (max(h["D_N"] for h in ult) - min(h["D_N"] for h in ult)) / abs(D) * 100 if len(ult) > 1 else float("nan")
            ym, yM = _yplus(s)
            q = 0.5 * RHO * args.velocidad ** 2
            fila = {"modelo": modelo, "paredes": args.paredes, "malla": args.malla.name, "alfa_deg": alfa,
                    "L_N": L, "D_N": D, "CL": L / (q * S_REF), "CD": D / (q * S_REF), "L_D": L / D if D else "",
                    "iteraciones": it, "convergio": int(conv), "var_L_pct": round(vL, 3), "var_D_pct": round(vD, 3),
                    "tiempo_s": round(dt, 1), "s_por_iter": round(ultimo_s_it, 2),
                    "yplus_media": "" if ym is None else round(ym, 3), "yplus_max": "" if yM is None else round(yM, 2)}
            nuevo = not csv_path.exists()
            with csv_path.open("a", newline="") as f:
                w = csv.DictWriter(f, fieldnames=COLUMNAS)
                if nuevo:
                    w.writeheader()
                w.writerow(fila)
            acumulado.setdefault("casos", []).append({**fila, "historia": hist})
            json_path.write_text(json.dumps({"parametros": {k: str(v) for k, v in vars(args).items()},
                                             "resultados": acumulado["casos"]}, indent=2))
            log("[%s] alfa %.2f %s: L %.2f N  D %.3f N  CL %.4f  CD %.5f  L/D %.1f  (y+ medio %s, %.1f s/it)" %
                (modelo, alfa, "CONVERGIO" if conv else "NO convergio", L, D, fila["CL"], fila["CD"],
                 fila["L_D"] or float("nan"), fila["yplus_media"], ultimo_s_it))
            if args.guardar_casos:
                s.tui.file.write_case_data('"%s"' % (json_path.parent / ("%s_a%.2f.cas.h5" % (modelo, alfa))).as_posix())
        return True
    finally:
        cerrar()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--malla", type=Path, default=SALIDA / "malla_v5.msh.h5")
    ap.add_argument("--plan", default=None, help='grupos "modelo:alfa,alfa;modelo:alfa" (modelo = sst | transicion)')
    ap.add_argument("--alfas", type=float, nargs="+", default=[0.0, 1.21, 4.0], help="si no hay --plan")
    ap.add_argument("--transicion", action="store_true", help="con --alfas: Transition SST en vez de k-omega SST")
    ap.add_argument("--paredes", choices=["velocidad", "simetria"], default="velocidad")
    ap.add_argument("--bloque", type=int, default=50)
    ap.add_argument("--iter-min-primera", type=int, default=300)
    ap.add_argument("--iter-max-primera", type=int, default=800)
    ap.add_argument("--iter-min", type=int, default=150)
    ap.add_argument("--iter-max", type=int, default=450)
    ap.add_argument("--tol-conv", type=float, default=0.3, help="variacion maxima de L y D en 3 bloques [%%]")
    ap.add_argument("--limite", default=None, help="hora HH:MM; no empieza un angulo que no alcance a terminar antes")
    ap.add_argument("--velocidad", type=float, default=22.22)
    ap.add_argument("--ti", type=float, default=0.1, help="intensidad de turbulencia de entrada [%%]")
    ap.add_argument("--procesos", type=int, default=8)
    ap.add_argument("--etiqueta", default="noche")
    ap.add_argument("--guardar-casos", action="store_true", help="escribe .cas.h5/.dat.h5 de cada angulo (~1 GB c/u)")
    ap.add_argument("--no-retomar", action="store_true")
    args = ap.parse_args()

    carpeta = SALIDA / "noche" / args.etiqueta
    carpeta.mkdir(parents=True, exist_ok=True)
    csv_path, json_path = carpeta / "resultados.csv", carpeta / "resultados.json"
    hechos = set() if args.no_retomar else _hechos(csv_path)
    acumulado = {}
    if json_path.exists() and not args.no_retomar:
        acumulado["casos"] = json.loads(json_path.read_text()).get("resultados", [])
    fin = _hora_limite(args.limite)
    plan = _plan(args)
    log("plan:", plan, "| paredes:", args.paredes, "| malla:", args.malla.name,
        "| limite:", args.limite or "sin limite", "| ya hechos:", sorted(hechos))
    for modelo, alfas in plan:
        try:
            if not correr_grupo(args, modelo, alfas, hechos, fin, csv_path, json_path, acumulado):
                break
        except Exception as e:  # noqa: BLE001  - un grupo roto no tira abajo toda la noche
            log("ERROR en el grupo %s %s: %r (sigo con el siguiente)" % (modelo, alfas, e))
    log("listo: %s" % csv_path)


if __name__ == "__main__":
    main()
