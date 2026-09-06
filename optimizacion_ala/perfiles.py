"""
Catálogo de perfiles reales, y selección de perfil por zona del ala.

==========================================================================
POR QUÉ SE ABANDONÓ EL PERFIL PARAMÉTRICO (2026-08-28)
==========================================================================
Hasta acá el perfil era una variable de diseño continua: una línea de
curvatura definida por 8 puntos de control (`z1..z8`) más un espesor, y el
optimizador la deformaba libremente.

Ese enfoque SE DEGENERA, y Felipe lo vio en los gráficos. El motivo es
estructural del método, no un bug: NeuralFoil es una red entrenada sobre
perfiles REALES. Cuando el optimizador la evalúa en formas que no se parecen
a nada de su set de entrenamiento -- y con 9 grados de libertad libres llega
ahí rápido -- la red sigue devolviendo un número, pero ese número ya no es
una predicción, es una extrapolación. Y como el optimizador busca justamente
los máximos de la función que le damos, VA DERECHO a esas zonas: son las que
prometen más rendimiento del que existe. El resultado es un perfil raro con
un CL/CD que nadie va a poder reproducir en un túnel.

La solución no es poner más restricciones a la forma sino sacarle al
optimizador la posibilidad de inventar perfiles. Ahora ELIGE de un catálogo
de perfiles reales de la base UIUC. Nunca se evalúa un perfil que no venga
de esa base (salvo las mezclas de la transición, ver abajo).

==========================================================================
POR QUÉ EL CATÁLOGO ESTÁ ORDENADO POR Cm0 -- no es cosmético
==========================================================================
El perfil elegido en cada zona es una variable DISCRETA (un índice), pero el
GA cruza con BLX-alfa, que interpola valores continuos. Interpolar entre el
índice 2 y el índice 9 solo tiene sentido si los índices vecinos son diseños
vecinos. Por eso el catálogo está ordenado por **Cm0 medido** (NeuralFoil,
Re = 3.9e5), que es el parámetro que decide si un perfil sirve o no para un
ala sin cola:

    idx  perfil     Cm0       espesor  L/D máx  CLmáx
     0   naca2412  -0.0586    12.0%     82.5    1.324
     1   rg15      -0.0558     8.9%     83.7    1.224
     2   mh60      -0.0032    10.1%     74.7    1.221
     3   s5010     +0.0034     9.8%     78.6    1.284
     4   eh3012    +0.0039    12.0%     83.2    1.206
     5   eh2010    +0.0061    10.1%     79.2    1.134
     6   eh2012    +0.0095    12.0%     78.9    1.151
     7   clarkys   +0.0174    11.7%     77.1    1.271
     8   e186      +0.0176    10.3%     73.1    1.042
     9   mh80      +0.0187    12.7%     73.3    1.527
    10   e340      +0.0315    13.7%     75.5    1.380
    11   mh78      +0.0489    14.5%     66.2    1.451

Leído de arriba a abajo es el compromiso central del ala volante: **más
reflejo = más Cm0 = menos L/D**. Del naca2412 al mh78 se ganan 0.107 de Cm0
y se pierden 16 puntos de L/D. Moverse un índice es moverse un poco sobre esa
curva, que es exactamente lo que uno quiere que haga una mutación.

Los cuatro primeros (Cm0 <= 0) NO sirven solos: un ala sin cola con ellos no
se equilibra a sustentación positiva. Se dejan igual porque combinados con
mucho washout, o usados solo en la PUNTA (donde la torsión hace el trabajo),
son estrategias legítimas. Que estén disponibles no significa que ganen.

==========================================================================
LAS MEZCLAS DE LA TRANSICIÓN
==========================================================================
Entre dos anclajes con perfiles distintos, las secciones intermedias son
MEZCLAS lineales de los dos perfiles vecinos (`blend_with_another_airfoil`).
Es la práctica estándar de la industria -- un ala real se especifica como
"perfil X en la raíz, perfil Y en el quiebre, transición lineal" -- y es lo
que Felipe eligió sobre el corte seco.

Honestidad sobre esto: una mezcla NO es un perfil de catálogo, así que en las
secciones de transición NeuralFoil vuelve a estar interpolando. La diferencia
con el esquema viejo es de grado pero es enorme: una mezcla de dos perfiles
reales cae ENTRE dos puntos del set de entrenamiento, no afuera, y el
optimizador no puede empujarla a donde quiera -- solo puede elegir sus dos
extremos y dónde ponerlos.
"""

from __future__ import annotations

import aerosandbox as asb
import numpy as np

# ORDENADO POR Cm0 MEDIDO, de más negativo a más positivo. El orden es parte
# del diseño del optimizador (ver encabezado): NO reordenar sin volver a medir.
CATALOGO = [
    "naca2412", "rg15", "mh60", "s5010", "eh3012", "eh2010",
    "eh2012", "clarkys", "e186", "mh80", "e340", "mh78",
]

# Los que tienen Cm0 > 0 -- los únicos que por sí solos equilibran un ala sin
# cola. Se usan para sembrar; el optimizador puede salirse de acá si quiere.
CATALOGO_REFLEJADOS = ["s5010", "eh3012", "eh2010", "eh2012",
                       "clarkys", "e186", "mh80", "e340", "mh78"]

N_CATALOGO = len(CATALOGO)

# Cm0 medido con NeuralFoil a Re = 3.9e5 (informativo, para reportes).
CM0_MEDIDO = {
    "naca2412": -0.0586, "rg15": -0.0558, "mh60": -0.0032, "s5010": +0.0034,
    "eh3012": +0.0039, "eh2010": +0.0061, "eh2012": +0.0095, "clarkys": +0.0174,
    "e186": +0.0176, "mh80": +0.0187, "e340": +0.0315, "mh78": +0.0489,
}

# Todos los perfiles se repanelan a la MISMA cantidad de puntos. Es obligatorio
# para poder mezclarlos (la mezcla es punto a punto) y además le da a
# NeuralFoil una entrada consistente entre candidatos.
N_PUNTOS_LADO = 100

_cache_perfil: dict = {}
_cache_mezcla: dict = {}

# Las mezclas se redondean a pasos de esta fracción antes de cachear. Un paso
# de 0.05 es muy inferior a la resolución con la que el solver ve el ala y
# hace que el cache sirva de verdad: sin esto, cada candidato pediría 11
# mezclas nuevas.
PASO_MEZCLA = 0.05


def indice_a_nombre(idx) -> str:
    """Índice continuo (como lo maneja el GA) -> nombre de perfil."""
    return CATALOGO[int(np.clip(round(float(idx)), 0, N_CATALOGO - 1))]


def cargar_perfil(nombre: str) -> asb.Airfoil:
    """Perfil real de la base UIUC, repanelado y cacheado."""
    if nombre not in _cache_perfil:
        _cache_perfil[nombre] = asb.Airfoil(nombre).repanel(n_points_per_side=N_PUNTOS_LADO)
    return _cache_perfil[nombre]


def mezclar(nombre_a: str, nombre_b: str, fraccion: float) -> asb.Airfoil:
    """Mezcla lineal entre dos perfiles reales. `fraccion` = 0 devuelve A, 1
    devuelve B. Cacheada y redondeada a `PASO_MEZCLA`."""
    f = float(np.clip(fraccion, 0.0, 1.0))
    if nombre_a == nombre_b:
        return cargar_perfil(nombre_a)
    f = round(f / PASO_MEZCLA) * PASO_MEZCLA
    if f <= 1e-9:
        return cargar_perfil(nombre_a)
    if f >= 1.0 - 1e-9:
        return cargar_perfil(nombre_b)
    clave = (nombre_a, nombre_b, round(f, 3))
    if clave not in _cache_mezcla:
        _cache_mezcla[clave] = cargar_perfil(nombre_a).blend_with_another_airfoil(
            cargar_perfil(nombre_b), f
        )
    return _cache_mezcla[clave]


def perfiles_del_diseno(params: dict) -> dict:
    """Los tres perfiles ANCLA de un diseño y dónde está el del medio.

    Devuelve nombres, no objetos, para reportes y para el JSON de salida."""
    return {
        "raiz": indice_a_nombre(params["perfil_raiz"]),
        "medio": indice_a_nombre(params["perfil_medio"]),
        "punta": indice_a_nombre(params["perfil_punta"]),
        "pos_medio": float(params["perfil_pos_medio"]),
    }


def perfil_en_fraccion(params: dict, frac: float) -> asb.Airfoil:
    """Perfil en una fracción de la semi-envergadura (0 = raíz, 1 = punta).

    Tres anclajes: raíz en 0, el del medio en `perfil_pos_medio`, punta en 1.
    Entre anclajes, mezcla lineal. Si dos anclajes vecinos tienen el MISMO
    perfil, ese tramo entero es ese perfil real, sin mezclar."""
    n_r = indice_a_nombre(params["perfil_raiz"])
    n_m = indice_a_nombre(params["perfil_medio"])
    n_p = indice_a_nombre(params["perfil_punta"])
    pos = float(np.clip(params["perfil_pos_medio"], 0.05, 0.95))

    f = float(np.clip(frac, 0.0, 1.0))
    if f <= pos:
        return mezclar(n_r, n_m, f / max(pos, 1e-9))
    return mezclar(n_m, n_p, (f - pos) / max(1.0 - pos, 1e-9))


def resumen_catalogo() -> str:
    """Tabla del catálogo, para imprimir en el notebook."""
    lineas = ["idx  perfil     Cm0       espesor"]
    for i, n in enumerate(CATALOGO):
        af = cargar_perfil(n)
        lineas.append("%3d  %-9s %+8.4f   %5.1f%%" % (i, n, CM0_MEDIDO[n], 100 * af.max_thickness()))
    return "\n".join(lineas)


# =====================================================================
# Backend de generación de hijos con inyección desde el catálogo
# =====================================================================
def generar_hijos_con_catalogo(
    parent_a, parent_b, n_crossbred: int = 7, n_wildcard: int = 3,
    alpha: float = 0.5, prob_mutacion: float = 0.3, sigma_frac: float = 0.08,
):
    """Misma firma que `ga_numerico.generar_hijos`, pero los WILDCARDS saltan a
    combinaciones de perfiles distintas en vez de muestrear todo el hipercubo.

    POR QUÉ. Los wildcards existen para inyectar diversidad y evitar que la
    búsqueda se estanque. Muestrear uniformemente en 30 dimensiones produce,
    con probabilidad prácticamente 1, un avión sin sentido: casi todo el
    hipercubo es basura aerodinámica, esos wildcards nunca ganan y solo gastan
    evaluaciones. Es buena parte del motivo por el que el loop se estancaba a
    las ~9 generaciones.

    Acá cada wildcard toma el planform de uno de los padres con una
    perturbación grande, y le CAMBIA los tres perfiles ancla por otros del
    catálogo. Son saltos largos pero a territorio plausible.
    """
    import random

    from .ga_numerico import _hijo_crossbred
    from .geometria import BOUNDS, clamp_to_bounds

    hijos = []
    for _ in range(n_crossbred):
        params = clamp_to_bounds(
            _hijo_crossbred(parent_a, parent_b, alpha, prob_mutacion, sigma_frac)
        )
        hijos.append({"params": params, "origin": "crossbred",
                      "rationale": f"BLX-alfa (alpha={alpha}) + mutación gaussiana"})

    claves_perfil = ("perfil_raiz", "perfil_medio", "perfil_punta")
    for _ in range(n_wildcard):
        p = dict(random.choice([parent_a, parent_b]).params())
        for k, (lo, hi) in BOUNDS.items():
            if k in claves_perfil:
                continue
            p[k] = p[k] + random.gauss(0, 3 * sigma_frac * (hi - lo))
        elegidos = [random.choice(CATALOGO_REFLEJADOS) for _ in claves_perfil]
        for k, nombre in zip(claves_perfil, elegidos):
            p[k] = float(CATALOGO.index(nombre))
        hijos.append({"params": clamp_to_bounds(p),
                      "origin": "catálogo:" + "/".join(elegidos),
                      "rationale": "perfiles nuevos del catálogo + planform perturbado"})
    return hijos


def poblacion_semilla(planforms: list[dict], perfiles: list[str] | None = None) -> list[dict]:
    """Población semilla: cada planform x cada perfil del catálogo reflejado,
    usado en las TRES zonas (ala de perfil único).

    Arrancar con ala de perfil único y dejar que el optimizador abra las zonas
    es deliberado: así el beneficio de tener perfiles distintos por zona tiene
    que ganarse contra la alternativa simple, en vez de venir impuesto.

    Sembrar variado importa más de lo que parece: BLX-alfa entre dos padres
    IGUALES en una dimensión devuelve siempre ese mismo valor, así que una
    dimensión donde todas las semillas coinciden queda sin explorar (le pasó a
    los winglets)."""
    from .geometria import clamp_to_bounds

    perfiles = perfiles or CATALOGO_REFLEJADOS
    salida = []
    for pf in planforms:
        for nombre in perfiles:
            idx = float(CATALOGO.index(nombre))
            p = dict(pf)
            p.update(perfil_raiz=idx, perfil_medio=idx, perfil_punta=idx)
            p.setdefault("perfil_pos_medio", 0.5)
            salida.append(clamp_to_bounds(p))
    return salida


def semilla_desde_perfil(nombre: str, planform: dict) -> dict:
    """Compatibilidad: un diseño con `nombre` en las tres zonas."""
    return poblacion_semilla([planform], [nombre])[0]
