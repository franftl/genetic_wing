"""
Compara los puntos de CFD (Fluent) con el modelo del optimizador (AeroBuildup, misma geometria, mismas condiciones) y
ajusta una funcion de transformacion  AeroBuildup -> CFD  por modelo de turbulencia.

Uso (Python del proyecto, desde la raiz del repo):
    python herramientas/calibrar_cfd_aerobuildup.py                         # lee resultados/cfd_run/noche/*/resultados.csv
    python herramientas/calibrar_cfd_aerobuildup.py --csv resultados/cfd_run/noche/noche/resultados.csv
    python herramientas/calibrar_cfd_aerobuildup.py --incluir-no-convergidos   # solo para mirar; NO para calibrar

Entrada : filas de resultados.csv generadas por correr_cfd_fluent.py (columnas modelo, paredes, malla, alfa_deg, CL, CD,
          convergio...). Solo se usan los casos convergidos (convergio = 1) salvo que se pida lo contrario.
Salida  : resultados/calibracion_cfd.json (coeficientes y errores) y resultados/calibracion_cfd.png.

Transformacion ajustada, por serie (modelo, paredes, malla):
    CL_cfd = a * CL_ab + b                    (recta; 'a' < 1 y 'b' ~ 0 si la pendiente de la CFD es menor)
    CD_cfd = CD_ab + d0 + d2 * CL_cfd^2       (exceso de resistencia: offset de perfil + parte que crece con CL^2)
Con 2 puntos las rectas pasan exacto (sin grados de libertad: se avisa); con 3 puntos el ajuste de CD queda justo. Hasta
tener 5-6 puntos por serie, tomar los coeficientes como indicativos. Para usarla en el optimizador:
    from calibrar_cfd_aerobuildup import corregir
    CL, CD = corregir(CL_ab, CD_ab, serie="transicion|velocidad|malla_grande.msh.h5")
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
RUTA_CALIBRACION = RAIZ / "resultados" / "calibracion_cfd.json"


# =============================================================================
# Ajuste (numpy puro)
# =============================================================================
def ajustar_serie(al, cl_cfd, cd_cfd, cl_ab, cd_ab) -> dict:
    """Ajusta la transformacion AeroBuildup -> CFD de una serie de puntos. Todas las entradas son arrays del mismo largo."""
    n = len(al)
    res = {"n_puntos": n, "alfa_deg": list(map(float, al)), "avisos": []}
    if n < 2:
        res["avisos"].append("con 1 punto no hay pendiente: solo se puede dar la diferencia")
        res["CL"] = {"a": 1.0, "b": float(cl_cfd[0] - cl_ab[0])}
        res["CD"] = {"d0": float(cd_cfd[0] - cd_ab[0]), "d2": 0.0}
        return res
    A = np.vstack([cl_ab, np.ones(n)]).T
    (a, b), *_ = np.linalg.lstsq(A, cl_cfd, rcond=None)
    pred = a * cl_ab + b
    res["CL"] = {"a": float(a), "b": float(b), "R2": _r2(cl_cfd, pred), "rms": float(np.sqrt(np.mean((cl_cfd - pred) ** 2)))}
    dcd = cd_cfd - cd_ab
    B = np.vstack([np.ones(n), cl_cfd ** 2]).T
    (d0, d2), *_ = np.linalg.lstsq(B, dcd, rcond=None)
    predcd = cd_ab + d0 + d2 * cl_cfd ** 2
    res["CD"] = {"d0": float(d0), "d2": float(d2), "R2": _r2(cd_cfd, predcd),
                 "rms": float(np.sqrt(np.mean((cd_cfd - predcd) ** 2))),
                 "rms_cuentas": float(1e4 * np.sqrt(np.mean((cd_cfd - predcd) ** 2)))}
    if n == 2:
        res["avisos"].append("2 puntos: las rectas pasan exacto, R2 y rms no significan nada")
    elif n == 3:
        res["avisos"].append("3 puntos: CL con 1 grado de libertad, CD con 1; indicativo")
    if n >= 4:  # error de validacion cruzada dejando uno afuera
        e_cl, e_cd = [], []
        for i in range(n):
            m = np.arange(n) != i
            (ai, bi), *_ = np.linalg.lstsq(A[m], cl_cfd[m], rcond=None)
            (d0i, d2i), *_ = np.linalg.lstsq(B[m], dcd[m], rcond=None)
            e_cl.append(cl_cfd[i] - (ai * cl_ab[i] + bi))
            e_cd.append(cd_cfd[i] - (cd_ab[i] + d0i + d2i * cl_cfd[i] ** 2))
        res["CL"]["rms_dejando_uno_afuera"] = float(np.sqrt(np.mean(np.square(e_cl))))
        res["CD"]["rms_dejando_uno_afuera_cuentas"] = float(1e4 * np.sqrt(np.mean(np.square(e_cd))))
    return res


def _r2(y, pred) -> float:
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")


def corregir(CL_ab, CD_ab, serie: str, ruta: Path = RUTA_CALIBRACION):
    """Aplica la transformacion guardada: devuelve (CL, CD) 'tipo Fluent' a partir de los de AeroBuildup."""
    c = json.loads(Path(ruta).read_text())["series"][serie]
    CL = c["CL"]["a"] * np.asarray(CL_ab, dtype=float) + c["CL"]["b"]
    CD = np.asarray(CD_ab, dtype=float) + c["CD"]["d0"] + c["CD"]["d2"] * CL ** 2
    return CL, CD


# =============================================================================
# Lectura de CFD
# =============================================================================
def leer_csv(rutas, incluir_no_conv=False):
    series = defaultdict(list)
    for r in rutas:
        with Path(r).open(newline="") as f:
            for fila in csv.DictReader(f):
                if fila["convergio"] != "1" and not incluir_no_conv:
                    continue
                clave = "%s|%s|%s" % (fila["modelo"], fila["paredes"], fila["malla"])
                series[clave].append({"alfa_deg": float(fila["alfa_deg"]), "CL": float(fila["CL"]), "CD": float(fila["CD"]),
                                      "convergio": int(fila["convergio"]), "origen": str(r)})
    for k in series:  # un alfa repetido (varias corridas): queda el ultimo
        unicos = {round(p["alfa_deg"], 3): p for p in series[k]}
        series[k] = [unicos[a] for a in sorted(unicos)]
    return dict(series)


def curva_aerobuildup(alfas):
    """CL y CD de AeroBuildup (V53, v_tail, 22.22 m/s) a los alfa dados."""
    sys.path.insert(0, str(RAIZ))
    sys.path.insert(0, str(RAIZ / "herramientas"))
    import aerosandbox as asb
    from exportar_cfd_avion import cargar_params
    from optimizacion_avion import mision_avion as ma
    from optimizacion_avion.geometria_avion import construir_avion

    params, top = cargar_params(RAIZ / "resultados" / "avion_design_params_v_tail.json", "v_tail")
    avion = construir_avion(params, top)
    atm, V = ma._atmosfera(), float(ma.V_CRUCERO)
    out = []
    for al in alfas:
        op = asb.OperatingPoint(atmosphere=atm, velocity=V, alpha=float(al))
        r = asb.AeroBuildup(airplane=avion, op_point=op).run()
        out.append((float(np.ravel(r["CL"])[0]), float(np.ravel(r["CD"])[0])))
    return np.array(out)


# =============================================================================
def main(curva=curva_aerobuildup):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, nargs="*", default=None)
    ap.add_argument("--incluir-no-convergidos", action="store_true")
    ap.add_argument("--salida", type=Path, default=RAIZ / "resultados")
    args = ap.parse_args()
    rutas = args.csv or sorted((RAIZ / "resultados" / "cfd_run" / "noche").glob("*/resultados.csv"))
    if not rutas:
        raise SystemExit("no hay resultados.csv: correr antes correr_cfd_fluent.py")
    series = leer_csv(rutas, args.incluir_no_convergidos)
    if not series:
        raise SystemExit("no hay casos convergidos en %s" % [str(r) for r in rutas])

    alfas_curva = np.arange(-4, 12.01, 1.0)
    todos = sorted({p["alfa_deg"] for s in series.values() for p in s})
    ab = curva(np.array(sorted(set(alfas_curva) | set(todos))))
    cache = dict(zip(sorted(set(alfas_curva) | set(todos)), ab))
    ab_curva = np.array([cache[a] for a in alfas_curva])

    salida = {"series": {}, "nota": "ajuste AeroBuildup -> CFD; ver docstring de calibrar_cfd_aerobuildup.py"}
    for clave, pts in series.items():
        al = np.array([p["alfa_deg"] for p in pts])
        cl, cd = np.array([p["CL"] for p in pts]), np.array([p["CD"] for p in pts])
        ab_p = np.array([cache[a] for a in al])
        aj = ajustar_serie(al, cl, cd, ab_p[:, 0], ab_p[:, 1])
        aj["CL_cfd"], aj["CD_cfd"] = cl.tolist(), cd.tolist()
        aj["CL_aerobuildup"], aj["CD_aerobuildup"] = ab_p[:, 0].tolist(), ab_p[:, 1].tolist()
        aj["solo_convergidos"] = not args.incluir_no_convergidos
        salida["series"][clave] = aj
        print("\n%s  (%d puntos)" % (clave, len(pts)))
        print("  CL_cfd = %.3f * CL_ab %+.4f   (R2 %.4f)" % (aj["CL"]["a"], aj["CL"]["b"], aj["CL"].get("R2", float("nan"))))
        print("  CD_cfd = CD_ab %+.5f %+.5f * CL^2   (R2 %.4f, rms %.1f cuentas)" % (
            aj["CD"]["d0"], aj["CD"]["d2"], aj["CD"].get("R2", float("nan")), aj["CD"].get("rms_cuentas", float("nan"))))
        for av in aj["avisos"]:
            print("  AVISO:", av)
    args.salida.mkdir(parents=True, exist_ok=True)
    (args.salida / "calibracion_cfd.json").write_text(json.dumps(salida, indent=2), encoding="utf-8")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 4, figsize=(18, 4.2))
    ax[0].plot(alfas_curva, ab_curva[:, 0], "k-", label="AeroBuildup")
    ax[1].plot(alfas_curva, ab_curva[:, 1], "k-", label="AeroBuildup")
    ax[2].plot(ab_curva[:, 1], ab_curva[:, 0], "k-", label="AeroBuildup")
    ax[3].plot(alfas_curva, ab_curva[:, 0] / ab_curva[:, 1], "k-", label="AeroBuildup")
    colores = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    for i, (clave, aj) in enumerate(salida["series"].items()):
        c = colores[i % len(colores)]
        al = np.array(aj["alfa_deg"])
        cl, cd = np.array(aj["CL_cfd"]), np.array(aj["CD_cfd"])
        ax[0].plot(al, cl, "o", color=c, label=clave)
        ax[1].plot(al, cd, "o", color=c)
        ax[2].plot(cd, cl, "o", color=c)
        ax[3].plot(al, cl / cd, "o", color=c)
        if aj["n_puntos"] >= 2:  # AeroBuildup transformado sobre toda la curva
            clt = aj["CL"]["a"] * ab_curva[:, 0] + aj["CL"]["b"]
            cdt = ab_curva[:, 1] + aj["CD"]["d0"] + aj["CD"]["d2"] * clt ** 2
            ax[0].plot(alfas_curva, clt, "--", color=c, lw=1)
            ax[1].plot(alfas_curva, cdt, "--", color=c, lw=1)
            ax[2].plot(cdt, clt, "--", color=c, lw=1)
            ax[3].plot(alfas_curva, clt / cdt, "--", color=c, lw=1)
    for x, (xl, yl, t) in zip(ax, [("alfa [deg]", "CL", "Sustentacion"), ("alfa [deg]", "CD", "Resistencia"),
                                   ("CD", "CL", "Polar"), ("alfa [deg]", "L/D", "Eficiencia")]):
        x.set(xlabel=xl, ylabel=yl, title=t)
        x.grid(alpha=0.3)
    ax[0].legend(fontsize=7)
    fig.suptitle("CFD (puntos) vs AeroBuildup (negro) y AeroBuildup transformado (trazos)")
    fig.tight_layout()
    fig.savefig(args.salida / "calibracion_cfd.png", dpi=140)
    print("\nescrito:", args.salida / "calibracion_cfd.json", "y .png")


if __name__ == "__main__":
    main()
