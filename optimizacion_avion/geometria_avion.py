"""
Geometría paramétrica de las topologías de avión con cola.

==========================================================================
REVISIÓN 2026-09-17 -- QUÉ CAMBIÓ Y POR QUÉ
==========================================================================
La versión anterior era un primer corte deliberadamente grueso: ala de 2
estaciones, sin winglets, cola sin incidencia, fuselaje de cono truncado, y
solo dos topologías. Esta revisión la reemplaza entera. Los cambios:

1. ALA MULTI-ESTACIÓN CON WINGLETS. Antes el ala era raíz + punta, o sea que
   el optimizador no podía elegir la FORMA en planta, solo el ahusamiento.
   Ahora son 5 estaciones con cuerda, offset de borde de ataque, torsión y
   elevación propios -- el mismo nivel de detalle que ya tenía el ala
   volante -- más winglets. El ala volante llegó a ese nivel porque hizo
   falta; no había razón para que el avión compitiera con una mano atada.

2. ENVERGADURA VARIABLE. Dejó de ser una constante (`HALF_SPAN`). La razón
   original para fijarla ya no existe: se fijó cuando la masa era una
   constante declarada, porque entonces agrandar el ala salía gratis y la
   envergadura era una dirección degenerada. Desde que `estructura_avion.py`
   hace que un ala más grande pese más y flexione más, la envergadura se
   paga sola y puede competir.

3. INCIDENCIA DE COLA. Antes la cola iba con `twist = 0` hardcodeado, y eso
   era un error concreto, no una simplificación: sin incidencia el avión no
   tiene con qué trimarse, y en las corridas el desvío entre el CL de
   equilibrio y el de crucero llegaba al 113%. La incidencia del
   estabilizador es LA variable de trim de un avión con cola.

4. FUSELAJE DE VERDAD. El morro era un cono (radio 0 en la punta, recto
   hasta la sección máxima) y la cola terminaba en un radio de 1 cm. Ahora:
   morro de ley potencial `r = R*(s^morro_exp)` -- con `morro_exp` = 1 es un
   cono y con 0.45 es un morro romo tipo ojiva -- sección central recta, y
   boat-tail que se contrae suave (tangente al cilindro) hasta un radio
   final que es variable de diseño, no un número mágico.

5. FLAPS. Ver `FLAP_*` más abajo y el encabezado de `mision_avion.py`: la
   misión pide crucero a 120 km/h Y vuelo a 10 m/s, que son un factor 11 en
   CL. Sin hipersustentación no cierra.

6. CINCO TOPOLOGÍAS en vez de dos (ver `TOPOLOGIAS`).

==========================================================================
LAS TOPOLOGÍAS, Y POR QUÉ ESTAS
==========================================================================
Un resultado teórico condiciona toda la competencia y conviene tenerlo a la
vista al leer los resultados: McGeer & Kroo (J. Aircraft 20(11), 1983,
https://ntrs.nasa.gov/citations/19840028263) muestran que A ENVERGADURA
DADA y con las restricciones de trimado y estabilidad puestas, la
configuración convencional con cola trasera está muy cerca del óptimo, y ni
el canard ni el tándem la superan salvo casos marginales. O sea: no hay que
esperar que una topología exótica gane por goleada. Lo que de verdad separa
a los candidatos es resistencia parásita, peso estructural y CL_max -- y por
eso la competencia sigue teniendo sentido, pero como una comparación fina y
no como la búsqueda de una configuración mágica.

Por esa misma razón NO se incluyeron canard ni box-wing/joined-wing:
- el canard limita el CL_max utilizable del ala principal, que es justo el
  recurso más escaso ahora que hay que volar a 10 m/s;
- el box-wing necesita separación vertical h/b ~ 0.2 (acá, ~0.5 m) para que
  aparezca el beneficio inducido de Prandtl, y a 7 kg de construcción
  artesanal la parásita y la interferencia de las uniones se lo comen.
Si se quisieran agregar como control negativo documentado, el lugar es acá.

==========================================================================
COEFICIENTES DE VOLUMEN DE COLA -- para leer los resultados
==========================================================================
`volumenes_de_cola()` calcula V_H y V_V de cada candidato. Rangos de
referencia para esta clase (Scholz, INCAS Bulletin 13(3), 2021,
https://www.fzt.haw-hamburg.de/pers/Scholz/Aero/AERO_PUB_INCAS_TailVolume_Vol13No3_2021.pdf):
V_H ~ 0.5-0.7 y V_V ~ 0.02-0.05. NO se imponen como restricción -- el
optimizador dimensiona la cola por sus consecuencias (estabilidad, masa,
resistencia), no por cumplir una regla de dimensionamiento. Se reportan para
poder decir en el informe si el resultado cayó en territorio conocido o no,
y para detectar el modo de falla que ya apareció una vez: un horizontal
enorme que empuja el punto neutro tan atrás que ningún CG alcanza la banda.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import aerosandbox as asb
import aerosandbox.numpy as np

# Las proyecciones isotónicas son matemática pura y no dependen de la
# topología: se reutilizan tal cual del ala volante (ver allí el porqué de
# PAVA y de permitir diedro Y anedro).
from optimizacion_ala.geometria import (
    N_SECCIONES_FILETE,
    WINGLET_MIN_H,
    _proyectar_monotona,
    _proyectar_no_decreciente,
    camino_winglet,
)
from .perfiles_avion import (
    N_CATALOGO_AVION,
    cargar_perfil_avion,
    perfil_en_fraccion_avion,
)

# Estaciones de control del ala: raíz (0) + 4. Una menos que el ala volante
# (que usa 6) a propósito: acá el ala comparte el presupuesto de parámetros
# con un fuselaje y una cola que el ala volante no tiene.
N_ESTACIONES = 5
_FRAC_ESTACION = np.linspace(0.0, 1.0, N_ESTACIONES)

# Perfil de las superficies de cola. Simétrico, como corresponde a una
# superficie que tiene que dar fuerza en los dos sentidos. Se deja FIJO (no
# es variable de diseño) porque su espesor casi no mueve la aguja frente a
# su superficie y su brazo, que sí son variables.
PERFIL_COLA = "naca0010"

# ---------------------------------------------------------------------
# FLAPS
# ---------------------------------------------------------------------
# Solo flap PLAIN (de contorno, sin ranura). No es una limitación de
# ambición sino de honestidad del modelo: el efecto del flap se calcula
# deflectando la geometría del perfil y evaluándola con NeuralFoil al
# Reynolds real del vuelo lento (ver `perfiles_avion.perfil_con_flap`), y esa
# técnica representa bien un flap de contorno. Un flap ranurado o Fowler
# tiene física que una deflexión de contorno NO captura (la ranura
# reenergiza la capa límite; el Fowler además AGRANDA la superficie), así
# que ofrecerlos sería prometer un CL_max que el modelo no puede sostener.
# Además, el flap plain es el realista para construcción artesanal.
FLAP_MIN_DEFL = 2.0   # [deg] por debajo de esto se considera que NO hay flap


# =====================================================================
# CATÁLOGO DE TOPOLOGÍAS
# =====================================================================
# `fuselaje` y `cola` eligen qué constructor compone cada topología -- así
# agregar una topología nueva es agregar una fila acá y (si hace falta) un
# constructor de cola, no duplicar el ala y el fuselaje otra vez.
TOPOLOGIAS = {
    "convencional": {
        "nombre": "Ala + fuselaje + cola convencional (cruciforme)",
        "referencia_real": "Motoveleros y UAV de fuselaje único; baseline estándar de diseño",
        "sm_band": (0.10, 0.20),
        "fuselaje": "completo",
        "cola": "convencional",
    },
    "t_tail": {
        "nombre": "Ala + fuselaje + cola en T",
        "referencia_real": "Planeadores y UAV con hélice propulsora; horizontal fuera del downwash",
        "sm_band": (0.10, 0.20),
        "fuselaje": "completo",
        "cola": "t",
    },
    "v_tail": {
        "nombre": "Ala + fuselaje + cola en V",
        "referencia_real": "Familia MQ-1 Predator (cola en V invertida)",
        "sm_band": (0.10, 0.20),
        "fuselaje": "completo",
        "cola": "v",
    },
    "doble_boom": {
        "nombre": "Ala + doble boom + doble estabilizador",
        "referencia_real": "Familia RQ-7 Shadow / ScanEagle-Integrator",
        "sm_band": (0.10, 0.20),
        "fuselaje": "corto",
        "cola": "doble_boom",
    },
    "pod_boom": {
        "nombre": "Motovelero: góndola corta + viga de cola + cola convencional",
        "referencia_real": "Arquitectura de planeador/motovelero (ej. Stemme S10, ASK 21)",
        "sm_band": (0.10, 0.20),
        "fuselaje": "pod_boom",
        "cola": "convencional",
    },
}

SM_BANDS = {t: TOPOLOGIAS[t]["sm_band"] for t in TOPOLOGIAS}


# =====================================================================
# BOUNDS -- ALA (compartido por todas las topologías)
# =====================================================================
BOUNDS_ALA = {
    # Envergadura: ahora es VARIABLE (ver punto 2 del encabezado). El techo
    # de 3.5 m no es aerodinámico sino logístico: por encima de eso el avión
    # deja de entrar desarmado en una camioneta y de ser lanzable a mano.
    "envergadura": (2.0, 3.5),

    # Cuerdas [m] en las 5 estaciones. Mínimo de FABRICACIÓN, no
    # aerodinámico: por debajo de ~15 cm el perfil se vuelve imposible de
    # construir con precisión y el Reynolds local se desploma.
    "root_chord": (0.16, 0.55),
    **{f"chord_{i}": (0.10, 0.55) for i in range(1, N_ESTACIONES)},

    # Borde de ataque: offset de cada estación como fracción de la
    # SEMI-envergadura (así el parámetro no cambia de significado cuando la
    # envergadura varía). Se proyecta a no decreciente en clamp_to_bounds.
    **{f"le_offset_{i}": (0.0, 0.14) for i in range(1, N_ESTACIONES)},

    # Torsión [deg] estación por estación. Rango que permite washout fuerte
    # (punta más descargada que la raíz) para que la punta no entre en
    # pérdida primero -- crítico ahora que hay que volar a 10 m/s.
    **{f"twist_{i}": (-6.0, 4.0) for i in range(N_ESTACIONES)},

    # Elevación (diedro/anedro) como fracción de la semi-envergadura. Se
    # proyecta a monótona: diedro o anedro, pero no una superficie ondulada.
    **{f"elev_{i}": (-0.06, 0.12) for i in range(1, N_ESTACIONES)},

    # Perfiles: tres anclas del catálogo COMPLETO del avión (19 perfiles,
    # incluidos los de alta sustentación). Ver perfiles_avion.py.
    "perfil_raiz": (0.0, float(N_CATALOGO_AVION - 1)),
    "perfil_medio": (0.0, float(N_CATALOGO_AVION - 1)),
    "perfil_punta": (0.0, float(N_CATALOGO_AVION - 1)),
    "perfil_pos_medio": (0.20, 0.80),

    # Winglets. `winglet_height` es el largo DESARROLLADO del panel (mismo
    # significado que en el ala volante). Por debajo de WINGLET_MIN_H se
    # considera que no hay winglet.
    "winglet_height": (0.0, 0.25),
    "winglet_cant_deg": (0.0, 70.0),
    "winglet_taper": (0.35, 1.0),
    "winglet_sweep_deg": (0.0, 45.0),
}

# =====================================================================
# BOUNDS -- FLAPS
# =====================================================================
BOUNDS_FLAP = {
    "flap_cuerda_frac": (0.15, 0.35),   # fracción de la cuerda local
    "flap_inicio_frac": (0.0, 0.35),    # fracción de la semi-envergadura
    "flap_fin_frac": (0.35, 0.95),      # idem (tiene que ser > inicio, se proyecta)
    "flap_defl_deg": (0.0, 40.0),       # deflexión en el punto de vuelo LENTO
}

# =====================================================================
# BOUNDS -- FUSELAJE
# =====================================================================
BOUNDS_FUSELAJE = {
    "fuselaje_largo": (0.55, 1.80),
    "fuselaje_diametro": (0.10, 0.24),
    # Morro: largo como fracción del fuselaje, y exponente de la ley de
    # radios r = R * s^exp. exp = 1 es un cono; exp -> 0.45 es un morro romo
    # de ojiva. Un morro romo tiene MÁS resistencia de presión a Mach alto
    # pero acá el Mach es 0.1, así que lo que manda es la superficie mojada y
    # el volumen útil para la carga.
    "morro_largo_frac": (0.10, 0.35),
    "morro_exp": (0.45, 1.00),
    # Boat-tail: largo como fracción del fuselaje, y radio final como
    # fracción del radio máximo. Que el radio final sea VARIABLE (y nunca 0)
    # es el arreglo concreto al "cono truncado" de la versión anterior.
    "boattail_largo_frac": (0.15, 0.45),
    "boattail_radio_frac": (0.10, 0.60),
    "ala_x_frac_fuselaje": (0.18, 0.55),
    "cg_frac_mac": (0.05, 0.50),
}

# =====================================================================
# BOUNDS -- COLAS
# =====================================================================
# Convencional y T comparten parametrización: cambia DÓNDE se monta el
# horizontal, no cómo se dimensiona.
_BOUNDS_COLA_HV = {
    "htail_span": (0.35, 0.95),
    "htail_root_chord": (0.10, 0.30),
    "htail_taper": (0.45, 1.0),
    "htail_sweep_deg": (0.0, 20.0),
    # LA variable de trim (ver punto 3 del encabezado). Negativa = borde de
    # ataque abajo, que es lo habitual en un avión estable (el horizontal
    # suele ir descargando).
    "htail_incidencia_deg": (-6.0, 2.0),
    "vstab_altura": (0.15, 0.40),
    "vstab_root_chord": (0.10, 0.30),
    "vstab_taper": (0.40, 1.0),
    "vstab_sweep_deg": (5.0, 35.0),
    "cola_arm_frac": (0.55, 0.95),
}

BOUNDS_CONVENCIONAL = {**BOUNDS_ALA, **BOUNDS_FLAP, **BOUNDS_FUSELAJE, **_BOUNDS_COLA_HV}

BOUNDS_T_TAIL = {**BOUNDS_CONVENCIONAL}

BOUNDS_V_TAIL = {
    **BOUNDS_ALA, **BOUNDS_FLAP, **BOUNDS_FUSELAJE,
    "v_tail_span": (0.35, 0.95),
    "v_tail_root_chord": (0.10, 0.30),
    "v_tail_taper": (0.45, 1.0),
    "v_dihedral_deg": (30.0, 50.0),
    "v_tail_sweep_deg": (5.0, 25.0),
    "v_tail_incidencia_deg": (-6.0, 2.0),
    "v_tail_arm_frac": (0.55, 0.95),
}

BOUNDS_DOBLE_BOOM = {
    **BOUNDS_ALA, **BOUNDS_FLAP, **BOUNDS_FUSELAJE,
    # El fuselaje del doble boom es CORTO: no lleva cola, solo carga y motor.
    "fuselaje_largo": (0.45, 1.00),
    "boom_largo": (0.35, 1.20),
    # Acotado respecto de la versión anterior (llegaba a 0.75). Con la
    # envergadura ahora variable y hasta 3.5 m, un boom muy afuera daba un
    # horizontal de superficie comparable al ala principal -- volumen de
    # cola absurdo, punto neutro imposible de alcanzar con el CG. Ver el
    # encabezado y `volumenes_de_cola()`.
    "boom_lateral_frac": (0.22, 0.55),
    "boom_diametro": (0.03, 0.07),
    # Diámetro del fuselaje corto ampliado respecto del BOUNDS_FUSELAJE común
    # (0.10-0.24): un fuselaje corto necesita poder ENGORDAR para alcanzar el
    # volumen útil mínimo (ver VOLUMEN_UTIL_MIN_L en mision_avion.py), porque
    # no puede alargarse tanto como el convencional. V = pi*R^2*L crece con
    # el CUADRADO del radio, así que es la palanca más barata que tiene esta
    # topología para no perder por empaquetamiento.
    "fuselaje_diametro": (0.10, 0.32),
    "htail_cuerda": (0.10, 0.24),
    "htail_incidencia_deg": (-6.0, 2.0),
    "vstab_altura": (0.12, 0.35),
    "vstab_cuerda": (0.10, 0.24),
    "vstab_taper": (0.40, 1.0),
}

BOUNDS_POD_BOOM = {
    **BOUNDS_ALA, **BOUNDS_FLAP, **BOUNDS_FUSELAJE, **_BOUNDS_COLA_HV,
    # Acá `fuselaje_largo` es la GÓNDOLA (pod), no el fuselaje entero: lleva
    # carga útil, batería y motor, y nada más. La cola la sostiene la viga.
    "fuselaje_largo": (0.35, 0.90),
    "boom_largo": (0.40, 1.30),
    "boom_diametro": (0.03, 0.08),
    # Mismo argumento que en doble_boom: la góndola es corta por diseño, así
    # que necesita poder engordar para alcanzar el volumen útil mínimo.
    "fuselaje_diametro": (0.10, 0.32),
}

BOUNDS_POR_TOPOLOGIA = {
    "convencional": BOUNDS_CONVENCIONAL,
    "t_tail": BOUNDS_T_TAIL,
    "v_tail": BOUNDS_V_TAIL,
    "doble_boom": BOUNDS_DOBLE_BOOM,
    "pod_boom": BOUNDS_POD_BOOM,
}


@dataclass
class CandidateAvion:
    topologia: str
    params: dict
    score: Optional[float] = None


def clamp_to_bounds_avion(params: dict, topologia: str) -> dict:
    """Recorta a BOUNDS y PROYECTA a una geometría fabricable.

    Se proyecta en vez de rechazar por la misma razón que en el ala volante:
    rechazar quema evaluaciones del GA en diseños inválidos, mientras que
    proyectar convierte cada hijo en el diseño fabricable más parecido.

    Tres proyecciones:
    - CUERDAS no crecientes de raíz a punta. El ala volante esto lo
      verificaba y RECHAZABA (`_ahusamiento_valido` en mision.py); acá se
      proyecta, que es estrictamente mejor: no se pierde la evaluación.
    - OFFSETS de borde de ataque no decrecientes (larguero recto: ver
      `optimizacion_ala.geometria.clamp_to_bounds`).
    - ELEVACIÓN monótona (diedro o anedro, no ondulada).
    """
    bounds = BOUNDS_POR_TOPOLOGIA[topologia]
    p = {k: min(max(params.get(k, lo), lo), hi) for k, (lo, hi) in bounds.items()}

    # Cuerdas no crecientes: se proyecta la secuencia INVERTIDA a no
    # decreciente y se vuelve a invertir.
    claves_c = ["root_chord"] + [f"chord_{i}" for i in range(1, N_ESTACIONES)]
    proy = _proyectar_no_decreciente([p[k] for k in reversed(claves_c)])[::-1]
    for k, v in zip(claves_c, proy):
        lo, hi = bounds[k]
        p[k] = min(max(v, lo), hi)

    claves_le = [f"le_offset_{i}" for i in range(1, N_ESTACIONES)]
    for k, v in zip(claves_le, _proyectar_no_decreciente([p[k] for k in claves_le])):
        lo, hi = bounds[k]
        p[k] = min(max(v, lo), hi)

    claves_e = [f"elev_{i}" for i in range(1, N_ESTACIONES)]
    for k, v in zip(claves_e, _proyectar_monotona([p[k] for k in claves_e])):
        lo, hi = bounds[k]
        p[k] = min(max(v, lo), hi)

    # El flap tiene que empezar antes de terminar. Si el GA los cruza, se
    # los separa por un mínimo en vez de invalidar el candidato.
    if p["flap_fin_frac"] <= p["flap_inicio_frac"] + 0.05:
        p["flap_fin_frac"] = min(bounds["flap_fin_frac"][1], p["flap_inicio_frac"] + 0.05)

    # Índices de perfil DISCRETOS: se redondean una sola vez acá, para que el
    # candidato guardado sea exactamente el que se evalúa.
    for k in ("perfil_raiz", "perfil_medio", "perfil_punta"):
        lo, hi = bounds[k]
        p[k] = float(min(max(round(p[k]), lo), hi))
    return p


# =====================================================================
# ALA PRINCIPAL
# =====================================================================
def semi_envergadura(params: dict) -> float:
    return 0.5 * float(params["envergadura"])


def _xsecs_ala(params: dict, x0: float = 0.0) -> list:
    """Secciones del ala principal, con el borde de ataque de la raíz en x0.

    5 estaciones de control; AeroBuildup interpola linealmente entre ellas,
    así que el borde de ataque resultante es una poligonal -- que es
    exactamente lo que se construye en la práctica con un larguero recto y
    nervaduras."""
    b2 = semi_envergadura(params)
    cuerdas = [params["root_chord"]] + [params[f"chord_{i}"] for i in range(1, N_ESTACIONES)]
    offs = [0.0] + [params[f"le_offset_{i}"] for i in range(1, N_ESTACIONES)]
    elevs = [0.0] + [params[f"elev_{i}"] for i in range(1, N_ESTACIONES)]
    twists = [params[f"twist_{i}"] for i in range(N_ESTACIONES)]

    xsecs = []
    for i in range(N_ESTACIONES):
        frac = float(_FRAC_ESTACION[i])
        xsecs.append(asb.WingXSec(
            xyz_le=[float(x0 + offs[i] * b2), float(frac * b2), float(elevs[i] * b2)],
            chord=float(cuerdas[i]),
            twist=float(twists[i]),
            airfoil=perfil_en_fraccion_avion(params, frac),
        ))
    return xsecs


def _xsecs_winglet_avion(params: dict, xsec_punta: asb.WingXSec) -> list:
    """Winglet a partir de la punta del ala. Reutiliza `camino_winglet` del
    ala volante (pura geometría del arco de transición) y arma las secciones
    acá, para no acoplarse a la firma interna de aquel módulo."""
    h = float(params.get("winglet_height", 0.0))
    if h < WINGLET_MIN_H:
        return []
    xyz_p = [float(v) for v in xsec_punta.xyz_le]
    camino = camino_winglet(params, xyz_p, n_filete=N_SECCIONES_FILETE)
    if not camino:
        return []
    c_punta = float(xsec_punta.chord)
    taper = float(params.get("winglet_taper", 1.0))
    af = xsec_punta.airfoil
    xsecs = []
    for (x, y, z, s) in camino:
        # Cuerda interpolada linealmente entre la punta del ala y la punta
        # del winglet, según cuánto se recorrió del largo desarrollado.
        xsecs.append(asb.WingXSec(
            xyz_le=[x, y, z],
            chord=c_punta * (1.0 - s * (1.0 - taper)),
            twist=float(xsec_punta.twist),
            airfoil=af,
        ))
    return xsecs


def construir_ala(params: dict, x0: float = 0.0) -> asb.Wing:
    xs = _xsecs_ala(params, x0)
    return asb.Wing(name="Ala principal", symmetric=True, xsecs=xs + _xsecs_winglet_avion(params, xs[-1]))


def _ala_de_referencia(params: dict) -> asb.Wing:
    """Ala SIN winglets, en x = 0, solo para sacar las magnitudes de
    referencia (S_ref, MAC, x_ac). Se excluye el winglet a propósito: si
    entrara, dos candidatos con winglets distintos dejarían de tener CL y CD
    comparables por estar referidos a superficies distintas."""
    return asb.Wing(name="ref", symmetric=True, xsecs=_xsecs_ala(params, 0.0))


def referencias_ala(params: dict):
    """(MAC, S_ref, b_ref, x_ac) del ala de referencia."""
    w = _ala_de_referencia(params)
    return (float(w.mean_aerodynamic_chord()), float(w.area()),
            float(w.span()), float(w.aerodynamic_center()[0]))


# =====================================================================
# FUSELAJE
# =====================================================================
def _fuselaje_completo(params: dict, largo: float) -> asb.Fuselage:
    """Morro de ley potencial + sección recta + boat-tail contraído.

    Morro:      r(s) = R * s^morro_exp           s: 0 -> 1 a lo largo del morro
    Boat-tail:  r(s) = R * (1 - (1-f) * s^1.5)   s: 0 -> 1 a lo largo del boat-tail

    El exponente 1.5 del boat-tail hace que la contracción arranque TANGENTE
    al cilindro (derivada nula en s=0) y se vaya cerrando -- que es la forma
    que no separa. Un cono, que es lo que había antes, arranca con un quiebre
    de pendiente en el hombro y ahí es donde se despega la capa límite."""
    R = 0.5 * float(params["fuselaje_diametro"])
    L_morro = float(params["morro_largo_frac"]) * largo
    L_boat = float(params["boattail_largo_frac"]) * largo
    L_recto = max(largo - L_morro - L_boat, 0.05 * largo)
    exp_m = float(params["morro_exp"])
    f_end = float(params["boattail_radio_frac"])

    xsecs = []
    for k in range(9):                                  # morro
        s = k / 8.0
        xsecs.append(asb.FuselageXSec(xyz_c=[float(s * L_morro), 0, 0],
                                      radius=float(R * s ** exp_m)))
    xsecs.append(asb.FuselageXSec(xyz_c=[float(L_morro + L_recto), 0, 0], radius=float(R)))
    for k in range(1, 8):                               # boat-tail
        s = k / 7.0
        xsecs.append(asb.FuselageXSec(
            xyz_c=[float(L_morro + L_recto + s * L_boat), 0, 0],
            radius=float(R * (1.0 - (1.0 - f_end) * s ** 1.5))))
    return asb.Fuselage(name="Fuselaje", xsecs=xsecs)


def _fuselaje_pod_boom(params: dict) -> asb.Fuselage:
    """Góndola corta que se contrae hasta el diámetro de la viga, y viga
    recta hasta la cola. Es la arquitectura de planeador: casi toda la
    superficie mojada está en la góndola, y la viga aporta el brazo de cola
    con muy poca superficie."""
    R = 0.5 * float(params["fuselaje_diametro"])
    r_boom = 0.5 * float(params["boom_diametro"])
    L_pod = float(params["fuselaje_largo"])
    L_boom = float(params["boom_largo"])
    L_morro = float(params["morro_largo_frac"]) * L_pod
    L_trans = float(params["boattail_largo_frac"]) * L_pod
    L_recto = max(L_pod - L_morro - L_trans, 0.05 * L_pod)
    exp_m = float(params["morro_exp"])

    xsecs = []
    for k in range(9):
        s = k / 8.0
        xsecs.append(asb.FuselageXSec(xyz_c=[float(s * L_morro), 0, 0],
                                      radius=float(R * s ** exp_m)))
    xsecs.append(asb.FuselageXSec(xyz_c=[float(L_morro + L_recto), 0, 0], radius=float(R)))
    for k in range(1, 8):                               # transición a la viga
        s = k / 7.0
        xsecs.append(asb.FuselageXSec(
            xyz_c=[float(L_morro + L_recto + s * L_trans), 0, 0],
            radius=float(R - (R - r_boom) * s ** 1.5)))
    xsecs.append(asb.FuselageXSec(xyz_c=[float(L_pod + L_boom), 0, 0], radius=float(r_boom)))
    return asb.Fuselage(name="Gondola + viga", xsecs=xsecs)


def _boom_lateral(params: dict, y: float, x_ini: float, x_fin: float, z: float, nombre: str) -> asb.Fuselage:
    """Una viga de cola lateral del doble boom, como cuerpo de revolución
    delgado. Se modela como fuselaje (y no se omite, como en la versión
    anterior) porque su superficie mojada es real y su resistencia también."""
    r = 0.5 * float(params["boom_diametro"])
    return asb.Fuselage(name=nombre, xsecs=[
        asb.FuselageXSec(xyz_c=[float(x_ini), float(y), float(z)], radius=float(0.35 * r)),
        asb.FuselageXSec(xyz_c=[float(x_ini + 0.10 * (x_fin - x_ini)), float(y), float(z)], radius=float(r)),
        asb.FuselageXSec(xyz_c=[float(x_fin), float(y), float(z)], radius=float(r)),
    ])


# =====================================================================
# COLAS
# =====================================================================
def _panel_horizontal(x, z, span, root_c, taper, sweep_deg, incid_deg, nombre) -> asb.Wing:
    af = cargar_perfil_avion(PERFIL_COLA)
    b2 = 0.5 * span
    return asb.Wing(name=nombre, symmetric=True, xsecs=[
        asb.WingXSec(xyz_le=[float(x), 0.0, float(z)], chord=float(root_c),
                     twist=float(incid_deg), airfoil=af),
        asb.WingXSec(xyz_le=[float(x + b2 * np.tan(np.radians(sweep_deg))), float(b2), float(z)],
                     chord=float(root_c * taper), twist=float(incid_deg), airfoil=af),
    ])


def _panel_vertical(x, y, z, altura, root_c, taper, sweep_deg, nombre) -> asb.Wing:
    af = cargar_perfil_avion(PERFIL_COLA)
    return asb.Wing(name=nombre, symmetric=False, xsecs=[
        asb.WingXSec(xyz_le=[float(x), float(y), float(z)], chord=float(root_c),
                     twist=0.0, airfoil=af),
        asb.WingXSec(xyz_le=[float(x + altura * np.tan(np.radians(sweep_deg))), float(y), float(z + altura)],
                     chord=float(root_c * taper), twist=0.0, airfoil=af),
    ])


def _cola_convencional(params, x_cola, z_ref, en_t=False) -> list:
    """Horizontal + vertical. Con `en_t`, el horizontal se monta EN LA PUNTA
    del vertical (cola en T) en vez de a la altura del fuselaje.

    Por qué la T puede ganar: el horizontal queda fuera del downwash del ala
    y de la estela de la hélice, así que rinde más por unidad de superficie.
    Por qué puede perder: el vertical pasa a cargar el horizontal en flexión
    y torsión, y eso lo paga en masa -- ver `estructura_avion.py`, donde la
    T lleva un factor de masa explícito. Si ese factor no estuviera, el GA
    elegiría la T por una ventaja que en la realidad no es gratis."""
    h_v = float(params["vstab_altura"])
    vert = _panel_vertical(x_cola, 0.0, z_ref, h_v, params["vstab_root_chord"],
                           params["vstab_taper"], params["vstab_sweep_deg"], "Deriva")
    if en_t:
        x_h = x_cola + h_v * float(np.tan(np.radians(params["vstab_sweep_deg"])))
        z_h = z_ref + h_v
    else:
        x_h, z_h = x_cola, z_ref
    horiz = _panel_horizontal(x_h, z_h, params["htail_span"], params["htail_root_chord"],
                              params["htail_taper"], params["htail_sweep_deg"],
                              params["htail_incidencia_deg"], "Estabilizador horizontal")
    return [horiz, vert]


def _cola_v(params, x_cola, z_ref) -> list:
    af = cargar_perfil_avion(PERFIL_COLA)
    dih = np.radians(float(params["v_dihedral_deg"]))
    swp = np.radians(float(params["v_tail_sweep_deg"]))
    b2 = 0.5 * float(params["v_tail_span"])
    y_t, z_t = b2 * np.cos(dih), b2 * np.sin(dih)
    inc = float(params["v_tail_incidencia_deg"])
    c_r = float(params["v_tail_root_chord"])
    return [asb.Wing(name="Cola en V", symmetric=True, xsecs=[
        asb.WingXSec(xyz_le=[float(x_cola), 0.0, float(z_ref)], chord=c_r, twist=inc, airfoil=af),
        asb.WingXSec(xyz_le=[float(x_cola + y_t * np.tan(swp)), float(y_t), float(z_ref + z_t)],
                     chord=float(c_r * params["v_tail_taper"]), twist=inc, airfoil=af),
    ])]


def _cola_doble_boom(params, x_cola, y_boom, z_boom) -> list:
    """Dos derivas sobre las vigas + un horizontal que va de viga a viga.
    El SPAN del horizontal no es variable de diseño: sale de dónde están las
    vigas, porque tiene que llegar de una a la otra."""
    af = cargar_perfil_avion(PERFIL_COLA)
    c_h = float(params["htail_cuerda"])
    inc = float(params["htail_incidencia_deg"])
    horiz = asb.Wing(name="Estabilizador horizontal", symmetric=True, xsecs=[
        asb.WingXSec(xyz_le=[float(x_cola), 0.0, float(z_boom)], chord=c_h, twist=inc, airfoil=af),
        asb.WingXSec(xyz_le=[float(x_cola), float(y_boom), float(z_boom)], chord=c_h, twist=inc, airfoil=af),
    ])
    derivas = [
        _panel_vertical(x_cola, signo * y_boom, z_boom, params["vstab_altura"],
                        params["vstab_cuerda"], params["vstab_taper"], 10.0, nombre)
        for signo, nombre in ((+1, "Deriva derecha"), (-1, "Deriva izquierda"))
    ]
    return [horiz] + derivas


# =====================================================================
# ENSAMBLADO
# =====================================================================
def construir_avion(params: dict, topologia: str) -> asb.Airplane:
    """Arma el `asb.Airplane` completo de una topología.

    Las magnitudes de referencia (S_ref, c_ref, b_ref) son SIEMPRE las del
    ala sola sin winglets -- ver `_ala_de_referencia`."""
    spec = TOPOLOGIAS[topologia]
    mac, s_ref, b_ref, x_ac = referencias_ala(params)

    L_fus = float(params["fuselaje_largo"])
    x_ala = float(params["ala_x_frac_fuselaje"]) * L_fus
    # El CG se mide sobre la MAC del ala YA UBICADA en el fuselaje. Omitir el
    # corrimiento x_ala fue un bug real de la versión anterior: dejaba el CG
    # cerca del morro y el margen estático daba > 100%.
    x_cg = x_ala + (x_ac - 0.25 * mac) + float(params["cg_frac_mac"]) * mac

    ala = construir_ala(params, x0=x_ala)
    alas = [ala]
    fuselajes = []

    if spec["fuselaje"] == "pod_boom":
        fuselajes.append(_fuselaje_pod_boom(params))
        x_fin = L_fus + float(params["boom_largo"])
    else:
        fuselajes.append(_fuselaje_completo(params, L_fus))
        x_fin = L_fus

    if spec["cola"] == "doble_boom":
        b2 = semi_envergadura(params)
        frac = float(params["boom_lateral_frac"])
        # Estación del ala donde nace la viga: se interpola la geometría del
        # ala en esa fracción para que la viga salga del borde de fuga real.
        cuerdas = [params["root_chord"]] + [params[f"chord_{i}"] for i in range(1, N_ESTACIONES)]
        offs = [0.0] + [params[f"le_offset_{i}"] for i in range(1, N_ESTACIONES)]
        elevs = [0.0] + [params[f"elev_{i}"] for i in range(1, N_ESTACIONES)]
        c_loc = float(np.interp(frac, _FRAC_ESTACION, cuerdas))
        x_le = x_ala + float(np.interp(frac, _FRAC_ESTACION, offs)) * b2
        z_loc = float(np.interp(frac, _FRAC_ESTACION, elevs)) * b2
        y_boom = frac * b2
        x_cola = x_le + c_loc + float(params["boom_largo"])
        alas += _cola_doble_boom(params, x_cola, y_boom, z_loc)
        for signo, nombre in ((+1, "Boom derecho"), (-1, "Boom izquierdo")):
            fuselajes.append(_boom_lateral(params, signo * y_boom, x_le, x_cola + params["htail_cuerda"],
                                           z_loc, nombre))
    else:
        # La cola en V tiene su propio parámetro de brazo (no comparte
        # BOUNDS con la convencional/T), así que se lee el que corresponda.
        clave_brazo = "v_tail_arm_frac" if spec["cola"] == "v" else "cola_arm_frac"
        x_cola = x_ala + float(params[clave_brazo]) * (x_fin - x_ala)
        if spec["cola"] == "v":
            alas += _cola_v(params, x_cola, 0.0)
        elif spec["cola"] == "t":
            alas += _cola_convencional(params, x_cola, 0.0, en_t=True)
        else:
            alas += _cola_convencional(params, x_cola, 0.0, en_t=False)

    return asb.Airplane(
        name=f"Candidate_{topologia}", xyz_ref=[x_cg, 0, 0],
        wings=alas, fuselages=fuselajes,
        s_ref=s_ref, c_ref=mac, b_ref=b_ref,
    )


# =====================================================================
# DIAGNÓSTICOS
# =====================================================================
def volumenes_de_cola(params: dict, topologia: str) -> dict:
    """Coeficientes de volumen de cola V_H y V_V del candidato.

        V_H = S_h * l_h / (S_ref * c_ref)     típico 0.5-0.7 en esta clase
        V_V = S_v * l_v / (S_ref * b_ref)     típico 0.02-0.05

    NO son restricciones (ver encabezado del módulo): se reportan para poder
    decir si el resultado cayó en territorio conocido. La cola en V se
    descompone en su proyección horizontal y vertical, que es la forma
    estándar de compararla contra una cola convencional."""
    avion = construir_avion(params, topologia)
    mac, s_ref, b_ref, _ = referencias_ala(params)
    x_cg = float(avion.xyz_ref[0])

    s_h = s_v = 0.0
    mom_h = mom_v = 0.0
    for w in avion.wings[1:]:
        area = float(w.area())
        x_w = float(w.aerodynamic_center()[0])
        # Inclinación media del panel respecto de la horizontal: separa
        # cuánto de la superficie trabaja como horizontal y cuánto como
        # deriva. Es exacto para paneles planos, que es lo que hay acá.
        #
        # OJO: NO se puede clasificar cada panel como "horizontal" O
        # "vertical" con un umbral. Una cola en V es genuinamente las dos
        # cosas a la vez, y clasificarla como horizontal (que es lo que hacía
        # la primera versión de esta función, con un umbral en 45°) dejaba
        # V_V = 0 para una configuración que evidentemente SÍ tiene
        # estabilidad direccional. Se reparte el área por proyección y se
        # acumulan los brazos PONDERADOS por esa misma proyección.
        dz = abs(float(w.xsecs[-1].xyz_le[2]) - float(w.xsecs[0].xyz_le[2]))
        dy = abs(float(w.xsecs[-1].xyz_le[1]) - float(w.xsecs[0].xyz_le[1]))
        ang = np.arctan2(dz, max(dy, 1e-9))
        ah = area * float(np.cos(ang)) ** 2
        av_ = area * float(np.sin(ang)) ** 2
        s_h += ah
        s_v += av_
        mom_h += ah * x_w
        mom_v += av_ * x_w

    x_h = mom_h / s_h if s_h > 1e-9 else x_cg
    x_v = mom_v / s_v if s_v > 1e-9 else x_cg
    l_h, l_v = max(x_h - x_cg, 1e-6), max(x_v - x_cg, 1e-6)
    return {
        "S_h": s_h, "S_v": s_v, "l_h": l_h, "l_v": l_v,
        "V_H": s_h * l_h / max(s_ref * mac, 1e-9),
        "V_V": s_v * l_v / max(s_ref * b_ref, 1e-9),
    }


def geometria_flap(params: dict) -> dict:
    """Datos del flap: fracción de la superficie del ala que lleva flap
    (es lo que escala el incremento de CL_max al pasar de 2D a 3D), y si
    el candidato efectivamente tiene flap."""
    defl = float(params.get("flap_defl_deg", 0.0))
    ini = float(params.get("flap_inicio_frac", 0.0))
    fin = float(params.get("flap_fin_frac", 0.0))
    if defl < FLAP_MIN_DEFL or fin <= ini:
        return {"tiene_flap": False, "frac_superficie": 0.0, "deflexion": 0.0,
                "cuerda_frac": float(params.get("flap_cuerda_frac", 0.0))}

    # Fracción de superficie: se integra la cuerda entre las dos estaciones
    # del flap y se divide por la integral total.
    b2 = semi_envergadura(params)
    fr = np.linspace(0.0, 1.0, 101)
    cuerdas = [params["root_chord"]] + [params[f"chord_{i}"] for i in range(1, N_ESTACIONES)]
    c = np.interp(fr, _FRAC_ESTACION, cuerdas)
    dentro = (fr >= ini) & (fr <= fin)
    trapz = getattr(np, "trapezoid", None) or np.trapz
    s_total = float(trapz(c, fr * b2))
    s_flap = float(trapz(np.where(dentro, c, 0.0), fr * b2))
    return {"tiene_flap": True, "frac_superficie": s_flap / max(s_total, 1e-9),
            "deflexion": defl, "cuerda_frac": float(params["flap_cuerda_frac"])}


CONSTRUCTORES = {t: (lambda p, _t=t: construir_avion(p, _t)) for t in TOPOLOGIAS}
