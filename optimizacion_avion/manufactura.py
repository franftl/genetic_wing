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


def abrir_borde_de_fuga(airfoil, espesor_frac: float):
    """Copia del perfil con el borde de fuga de `espesor_frac` (fracción de cuerda),
    abierto SIEMPRE en vertical: el extradós sube y el intradós baja.

    Reemplaza a `asb.Airfoil.set_TE_thickness` (V54.2). Esa función abre el borde de
    fuga en la dirección del hueco que el perfil ya tiene; en un perfil cerrado ese
    hueco es ruido numérico (~1e-20) y la dirección sale al azar: en sd7062, fx63137,
    mh60 y sus mezclas el extradós quedaba POR DEBAJO del intradós (borde de fuga
    cruzado, espesor negativo), y en las mezclas mh80/fx63137 el hueco se abría en x
    (filo, sin espesor real). XFoil no converge con un borde de fuga cruzado (polares
    vacías en XFLR5) y en Fusion el loft se corta a sí mismo.

    El corrimiento es lineal desde el borde de ataque (0) hasta el borde de fuga
    (espesor completo), como `_abrir_borde_de_fuga` de exportar_cad_avion.py. Si el
    perfil ya tenía un borde de fuga (o venía cruzado), se corrige la DIFERENCIA con
    signo, así que el resultado es exactamente `espesor_frac` con la orientación correcta.
    Contorno en orden Selig: borde de fuga -> extradós -> borde de ataque -> intradós."""
    co = np.array(airfoil.coordinates, dtype=float)
    i_le = int(np.argmin(co[:, 0]))
    x_le = co[i_le, 0]
    hueco = co[0, 1] - co[-1, 1]                 # con signo: > 0 = extradós arriba
    delta = float(espesor_frac) - hueco
    arriba = co[:i_le + 1]
    abajo = co[i_le:]
    xi_up = (arriba[:, 0] - x_le) / max(co[0, 0] - x_le, 1e-12)
    xi_lo = (abajo[:, 0] - x_le) / max(co[-1, 0] - x_le, 1e-12)
    co[:i_le + 1, 1] = arriba[:, 1] + 0.5 * delta * xi_up
    co[i_le:, 1] = abajo[:, 1] - 0.5 * delta * xi_lo
    # El borde de ataque (i_le) es común a los dos tramos y no se mueve (xi = 0).
    nuevo = type(airfoil)(name=airfoil.name, coordinates=co)
    assert co[0, 1] - co[-1, 1] > -1e-12, "borde de fuga cruzado tras abrirlo"
    return nuevo


def perfil_con_te(airfoil, cuerda: float):
    """Copia del perfil con el borde de fuga exactamente de
    `ESPESOR_BORDE_FUGA_M` (absoluto) sobre una cuerda dada."""
    # Redondeado ANTES de calcular, para que el perfil cacheado no dependa del
    # orden de evaluación (ver perfiles_avion.perfil_con_flap).
    frac = round(ESPESOR_BORDE_FUGA_M / max(float(cuerda), 1e-6), 6)
    clave = (airfoil.name, hash(np.asarray(airfoil.coordinates).tobytes()), frac)
    if clave not in _cache_te:
        _cache_te[clave] = abrir_borde_de_fuga(airfoil, frac)
    return _cache_te[clave]


def aplicar_borde_de_fuga(alas) -> None:
    """Fuerza el borde de fuga de 2 mm en cada sección de cada ala (in situ)."""
    for ala in alas:
        for xsec in ala.xsecs:
            xsec.airfoil = perfil_con_te(xsec.airfoil, xsec.chord)
