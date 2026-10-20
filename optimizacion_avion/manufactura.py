"""
Restricciones de MANUFACTURABILIDAD del avión.

Se aplican en `geometria_avion.construir_avion`, o sea que las ve TODO el
pipeline con la misma geometría: el optimizador (AeroBuildup / NeuralFoil),
el export CAD, el export CFD y el script de Fusion. Si estuvieran sólo en el
exportador, el GA optimizaría un avión (filo exacto, nariz en punta) distinto
del que se construye.

1) Borde de fuga de ESPESOR ABSOLUTO
------------------------------------
Todas las superficies sustentadoras (ala, winglets, estabilizadores, cola en V,
derivas) terminan con un borde de fuga de `ESPESOR_BORDE_FUGA_M` = 2 mm, sea
cual sea la cuerda. Es un espesor absoluto, no relativo: un filo exacto no se
puede fabricar (ni cortar en foam, ni imprimir, ni laminar), y a 2 mm la pieza
es robusta. Por eso la fracción de cuerda que se le pide a cada sección es
2 mm / cuerda de ESA sección: en una cuerda de 400 mm es 0.5 %, en una de
50 mm (punta de winglet) es 4 %.

Costo aerodinámico: un borde de fuga romo agrega resistencia de base. NeuralFoil
modela el espesor de borde de fuga (lo recibe como parte de las coordenadas),
así que ese costo YA entra en el CD que ve el optimizador; no hay que sumarlo
a mano. El optimizador ve entonces la penalidad real y tenderá a evitar
cuerdas muy chicas en las puntas.

"Terminaciones": la punta del ala (y de cada superficie) queda cerrada por la
sección terminal, que ya tiene el borde de fuga de 2 mm, así que el espesor
mínimo se respeta también en las puntas.

2) Nariz sin punta
-------------------
Una nariz que arranca en radio 0 no se fabrica (se rompe y no se puede tornear
ni imprimir limpia) y en CAD obliga a un loft/revolución degenerado. La nariz
ahora arranca con una cara plana de radio `NARIZ_RADIO_PUNTA_M` y sigue una ley
de potencia con exponente `morro_exp` (variable de diseño, 0.45-1.0; los
exponentes bajos dan la nariz roma, tipo Von Kármán truncado).

Nota sobre "Von Kármán": la ojiva de Von Kármán / Haack es una forma de nariz
para régimen transónico-supersónico y es PUNTIAGUDA por definición. A 22 m/s,
sin onda de choque, la forma óptima es redondeada (elíptica / punta roma).
La ley de potencia con exponente < 1 es una aproximación cercana a una ojiva
tangente truncada y deja que el GA elija la bluntness; la cara plana de 5 mm
de radio es el truncamiento que la hace fabricable.

La mayoría de los puntos de la nariz se concentran cerca del extremo (la
curvatura está ahí) para que los splines del CAD y la malla no la pierdan.
"""

from __future__ import annotations

import numpy as np

# --- Borde de fuga ----------------------------------------------------------
ESPESOR_BORDE_FUGA_M = 0.002          # 2 mm, absoluto, todas las superficies

# --- Nariz -------------------------------------------------------------------
NARIZ_RADIO_PUNTA_M = 0.005           # radio de la cara plana de la nariz
N_SECCIONES_NARIZ = 11                # secciones de revolución del morro
NARIZ_CONCENTRACION = 1.8             # >1 densifica secciones cerca de la punta

_cache_te: dict = {}


def fracciones_morro() -> np.ndarray:
    """s en [0, 1] a lo largo del morro, más denso cerca de la punta."""
    return np.linspace(0.0, 1.0, N_SECCIONES_NARIZ) ** NARIZ_CONCENTRACION


def radio_morro(R: float, s: np.ndarray, exponente: float) -> np.ndarray:
    """Radio del morro. Parte de `NARIZ_RADIO_PUNTA_M` (nunca 0) y llega a R.

    r(s) = r0 + (R - r0) * s^exponente, con r0 acotado a 0.4 R para que un
    fuselaje muy fino no quede con la cara plana más grande que el cuerpo."""
    r0 = min(NARIZ_RADIO_PUNTA_M, 0.4 * R)
    return r0 + (R - r0) * np.asarray(s, float) ** float(exponente)


def _perfil_abierto(airfoil, frac: float):
    """Copia del perfil con el borde de fuga abierto a `frac` (fraccion de cuerda).

    NO se usa `asb.Airfoil.set_TE_thickness`: sobre los perfiles repanelados de la
    base UIUC deja la apertura INVERTIDA en varios de ellos (sd7062, mh80, rg15,
    e423, ... ; el extrados termina POR DEBAJO del intrados y el contorno se cruza
    cerca del borde de fuga, asi que el CAD sale con la punta afilada y el
    analisis ve un perfil de espesor negativo). Aca se abre a mano: se verifica que
    el perfil vaya extrados -> borde de ataque -> intrados (si no, se invierte) y
    se desplaza cada punto en y, +/- 0.5*delta*x (nulo en el borde de ataque, maximo
    en el de fuga), con delta = apertura pedida - apertura actual."""
    import aerosandbox as asb
    c = np.asarray(airfoil.coordinates, dtype=float).copy()
    i_le = int(np.argmin(c[:, 0]))
    if c[:i_le + 1, 1].mean() < c[i_le:, 1].mean():          # va intrados -> extrados: invertir
        c = c[::-1].copy()
        i_le = len(c) - 1 - i_le
    delta = float(frac) - float(c[0, 1] - c[-1, 1])
    signo = np.where(np.arange(len(c)) <= i_le, 1.0, -1.0)
    c[:, 1] += signo * 0.5 * delta * c[:, 0]
    return asb.Airfoil(name=airfoil.name, coordinates=c)


def perfil_con_te(airfoil, cuerda: float):
    """Copia del perfil con el borde de fuga exactamente de
    `ESPESOR_BORDE_FUGA_M` (absoluto) sobre una cuerda dada."""
    frac = ESPESOR_BORDE_FUGA_M / max(float(cuerda), 1e-6)
    clave = (airfoil.name, hash(np.asarray(airfoil.coordinates).tobytes()), round(frac, 6))
    if clave not in _cache_te:
        _cache_te[clave] = _perfil_abierto(airfoil, frac)
    return _cache_te[clave]


def aplicar_borde_de_fuga(alas) -> None:
    """Fuerza el borde de fuga de 2 mm en cada sección de cada ala (in situ)."""
    for ala in alas:
        for xsec in ala.xsecs:
            xsec.airfoil = perfil_con_te(xsec.airfoil, xsec.chord)
