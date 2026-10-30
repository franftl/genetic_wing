"""
Arma semillas VÁLIDAS para la misión con batería (y viento, si está activo)
a partir de los ganadores que ya existen (por defecto ganadores_viento.json).

Por qué hace falta: con la batería de 350 km el avión pasa de ~7.5 kg a ~11 kg y
la batería (~1.5 L) tiene que entrar en el fuselaje, así que las semillas de
semillas.json (pensadas para 8.2 L útiles y ~7 kg) quedan inválidas. Este script
agranda el fuselaje hasta que el volumen alcance y, si hace falta, escala el
ala hasta que vuele a 10 m/s. No optimiza nada: solo deja un punto de partida
que el GA pueda evaluar.

    python evaluacion_bateria_350km/reparar_semillas.py [topologias...]
Parte de optimizacion_avion/ganadores_viento.json y ganadores.json (ver BASES).
Salida: evaluacion_bateria_350km/semillas_bateria.json (solo se reemplazan las
topologías pedidas; las demás quedan como estaban). Después copiarlo a
semillas/bateria_350km.json para que la biblioteca de semillas quede al día.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from optimizacion_avion import mision_avion as ma                      # noqa: E402
from optimizacion_avion.geometria_avion import (                       # noqa: E402
    TOPOLOGIAS, BOUNDS_POR_TOPOLOGIA, clamp_to_bounds_avion)

SALIDA = Path(__file__).with_name("semillas_bateria.json")


def reparar(params: dict, top: str, verbose: bool = True):
    b = BOUNDS_POR_TOPOLOGIA[top]
    p = dict(params)
    # 1) fuselaje: primero diámetro, después largo, hasta que entre el volumen
    for dia in (None, 0.17, 0.19, 0.21, 0.23, 0.24):
        for largo in (None, 1.3, 1.5, 1.7, 1.8):
            q = dict(p)
            if dia:
                q["fuselaje_diametro"] = max(q["fuselaje_diametro"], dia)
            if largo:
                q["fuselaje_largo"] = max(q["fuselaje_largo"], largo)
            q = clamp_to_bounds_avion(q, top)
            # 2) ala: escalar cuerdas hasta que vuele lento con el peso nuevo
            for k in (1.0, 1.05, 1.10, 1.15, 1.20, 1.30):
                r = dict(q)
                for c in ["root_chord"] + [f"chord_{i}" for i in range(1, 5)]:
                    r[c] = q[c] * k
                r = clamp_to_bounds_avion(r, top)
                s = ma.evaluar_mision_avion(r, top)
                if ma.es_factible(s):
                    if verbose:
                        print(f"  [{top}] valida con fuselaje {r['fuselaje_largo']:.2f}x{r['fuselaje_diametro']:.2f}, "
                              f"cuerdas x{k:.2f}, score {s:.3f}", flush=True)
                    return r, s
    return None, None


def reparar_con_afinado(params: dict, top: str, verbose: bool = True):
    """Último recurso: agranda ala y fuselaje y RE-AFINA el CG y la incidencia
    de cola (el mismo procedimiento de gen_semillas.afinar), porque al cambiar
    la masa y las cuerdas el margen estático y el Cm en crucero se corren y el
    candidato queda inválido aunque vuele lento. Es lento (~30 evaluaciones)."""
    from optimizacion_avion.gen_semillas import afinar
    for k in (1.25, 1.35, 1.45):
        q = dict(params)
        for c in ["root_chord"] + [f"chord_{i}" for i in range(1, 5)]:
            q[c] = params[c] * k
        q["fuselaje_diametro"] = max(q["fuselaje_diametro"], 0.20)
        q = clamp_to_bounds_avion(q, top)
        r = afinar(top, q, n=10)
        s = ma.evaluar_mision_avion(r, top)
        if verbose:
            print(f"  [{top}] afinado con cuerdas x{k:.2f}: score {s:.3f}", flush=True)
        if ma.es_factible(s):
            return r, s
    return None, None


BASES = [REPO / "optimizacion_avion" / "ganadores_viento.json",   # semilla A: ganadores CON viento
         REPO / "optimizacion_avion" / "ganadores.json"]           # semilla B: ganadores SIN viento (18/09)


def variante(semilla_a: dict, top: str):
    """Segunda semilla de respaldo: la A con el ala algo más grande, el flap más
    chico y el fuselaje más largo (se prueban en orden y se toma la primera
    válida). Sirve cuando los ganadores sin viento no se pueden reparar."""
    for k, dflap, dlar in ((1.08, -3.0, 1.06), (1.12, -4.0, 1.08), (1.05, -2.0, 1.04), (1.15, -5.0, 1.10)):
        q = dict(semilla_a)
        for c in ["root_chord"] + [f"chord_{i}" for i in range(1, 5)]:
            q[c] = semilla_a[c] * k
        q["flap_defl_deg"] = semilla_a["flap_defl_deg"] + dflap
        q["fuselaje_largo"] = semilla_a["fuselaje_largo"] * dlar
        q = clamp_to_bounds_avion(q, top)
        if ma.es_factible(ma.evaluar_mision_avion(q, top)):
            return q
    return None


def reparar_base(top: str, ruta: Path):
    g = json.loads(ruta.read_text(encoding="utf-8"))
    r, s = reparar(g[top]["params"], top)
    if r is None:
        r, s = reparar_con_afinado(g[top]["params"], top)
    return r


if __name__ == "__main__":
    # El GA necesita DOS semillas distintas por topología (el cruce BLX entre dos
    # padres iguales no explora nada, ver competencia.py): una sale de los
    # ganadores con viento y la otra de los ganadores sin viento.
    args = sys.argv[1:]
    solo = [a for a in args if a in TOPOLOGIAS]
    out = json.loads(SALIDA.read_text(encoding="utf-8")) if SALIDA.exists() else {}
    for top in (solo or list(TOPOLOGIAS)):
        lista = []
        for ruta in BASES:
            r = reparar_base(top, ruta)
            if r is None:
                print(f"  [{top}] NO se pudo reparar desde {ruta.name}")
            else:
                lista.append(r)
        if len(lista) == 1:
            v = variante(lista[0], top)
            if v is not None:
                print(f"  [{top}] segunda semilla = variante de la primera")
                lista.append(v)
        out[top] = lista
        SALIDA.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("->", SALIDA)
