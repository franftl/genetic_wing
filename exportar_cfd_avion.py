"""
Exporta la geometria del avion ganador a STL para hacer CFD (Fluent, OpenFOAM,
etc.) y deja escrito el caso de calculo y el drag que predice el modelo, para
poder compararlos.

Misma regla que el exportador del ala (optimizacion_ala/exportar_cad.py):
NO se reconstruye nada. Se le pide a AeroSandbox la malla de la MISMA geometria
que evaluo el optimizador (`construir_avion`), asi que el STL es el avion que
se analizo, no uno parecido.

USO (desde la raiz del repo, con el kernel/venv que tiene aerosandbox):

    # Lo que exporto el notebook (seccion 11), o un ganadores_*.json:
    python exportar_cfd_avion.py --params avion_design_params_v_tail.json
    python exportar_cfd_avion.py --params evaluacion_bateria_350km/resultados/ganadores_viento-on_bateria-oncorta_pod_continuo.json --topologia pod_boom

    # Mas fino / en metros / otro escenario:
    python exportar_cfd_avion.py --params X.json --topologia v_tail --resolucion alta --unidades m --viento off --bateria off

    # Despues de correr el CFD, comparar el drag (pasar CD, o la fuerza en N):
    python exportar_cfd_avion.py --params X.json --topologia v_tail --cd-cfd 0.0185 --cl-cfd 0.352
    python exportar_cfd_avion.py --params X.json --topologia v_tail --d-cfd 3.1 --medio-modelo

SALIDA, en `cfd_<topologia>/`:
    <top>_completo.stl         todos los cuerpos, un "solid" por cuerpo (ASCII)
    <top>_<cuerpo>.stl         un STL por cuerpo (binario)
    <top>_caso_cfd.json        condiciones, referencias, alpha de crucero y el
                               drag predicho por el modelo (total y por cuerpo)
    <top>_caso_cfd.md          lo mismo, legible
    comparacion_drag.md        solo si se paso --cd-cfd o --d-cfd

QUE TIENE Y QUE NO TIENE EL STL
  * Cada cuerpo sale como superficie CERRADA (se tapan los extremos abiertos,
    p. ej. el final del fuselaje) y con normales hacia afuera. El script lo
    verifica y lo imprime (aristas abiertas, volumen).
  * Los cuerpos se SUPERPONEN (el ala atraviesa el fuselaje, la cola entra en
    el fuselaje o en la viga): el STL no es una union booleana. Hay que unir en
    el CAD (SpaceClaim/Fusion: Combine) o dejar que lo resuelva el wrapper de
    Fluent Meshing.
  * NO hay helice, ni spinner, ni superficies de control deflectadas, ni
    mecanismos. Los perfiles tienen el espesor de borde de fuga del modelo.
  * Simetria: el avion es simetrico respecto de y = 0. Se puede correr medio
    modelo con plano de simetria (el script lo avisa en la comparacion).

SOBRE COMPARAR EL DRAG (leer antes de sacar conclusiones)
  * El modelo es AeroBuildup (metodo de bajo orden + NeuralFoil con transicion).
    Con Re ~ 5-7e5 hay burbujas laminares y transicion: un CFD totalmente
    turbulento (k-epsilon, k-omega SST sin transicion) suele dar MAS drag de
    perfil. Para comparar lo justo conviene un modelo con transicion
    (k-omega SST con gamma-Re_theta) o, al menos, tener presente ese sesgo.
  * Comparar a igual CL, no a igual alpha: el CFD tiene que sostener el peso
    (CL = W / (q S)). El script informa el alpha del modelo como punto de
    partida; ajustalo hasta que el CL del CFD coincida (con 1-2 corridas
    alcanza) y recien ahi compara CD.
  * El drag del modelo que se reporta es el de AeroBuildup puro, SIN el
    recargo por flap ni el termino de turbulencia del optimizador, que son
    terminos de puntaje y no fisica del flujo medio.
"""
from __future__ import annotations

import argparse
import json
import re
import struct
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

RESOLUCIONES = {"baja": 24, "media": 48, "alta": 96}   # puntos por lado / por perfil


# ======================================================================
# CARGA DE PARAMETROS
# ======================================================================
def _es_params(d) -> bool:
    return isinstance(d, dict) and "envergadura" in d and "chord_1" in d


def cargar_params(ruta: Path, topologia: str | None) -> tuple[dict, str]:
    """Acepta lo que escribe el notebook (seccion 11: `parametros`), un
    `ganadores_*.json` ({topologia: {params, ...}}) o un dict de parametros."""
    d = json.loads(Path(ruta).read_text(encoding="utf-8"))
    top = topologia or (d.get("topologia") if isinstance(d, dict) else None)

    if _es_params(d):
        params = d
    elif isinstance(d, dict) and _es_params(d.get("parametros")):
        params = d["parametros"]
    elif isinstance(d, dict) and _es_params(d.get("params")):
        params = d["params"]
    elif isinstance(d, dict) and top and isinstance(d.get(top), dict):
        v = d[top]
        params = v.get("params") or v.get("parametros") or v
    elif isinstance(d, dict) and len([k for k in d if k in TOPOLOGIAS]) == 1 and not top:
        top = next(k for k in d if k in TOPOLOGIAS)
        v = d[top]
        params = v.get("params") or v.get("parametros") or v
    else:
        raise SystemExit(f"No encuentro los parametros del avion en {ruta}. "
                         "Pasa --topologia si el archivo tiene varias.")
    if not _es_params(params):
        raise SystemExit(f"{ruta}: lo que encontre no parece un set de parametros del avion.")
    if top is None or top not in TOPOLOGIAS:
        raise SystemExit(f"Falta --topologia (una de {list(TOPOLOGIAS)}).")
    return params, top


# ======================================================================
# MALLAS
# ======================================================================
def _soldar(P: np.ndarray, F: np.ndarray, tol: float = 1e-7):
    """Une vertices coincidentes y descarta triangulos degenerados."""
    clave = np.round(P / tol).astype(np.int64)
    _, idx, inv = np.unique(clave, axis=0, return_index=True, return_inverse=True)
    inv = np.asarray(inv).reshape(-1)
    P2 = P[idx]
    F2 = inv[F]
    ok = (F2[:, 0] != F2[:, 1]) & (F2[:, 1] != F2[:, 2]) & (F2[:, 0] != F2[:, 2])
    F2 = F2[ok]
    # triangulos de area ~0 (p. ej. el cono de la nariz con radio 0)
    a, b, c = P2[F2[:, 0]], P2[F2[:, 1]], P2[F2[:, 2]]
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    return P2, F2[area > 1e-14]


def _aristas_abiertas(F: np.ndarray):
    """Aristas dirigidas (a, b) que NO tienen su opuesta (b, a): borde abierto."""
    e = np.vstack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    conjunto = {(int(a), int(b)) for a, b in e}
    return [(a, b) for (a, b) in conjunto if (b, a) not in conjunto]


def _orientar(F: np.ndarray):
    """Hace consistente el sentido de giro de todos los triangulos (cada arista
    compartida debe recorrerse en sentidos opuestos por sus dos caras) y
    devuelve (F, etiqueta_de_componente). Hace falta porque AeroSandbox arma
    la mitad izquierda de un ala simetrica con la orientacion espejada."""
    n = len(F)
    F = F.copy()
    ady: dict = {}
    for i, t in enumerate(F):
        for k in range(3):
            a, b = int(t[k]), int(t[(k + 1) % 3])
            ady.setdefault((min(a, b), max(a, b)), []).append(i)
    vecinos = [[] for _ in range(n)]
    for caras in ady.values():
        if len(caras) == 2:
            vecinos[caras[0]].append(caras[1])
            vecinos[caras[1]].append(caras[0])
    comp = -np.ones(n, dtype=int)
    nc = 0
    for s0 in range(n):
        if comp[s0] >= 0:
            continue
        comp[s0] = nc
        pila = [s0]
        while pila:
            i = pila.pop()
            ei = {(int(F[i][k]), int(F[i][(k + 1) % 3])) for k in range(3)}
            for j in vecinos[i]:
                if comp[j] >= 0:
                    continue
                ej = {(int(F[j][k]), int(F[j][(k + 1) % 3])) for k in range(3)}
                if ei & ej:                    # mismo sentido en la arista comun -> dar vuelta j
                    F[j] = F[j][[0, 2, 1]]
                comp[j] = nc
                pila.append(j)
        nc += 1
    return F, comp


def _tapar_agujeros(P: np.ndarray, F: np.ndarray):
    """Cierra cada lazo de borde abierto con un abanico desde su baricentro."""
    abiertas = _aristas_abiertas(F)
    if not abiertas:
        return P, F, 0
    sig = {}
    for a, b in abiertas:
        sig.setdefault(a, []).append(b)
    usado, lazos = set(), []
    for a0, b0 in abiertas:
        if (a0, b0) in usado:
            continue
        lazo, a, b = [a0], a0, b0
        usado.add((a0, b0))
        while b != a0:
            lazo.append(b)
            cand = [x for x in sig.get(b, []) if (b, x) not in usado]
            if not cand:
                break
            usado.add((b, cand[0]))
            a, b = b, cand[0]
        if len(lazo) >= 3:
            lazos.append(lazo)
    P = P.copy()
    nuevos = []
    for lazo in lazos:
        c = P[lazo].mean(axis=0)
        P = np.vstack([P, c])
        ic = len(P) - 1
        for i in range(len(lazo)):
            a, b = lazo[i], lazo[(i + 1) % len(lazo)]
            nuevos.append((b, a, ic))   # contiene la arista (b, a): cierra la (a, b)
    if nuevos:
        F = np.vstack([F, np.array(nuevos, dtype=F.dtype)])
    return P, F, len(lazos)


def _volumen_firmado(P, F) -> float:
    a, b, c = P[F[:, 0]], P[F[:, 1]], P[F[:, 2]]
    return float(np.sum(np.einsum("ij,ij->i", a, np.cross(b, c))) / 6.0)


def _area(P, F) -> float:
    a, b, c = P[F[:, 0]], P[F[:, 1]], P[F[:, 2]]
    return float(0.5 * np.sum(np.linalg.norm(np.cross(b - a, c - a), axis=1)))


def _slug(txt: str) -> str:
    s = txt.lower()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ñ", "n")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def mallar_cuerpos(avion: asb.Airplane, n: int) -> list[dict]:
    cuerpos = []
    for w in avion.wings:
        P, F = w.mesh_body(method="tri", chordwise_resolution=n,
                           mesh_surface=True, mesh_tips=True,
                           mesh_trailing_edge=True, mesh_symmetric=True)
        cuerpos.append(dict(nombre=w.name, tipo="ala", P=np.asarray(P), F=np.asarray(F)))
    for f in avion.fuselages:
        P, F = f.mesh_body(method="tri", tangential_resolution=n)
        cuerpos.append(dict(nombre=f.name, tipo="fuselaje", P=np.asarray(P), F=np.asarray(F)))

    for c in cuerpos:
        P, F = _soldar(c["P"], c["F"])
        F, _ = _orientar(F)
        P, F, n_tapas = _tapar_agujeros(P, F)
        P, F = _soldar(P, F)
        F, comp = _orientar(F)
        v = 0.0
        for k in np.unique(comp):       # normales hacia afuera, componente por componente
            m = comp == k
            vk = _volumen_firmado(P, F[m])
            if vk < 0:
                F[m] = F[m][:, [0, 2, 1]]
                vk = -vk
            v += vk
        c.update(P=P, F=F, volumen_m3=v, area_mojada_m2=_area(P, F),
                 aristas_abiertas=len(_aristas_abiertas(F)), tapas=n_tapas)
    return cuerpos


# ======================================================================
# ESCRITURA STL
# ======================================================================
def _normales(P, F):
    a, b, c = P[F[:, 0]], P[F[:, 1]], P[F[:, 2]]
    n = np.cross(b - a, c - a)
    L = np.linalg.norm(n, axis=1, keepdims=True)
    return n / np.where(L == 0, 1, L)


def escribir_stl_binario(ruta: Path, P, F, escala: float) -> None:
    N = _normales(P, F).astype("<f4")
    V = (P[F] * escala).astype("<f4")
    reg = np.zeros(len(F), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    reg["n"], reg["v"] = N, V
    with open(ruta, "wb") as fh:
        fh.write(b"AeroSandbox export - exportar_cfd_avion.py".ljust(80, b" "))
        fh.write(struct.pack("<I", len(F)))
        fh.write(reg.tobytes())


def escribir_stl_ascii_multi(ruta: Path, cuerpos: list[dict], escala: float) -> None:
    with open(ruta, "w", encoding="ascii") as fh:
        for c in cuerpos:
            nombre = _slug(c["nombre"])
            fh.write(f"solid {nombre}\n")
            N = _normales(c["P"], c["F"])
            V = c["P"][c["F"]] * escala
            for n, tri in zip(N, V):
                fh.write(f"  facet normal {n[0]:.6e} {n[1]:.6e} {n[2]:.6e}\n    outer loop\n")
                for p in tri:
                    fh.write(f"      vertex {p[0]:.6e} {p[1]:.6e} {p[2]:.6e}\n")
                fh.write("    endloop\n  endfacet\n")
            fh.write(f"endsolid {nombre}\n")


# ======================================================================
# CASO DE CALCULO Y DRAG DEL MODELO
# ======================================================================
def _f(x) -> float:
    return float(np.atleast_1d(x)[0])


def _componentes(res: dict, avion: asb.Airplane, q: float, S: float) -> dict:
    """Drag por cuerpo, si AeroBuildup lo entrega."""
    out = {}
    try:
        for w, r in zip(avion.wings, res["wing_aero_components"]):
            out[w.name] = _f(r["D"])
        for f, r in zip(avion.fuselages, res["fuselage_aero_components"]):
            out[f.name] = _f(r["D"])
    except Exception:
        return {}
    return out


def caso_de_calculo(params: dict, top: str, avion: asb.Airplane, cuerpos: list[dict]) -> dict:
    a = ma.analizar_mision_avion(params, top)
    if a is None:
        raise SystemExit("El modelo declara INVALIDO este diseno con los interruptores actuales "
                         "(--viento / --bateria). Si el diseno es anterior al modelo de bateria (p. ej. un "
                         "avion_design_params_*.json viejo), probar con --viento off --bateria off.")
    atm = ma._atmosfera()
    V = float(ma.V_CRUCERO)
    rho, mu = _f(atm.density()), _f(atm.dynamic_viscosity())
    T, p, vs = _f(atm.temperature()), _f(atm.pressure()), _f(atm.speed_of_sound())
    q = 0.5 * rho * V ** 2
    S, mac, b = float(avion.s_ref), float(avion.c_ref), float(avion.b_ref)
    alpha = float(a["alpha_crucero"])

    r = asb.AeroBuildup(airplane=avion,
                        op_point=asb.OperatingPoint(atmosphere=atm, velocity=V, alpha=alpha)).run()
    CD, CL = _f(r["CD"]), _f(r["CL"])
    D, L = _f(r["D"]), _f(r["L"])

    return {
        "topologia": top,
        "nombre_topologia": TOPOLOGIAS[top]["nombre"],
        "escenario_modelo": {"viento_activo": bool(ma.VIENTO_ACTIVO),
                             "bateria_activa": bool(ma.BATERIA_ACTIVA)},
        "condiciones": {
            "V_m_s": V, "V_km_h": V * 3.6, "rho_kg_m3": rho, "mu_Pa_s": mu,
            "nu_m2_s": mu / rho, "T_K": T, "p_Pa": p, "a_m_s": vs,
            "Mach": V / vs, "q_Pa": q,
            "Re_MAC": rho * V * mac / mu,
            "intensidad_turbulencia_sugerida_%": 0.1,
        },
        "referencias": {
            "S_ref_m2": S, "c_ref_MAC_m": mac, "b_ref_m": b,
            "AR": b ** 2 / S,
            "punto_de_momentos_xyz_m": [float(x) for x in avion.xyz_ref],
            "masa_kg": float(a["masa_total"]), "peso_N": float(a["peso"]),
            "ejes": "x hacia atras (del morro a la cola), y a la derecha, z hacia arriba",
        },
        "punto_de_calculo_crucero": {
            "alpha_deg": alpha,
            "CL_objetivo_L_igual_W": float(a["CL_crucero"]),
            "nota": "El CFD debe sostener el peso: ajustar alpha hasta CL = CL_objetivo y "
                    "recien ahi comparar CD. El alpha de arriba es el que da el modelo.",
        },
        "modelo_AeroBuildup_en_ese_punto": {
            "CL": CL, "CD": CD, "L_N": L, "D_N": D, "L_sobre_D": CL / CD,
            "D_perfil_N": _f(r["D_profile"]), "D_inducido_N": _f(r["D_induced"]),
            "CM_respecto_punto_de_momentos": _f(r["Cm"]),
            "D_por_cuerpo_N": _componentes(r, avion, q, S),
            "CD_del_optimizador_con_recargo_de_flap": float(a["CD_crucero"]),
            "nota": "CD / D_N de esta seccion son AeroBuildup puro (lo comparable con CFD). "
                    "CD_del_optimizador incluye un recargo por flap que es un termino de puntaje.",
        },
        "geometria_stl": [
            {"cuerpo": c["nombre"], "tipo": c["tipo"], "triangulos": int(len(c["F"])),
             "area_mojada_m2": c["area_mojada_m2"], "volumen_L": c["volumen_m3"] * 1000.0,
             "aristas_abiertas": c["aristas_abiertas"], "cerrado": c["aristas_abiertas"] == 0}
            for c in cuerpos
        ],
        "volumen_fuselaje_modelo_L": float(a["vol_geo_fuselaje_L"]),
    }


def escribir_md(caso: dict, ruta: Path, unidades: str) -> None:
    c, r, m = caso["condiciones"], caso["referencias"], caso["modelo_AeroBuildup_en_ese_punto"]
    pc = caso["punto_de_calculo_crucero"]
    L = [f"# Caso CFD - {caso['topologia']}",
         f"_{caso['nombre_topologia']}_  |  escenario del modelo: viento "
         f"{'ON' if caso['escenario_modelo']['viento_activo'] else 'OFF'}, bateria "
         f"{'ON' if caso['escenario_modelo']['bateria_activa'] else 'OFF'}", "",
         f"STL en **{unidades}**. Ejes: {r['ejes']}.", "",
         "## Condiciones de entrada",
         f"- Velocidad: {c['V_m_s']:.2f} m/s ({c['V_km_h']:.0f} km/h), Mach {c['Mach']:.3f}",
         f"- rho = {c['rho_kg_m3']:.4f} kg/m3, mu = {c['mu_Pa_s']:.4e} Pa.s, T = {c['T_K']:.1f} K, "
         f"p = {c['p_Pa']:.0f} Pa",
         f"- Re (MAC) = {c['Re_MAC']:.3e}   q = {c['q_Pa']:.2f} Pa", "",
         "## Referencias para los coeficientes",
         f"- S_ref = {r['S_ref_m2']:.4f} m2, c_ref (MAC) = {r['c_ref_MAC_m']:.4f} m, "
         f"b = {r['b_ref_m']:.3f} m (AR {r['AR']:.2f})",
         f"- Momentos respecto de xyz = {[round(x, 4) for x in r['punto_de_momentos_xyz_m']]} m",
         f"- Masa {r['masa_kg']:.2f} kg, peso {r['peso_N']:.1f} N", "",
         "## Punto de calculo (crucero)",
         f"- alpha del modelo = {pc['alpha_deg']:.3f} deg  ->  CL objetivo = {pc['CL_objetivo_L_igual_W']:.4f}",
         "- Ajustar alpha en el CFD hasta que CL coincida, y comparar CD a igual CL.", "",
         "## Lo que predice el modelo (AeroBuildup) en ese punto",
         f"- CL = {m['CL']:.4f}   CD = {m['CD']:.5f}   L/D = {m['L_sobre_D']:.2f}",
         f"- D = {m['D_N']:.3f} N  (perfil {m['D_perfil_N']:.3f} N + inducido {m['D_inducido_N']:.3f} N)"]
    if m["D_por_cuerpo_N"]:
        L.append("- Por cuerpo: " + ", ".join(f"{k} {v:.3f} N" for k, v in m["D_por_cuerpo_N"].items()))
    L += ["", "## Geometria exportada",
          "| Cuerpo | Triangulos | Area mojada [m2] | Volumen [L] | Cerrado |", "|---|---|---|---|---|"]
    for g in caso["geometria_stl"]:
        L.append(f"| {g['cuerpo']} | {g['triangulos']} | {g['area_mojada_m2']:.4f} | "
                 f"{g['volumen_L']:.2f} | {'si' if g['cerrado'] else 'NO'} |")
    L += ["", f"Volumen de fuselaje segun el modelo: {caso['volumen_fuselaje_modelo_L']:.2f} L "
              "(debe coincidir con el volumen del cuerpo 'Fuselaje').", "",
          "## Recordatorios",
          "- Los cuerpos se superponen: unir en el CAD o con el wrapper de Fluent Meshing.",
          "- No incluye helice ni spinner ni superficies deflectadas.",
          "- Re ~ 5-7e5: usar un modelo con transicion (k-omega SST gamma-Re_theta) si se quiere "
          "comparar con AeroBuildup/NeuralFoil; un modelo totalmente turbulento da mas drag de perfil.",
          "- Se puede correr medio modelo (y >= 0) con plano de simetria."]
    ruta.write_text("\n".join(L) + "\n", encoding="utf-8")


# ======================================================================
# COMPARACION CON EL CFD
# ======================================================================
def comparar(caso: dict, cd_cfd: float | None, d_cfd: float | None, cl_cfd: float | None,
             medio: bool, ruta: Path) -> None:
    q = caso["condiciones"]["q_Pa"]
    S = caso["referencias"]["S_ref_m2"]
    m = caso["modelo_AeroBuildup_en_ese_punto"]
    k = 2.0 if medio else 1.0
    if d_cfd is not None:
        d_cfd = d_cfd * k
        cd_cfd = d_cfd / (q * S)
    else:
        d_cfd = cd_cfd * q * S
    dif_cd = 100.0 * (cd_cfd - m["CD"]) / m["CD"]
    L = [f"# Comparacion de drag - {caso['topologia']}", "",
         "| | Modelo (AeroBuildup) | CFD | Diferencia |", "|---|---|---|---|",
         f"| CD | {m['CD']:.5f} | {cd_cfd:.5f} | {dif_cd:+.1f} % |",
         f"| D [N] | {m['D_N']:.3f} | {d_cfd:.3f} | {d_cfd - m['D_N']:+.3f} N |"]
    if cl_cfd is not None:
        dif_cl = 100.0 * (cl_cfd - m["CL"]) / m["CL"]
        L.append(f"| CL | {m['CL']:.4f} | {cl_cfd:.4f} | {dif_cl:+.1f} % |")
        L.append(f"| L/D | {m['L_sobre_D']:.2f} | {cl_cfd / cd_cfd:.2f} | "
                 f"{100.0 * (cl_cfd / cd_cfd - m['L_sobre_D']) / m['L_sobre_D']:+.1f} % |")
    L.append("")
    if medio:
        L.append("Se paso la fuerza de MEDIO modelo: se duplico para comparar el avion completo.")
    if cl_cfd is None:
        L.append("AVISO: no se paso --cl-cfd. Sin el CL no se puede saber si se comparo a igual sustentacion.")
    elif abs(100.0 * (cl_cfd - m["CL"]) / m["CL"]) > 3.0:
        L.append("AVISO: el CL del CFD difiere mas de 3 % del modelo. El drag inducido cambia con CL^2: "
                 "ajustar alpha hasta igualar CL antes de sacar conclusiones.")
    ruta.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


# ======================================================================
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("USO")[0].strip(),
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--params", required=True, type=Path,
                    help="avion_design_params_<top>.json (notebook, seccion 11), ganadores_*.json o un dict de parametros")
    ap.add_argument("--topologia", choices=list(TOPOLOGIAS), help="obligatoria si el archivo no la trae")
    ap.add_argument("--resolucion", choices=list(RESOLUCIONES), default="media",
                    help="finura de la malla superficial del STL (baja/media/alta)")
    ap.add_argument("--unidades", choices=("mm", "m"), default="mm", help="unidades del STL (default mm)")
    ap.add_argument("--salida", type=Path, help="carpeta de salida (default cfd_<topologia>/)")
    ap.add_argument("--viento", choices=("on", "off"), default=None,
                    help="escenario del modelo (default: el que dejo mision_avion.py)")
    ap.add_argument("--bateria", choices=("on", "off"), default=None)
    ap.add_argument("--cd-cfd", type=float, help="CD que dio el CFD (con S_ref del caso)")
    ap.add_argument("--d-cfd", type=float, help="fuerza de drag del CFD [N]")
    ap.add_argument("--cl-cfd", type=float, help="CL que dio el CFD (para chequear igual sustentacion)")
    ap.add_argument("--medio-modelo", action="store_true",
                    help="el CFD fue de medio modelo (y>=0): se duplica la fuerza")
    args = ap.parse_args()

    if args.viento:
        ma.VIENTO_ACTIVO = args.viento == "on"
    if args.bateria:
        ma.BATERIA_ACTIVA = args.bateria == "on"

    params, top = cargar_params(args.params, args.topologia)
    params = clamp_to_bounds_avion(params, top)   # mismo set que evalua el optimizador
    out = args.salida or (RAIZ / f"cfd_{top}")
    out.mkdir(parents=True, exist_ok=True)

    if args.cd_cfd is not None or args.d_cfd is not None:
        ruta_caso = out / f"{top}_caso_cfd.json"
        if not ruta_caso.exists():
            raise SystemExit(f"Falta {ruta_caso}: correr primero sin --cd-cfd para generar el caso.")
        caso = json.loads(ruta_caso.read_text(encoding="utf-8"))
        comparar(caso, args.cd_cfd, args.d_cfd, args.cl_cfd, args.medio_modelo,
                 out / "comparacion_drag.md")
        return

    escala = 1000.0 if args.unidades == "mm" else 1.0
    avion = construir_avion(params, top)
    cuerpos = mallar_cuerpos(avion, RESOLUCIONES[args.resolucion])

    for c in cuerpos:
        escribir_stl_binario(out / f"{top}_{_slug(c['nombre'])}.stl", c["P"], c["F"], escala)
    escribir_stl_ascii_multi(out / f"{top}_completo.stl", cuerpos, escala)

    caso = caso_de_calculo(params, top, avion, cuerpos)
    caso["unidades_stl"] = args.unidades
    (out / f"{top}_caso_cfd.json").write_text(json.dumps(caso, indent=2, ensure_ascii=False),
                                              encoding="utf-8")
    escribir_md(caso, out / f"{top}_caso_cfd.md", args.unidades)

    print(f"\nTopologia: {top}   ({TOPOLOGIAS[top]['nombre']})")
    print(f"Escrito en: {out}")
    for g in caso["geometria_stl"]:
        est = "cerrado" if g["cerrado"] else f"ABIERTO ({g['aristas_abiertas']} aristas)"
        print(f"  {g['cuerpo']:<28} {g['triangulos']:>6} tri   area {g['area_mojada_m2']:.4f} m2   "
              f"vol {g['volumen_L']:.2f} L   {est}")
    pc, m = caso["punto_de_calculo_crucero"], caso["modelo_AeroBuildup_en_ese_punto"]
    print(f"\nCrucero: V={caso['condiciones']['V_m_s']:.2f} m/s  Re_MAC={caso['condiciones']['Re_MAC']:.2e}  "
          f"alpha={pc['alpha_deg']:.2f} deg  CL={m['CL']:.4f}")
    print(f"Modelo: CD={m['CD']:.5f}  D={m['D_N']:.3f} N  L/D={m['L_sobre_D']:.2f}")
    print(f"Volumen de fuselaje: STL {[g['volumen_L'] for g in caso['geometria_stl'] if g['tipo']=='fuselaje'][0]:.2f} L"
          f"  vs modelo {caso['volumen_fuselaje_modelo_L']:.2f} L")


if __name__ == "__main__":
    main()
