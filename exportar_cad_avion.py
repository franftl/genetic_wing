"""
Exporta la geometria del avion ganador a un JSON de SECCIONES 3D (en mm) para
reconstruirla en Fusion 360 con `fusion_generar_avion.py`, y deja escrito el
caso de calculo y el drag que predice el modelo (para comparar con Ansys).

Es el mismo esquema que `optimizacion_ala/exportar_cad.py` +
`fusion_generar_ala.py`: ACA se calculan las coordenadas, ALLA solo se dibujan.
La regla es la misma: el CAD tiene que ser exactamente la geometria que evaluo
el solver, no una reconstruccion parecida. Por eso no se re-calcula nada: se le
pide a AeroSandbox el marco de cada seccion de cada ala
(`Wing._compute_frame_of_WingXSec`) y las secciones de cada fuselaje
(`Fuselage.xsecs`), que son los que usa el solver.

USO (desde la raiz del repo, con el kernel/venv que tiene aerosandbox):

    # lo que exporta el notebook (seccion 11) o un ganadores_*.json
    python exportar_cad_avion.py --params evaluacion_bateria_350km/resultados/ganadores_viento-on_bateria-oncorta_pod_continuo.json --topologia pod_boom
    python exportar_cad_avion.py --params avion_design_params_v_tail.json --viento off --bateria off

SALIDA
    avion_geometry_cad.json            lo que lee fusion_generar_avion.py
    cfd_<top>/<top>_caso_cfd.json/.md  condiciones de calculo + drag del modelo
                                       (lo usa `exportar_cfd_avion.py --cd-cfd`
                                       para comparar contra Ansys)

QUE HAY EN EL JSON (todo en MILIMETROS; ejes: x del morro a la cola, y a la
derecha, z hacia arriba)
    alas        una entrada por superficie (ala, estabilizadores, deriva): sus
                secciones con los puntos 3D de cada perfil ya ubicados en el
                espacio. Si `simetrica` es true se exporta SOLO el lado
                derecho (y >= 0) y Fusion lo espeja.
    fuselajes   perfil de revolucion (x, radio) alrededor de un eje paralelo a x
                (para fuselaje, gondola, viga). Fusion lo hace con Revolve.
    meta        superficies de referencia, CG, y el VOLUMEN y AREA MOJADA
                esperados de cada cuerpo, para chequear en Fusion que el CAD
                coincide con lo analizado (Inspect > Properties).

Despues de exportar, correr `verificar_avion` (se llama sola y se imprime): si
algun *_ok da False, el loft de Fusion puede salir retorcido.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

import aerosandbox as asb                                           # noqa: E402
from optimizacion_avion import mision_avion as ma                   # noqa: E402
from optimizacion_avion.geometria_avion import (                    # noqa: E402
    TOPOLOGIAS, clamp_to_bounds_avion, construir_avion,
)
import exportar_cfd_avion as ecfd                                   # noqa: E402

# Puntos por perfil que se emiten al CAD (los perfiles internos tienen mas; para
# un spline de Fusion no hace falta). Mismo valor que el exportador del ala.
N_PUNTOS_CAD = 120

# Espesor de BORDE DE FUGA que se le da al CAD, en mm. Mismas razones que en
# optimizacion_ala/exportar_cad.py (ESPESOR_BORDE_FUGA_MM): el perfil analizado
# cierra en filo exacto, que no se puede fabricar y que Fusion puede interpretar
# como spline cerrada y redondear. 0.0 desactiva la apertura.
# Desde V51 es una restriccion de manufacturabilidad del MODELO
# (optimizacion_avion/manufactura.py): el borde de fuga de 2 mm ya viene en los
# perfiles de `construir_avion`, asi que aca solo se completa lo que falte.
from optimizacion_avion.manufactura import ESPESOR_BORDE_FUGA_M as _TE_M   # noqa: E402
ESPESOR_BORDE_FUGA_MM = 1000.0 * _TE_M


# ----------------------------------------------------------------------
# Copia local de dos funciones de optimizacion_ala/exportar_cad.py (se copian,
# no se importan, para que este exportador no dependa del paquete del ala
# volante, que cambia por su lado).
# ----------------------------------------------------------------------
def _abrir_borde_de_fuga(coords: np.ndarray, espesor_frac: float) -> np.ndarray:
    if espesor_frac <= 0:
        return coords
    out = coords.copy()
    i_le = int(np.argmin(out[:, 0]))
    x = out[:, 0]
    signo = np.where(np.arange(len(out)) <= i_le, 1.0, -1.0)
    out[:, 1] = out[:, 1] + signo * 0.5 * espesor_frac * x
    return out


def _resamplear_perfil(coords: np.ndarray, n: int) -> np.ndarray:
    d = np.sqrt(np.sum(np.diff(coords, axis=0) ** 2, axis=1))
    s = np.concatenate([[0.0], np.cumsum(d)])
    s_new = np.linspace(0.0, s[-1], n)
    return np.stack([np.interp(s_new, s, coords[:, 0]),
                     np.interp(s_new, s, coords[:, 1])], axis=1)


# ----------------------------------------------------------------------
def secciones_de_ala(ala: asb.Wing, n_puntos: int, espesor_te_mm: float) -> list[dict]:
    """Secciones 3D (en mm) de un ala de AeroSandbox, con el marco del solver."""
    out = []
    for i, xsec in enumerate(ala.xsecs):
        xg, yg, zg = ala._compute_frame_of_WingXSec(i)
        xg, yg, zg = np.asarray(xg, float), np.asarray(yg, float), np.asarray(zg, float)
        origen = np.asarray(xsec.xyz_le, dtype=float)

        co = _resamplear_perfil(np.asarray(xsec.airfoil.coordinates, dtype=float), n_puntos)
        # El perfil ya trae el borde de fuga del modelo (2 mm); solo se abre la
        # DIFERENCIA, para no sumarlo dos veces.
        gap = float(np.hypot(co[0, 0] - co[-1, 0], co[0, 1] - co[-1, 1]))
        extra = espesor_te_mm / 1000.0 / max(float(xsec.chord), 1e-6) - gap
        co = _abrir_borde_de_fuga(co, max(extra, 0.0))
        pts = origen[None, :] + xsec.chord * (co[:, 0:1] * xg[None, :] + co[:, 1:2] * zg[None, :])
        out.append({
            "indice": i,
            "perfil": xsec.airfoil.name,
            "cuerda_mm": 1000.0 * float(xsec.chord),
            "torsion_deg": float(xsec.twist),
            "xyz_le_mm": [1000.0 * float(v) for v in origen],
            "normal_seccion": [float(v) for v in yg],
            "puntos_mm": (1000.0 * pts).tolist(),
        })
    return out


def perfil_de_fuselaje(fus: asb.Fuselage) -> dict:
    """Perfil de revolucion (x, r) en mm y la posicion (y, z) del eje."""
    xs = np.array([[float(c) for c in s.xyz_c] for s in fus.xsecs])
    rs = np.array([0.5 * float(s.width) for s in fus.xsecs])   # xsec circular: width = height = 2 r
    return {
        "nombre": fus.name,
        "eje_y_mm": 1000.0 * float(xs[0, 1]),
        "eje_z_mm": 1000.0 * float(xs[0, 2]),
        "eje_constante": bool(np.allclose(xs[:, 1], xs[0, 1]) and np.allclose(xs[:, 2], xs[0, 2])),
        "secciones_x_r_mm": [[1000.0 * float(x), 1000.0 * float(r)] for x, r in zip(xs[:, 0], rs)],
    }


# ----------------------------------------------------------------------
def verificar_avion(alas: list[dict], fuselajes: list[dict]) -> dict:
    """Chequeos baratos que atrapan lo que en Fusion se ve recien cuando el
    loft falla o sale retorcido (ver la docstring de optimizacion_ala.exportar_cad.verificar)."""
    res = {}
    for a in alas:
        secs = a["secciones"]
        plan = 0.0
        for s in secs:
            p = np.array(s["puntos_mm"])
            d = np.abs((p - np.array(s["xyz_le_mm"])) @ np.array(s["normal_seccion"]))
            plan = max(plan, float(d.max()))
        # todas las secciones arrancan del mismo lado del contorno (borde de fuga)
        arr = []
        for s in secs:
            p0 = np.array(s["puntos_mm"])[0] - np.array(s["xyz_le_mm"])
            # el primer punto debe estar "detras" del borde de ataque, del lado de la cuerda
            arr.append(float(np.linalg.norm(p0)) / max(s["cuerda_mm"], 1e-9))
        gaps = [float(np.linalg.norm(np.array(s["puntos_mm"])[0] - np.array(s["puntos_mm"])[-1]))
                for s in secs]
        seps = [float(np.linalg.norm(np.array(b["xyz_le_mm"]) - np.array(c["xyz_le_mm"])))
                for b, c in zip(secs[:-1], secs[1:])]
        res[a["nombre"]] = {
            "n_secciones": len(secs),
            "planaridad_max_mm": plan, "planaridad_ok": plan < 1e-6,
            "orden_consistente_ok": all(v > 0.9 for v in arr),
            "cuerda_min_mm": min(s["cuerda_mm"] for s in secs),
            "cuerda_min_ok": min(s["cuerda_mm"] for s in secs) > 20.0,
            "separacion_min_mm": min(seps) if seps else 0.0,
            "separacion_ok": (min(seps) > 0.1) if seps else True,
            "borde_fuga_min_mm": min(gaps), "borde_fuga_ok": min(gaps) > 1e-3,
        }
    for f in fuselajes:
        x = np.array([p[0] for p in f["secciones_x_r_mm"]])
        r = np.array([p[1] for p in f["secciones_x_r_mm"]])
        res[f["nombre"]] = {
            "n_secciones": len(x),
            "x_creciente_ok": bool(np.all(np.diff(x) > 0)),
            "radio_positivo_ok": bool(np.all(r[1:] > 0) and r[0] >= 0),
            "eje_constante_ok": f["eje_constante"],
        }
    return res


def _todo_ok(ver: dict) -> bool:
    return all(v for d in ver.values() for k, v in d.items() if k.endswith("_ok"))


# ----------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Exporta el avion a secciones 3D para Fusion.")
    ap.add_argument("--params", required=True, type=Path,
                    help="avion_design_params_<top>.json, ganadores_*.json o un dict de parametros")
    ap.add_argument("--topologia", choices=list(TOPOLOGIAS))
    ap.add_argument("--salida", type=Path, default=RAIZ / "avion_geometry_cad.json")
    ap.add_argument("--puntos", type=int, default=N_PUNTOS_CAD, help="puntos por perfil")
    ap.add_argument("--espesor-te-mm", type=float, default=ESPESOR_BORDE_FUGA_MM)
    ap.add_argument("--viento", choices=("on", "off"), default=None)
    ap.add_argument("--bateria", choices=("on", "off"), default=None)
    args = ap.parse_args()

    if args.viento:
        ma.VIENTO_ACTIVO = args.viento == "on"
    if args.bateria:
        ma.BATERIA_ACTIVA = args.bateria == "on"

    params, top = ecfd.cargar_params(args.params, args.topologia)
    params = clamp_to_bounds_avion(params, top)
    avion = construir_avion(params, top)

    alas = []
    for w in avion.wings:
        alas.append({"nombre": w.name, "simetrica": bool(w.symmetric),
                     "secciones": secciones_de_ala(w, args.puntos, args.espesor_te_mm)})
    fuselajes = [perfil_de_fuselaje(f) for f in avion.fuselages]

    ver = verificar_avion(alas, fuselajes)
    ok = _todo_ok(ver)

    # Caso de calculo + volumenes/areas esperados (malla solo para medir).
    cuerpos = ecfd.mallar_cuerpos(avion, ecfd.RESOLUCIONES["media"])
    caso = ecfd.caso_de_calculo(params, top, avion, cuerpos)
    caso["unidades_stl"] = "n/a (solo se exporta el caso; la geometria va en avion_geometry_cad.json)"
    carpeta_cfd = RAIZ / f"cfd_{top}"
    carpeta_cfd.mkdir(exist_ok=True)
    (carpeta_cfd / f"{top}_caso_cfd.json").write_text(
        json.dumps(caso, indent=2, ensure_ascii=False), encoding="utf-8")
    ecfd.escribir_md(caso, carpeta_cfd / f"{top}_caso_cfd.md", "n/a")

    S = float(avion.s_ref)
    meta = {
        "unidades": "mm",
        "generado_por": "exportar_cad_avion.py",
        "topologia": top,
        "nombre_topologia": TOPOLOGIAS[top]["nombre"],
        "envergadura_mm": 1000.0 * float(avion.b_ref),
        "superficie_m2": S,
        "mac_mm": 1000.0 * float(avion.c_ref),
        "cg_x_mm": 1000.0 * float(avion.xyz_ref[0]),
        "xyz_ref_mm": [1000.0 * float(v) for v in avion.xyz_ref],
        "masa_kg": caso["referencias"]["masa_kg"],
        "n_puntos_por_perfil": args.puntos,
        "espesor_borde_fuga_mm": args.espesor_te_mm,
        "_nota_borde_fuga": ("el borde de fuga se abrio a este espesor: el perfil analizado cierra "
                             "en filo exacto, que no es fabricable ni loftea sin ambiguedad."),
        "_nota_simetria": ("las alas con `simetrica: true` se exportan solo del lado derecho (y >= 0); "
                           "el script de Fusion las espeja respecto del plano XZ."),
        "verificacion_en_fusion": {
            g["cuerpo"]: {"volumen_L": g["volumen_L"], "area_mojada_m2": g["area_mojada_m2"]}
            for g in caso["geometria_stl"]
        },
        "_nota_verificacion": ("volumen y area medidos sobre una malla triangular: el CAD debe dar lo "
                               "mismo con ~0.5 % de diferencia (la malla subestima un poco). "
                               "Fusion: Inspect > Properties. Para el ala/estabilizadores simetricos el "
                               "valor es del cuerpo completo (ambas mitades)."),
        "caso_cfd": {
            "condiciones": caso["condiciones"],
            "punto_de_calculo_crucero": caso["punto_de_calculo_crucero"],
            "modelo_AeroBuildup_en_ese_punto": caso["modelo_AeroBuildup_en_ese_punto"],
        },
    }
    salida = {"meta": meta, "alas": alas, "fuselajes": fuselajes}
    args.salida.write_text(json.dumps(salida, indent=1), encoding="utf-8")

    print(f"\nTopologia: {top}   ({TOPOLOGIAS[top]['nombre']})")
    print(f"JSON para Fusion: {args.salida}")
    print(f"Caso de calculo:  {carpeta_cfd / (top + '_caso_cfd.md')}\n")
    for nombre, d in ver.items():
        malos = [k for k, v in d.items() if k.endswith('_ok') and not v]
        print(f"  {nombre:<28} {'OK' if not malos else 'PROBLEMA: ' + ', '.join(malos)}")
    print("\nVerificacion global:", "OK, se puede mandar a Fusion" if ok else "HAY PROBLEMAS: revisar antes de usar")
    print("\nVolumenes/areas esperados para chequear en Fusion:")
    for k, v in meta["verificacion_en_fusion"].items():
        print(f"  {k:<28} {v['volumen_L']:8.2f} L   {v['area_mojada_m2']:.4f} m2")
    m = caso["modelo_AeroBuildup_en_ese_punto"]
    c = caso["condiciones"]
    print(f"\nPara Ansys: V={c['V_m_s']:.2f} m/s  rho={c['rho_kg_m3']:.4f}  Re_MAC={c['Re_MAC']:.2e}  "
          f"alpha={caso['punto_de_calculo_crucero']['alpha_deg']:.2f} deg")
    print(f"Modelo: CL={m['CL']:.4f}  CD={m['CD']:.5f}  D={m['D_N']:.3f} N  L/D={m['L_sobre_D']:.2f}")


if __name__ == "__main__":
    main()
