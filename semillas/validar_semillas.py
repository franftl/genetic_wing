"""
Dice con qué modelo de misión es válido cada avión de un set de semillas.

    python semillas/validar_semillas.py                    # todos los sets
    python semillas/validar_semillas.py bateria_350km      # uno solo

Evalúa cada avión con las cuatro combinaciones de VIENTO_ACTIVO y
BATERIA_ACTIVA de mision_avion.py y cuenta cuántos son válidos: puntaje finito
con el modo de puntaje vigente (en el modo "mision", además de pasar
analizar_mision_avion, tienen que cumplir los requisitos pasa/no pasa). Un set con todos sus aviones
inválidos igual puede servir de punto de partida -- el GA reemplaza a los
padres con el primer hijo válido -- pero arranca más lento.
"""
from __future__ import annotations

import sys
from pathlib import Path

CARPETA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARPETA.parent))

import semillas  # noqa: E402
from optimizacion_avion import mision_avion as ma  # noqa: E402

COMBINACIONES = [(False, False), (True, False), (False, True), (True, True)]


def validar(nombre: str) -> dict:
    """{(viento, bateria): (validos, total)}"""
    sets = semillas.cargar(nombre)
    original = (ma.VIENTO_ACTIVO, getattr(ma, "BATERIA_ACTIVA", False))
    resultado = {}
    try:
        for viento, bateria in COMBINACIONES:
            ma.VIENTO_ACTIVO = viento
            ma.BATERIA_ACTIVA = bateria
            aviones = [(t, p) for t, ps in sets.items() for p in ps]
            validos = sum(ma.es_factible(ma.evaluar_mision_avion(p, t)) for t, p in aviones)
            resultado[(viento, bateria)] = (validos, len(aviones))
    finally:
        ma.VIENTO_ACTIVO, ma.BATERIA_ACTIVA = original
    return resultado


def main():
    nombres = sys.argv[1:] or semillas.listar()
    print(f"{'set':<30} " + "  ".join(f"viento {'sí' if v else 'no'}/bat. {'sí' if b else 'no'}" for v, b in COMBINACIONES))
    for nombre in nombres:
        r = validar(nombre)
        print(f"{nombre:<30} " + "  ".join(f"{r[c][0]:>4}/{r[c][1]:<12}" for c in COMBINACIONES))


if __name__ == "__main__":
    main()
