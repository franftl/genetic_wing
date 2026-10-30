"""
Modelo estructural: estima la masa del ala a partir de su geometría.

==========================================================================
POR QUÉ ESTE MÓDULO CAMBIA EL PROBLEMA
==========================================================================
Hasta ahora la masa era una constante declarada a mano (`MASA_TOTAL = 3 kg`).
Con eso, el optimizador no pagaba NADA por hacer el ala más grande: más
envergadura y más cuerda mejoraban el L/D gratis. Por eso la envergadura tuvo
que quedar fija -- era una dirección degenerada.

Acá la masa pasa a DEPENDER de la geometría, y eso cierra el círculo: un ala
más grande o más esbelta tiene más momento flector en la raíz, necesita
larguero más pesado, pesa más, necesita más sustentación, y genera más
resistencia inducida. Recién con esto el compromiso aerodinámico-estructural
es real y no un adorno.

==========================================================================
EL MODELO -- qué hace y qué NO hace
==========================================================================
Tres contribuciones:

1. LARGUERO (spar caps), dimensionado por FLEXIÓN. Es la parte que de verdad
   depende de la forma del ala:

       l(y)  = carga por unidad de envergadura, supuesta proporcional a la
               cuerda local (aproximación razonable para un ala ahusada)
       M(y)  = integral del momento flector desde la estación y hasta la punta
       h(y)  = ESPESOR_FRAC * c(y)  = altura disponible del larguero
       A(y)  = M(y) / (sigma_adm * h(y))   = área de cada cordón (arriba/abajo)
       masa  = 2 cordones * 2 alas * rho * integral de A(y) dy

   La dependencia clave está en `h(y)`: un ala de cuerda chica tiene poca
   altura de larguero, y el área necesaria crece como 1/h. Por eso achicar
   cuerdas para ganar alargamiento no sale gratis.

2. RECUBRIMIENTO: masa por unidad de superficie mojada. Escala con el tamaño
   del ala pero no con la carga.

3. WINGLETS: mismo criterio de recubrimiento sobre su superficie, sin
   larguero dimensionado (son superficies chicas y poco cargadas comparadas
   con el ala).

LO QUE EL MODELO NO CONTEMPLA, y conviene tener presente al leer resultados:
- Nervaduras, encastres, herrajes de elevón, cableado: se cubren con un
  factor global `FACTOR_DETALLES`, que es un fudge factor honesto, no un
  cálculo.
- Pandeo del recubrimiento, torsión, flameo (flutter). Un ala muy esbelta y
  fina puede ser aceptable en flexión y aun así ser inviable por torsión o
  flutter. ESTE MODELO NO LO VE.
- La distribución de sustentación real (elíptica-ish) no es exactamente
  proporcional a la cuerda; para un ala ahusada la aproximación es razonable
  pero no exacta.

Es un modelo de PREDIMENSIONAMIENTO. Sirve para que el optimizador sienta el
compromiso correcto, no para firmar un plano.
"""

from __future__ import annotations

# numpy puro, NO aerosandbox.numpy: el trapz de aerosandbox tiene otra firma
# (trapz(x, modify_endpoints) -- no integra contra un eje x) y rompe silenciosamente.
import numpy as np

from .geometria import (
    ESPESOR_FRAC,
    HALF_SPAN,
    WINGLET_MIN_H,
    distribucion_envergadura,
    elevacion_envergadura,
    perfil_en_fraccion,
)

G = 9.81  # [m/s^2]


def espesor_en_estaciones(params: dict, n: int):
    """Espesor relativo (fracción de cuerda) en cada estación, LEÍDO DEL PERFIL
    que va en esa estación.

    Antes esto era un parámetro declarado (`params["espesor"]`), lo que dejaba
    el modelo internamente inconsistente: a NeuralFoil se le pasaba un perfil
    con una forma y al larguero se le daba una altura de otra. Ahora la altura
    del larguero es la del perfil que realmente está ahí -- que además ya no es
    constante a lo largo del ala, porque el perfil cambia."""
    fr = np.linspace(0.0, 1.0, n)
    try:
        return np.array([float(perfil_en_fraccion(params, f).max_thickness()) for f in fr])
    except Exception:
        # Respaldo para dicts viejos, sin selección de perfil.
        return np.full(n, params.get("espesor", ESPESOR_FRAC))


def _coordenada_desarrollada(y, z):
    """Coordenada a lo largo de la SUPERFICIE del ala, no de la proyección
    horizontal. Con diedro, el ala es más larga de lo que mide su envergadura
    proyectada, y esa diferencia es material real que pesa. Sin esto, poner
    diedro saldría gratis."""
    ds = np.sqrt(np.diff(y) ** 2 + np.diff(z) ** 2)
    return np.concatenate([[0.0], np.cumsum(ds)])


def _acumular(valores, x):
    """Integral acumulada (trapecio) -- devuelve un array del mismo largo,
    empezando en 0. Se usa para integrar dos veces la curvatura y obtener la
    flecha del ala."""
    d = np.diff(x)
    incr = 0.5 * (valores[1:] + valores[:-1]) * d
    return np.concatenate([[0.0], np.cumsum(incr)])


def _integrar(valores, x):
    """Integral trapezoidal. numpy >= 2.0 renombro trapz -> trapezoid; esto
    funciona con las dos versiones."""
    f = getattr(np, "trapezoid", None) or np.trapz
    return float(f(valores, x))

# =====================================================================
# PROPIEDADES DE MATERIALES Y CRITERIOS -- datos de entrada, editables
# =====================================================================
# Cordones de larguero: fibra de carbono unidireccional.
RHO_LARGUERO = 1600.0        # densidad [kg/m^3]
SIGMA_ADM = 600e6            # tensión admisible de trabajo [Pa]. Un UD de
                             # carbono rompe cerca de 1.5-2 GPa; 600 MPa deja
                             # margen para defectos de fabricación artesanal,
                             # fatiga y concentraciones de tensión.

# Recubrimiento: núcleo de espuma + laminado de vidrio/carbono.
MASA_AREAL_PIEL = 0.80       # [kg/m^2] de superficie mojada

# Módulo elástico de los cordones (carbono UD) y criterio de RIGIDEZ.
E_LARGUERO = 130e9           # [Pa]
FLECHA_MAX_FRAC = 0.05       # flecha en punta admisible a carga LÍMITE, como
                             # fracción de la semi-envergadura. 5% es un
                             # criterio habitual en modelos: más que eso y el
                             # ala se siente "blanda", empeora la respuesta de
                             # los elevones y acerca el riesgo de flameo.

# Todo lo que el modelo no calcula explícitamente: nervaduras, encastre de
# semialas, herrajes de elevón, cableado, pegamentos. Es un factor honesto,
# no un cálculo.
FACTOR_DETALLES = 1.25

# Factor de carga último de diseño. n_lim = 3.0 es razonable para un UAV de
# vigilancia (no acrobático) que debe aguantar ráfagas y maniobras suaves;
# 1.5 es el coeficiente de seguridad clásico sobre el límite.
N_LIMITE = 3.0
FACTOR_SEGURIDAD = 1.5
N_ULTIMO = N_LIMITE * FACTOR_SEGURIDAD  # = 4.5

# =====================================================================
# MASAS FIJAS -- no dependen de la geometría
# =====================================================================
MASA_PAYLOAD = 3.0    # [kg] carga útil pedida (cámara/sensor), aparte del avión
MASA_SISTEMAS = 1.5   # [kg] motor + ESC + hélice + batería + servos + piloto
                      # automático + receptor. Estimación para esta escala.


def masa_estructura(params: dict, masa_total_supuesta: float) -> dict:
    """Masa estructural del ala para una masa total supuesta.

    Se necesita `masa_total_supuesta` porque el momento flector depende del
    peso que el ala tiene que sostener -- de ahí la circularidad que resuelve
    `converger_masa()`.

    Devuelve un desglose para que el notebook pueda mostrar de dónde sale
    cada kilo."""
    y_proy, cuerda, _, _ = distribucion_envergadura(params, n=40)
    z_elev = elevacion_envergadura(params, n=40)
    # Se integra a lo largo de la superficie del ala (coordenada desarrollada),
    # no de la envergadura proyectada: con diedro no son lo mismo.
    y = _coordenada_desarrollada(y_proy, z_elev)

    W_ult = N_ULTIMO * masa_total_supuesta * G  # carga última sobre las DOS alas

    # Carga por unidad de envergadura, proporcional a la cuerda local.
    integral_cuerda = _integrar(cuerda, y)
    if integral_cuerda <= 0:
        return None
    carga_lineal = (W_ult / 2.0) * cuerda / integral_cuerda  # [N/m] en UNA semiala

    # Momento flector: M(y) = integral desde y hasta la punta de l(y')*(y'-y) dy'
    momento = np.array([
        _integrar(carga_lineal[i:] * (y[i:] - y[i]), y[i:]) if i < len(y) - 1 else 0.0
        for i in range(len(y))
    ])

    # Área de cada cordón: A = M / (sigma * h), con h = altura del larguero =
    # espesor del perfil. Usa el espesor de DISEÑO, no la constante: si el
    # optimizador engorda el perfil, gana altura de larguero y ahorra masa.
    h = espesor_en_estaciones(params, len(cuerda)) * cuerda
    area_cordon = momento / (SIGMA_ADM * np.maximum(h, 1e-6))

    # --- Criterio de RIGIDEZ ---------------------------------------------
    # En un ala de modelo el larguero casi nunca lo dimensiona la resistencia,
    # lo dimensiona la DEFORMACIÓN. La flecha en punta va como b^3, así que
    # este criterio es el que hace que un ala muy esbelta pague de verdad --
    # con resistencia sola, el larguero pesaba gramos y la envergadura salía
    # casi gratis.
    #
    # Se calcula la flecha con el larguero dimensionado por resistencia y, si
    # se pasa del límite, se escala el área. Como la flecha va con 1/I y I es
    # proporcional al área de los cordones, escalar el área por k divide la
    # flecha por k: el ajuste es directo, sin iterar.
    area_resistencia = np.maximum(area_cordon, 1e-12)
    # Dos cordones separados h: I = 2 * A * (h/2)^2 = A*h^2/2
    inercia = area_resistencia * h**2 / 2.0
    # Flecha a carga LÍMITE (no última): la rigidez se juzga en vuelo normal.
    curvatura = (momento / FACTOR_SEGURIDAD) / (E_LARGUERO * np.maximum(inercia, 1e-16))
    giro = _acumular(curvatura, y)
    flecha = _acumular(giro, y)
    flecha_punta = float(flecha[-1])

    flecha_admisible = FLECHA_MAX_FRAC * float(y[-1])
    factor_rigidez = max(1.0, flecha_punta / flecha_admisible) if flecha_admisible > 0 else 1.0
    area_cordon = area_resistencia * factor_rigidez

    # 2 cordones (arriba/abajo) * 2 semialas
    masa_larguero = 4.0 * RHO_LARGUERO * _integrar(area_cordon, y)

    # Recubrimiento: superficie mojada ~ 2.05 * superficie en planta.
    area_planta = 2.0 * _integrar(cuerda, y)  # las dos semialas
    masa_piel = MASA_AREAL_PIEL * 2.05 * area_planta

    # Winglets
    masa_winglet = 0.0
    if params["winglet_height"] >= WINGLET_MIN_H:
        cuerda_media_wl = 0.5 * cuerda[-1] * (1.0 + params["winglet_taper"])
        # `winglet_height` es el largo DESARROLLADO del winglet, así que esta
        # área sigue siendo correcta con transición por radio: el radio curva
        # el winglet pero no le agrega superficie (ver geometria._xsecs_winglet).
        area_wl = 2.0 * params["winglet_height"] * cuerda_media_wl  # dos winglets
        masa_winglet = MASA_AREAL_PIEL * 2.05 * area_wl

    masa_ala = FACTOR_DETALLES * (masa_larguero + masa_piel + masa_winglet)

    return {
        "masa_ala": masa_ala,
        "masa_larguero": FACTOR_DETALLES * masa_larguero,
        "masa_piel": FACTOR_DETALLES * masa_piel,
        "masa_winglet": FACTOR_DETALLES * masa_winglet,
        "momento_raiz": float(momento[0]),
        "area_planta": area_planta,
        "flecha_punta_mm": 1000.0 * flecha_punta / max(factor_rigidez, 1e-9),
        "manda_rigidez": bool(factor_rigidez > 1.0),
        "factor_rigidez": float(factor_rigidez),
    }


def converger_masa(params: dict, tol: float = 1e-4, max_iter: int = 30) -> dict | None:
    """Resuelve la circularidad masa <-> carga por iteración de punto fijo.

    La estructura pesa según la carga, y la carga es el peso total, que
    incluye la estructura. Se arranca de una estimación y se itera hasta que
    la masa deja de moverse. Converge rápido porque el ala es una fracción
    moderada del total.

    Devuelve None si diverge (geometría absurda que no cierra
    estructuralmente): un ala que necesita un larguero más pesado que todo el
    avión no es un diseño."""
    m_total = MASA_PAYLOAD + MASA_SISTEMAS + 1.0  # semilla
    for _ in range(max_iter):
        est = masa_estructura(params, m_total)
        if est is None:
            return None
        nueva = MASA_PAYLOAD + MASA_SISTEMAS + est["masa_ala"]
        if not np.isfinite(nueva) or nueva > 50.0:
            return None  # no cierra: el larguero se come el avión
        if abs(nueva - m_total) < tol:
            m_total = nueva
            break
        m_total = nueva
    else:
        return None  # no convergió

    est = masa_estructura(params, m_total)
    if est is None:
        return None
    return {
        **est,
        "masa_total": m_total,
        "masa_payload": MASA_PAYLOAD,
        "masa_sistemas": MASA_SISTEMAS,
        "peso_total": m_total * G,
        "fraccion_estructural": est["masa_ala"] / m_total,
    }
