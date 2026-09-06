"""
Representación del candidato de diseño y construcción de la geometría del ala
en AeroSandbox.

Lógica estable y reutilizable: no cambia según qué backend de optimización se
use. Por eso vive en un módulo aparte y no dentro del notebook.

==========================================================================
REVISIÓN 2026-08-27 -- se arregló el "pozo" y se suavizó todo
==========================================================================
Felipe reportó que el ala mostraba un POZO en el medio. Diagnosticado: no era
un problema del ala sino del PERFIL, y tenía dos causas que se sumaban.

1. LÍMITES DE CURVATURA ABSURDOS. Los `z1..z5` iban de 0 a 0.20, o sea hasta
   un 20% de curvatura sobre la cuerda. Un perfil real anda en 2-6%. Con `z`
   en el medio de sus límites (0.10), la línea media saltaba de 0 en el borde
   de ataque a 0.10 en el primer 10% de la cuerda: una pared casi vertical
   seguida de una meseta. Eso no es un perfil, es un gancho -- y como la
   cuerda de raíz es la más grande, el gancho se veía enorme en el centro.
   Ese era el pozo.

2. INTERPOLACIÓN LINEAL. `np.interp` entre los puntos de control da una
   poligonal, con un quiebre en cada punto. Nada de curvas suaves.

Qué se cambió:

- Curvatura con límites FÍSICOS (ver BOUNDS), y se permiten valores
  NEGATIVOS. Eso último importa: un perfil reflejado (el que necesita un ala
  volante sin cola) tiene curvatura positiva adelante y NEGATIVA cerca del
  borde de fuga. Con el rango viejo, que arrancaba en 0, la forma en S no era
  representable y el reflejo tenía que salir del washout solamente.
- Interpolación PCHIP (spline cúbica monótona por tramos) en vez de lineal,
  tanto para la curvatura como para las distribuciones a lo largo de la
  envergadura. PCHIP y no spline cúbica común porque PCHIP NO SE PASA
  (no overshoot): entre dos puntos de control no inventa jorobas que el
  diseñador no pidió, cosa que una cúbica clásica sí hace.
- Puntos de control MÁS DENSOS cerca del borde de ataque y del borde de
  fuga (espaciado tipo coseno), que es donde la curvatura cambia rápido y
  donde se define el comportamiento del perfil. En el medio, donde la forma
  es suave, alcanza con menos puntos. Es lo que pidió Felipe: "puntos de
  control a izquierda y derecha más cortos para que el cambio sea gradual".
- El ala se LOFTEA a través de `N_SECCIONES_LOFT` secciones interpoladas, no
  solo las 6 de control. Las 6 siguen siendo las variables de diseño (el
  optimizador no ve más parámetros), pero la superficie que se le pasa al
  solver es suave en vez de facetada.

==========================================================================
UNIDADES DE CADA PARÁMETRO -- pregunta de Felipe, importa
==========================================================================
No todos los parámetros están en las mismas unidades. La regla es:

| Grupo | Unidad | ¿Escala con la envergadura? |
|---|---|---|
| Estaciones de envergadura | fracción de HALF_SPAN | SÍ |
| `le_offset_*` | fracción de HALF_SPAN | SÍ |
| `elev_*` (diedro) | fracción de HALF_SPAN | SÍ |
| `root_chord`, `chord_*` | METROS absolutos | no |
| `perfil_*` | índice al catálogo / fracción | -- |
| `twist_*` | grados | -- |
| `winglet_height` | METROS absolutos | no |

Por qué esta mezcla y no todo igual:
- Las posiciones a lo largo de la envergadura y los desvíos del borde de
  ataque son fracciones de HALF_SPAN, así que si mañana cambiás la
  envergadura, la FORMA del ala se mantiene y solo cambia la escala.
- Las cuerdas quedan en metros porque sus límites son restricciones de
  FABRICACIÓN (abajo de ~80 mm no entra el herraje del elevón); eso es un
  número absoluto, no proporcional.
- La elevación va en fracción de HALF_SPAN por la misma razón que los offsets:
  así el ÁNGULO de diedro no cambia si se reescala la envergadura.

==========================================================================
REVISIÓN 2026-08-28 -- el perfil se ELIGE, ya no se inventa
==========================================================================
Felipe reportó que el perfil se degeneraba. Se sacaron del espacio de diseño
los 8 puntos de curvatura (`z1..z8`) y el `espesor`: el perfil ahora se elige
de un catálogo de perfiles REALES (base UIUC), con tres anclajes -- raíz,
medio y punta -- y el anclaje del medio puede ubicarse donde el optimizador
quiera. El porqué completo está en el encabezado de `perfiles.py`.

En su lugar entró una variable que faltaba desde el principio: la ELEVACIÓN
de cada estación (`elev_1..elev_5`), o sea el DIEDRO. Hasta acá el ala era
plana por omisión -- nadie había decidido que el diedro valiera cero, era una
consecuencia de que no existía el parámetro.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional

import aerosandbox as asb
import aerosandbox.numpy as np
from scipy.interpolate import PchipInterpolator

# =====================================================================
# DATOS DE ENTRADA DEL PROBLEMA -- no son variables de diseño.
# El optimizador NO puede tocarlos; se editan acá a mano.
# =====================================================================
HALF_SPAN = 1.1          # semi-envergadura [m]. Envergadura total = 2.2 m.
CG_FRAC_MAC = 0.25       # CG como fracción de la MAC (dónde va la batería/payload)
MASA_TOTAL = 3.0         # masa total en vuelo [kg] -- para velocidad de pérdida y
                         # curvas de vuelo nivelado. Estimación: estructura +
                         # batería + payload de un ala volante de 2.2 m.
ESPESOR_FRAC = 0.10      # SOLO respaldo para código viejo. El espesor real ya no
                         # se declara: sale del perfil elegido en cada estación
                         # (ver estructura.espesor_en_fraccion).

# =====================================================================
# GRILLAS -- no son variables de diseño, son dónde se ubican los puntos
# de control sobre los que se interpola.
# =====================================================================
# 6 estaciones de control a lo largo de la semi-envergadura (fracción de HALF_SPAN).
_STATION_FRACTIONS = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
_N_ESTACIONES = len(_STATION_FRACTIONS)

# Cuántas secciones se le pasan realmente al solver. Las 6 de arriba son las
# variables de diseño; estas son el resultado de interpolarlas con PCHIP. Más
# secciones = superficie más suave y mejor resolución del solver, sin agregar
# ni un parámetro al espacio de búsqueda.
#
# 11 sale de un estudio de convergencia (mismo diseño, variando solo esto):
#     6 secc -> L/D 22.611, SM 5.966%, 246 ms
#     9      -> L/D 22.634, SM 6.017%, 387 ms
#    11      -> L/D 22.639, SM 6.017%, 481 ms   <-- elegido
#    15      -> L/D 22.643, SM 6.020%, 700 ms
#    21      -> L/D 22.645, SM 6.024%, 945 ms
# De 11 en adelante el resultado no se mueve (menos de 0.03% hasta 21) y el
# costo sigue subiendo lineal. Para GRAFICAR se puede pedir muchas más
# secciones sin tocar esto: `distribucion_envergadura(params, n=60)`.
N_SECCIONES_LOFT = 11

# OBSOLETO desde 2026-08-28: eran las posiciones x/c de los puntos de control
# de la curvatura, cuando el perfil era una variable de diseño. Ya no se usan
# para diseñar; quedan porque algún gráfico viejo los importa.
_CAMBER_X = (0.0, 0.02, 0.06, 0.12, 0.30, 0.55, 0.75, 0.88, 0.96, 1.0)
_N_CAMBER = 8

# Por debajo de esta altura no se genera el winglet (se considera "sin
# winglet"). Evita paneles degenerados de área ~0 que rompen el solver.
WINGLET_MIN_H = 0.02  # [m]

# Cuántas secciones intermedias se usan para dibujar el RADIO de transición
# ala->winglet (ver _xsecs_winglet). Cada sección extra cuesta ~14 ms por
# corrida de AeroBuildup, así que no conviene pasarse: con 3 el arco ya se ve
# limpio y la aerodinámica no se mueve.
N_SECCIONES_FILETE = 3

# =====================================================================
# LÍMITES DEL ESPACIO DE DISEÑO -- 30 parámetros
# =====================================================================
BOUNDS = {
    # --- Forma en planta ---
    "sweep_deg": (0.0, 40.0),      # flecha de la recta de referencia del borde de ataque [deg]
    # Cuerdas [m]. MÍNIMOS DE FABRICACIÓN, no aerodinámicos: por debajo de
    # ~80 mm no entra el herraje del elevón y la Re local se va a cero, que es
    # donde NeuralFoil deja de ser confiable.
    "root_chord": (0.20, 0.50),
    "chord_1": (0.18, 0.45),
    "chord_2": (0.15, 0.40),
    "chord_3": (0.12, 0.35),
    "chord_4": (0.10, 0.30),
    "chord_5": (0.08, 0.25),       # punta
    # Desvío del borde de ataque respecto de la recta de flecha, como FRACCIÓN
    # DE HALF_SPAN. Se permite negativo para que el borde pueda curvarse hacia
    # adelante y no solo hacia atrás.
    # Deben ser NO DECRECIENTES desde la raíz hacia la punta (ver
    # _proyectar_no_decreciente). Por eso el límite inferior es 0: el offset en
    # la raíz vale 0 por definición, así que un valor negativo violaría la
    # monotonía de entrada.
    "le_offset_1": (0.0, 0.04),
    "le_offset_2": (0.0, 0.06),
    "le_offset_3": (0.0, 0.08),
    "le_offset_4": (0.0, 0.10),
    "le_offset_5": (0.0, 0.12),
    # --- Torsión en las 6 estaciones de control [deg] ---
    "twist_0": (-5.0, 5.0),        # raíz
    "twist_1": (-12.0, 2.0),
    "twist_2": (-12.0, 2.0),
    "twist_3": (-12.0, 1.0),
    "twist_4": (-12.0, 0.0),
    "twist_5": (-12.0, 0.0),       # punta
    # --- ELEVACIÓN (diedro), fracción de HALF_SPAN -----------------------
    # Es la altura de cada estación sobre el plano de la raíz: lo que se ve
    # como el "ángulo del ala" en la vista frontal. Hasta 2026-08-28 esta
    # variable NO EXISTÍA -- el ala era perfectamente plana, y el diedro,
    # que es la palanca principal de estabilidad lateral (roll), estaba
    # implícitamente congelado en cero sin que nadie lo hubiera decidido.
    #
    # Los límites: 0.10 de HALF_SPAN en la punta son 110 mm, o sea ~5.7 grados
    # de diedro, que es mucho para un ala volante ya flechada (la flecha por sí
    # sola aporta diedro efectivo). Se permite algo NEGATIVO -- anedro -- que
    # es un recurso real para bajar la estabilidad en roll y evitar el balanceo
    # del holandés en alas muy flechadas.
    # Deben ser MONÓTONAS (ver _proyectar_monotona): diedro puro o anedro puro,
    # nunca un ala ondulada.
    "elev_1": (-0.010, 0.020),
    "elev_2": (-0.020, 0.040),
    "elev_3": (-0.030, 0.060),
    "elev_4": (-0.040, 0.080),
    "elev_5": (-0.050, 0.100),   # punta
    # --- PERFIL: qué perfil REAL va en cada zona --------------------------
    # Índices al CATALOGO de perfiles.py, ORDENADO POR Cm0. El orden importa:
    # es lo que hace que interpolar entre dos índices con BLX-alfa signifique
    # algo (índices vecinos = perfiles vecinos en reflejo).
    # Ya NO hay parámetros de forma de perfil: el optimizador ELIGE perfiles
    # reales, no los inventa. Ver el encabezado de perfiles.py para el porqué.
    "perfil_raiz": (0.0, 11.0),
    "perfil_medio": (0.0, 11.0),
    "perfil_punta": (0.0, 11.0),
    # Dónde está el anclaje del medio, como fracción de la semi-envergadura.
    # Es "el ala puede cambiar de perfil en el medio": el optimizador elige el
    # perfil Y dónde ponerlo.
    "perfil_pos_medio": (0.20, 0.80),
    # --- Winglet ---
    # winglet_height = 0 significa SIN winglet: es una respuesta legítima que
    # el optimizador puede elegir.
    "winglet_height": (0.0, 0.25),      # [m]
    "winglet_cant_deg": (0.0, 60.0),    # inclinación respecto de la VERTICAL [deg]
    "winglet_taper": (0.30, 1.00),      # cuerda punta winglet / cuerda punta ala
    "winglet_sweep_deg": (0.0, 45.0),   # flecha del winglet [deg]
    # Radio de la transición ala->winglet, como FRACCIÓN de winglet_height.
    # 0 = quiebre vivo (el modelo de un solo panel de siempre). Ver
    # _xsecs_winglet para por qué el radio no es un adorno.
    "winglet_radio": (0.0, 0.60),
    # NOTA: el ESPESOR ya no es variable de diseño. Sale del perfil elegido en
    # cada estación (un mh78 tiene 14.5%, un rg15 8.9%). Declararlo aparte del
    # perfil era inconsistente: se le pedía a NeuralFoil un perfil de una forma
    # y al modelo estructural una altura de larguero de otra.
}


@dataclass
class Candidate:
    sweep_deg: float
    root_chord: float
    chord_1: float
    chord_2: float
    chord_3: float
    chord_4: float
    chord_5: float
    le_offset_1: float
    le_offset_2: float
    le_offset_3: float
    le_offset_4: float
    le_offset_5: float
    twist_0: float
    twist_1: float
    twist_2: float
    twist_3: float
    twist_4: float
    twist_5: float
    elev_1: float
    elev_2: float
    elev_3: float
    elev_4: float
    elev_5: float
    perfil_raiz: float
    perfil_medio: float
    perfil_punta: float
    perfil_pos_medio: float
    winglet_height: float
    winglet_cant_deg: float
    winglet_taper: float
    winglet_sweep_deg: float
    winglet_radio: float = 0.0
    score: Optional[float] = None

    def params(self) -> dict:
        d = asdict(self)
        d.pop("score", None)
        return d


def _proyectar_no_decreciente(v):
    """Proyecta una secuencia a la más cercana que sea NO DECRECIENTE
    (regresión isotónica por el algoritmo PAVA -- pool adjacent violators).

    Se usa PAVA y no un simple máximo acumulado a propósito. El máximo
    acumulado también daría una secuencia creciente, pero SOLO SUBE valores:
    aplicado generación tras generación, empujaría sistemáticamente el borde
    de ataque hacia atrás, metiendo un sesgo que nadie pidió. PAVA promedia
    los tramos que violan la condición, así que es la proyección de mínima
    distancia y no tiene dirección preferida."""
    v = list(map(float, v))
    # Cada bloque: [suma, cantidad]. Se fusionan mientras el anterior sea mayor.
    bloques = []
    for x in v:
        bloques.append([x, 1])
        while len(bloques) > 1 and bloques[-2][0] / bloques[-2][1] > bloques[-1][0] / bloques[-1][1]:
            s_, n_ = bloques.pop()
            bloques[-1][0] += s_
            bloques[-1][1] += n_
    out = []
    for suma, n in bloques:
        out.extend([suma / n] * n)
    return out


def _proyectar_monotona(v):
    """Proyecta a la secuencia monótona más cercana, creciente O decreciente
    (la que quede más cerca en distancia L2).

    Se usa para la ELEVACIÓN de las estaciones. La razón es la misma que en el
    borde de ataque pero al revés de simple: un ala con diedro es un ala que
    sube desde la raíz hasta la punta, y un ala con anedro es una que baja.
    Las dos son diseños válidos. Lo que no existe es un ala que suba, baje y
    vuelva a subir: eso no es diedro, es una superficie ondulada que ningún
    larguero puede seguir y que además rompe la lógica de estabilidad lateral.
    Permitir las dos direcciones y quedarse con la más cercana deja al
    optimizador elegir libremente entre diedro y anedro, sin sesgarlo."""
    creciente = _proyectar_no_decreciente(v)
    # Decreciente = proyección creciente de la secuencia invertida en signo.
    decreciente = [-x for x in _proyectar_no_decreciente([-x for x in v])]
    d_c = sum((a - b) ** 2 for a, b in zip(v, creciente))
    d_d = sum((a - b) ** 2 for a, b in zip(v, decreciente))
    return creciente if d_c <= d_d else decreciente


def clamp_to_bounds(params: dict) -> dict:
    """Recorta cada parámetro a BOUNDS y proyecta el borde de ataque a una
    forma FABRICABLE.

    Además del recorte, impone que los `le_offset_*` sean NO DECRECIENTES de
    la raíz a la punta. Es una restricción de FABRICACIÓN, no aerodinámica:

    - Un larguero recto tiene que poder atravesar el ala entera. Si el borde
      de ataque avanza y después retrocede, la posición del larguero como
      fracción de la cuerda se mueve de un lado al otro, y mantenerlo cerca
      del centro de la cuerda -- que es donde mejor resiste la TORSIÓN del
      perfil -- se vuelve imposible.
    - Un borde de ataque ondulado también es bastante más difícil de
      construir y de encastrar entre semialas.

    POR QUÉ COMO RESTRICCIÓN Y NO COMO PENALIZACIÓN. Se midió que variar los
    `le_offset` en todo su rango cambia la resistencia de crucero un 0.1%,
    pero mueve el margen estático un 9% y el CL de equilibrio un 5.7%. O sea:
    son casi inertes aerodinámicamente pero son una palanca fortísima de
    centrado, y el optimizador los usaba para meter el margen estático en la
    banda. Como el modelo no les cobraba NADA (ni resistencia, ni estructura,
    ni fabricación), el problema quedaba subdeterminado: había infinitas
    formas de borde de ataque con el mismo margen estático y nada prefería la
    lisa. Una penalización suave solo desempata; la restricción elimina de
    plano las formas no fabricables, sin dejarle al optimizador la opción de
    "pagar" el puntaje y ondular igual.

    Se PROYECTA en vez de rechazar: rechazar candidatos quemaría evaluaciones
    del GA en diseños inválidos. Proyectar convierte cada hijo en el diseño
    fabricable más parecido, así ninguna evaluación se desperdicia."""
    # Se usa .get con el límite inferior por defecto para que un dict viejo
    # (anterior a que existiera, p.ej., `winglet_radio`) siga funcionando: el
    # parámetro que falta toma su valor neutro en vez de romper.
    p = {k: min(max(params.get(k, lo), lo), hi) for k, (lo, hi) in BOUNDS.items()}

    claves = [f"le_offset_{i}" for i in range(1, _N_ESTACIONES)]
    proyectados = _proyectar_no_decreciente([p[k] for k in claves])
    for k, v in zip(claves, proyectados):
        lo, hi = BOUNDS[k]
        p[k] = min(max(v, lo), hi)

    # La elevación (diedro) también se proyecta a monótona -- creciente o
    # decreciente, la que esté más cerca. Ver _proyectar_monotona.
    claves_e = [f"elev_{i}" for i in range(1, _N_ESTACIONES)]
    for k, v in zip(claves_e, _proyectar_monotona([p[k] for k in claves_e])):
        lo, hi = BOUNDS[k]
        p[k] = min(max(v, lo), hi)

    # Los índices de perfil son DISCRETOS: se redondean acá, una sola vez, para
    # que el candidato guardado sea el mismo que se evalúa. Si se redondearan
    # recién al construir la geometría, dos candidatos con índices 5.1 y 5.4
    # figurarían como distintos y serían el mismo avión.
    for k in ("perfil_raiz", "perfil_medio", "perfil_punta"):
        lo, hi = BOUNDS[k]
        p[k] = float(min(max(round(p[k]), lo), hi))
    return p


# ---------------------------------------------------------------------
# Perfil
# ---------------------------------------------------------------------
def _grilla_coseno(n: int):
    """Espaciado tipo coseno en [0, 1]: puntos AGRUPADOS cerca del borde de
    ataque y del borde de fuga, ralos en el medio.

    Por qué hace falta, y no es un detalle estético: la distribución de
    espesor va como sqrt(x), o sea con PENDIENTE INFINITA en el borde de
    ataque. Con espaciado uniforme, el primer tramo después del borde tiene
    que cubrir de un salto casi todo el descenso de la superficie inferior --
    en la práctica el primer segmento caía 0.0063 y el siguiente 0.0016, 4
    veces menos. Dibujado, eso es un pico seguido de un aplanamiento brusco:
    se ve como un ESCALÓN o "pozo" en la panza justo detrás del borde de
    ataque, aunque la superficie sea perfectamente monótona.

    Es el motivo por el que todos los formatos de perfil (Selig, Lednicer)
    usan espaciado tipo coseno. Además no es solo visual: NeuralFoil lee
    estas coordenadas, así que una nariz mal resuelta también ensucia la
    aerodinámica."""
    theta = np.linspace(0.0, np.pi, n)
    return 0.5 * (1.0 - np.cos(theta))


def perfil_en_fraccion(params: dict, frac: float):
    """Perfil REAL (o mezcla de dos reales) en una fracción de la
    semi-envergadura. Delegado a perfiles.py -- ver allá el porqué del
    catálogo. Se importa adentro para no crear un ciclo de importación."""
    from .perfiles import perfil_en_fraccion as _pef
    return _pef(params, frac)


def linea_de_curvatura(params: dict, n: int = 120, coseno: bool = False):
    """Devuelve (x, camber) de la línea media del perfil de RAÍZ.

    Antes esto interpolaba puntos de control que eran variables de diseño. Hoy
    la curvatura ya no se diseña: sale del perfil real elegido. Se conserva la
    función porque los gráficos la usan para dibujar la línea media."""
    af = perfil_en_fraccion(params, 0.0)
    x = _grilla_coseno(n) if coseno else np.linspace(0, 1, n)
    return x, np.asarray(af.local_camber(x), dtype=float)


def construir_perfil(params: dict):
    """Perfil de la RAÍZ del ala.

    ==================================================================
    CAMBIO DE FONDO (2026-08-28) -- esto ya no CONSTRUYE nada
    ==================================================================
    Hasta acá esta función fabricaba un perfil a medida: línea de curvatura
    por PCHIP sobre 8 puntos de control que eran variables de diseño, más una
    distribución de espesor tipo NACA 00XX. Ese esquema se DEGENERABA: con 9
    grados de libertad libres el optimizador encontraba formas que NeuralFoil
    nunca vio en su entrenamiento, y ahí la red extrapola -- devuelve números
    optimistas que no representan nada. Como el optimizador busca máximos, iba
    derecho a esas zonas.

    Ahora el perfil se ELIGE de un catálogo de perfiles reales (base UIUC) y
    esta función simplemente devuelve el de la raíz. Se conserva el nombre
    porque los gráficos y el código viejo la llaman así.

    Para el perfil en otra estación: `perfil_en_fraccion(params, frac)`.
    """
    return perfil_en_fraccion(params, 0.0)


# ---------------------------------------------------------------------
# Distribuciones a lo largo de la envergadura
# ---------------------------------------------------------------------
def distribucion_envergadura(params: dict, n: int | None = None):
    """Interpola con PCHIP las 6 estaciones de control a `n` estaciones.

    Devuelve (y, cuerda, x_le, torsion) como arrays de largo `n`. La ELEVACIÓN
    de cada estación se pide aparte con `elevacion_envergadura` -- se dejó
    separada a propósito para no romper todo el código que ya desempaquetaba
    cuatro valores de acá.

    PCHIP es shape-preserving: si las cuerdas de control decrecen de raíz a
    punta, las interpoladas también, sin jorobas intermedias. Con una spline
    cúbica común podrían aparecer bultos que nadie pidió."""
    # Se lee N_SECCIONES_LOFT en tiempo de llamada (no como default del
    # argumento) para que se pueda ajustar en caliente desde el notebook sin
    # reimportar el modulo.
    n = N_SECCIONES_LOFT if n is None else n
    fr = np.array(_STATION_FRACTIONS)
    cuerdas_ctrl = np.array([params["root_chord"]] + [params[f"chord_{i}"] for i in range(1, _N_ESTACIONES)])
    off_ctrl = np.array([0.0] + [params[f"le_offset_{i}"] for i in range(1, _N_ESTACIONES)])
    twist_ctrl = np.array([params[f"twist_{i}"] for i in range(_N_ESTACIONES)])

    fr_fina = np.linspace(0.0, 1.0, n)
    cuerda = PchipInterpolator(fr, cuerdas_ctrl)(fr_fina)
    offset = PchipInterpolator(fr, off_ctrl)(fr_fina)      # fracción de HALF_SPAN
    torsion = PchipInterpolator(fr, twist_ctrl)(fr_fina)

    y = fr_fina * HALF_SPAN
    x_le = y * np.tan(np.radians(params["sweep_deg"])) + offset * HALF_SPAN
    return y, cuerda, x_le, torsion


def elevacion_envergadura(params: dict, n: int | None = None):
    """Altura z de cada estación sobre el plano de la raíz [m] -- el diedro.

    Misma mecánica que las otras distribuciones: 5 puntos de control (la raíz
    vale 0 por definición) interpolados con PCHIP. Como los valores de control
    ya vienen proyectados a monótonos por `clamp_to_bounds` y PCHIP preserva la
    forma, la curva interpolada también es monótona: el ala sube (o baja) de
    corrido, sin ondulaciones."""
    n = N_SECCIONES_LOFT if n is None else n
    elev_ctrl = np.array([0.0] + [params[f"elev_{i}"] for i in range(1, _N_ESTACIONES)])
    fr_fina = np.linspace(0.0, 1.0, n)
    return PchipInterpolator(np.array(_STATION_FRACTIONS), elev_ctrl)(fr_fina) * HALF_SPAN


def _xsecs_ala_principal(params: dict) -> list:
    """Secciones del ala principal. Cada una lleva SU PROPIO perfil, tomado del
    catálogo según su posición en la envergadura -- esa es la novedad de
    2026-08-28: el perfil ya no es uno solo para toda el ala."""
    y, cuerda, x_le, torsion = distribucion_envergadura(params)
    z = elevacion_envergadura(params, n=len(y))
    fr = np.linspace(0.0, 1.0, len(y))
    return [
        asb.WingXSec(xyz_le=[float(x_le[i]), float(y[i]), float(z[i])],
                     chord=float(cuerda[i]), twist=float(torsion[i]),
                     airfoil=perfil_en_fraccion(params, float(fr[i])))
        for i in range(len(y))
    ]


def camino_winglet(params: dict, xyz_punta, n_filete: int | None = None):
    """Puntos (x, y, z) del borde de ataque del winglet, desde la punta del ala
    hasta la punta del winglet, incluyendo el arco de transición.

    Se expone aparte de `_xsecs_winglet` para que los gráficos puedan dibujar
    el arco con mucha más resolución que la que se le pasa al solver, sin
    duplicar la matemática. Devuelve [] si no hay winglet."""
    h = params["winglet_height"]
    if h < WINGLET_MIN_H:
        return []
    n_filete = N_SECCIONES_FILETE if n_filete is None else n_filete
    cant = np.radians(params["winglet_cant_deg"])
    swp = np.radians(params["winglet_sweep_deg"])
    x_p, y_p, z_p = xyz_punta

    # `winglet_height` es el LARGO DESARROLLADO del winglet (el "span" del
    # panel), no su altura vertical -- que es lo que significaba antes, cuando
    # la punta quedaba en z = h*cos(cant). Se conserva ese significado a
    # propósito: así el radio redistribuye el winglet sin cambiar su
    # superficie, y comparar dos diseños que solo difieren en el radio es
    # comparar la MISMA cantidad de material.
    delta = 0.5 * np.pi - cant                       # ángulo a doblar [rad]
    R = float(params.get("winglet_radio", 0.0)) * h
    # El arco no puede comerse todo el winglet: se le reserva al menos un 10%
    # del largo al tramo recto, si no el "winglet" es puro filete.
    if delta > 1e-6 and R * delta > 0.9 * h:
        R = 0.9 * h / delta

    s_yz = []  # (largo recorrido, y, z)
    if R > 1e-6 and delta > 1e-6 and n_filete > 0:
        for k in range(1, n_filete + 1):
            th = delta * k / n_filete
            s_yz.append((R * th, y_p + R * np.sin(th), z_p + R * (1.0 - np.cos(th))))
    s_a, y_a, z_a = s_yz[-1] if s_yz else (0.0, y_p, z_p)
    L = h - s_a                                       # tramo recto restante
    s_yz.append((h, y_a + L * np.sin(cant), z_a + L * np.cos(cant)))

    return [(float(x_p + (s_i / max(h, 1e-9)) * h * np.tan(swp)), float(y_i), float(z_i),
             float(s_i / max(h, 1e-9)))
            for s_i, y_i, z_i in s_yz]


def _xsecs_winglet(params: dict, airfoil, xsec_punta) -> list:
    """Secciones que forman el winglet, o lista vacía si no hay winglet.

    El winglet arranca en la punta del ala y sube `winglet_height`, inclinado
    `winglet_cant_deg` respecto de la VERTICAL (0 = vertical, 60 = muy tumbado
    hacia afuera).

    ==================================================================
    TRANSICIÓN CON RADIO -- `winglet_radio` (pedido de Felipe)
    ==================================================================
    Con `winglet_radio = 0` esto devuelve UNA sola sección y reproduce
    exactamente el modelo anterior: un quiebre vivo entre ala y winglet. Con
    radio > 0, la unión se hace con un ARCO DE CIRCUNFERENCIA tangente al ala
    en la punta y tangente al plano del winglet arriba, discretizado en
    `N_SECCIONES_FILETE` secciones intermedias.

    POR QUÉ IMPORTA, y no es solo estética:

    - AERODINÁMICA. Un quiebre vivo entre dos superficies sustentadoras genera
      un vórtice de esquina y una zona de interferencia donde las dos capas
      límite se juntan contra un ángulo diedro brusco -- separación local y
      resistencia de interferencia. Es el mismo motivo por el que todo avión
      real tiene filete en el encastre ala-fuselaje. Un radio bien puesto es
      justamente lo que hace que el winglet se comporte como una continuación
      del ala y no como una placa pegada.
    - FABRICACIÓN. Con molde de espuma o impresión 3D, una unión en ángulo
      vivo es un concentrador de tensiones y el punto por donde se rompe el
      winglet en el primer aterrizaje duro. Un radio reparte la carga.

    LO QUE EL MODELO SÍ Y NO VE. AeroBuildup no resuelve la interferencia de
    esquina, así que NO le va a cobrar al quiebre vivo la resistencia que
    tendría en la realidad. Lo que sí cambia con el radio es la distribución de
    sustentación y la superficie mojada, que son reales. O sea: el radio acá se
    ofrece como OPCIÓN de diseño y de fabricación, y el optimizador lo va a
    elegir por esos efectos, no porque el modelo penalice el quiebre. Conviene
    tenerlo presente al leer el resultado -- si sale radio chico, es porque el
    modelo no ve el costo del quiebre, no porque el quiebre sea bueno.

    GEOMETRÍA. El arco tiene radio R = winglet_radio * h, centro sobre la
    vertical de la punta, y gira un ángulo Δ = 90° - cant (lo que hay que
    doblar para pasar de horizontal a la dirección del winglet):

        y(θ) = y_p + R sin θ ,  z(θ) = z_p + R (1 - cos θ) ,  θ ∈ [0, Δ]

    Después del arco sigue un tramo recto hasta completar el LARGO `h`. Ojo con
    esto: `winglet_height` es el largo desarrollado del winglet (el "span" del
    panel), igual que antes -- el radio redistribuye ese largo, no lo agrega.
    Por eso dos diseños que solo difieren en el radio tienen la MISMA
    superficie de winglet y la misma masa: la comparación es limpia. Lo que sí
    cambia es la altura vertical alcanzada, que baja al curvar la base.

    La cuerda y la coordenada x se interpolan contra el LARGO RECORRIDO, de
    modo que con R=0 el resultado coincide punto por punto con el modelo recto
    anterior."""
    camino = camino_winglet(params, xsec_punta.xyz_le)
    if not camino:
        return []

    c_p = xsec_punta.chord
    c_wl = c_p * params["winglet_taper"]

    # La cuerda se interpola contra el LARGO RECORRIDO (no contra la altura),
    # para que con radio 0 dé exactamente el ahusamiento lineal de siempre.
    xsecs = []
    for x_i, y_i, z_i, s in camino:
        xsecs.append(asb.WingXSec(
            xyz_le=[x_i, y_i, z_i],
            chord=float(c_p + s * (c_wl - c_p)),
            twist=xsec_punta.twist,
            airfoil=airfoil,
        ))
    return xsecs


def _xsec_winglet(params: dict, airfoil, xsec_punta):
    """Compatibilidad hacia atrás: devuelve solo la sección de PUNTA del
    winglet (o None). Código nuevo debería usar `_xsecs_winglet`."""
    xs = _xsecs_winglet(params, airfoil, xsec_punta)
    return xs[-1] if xs else None


def construir_avion(params: dict) -> asb.Airplane:
    """Arma la geometría 3D (ala + winglets opcionales). Es la ÚNICA función
    que traduce "números" a "geometría".

    IMPORTANTE sobre las referencias: MAC, centro aerodinámico y superficie de
    referencia se calculan SOLO sobre el ala principal, sin winglet. Si se
    incluyera, agregarle un winglet a un diseño le cambiaría la S_ref y los
    coeficientes de dos candidatos dejarían de ser comparables entre sí -- que
    es justo lo que el optimizador necesita hacer."""
    xsecs_principal = _xsecs_ala_principal(params)
    # El winglet usa el perfil de la PUNTA del ala: es la continuación de esa
    # superficie, no una pieza con perfil propio.
    airfoil = xsecs_principal[-1].airfoil

    ala_ref = asb.Wing(name="ref", symmetric=True, xsecs=xsecs_principal)
    mac = ala_ref.mean_aerodynamic_chord()
    s_ref = ala_ref.area()
    b_ref = ala_ref.span()
    x_cg = (ala_ref.aerodynamic_center()[0] - 0.25 * mac) + CG_FRAC_MAC * mac

    xsecs = list(xsecs_principal)
    xsecs.extend(_xsecs_winglet(params, airfoil, xsecs_principal[-1]))

    return asb.Airplane(
        name="Candidate",
        xyz_ref=[x_cg, 0, 0],
        wings=[asb.Wing(name="Main Wing", symmetric=True, xsecs=xsecs)],
        s_ref=s_ref, c_ref=mac, b_ref=b_ref,
    )
