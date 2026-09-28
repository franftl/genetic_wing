"""
Catálogo de perfiles para las topologías CON COLA.

==========================================================================
POR QUÉ UN CATÁLOGO PROPIO Y NO EL DE `optimizacion_ala.perfiles`
==========================================================================
Dos razones, y la segunda es la que obliga:

1. El ala volante necesitaba perfiles REFLEJADOS (Cm0 > 0) porque sin cola
   no hay con qué trimar. Un avión con cola no tiene esa restricción, así
   que puede usar perfiles muy cambados, que son más eficientes y sobre
   todo dan MUCHO más CL_max -- y desde que la misión pide volar a 10 m/s
   (ver `mision_avion.py`), el CL_max pasó de ser un detalle a ser el
   requisito que más aprieta.

2. NO SE PUEDE simplemente agregarle perfiles a `perfiles.CATALOGO`. El
   perfil es una variable de diseño DISCRETA codificada como índice, así
   que insertar o reordenar entradas le cambiaría el significado a todos
   los diseños ya guardados del ala volante (un `perfil_raiz = 7` dejaría
   de ser clarkys). Por eso acá el catálogo ARRANCA con los 12 de
   `perfiles.CATALOGO`, en el mismo orden y con los mismos índices, y los
   perfiles nuevos se AGREGAN al final, del 12 al 18.

==========================================================================
EL CATÁLOGO, Y POR QUÉ ESTE ORDEN
==========================================================================
Igual que en el ala volante, el orden no es cosmético: el GA cruza índices
con BLX-alfa, o sea que interpola. Para que interpolar tenga sentido, los
índices vecinos tienen que ser diseños vecinos. El catálogo sigue ordenado
por Cm0 medido (NeuralFoil, Re = 3.9e5), y da la casualidad afortunada de
que en el tramo nuevo ese orden es TAMBIÉN el orden de CL_max creciente --
que es lo que uno quiere que recorra una mutación cuando el binding
constraint es el vuelo lento.

  idx  perfil      Cm0      espesor  L/D max  CLmax@390k  CLmax@200k
   0   naca2412  -0.0580     12.0%     82.5     1.330       1.313
   1   rg15      -0.0563      8.9%     83.7     1.224       1.173
   2   mh60      -0.0028     10.1%     74.7     1.222       1.202
   3   s5010     +0.0032      9.8%     78.6     1.284       1.240
   4   eh3012    +0.0035     12.0%     83.2     1.211       1.225
   5   eh2010    +0.0067     10.1%     79.2     1.134       1.135
   6   eh2012    +0.0101     12.0%     78.9     1.152       1.133
   7   clarkys   +0.0185     11.7%     77.1     1.271       1.218
   8   e186      +0.0171     10.3%     73.1     1.043       1.026
   9   mh80      +0.0193     12.7%     73.3     1.537       1.513
  10   e340      +0.0315     13.7%     75.7     1.380       1.358
  11   mh78      +0.0489     14.5%     66.3     1.472       1.348
  --------- desde acá, perfiles NUEVOS de alta sustentación ---------
  12   naca4412  -0.1054     12.0%     99.3     1.440       1.397
  13   naca6412  -0.1522     12.0%    105.9     1.600       1.611
  14   sd7062    -0.0852     14.0%     89.6     1.595       1.563
  15   fx63137   -0.2117     13.7%    115.0     1.795       1.737
  16   e423      -0.2401     12.5%    112.1     1.995       1.992
  17   s1210     -0.2549     12.0%    115.2     1.996       1.938
  18   s1223     -0.2675     12.1%     91.5     2.237       2.236

LO QUE ESTA TABLA NO DICE, Y HAY QUE TENER PRESENTE: el "L/D max" de los
perfiles nuevos es altísimo, pero ocurre a CL ALTO. En crucero a 120 km/h
el CL del ala es del orden de 0.1-0.3, y ahí un perfil muy cambado como el
s1223 es un mal negocio (mucha resistencia de perfil y un Cm0 que hay que
trimar con la cola, lo que cuesta más resistencia todavía). Por eso NO hay
que leer esta tabla como "los de abajo son mejores": son mejores PARA VOLAR
LENTO y peores para crucero. El optimizador ve ese compromiso completo
porque evalúa los dos puntos de vuelo (ver `mision_avion.py`), y el
resultado de esa pelea es justamente uno de los resultados interesantes de
la tesis.

Fuente del s1223 y su régimen: Guglielmo & Selig, "High-Lift Low Reynolds
Number Airfoil Design", Journal of Aircraft 34(1), 1997 --
https://m-selig.ae.illinois.edu/pubs/GuglielmoSelig-1997-JofAC-S1223.pdf
"""

from __future__ import annotations

import aerosandbox as asb
import numpy as np

from optimizacion_ala.perfiles import CATALOGO as _CATALOGO_ALA
from optimizacion_ala.perfiles import N_PUNTOS_LADO, PASO_MEZCLA

# Perfiles de ALTA SUSTENTACIÓN agregados para la misión con vuelo lento.
# Ordenados por Cm0 decreciente, que en este tramo coincide con CL_max
# creciente (ver la tabla del encabezado).
ALTA_SUSTENTACION = ["naca4412", "naca6412", "sd7062", "fx63137", "e423", "s1210", "s1223"]

# Los índices 0..11 coinciden EXACTAMENTE con perfiles.CATALOGO -- ver el
# punto 2 del encabezado para por qué eso no es negociable.
CATALOGO_AVION = list(_CATALOGO_ALA) + ALTA_SUSTENTACION
N_CATALOGO_AVION = len(CATALOGO_AVION)

_cache_perfil: dict = {}
_cache_mezcla: dict = {}
_cache_flap: dict = {}


def indice_a_nombre_avion(idx) -> str:
    """Índice continuo (como lo maneja el GA) -> nombre de perfil."""
    return CATALOGO_AVION[int(np.clip(round(float(idx)), 0, N_CATALOGO_AVION - 1))]


def cargar_perfil_avion(nombre: str) -> asb.Airfoil:
    """Perfil real de la base UIUC, repanelado y cacheado. Cache propia (no
    la de `optimizacion_ala.perfiles`) para no ensuciar la del ala volante."""
    if nombre not in _cache_perfil:
        _cache_perfil[nombre] = asb.Airfoil(nombre).repanel(n_points_per_side=N_PUNTOS_LADO)
    return _cache_perfil[nombre]


def mezclar_avion(nombre_a: str, nombre_b: str, fraccion: float) -> asb.Airfoil:
    """Mezcla lineal entre dos perfiles reales, redondeada a `PASO_MEZCLA` y
    cacheada. Mismo criterio que `perfiles.mezclar`."""
    f = float(np.clip(fraccion, 0.0, 1.0))
    if nombre_a == nombre_b:
        return cargar_perfil_avion(nombre_a)
    f = round(f / PASO_MEZCLA) * PASO_MEZCLA
    if f <= 1e-9:
        return cargar_perfil_avion(nombre_a)
    if f >= 1.0 - 1e-9:
        return cargar_perfil_avion(nombre_b)
    clave = (nombre_a, nombre_b, round(f, 3))
    if clave not in _cache_mezcla:
        _cache_mezcla[clave] = cargar_perfil_avion(nombre_a).blend_with_another_airfoil(
            cargar_perfil_avion(nombre_b), f
        )
    return _cache_mezcla[clave]


def perfil_en_fraccion_avion(params: dict, frac: float) -> asb.Airfoil:
    """Perfil en una fracción de la semi-envergadura (0 = raíz, 1 = punta).
    Tres anclajes: raíz en 0, el del medio en `perfil_pos_medio`, punta en 1.
    Idéntico en método a `perfiles.perfil_en_fraccion`, pero sobre
    `CATALOGO_AVION`."""
    n_r = indice_a_nombre_avion(params["perfil_raiz"])
    n_m = indice_a_nombre_avion(params["perfil_medio"])
    n_p = indice_a_nombre_avion(params["perfil_punta"])
    pos = float(np.clip(params["perfil_pos_medio"], 0.05, 0.95))

    f = float(np.clip(frac, 0.0, 1.0))
    if f <= pos:
        return mezclar_avion(n_r, n_m, f / max(pos, 1e-9))
    return mezclar_avion(n_m, n_p, (f - pos) / max(1.0 - pos, 1e-9))


def perfil_con_flap(base: asb.Airfoil, deflexion_deg: float, cuerda_flap_frac: float) -> asb.Airfoil:
    """Perfil con el flap deflectado, para evaluar el punto de vuelo lento.

    ==================================================================
    POR QUÉ ASÍ Y NO CON UNA TABLA DE dCL_max
    ==================================================================
    Lo habitual en diseño preliminar es sumarle al CL_max limpio un
    incremento de tabla según el tipo de flap (Raymer/Roskam: plain ~0.9,
    ranurado ~1.3, Fowler ~1.9). El problema es que esas tablas están
    medidas a Reynolds de avión grande (10^6-10^7), y este avión vuela
    lento a Re ~2x10^5. La bibliografía que encontramos dice que a Re bajo
    la curva de sustentación con flap se vuelve no lineal y el CL_max cae
    (ICAS 2010, paper 246: NACA 2412 con flap 30%c a Re 61k-260k), pero
    NO da un factor de corrección publicable.

    En vez de inventar ese factor, se deflecta la GEOMETRÍA del perfil y se
    la evalúa con NeuralFoil al Reynolds real del vuelo lento -- el mismo
    modelo aerodinámico que se usa en todo el resto del pipeline. Medido
    así, un flap plain del 25% a 30° da dCL_max ~0.43-0.58 según el perfil,
    bastante por DEBAJO del 0.9 de tabla, que es exactamente la degradación
    por bajo Reynolds que la bibliografía describe cualitativamente.

    LIMITACIÓN HONESTA: `add_control_surface` deflecta el contorno, así que
    esto modela bien un flap PLAIN (sin ranura). Un flap ranurado o Fowler
    tiene física adicional (la ranura reenergiza la capa límite, el Fowler
    además agranda la superficie) que una deflexión de contorno NO captura.
    Por eso el modelo ofrece solo flap plain, que además es el realista
    para construcción artesanal -- ver `FLAP_TIPOS` en `geometria_avion.py`.
    """
    d = float(deflexion_deg)
    if abs(d) < 0.1:
        return base
    # La bisagra va medida desde el borde de ataque: un flap del 25% de
    # cuerda tiene la bisagra al 75%.
    hinge = float(np.clip(1.0 - cuerda_flap_frac, 0.60, 0.92))
    clave = (base.name, round(d, 1), round(hinge, 3))
    if clave not in _cache_flap:
        _cache_flap[clave] = base.add_control_surface(deflection=d, hinge_point_x=hinge)
    return _cache_flap[clave]


def resumen_catalogo_avion(re_lento: float = 2.0e5, re_crucero: float = 6.7e5) -> str:
    """Tabla del catálogo medida a los DOS Reynolds de la misión -- para
    imprimir en el notebook y poder discutir el compromiso crucero/lento."""
    alphas = np.linspace(-2, 22, 49)
    lineas = [f"idx  perfil     Cm0       espesor  CLmax@{re_crucero/1e3:.0f}k  CLmax@{re_lento/1e3:.0f}k"]
    for i, n in enumerate(CATALOGO_AVION):
        af = cargar_perfil_avion(n)
        r1 = af.get_aero_from_neuralfoil(alpha=alphas, Re=re_crucero, mach=0.1)
        r2 = af.get_aero_from_neuralfoil(alpha=alphas, Re=re_lento, mach=0.03)
        cl, cm = np.array(r1["CL"]), np.array(r1["CM"])
        cm0 = float(np.interp(0.0, cl, cm))
        marca = "  <- alta sustentacion" if n in ALTA_SUSTENTACION else ""
        lineas.append("%3d  %-9s %+8.4f   %5.1f%%    %7.3f     %7.3f%s" % (
            i, n, cm0, 100 * af.max_thickness(),
            float(np.max(cl)), float(np.max(np.array(r2["CL"]))), marca))
    return "\n".join(lineas)
