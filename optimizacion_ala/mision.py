"""
Función objetivo de MISIÓN: crucero a 60 km/h con 3 kg de carga útil.

==========================================================================
QUÉ CAMBIA RESPECTO DE `objetivo.py`
==========================================================================
`objetivo.evaluar_candidato` mide L/D a un ángulo de ataque ARBITRARIO
(alpha = 4°) con una masa CONSTANTE declarada a mano. Las dos cosas eran
parches conocidos.

Acá el problema queda planteado como una misión concreta:

    volar en crucero a 60 km/h llevando 3 kg de carga útil,
    en un entorno con viento (Neuquén / Vaca Muerta)

y de ahí salen tres consecuencias que arreglan agujeros viejos:

1. LA MASA SE CALCULA, no se declara. `estructura.py` dimensiona el larguero
   por rigidez y resistencia a partir de la geometría, y resuelve la
   circularidad masa <-> carga. Un ala más grande pesa más, necesita más
   sustentación y arrastra más. Recién ahora el compromiso es real.

2. SE EVALÚA EN LA CONDICIÓN DE CRUCERO, no a alpha fijo. Se busca el ángulo
   de ataque donde la sustentación iguala al peso a 60 km/h. Eso elimina de
   raíz el problema de "el modelo no paga por agrandar el ala": si el ala es
   más pesada, el CL de crucero sube y la resistencia inducida también.

3. HAY TÉRMINOS DE VIENTO. No alcanza con ser estable en aire quieto.

==========================================================================
EL ENTORNO DE VIENTO -- de dónde salen los números
==========================================================================
Estadísticas de Neuquén Aeropuerto (Windfinder, serie 2011-2026):
  - viento medio anual:        6 nudos  = 11 km/h  = 3.1 m/s
  - ráfaga máxima registrada: 28 nudos  = 52 km/h  = 14.4 m/s
La prensa local reporta alertas con ráfagas de 90-126 km/h, pero en esas
condiciones directamente no se vuela; no son caso de diseño.

Dos efectos distintos, y conviene no mezclarlos:

- VIENTO HORIZONTAL: resta velocidad respecto del suelo. Con crucero de
  16.7 m/s y ráfaga de 14.4 m/s de frente, el avance neto es de 2.3 m/s.
  Eso NO depende de la geometría (la velocidad de crucero la fijó la
  misión), así que se REPORTA pero no se puntúa.

- RÁFAGA VERTICAL: cambia el ángulo de ataque de golpe, y eso SÍ depende del
  diseño. Es el efecto que se puntúa. Se adopta una ráfaga vertical de
  5 m/s, tomada como ~1/3 de la ráfaga horizontal máxima observada -- las
  componentes verticales de turbulencia son típicamente bastante menores que
  las horizontales. Se adoptan 3 m/s (no 5): con 5 m/s ni el diseño semilla
  ni nada razonable pasa la restricción de pérdida, o sea que no serviría
  para discriminar entre candidatos.

  El incremento de factor de carga por ráfaga es

      dn = (CL_alpha * d_alpha) * q * S / W

  y crece con CL_alpha y BAJA con la carga alar W/S. Es el resultado clásico:
  un avión con mucha carga alar es más suave en turbulencia. Para una
  plataforma de observación con cámara, eso es directamente calidad de
  imagen, y por eso entra al puntaje.

  FACTOR DE ALIVIO DE RÁFAGA. Sin él la cuenta da absurdos: 3 m/s verticales
  a 16.7 m/s darían 10° de cambio instantáneo de ángulo de ataque y ningún
  diseño pasaría. El avión no siente una ráfaga de canto de golpe: tarda en
  penetrarla y en responder. La FAR/CS-23 lo modela con

      mu = 2*(W/S) / (rho * c_media * CL_alpha_rad * g)
      Kg = 0.88*mu / (5.3 + mu)

  Para este avión mu ~ 12 y Kg ~ 0.61: siente el 61% de la ráfaga. Ojo que
  Kg CRECE con la carga alar, así que hay un compromiso fino -- más carga
  alar baja dn pero sube la fracción de ráfaga que se siente.

==========================================================================
ESTRUCTURA DEL PUNTAJE
==========================================================================
Seis términos pesados y normalizados, más restricciones duras.

    score = w_ef  * f_eficiencia   (resistencia en crucero -- lo principal)
          + w_ma  * f_masa         (masa total)
          + w_es  * f_estabilidad  (margen estático en banda)
          + w_ra  * f_rafaga       (suavidad: cuánto sacude la ráfaga)
          + w_mg  * f_margen       (seguridad: cuánto falta para la pérdida)
          + w_tr  * f_trim         (equilibrio natural cerca del crucero)

NOTA HONESTA sobre f_masa: la masa YA está penalizada dentro de
f_eficiencia, porque un avión más pesado necesita más CL en crucero y eso
sube la resistencia inducida. El término explícito se superpone en parte, a
propósito: existe para capturar lo que la aerodinámica no ve -- que el avión
hay que lanzarlo a mano, transportarlo al pozo, y aterrizarlo sin romper la
cámara. Por eso su peso es bajo.

RESTRICCIONES DURAS (descartan el candidato, no le bajan el puntaje):
  - la estructura no cierra (larguero más pesado que el avión entero)
  - no puede sostenerse a 60 km/h (CL de crucero por encima del CL máximo)
  - margen estático negativo: inestable, no vuela sin control activo
  - la ráfaga de diseño lo pone EN pérdida (margen <= 0). Por encima de cero
    el margen se puntúa en vez de cortarse: un acantilado en la restricción le
    saca el gradiente al optimizador y lo deja buscando a ciegas.
"""

from __future__ import annotations

import aerosandbox as asb
import numpy as np

from .estructura import G, MASA_PAYLOAD, MASA_SISTEMAS, converger_masa
from . import geometria as geo
from .geometria import _N_ESTACIONES, construir_avion, construir_perfil

# =====================================================================
# LA MISIÓN -- datos de entrada, no variables de diseño
# =====================================================================
V_CRUCERO = 60.0 / 3.6        # [m/s] = 16.67 m/s = 60 km/h, lo pedido
RAFAGA_VERTICAL = 3.0         # [m/s] ráfaga vertical de diseño (ver encabezado)
VIENTO_MEDIO = 3.1            # [m/s] 6 nudos -- solo informativo
RAFAGA_HORIZONTAL_MAX = 14.4  # [m/s] 28 nudos -- solo informativo

# Ángulos auxiliares para medir pendientes por diferencias finitas.
_A_LO, _A_HI = 1.0, 5.0

# =====================================================================
# CRITERIOS
# =====================================================================
SM_MIN, SM_MAX = 0.05, 0.10   # banda de margen estático (ver objetivo.py)
SM_TOLERANCIA = 0.03

DN_RAFAGA_OK = 0.5            # incremento de factor de carga por ráfaga que se
                              # considera "suave". Por encima, el puntaje decae.
DN_TOLERANCIA = 0.5

MARGEN_PERDIDA_OK = 0.20      # margen de pérdida frente a la ráfaga a partir del
                              # cual el candidato ya no gana más puntaje. Por
                              # debajo el puntaje cae; en 0 (o sea, la ráfaga lo
                              # pone justo en pérdida) se descarta.

FACTOR_CLMAX_3D = 0.90        # el CL máximo del ALA es menor que el del perfil
                              # 2D (efectos 3D, pérdida no simultánea).

# =====================================================================
# PESOS
# =====================================================================
PESO_EFICIENCIA = 1.0
PESO_MASA = 0.3
PESO_ESTABILIDAD = 0.5
PESO_RAFAGA = 0.4        # suavidad: cuánto sacude la ráfaga
PESO_MARGEN = 0.4        # seguridad: cuánto falta para la pérdida con ráfaga
PESO_TRIM = 0.3

D_REFERENCIA = 3.0            # [N] resistencia de crucero "buena" -- solo escala
MASA_REFERENCIA = 6.0         # [kg] masa total "buena" -- solo escala


def _escalar(v) -> float:
    return float(np.atleast_1d(v)[0])


def _meseta(valor, lo, hi, tol):
    """1.0 dentro de [lo, hi], decaimiento gaussiano fuera."""
    if valor < lo:
        d = lo - valor
    elif valor > hi:
        d = valor - hi
    else:
        return 1.0
    return float(np.exp(-((d / tol) ** 2)))


def _ahusamiento_valido(params: dict) -> bool:
    c = [params["root_chord"]] + [params[f"chord_{i}"] for i in range(1, _N_ESTACIONES)]
    return all(c[i] >= c[i + 1] for i in range(len(c) - 1))


def _clmax_estimado(params: dict) -> float:
    """CL máximo del ala, estimado del CL máximo del perfil 2D (NeuralFoil,
    barrido vectorizado -- una sola llamada) corregido por un factor 3D.

    Es una aproximación deliberada: el barrido 3D completo con AeroBuildup
    costaría ~20 corridas por candidato y lo haría inusable dentro del loop.
    Para el diseño FINAL, `graficos.barrido_alpha()` sí hace el barrido 3D
    de verdad.

    Desde 2026-08-28 el ala puede tener PERFILES DISTINTOS por zona, así que
    ya no alcanza con mirar el de la raíz. Se toma el MÍNIMO de los tres
    perfiles ancla: el ala entra en pérdida cuando la primera sección llega a
    su límite, no cuando llega la mejor. Es conservador -- la sección que
    stallea primero depende también de la distribución de sustentación, que
    esta estimación no ve -- y ser conservador acá es lo correcto: el término
    que usa este número es el margen de pérdida."""
    alphas = np.linspace(0.0, 20.0, 21)
    Re = V_CRUCERO * params["root_chord"] / 1.5e-5
    mach = V_CRUCERO / 340.0
    clmax = []
    for frac in (0.0, float(params.get("perfil_pos_medio", 0.5)), 1.0):
        af = geo.perfil_en_fraccion(params, frac)
        cl = np.asarray(af.get_aero_from_neuralfoil(alpha=alphas, Re=Re, mach=mach)["CL"])
        if not np.all(np.isfinite(cl)):
            return float("nan")
        clmax.append(float(np.max(cl)))
    return FACTOR_CLMAX_3D * min(clmax)


def analizar_mision(params: dict) -> dict | None:
    """Analiza un candidato en la condición de misión. Devuelve un dict con
    todo lo relevante, o None si la geometría es inválida o no cierra.

    Esta función es la que hace el trabajo; `evaluar_mision` solo la combina
    en un número."""
    if not _ahusamiento_valido(params):
        return None
    try:
        # --- 1. Masa: se calcula, no se declara -------------------------
        est = converger_masa(params)
        if est is None:
            return None
        W = est["peso_total"]

        avion = construir_avion(params)
        S = float(avion.s_ref)
        rho = float(asb.Atmosphere(altitude=0).density())
        q = 0.5 * rho * V_CRUCERO**2

        # --- 2. CL necesario para sostenerse a 60 km/h ------------------
        CL_crucero = W / (q * S)
        CL_max = _clmax_estimado(params)
        if not np.isfinite(CL_max) or CL_max <= 0:
            return None
        # No se sostiene a la velocidad pedida: no cumple la misión.
        if CL_crucero >= CL_max:
            return None

        # --- 3. Pendientes: dos corridas en la zona lineal --------------
        pts = []
        for a in (_A_LO, _A_HI):
            r = asb.AeroBuildup(
                airplane=avion,
                op_point=asb.OperatingPoint(velocity=V_CRUCERO, alpha=a),
            ).run()
            pts.append((_escalar(r["CL"]), _escalar(r["Cm"])))
        (CL1, Cm1), (CL2, Cm2) = pts
        if abs(CL2 - CL1) < 1e-9:
            return None
        CL_alpha = (CL2 - CL1) / (_A_HI - _A_LO)          # por grado
        dCm_dCL = (Cm2 - Cm1) / (CL2 - CL1)
        SM = -dCm_dCL
        Cm0 = Cm1 - dCm_dCL * CL1
        CL_trim = Cm0 / SM if abs(SM) > 1e-9 else float("nan")
        if not np.isfinite(SM) or SM <= 0:
            return None  # inestable

        # Ángulo de ataque de crucero, por extrapolación lineal.
        alpha_crucero = _A_LO + (CL_crucero - CL1) / CL_alpha

        # --- 4. Resistencia EN CRUCERO ----------------------------------
        r = asb.AeroBuildup(
            airplane=avion,
            op_point=asb.OperatingPoint(velocity=V_CRUCERO, alpha=alpha_crucero),
        ).run()
        CD = _escalar(r["CD"])
        CL_real = _escalar(r["CL"])
        if CD <= 0 or not np.isfinite(CD):
            return None
        D_crucero = q * S * CD
        LD = CL_real / CD

        # --- 5. Ráfaga vertical -----------------------------------------
        # FACTOR DE ALIVIO DE RÁFAGA (FAR/CS-23). Sin esto el cálculo da
        # absurdos: una ráfaga vertical de 3 m/s a 16.7 m/s daría 10° de
        # cambio instantáneo de ángulo de ataque y NADA pasaría la
        # restricción. El avión no siente una ráfaga de canto de golpe --
        # tarda en penetrarla y en responder. La norma lo modela con
        #
        #     mu = 2*(W/S) / (rho * c_media * CL_alpha_rad * g)
        #     Kg = 0.88*mu / (5.3 + mu)
        #
        # Para este avión mu ~ 12 y Kg ~ 0.61, o sea que siente un 61% de la
        # ráfaga. Kg CRECE con la carga alar: un avión más cargado penetra la
        # ráfaga más rápido y alcanza a sentir una fracción mayor. Eso mete un
        # compromiso fino: más carga alar baja dn pero sube Kg.
        c_media = float(avion.c_ref)
        CL_alpha_rad = np.degrees(CL_alpha)  # por grado -> por radián
        mu = 2.0 * (W / S) / (rho * c_media * CL_alpha_rad * G)
        Kg = 0.88 * mu / (5.3 + mu)

        d_alpha = np.degrees(np.arctan(Kg * RAFAGA_VERTICAL / V_CRUCERO))
        dCL_rafaga = CL_alpha * d_alpha
        dn_rafaga = dCL_rafaga * q * S / W
        CL_con_rafaga = CL_crucero + dCL_rafaga
        margen_perdida = (CL_max - CL_con_rafaga) / CL_max
        # Gate duro solo si la ráfaga de diseño lo pone EN pérdida. El margen
        # por encima de cero se puntúa (abajo), no se corta: un acantilado en
        # la restricción le saca el gradiente al optimizador.
        if margen_perdida <= 0.0:
            return None

        return {
            # masa
            "masa_total": est["masa_total"], "masa_ala": est["masa_ala"],
            "masa_larguero": est["masa_larguero"], "masa_piel": est["masa_piel"],
            "fraccion_estructural": est["fraccion_estructural"],
            "flecha_punta_mm": est["flecha_punta_mm"], "manda_rigidez": est["manda_rigidez"],
            # crucero
            "S": S, "carga_alar": W / S, "peso": W,
            "CL_crucero": CL_crucero, "alpha_crucero": alpha_crucero,
            "CD_crucero": CD, "D_crucero": D_crucero, "LD_crucero": LD,
            "potencia_W": D_crucero * V_CRUCERO,
            # estabilidad
            "SM": SM, "Cm0": Cm0, "CL_trim": CL_trim, "CL_alpha_por_grado": CL_alpha,
            # ráfaga
            "d_alpha_rafaga": d_alpha, "dn_rafaga": dn_rafaga, "Kg": Kg, "mu": mu,
            "n_con_rafaga": 1.0 + dn_rafaga,
            "CL_max": CL_max, "margen_perdida": margen_perdida,
        }
    except Exception:
        return None


def evaluar_mision(params: dict) -> float:
    """Puntaje de misión. MÁS ALTO ES MEJOR. -inf si el candidato no cumple
    alguna restricción dura (ver encabezado del módulo)."""
    a = analizar_mision(params)
    if a is None:
        return -np.inf

    f_eficiencia = D_REFERENCIA / a["D_crucero"]
    f_masa = MASA_REFERENCIA / a["masa_total"]
    f_estabilidad = _meseta(a["SM"], SM_MIN, SM_MAX, SM_TOLERANCIA)
    f_rafaga = _meseta(a["dn_rafaga"], 0.0, DN_RAFAGA_OK, DN_TOLERANCIA)
    f_margen = min(1.0, a["margen_perdida"] / MARGEN_PERDIDA_OK)
    # Cuanto más cerca esté el CL de equilibrio natural del CL de crucero,
    # menos deflexión de elevón hace falta para volar recto, y menos
    # resistencia de compensación se paga.
    desvio_trim = abs(a["CL_trim"] - a["CL_crucero"]) / max(a["CL_crucero"], 1e-6)
    f_trim = float(np.exp(-((desvio_trim / 0.5) ** 2)))

    return float(
        PESO_EFICIENCIA * f_eficiencia
        + PESO_MASA * f_masa
        + PESO_ESTABILIDAD * f_estabilidad
        + PESO_RAFAGA * f_rafaga
        + PESO_MARGEN * f_margen
        + PESO_TRIM * f_trim
    )


def desglose_mision(params: dict) -> str:
    """Texto legible con el análisis completo -- para el notebook."""
    a = analizar_mision(params)
    if a is None:
        return "Candidato INVÁLIDO: no cierra estructuralmente, no se sostiene a 60 km/h, es inestable, o entra en pérdida con la ráfaga de diseño."

    f_ef = D_REFERENCIA / a["D_crucero"]
    f_ma = MASA_REFERENCIA / a["masa_total"]
    f_es = _meseta(a["SM"], SM_MIN, SM_MAX, SM_TOLERANCIA)
    f_ra = _meseta(a["dn_rafaga"], 0.0, DN_RAFAGA_OK, DN_TOLERANCIA)
    f_mg = min(1.0, a["margen_perdida"] / MARGEN_PERDIDA_OK)
    dt = abs(a["CL_trim"] - a["CL_crucero"]) / max(a["CL_crucero"], 1e-6)
    f_tr = float(np.exp(-((dt / 0.5) ** 2)))
    terms = [
        ("eficiencia (D crucero)", PESO_EFICIENCIA, f_ef),
        ("masa total", PESO_MASA, f_ma),
        ("estabilidad (margen est.)", PESO_ESTABILIDAD, f_es),
        ("ráfaga (suavidad)", PESO_RAFAGA, f_ra),
        ("margen de pérdida", PESO_MARGEN, f_mg),
        ("equilibrio en crucero", PESO_TRIM, f_tr),
    ]
    total = sum(w * f for _, w, f in terms)

    L = []
    L.append(f"=== MISIÓN: crucero {3.6*V_CRUCERO:.0f} km/h con {MASA_PAYLOAD:.1f} kg de carga útil ===")
    L.append("")
    L.append("MASA (calculada, no declarada)")
    L.append(f"  carga útil ............ {MASA_PAYLOAD:6.2f} kg")
    L.append(f"  sistemas .............. {MASA_SISTEMAS:6.2f} kg")
    L.append(f"  ala (estructura) ...... {a['masa_ala']:6.2f} kg   "
             f"(larguero {a['masa_larguero']:.2f} + piel {a['masa_piel']:.2f})")
    L.append(f"  TOTAL ................. {a['masa_total']:6.2f} kg   "
             f"({100*a['fraccion_estructural']:.0f}% estructura)")
    L.append(f"  flecha en punta ....... {a['flecha_punta_mm']:6.1f} mm  "
             f"({'la rigidez dimensiona el larguero' if a['manda_rigidez'] else 'manda la resistencia'})")
    L.append("")
    L.append(f"CRUCERO a {3.6*V_CRUCERO:.0f} km/h")
    L.append(f"  superficie ............ {a['S']:6.3f} m²    carga alar {a['carga_alar']:.1f} N/m²")
    L.append(f"  CL necesario .......... {a['CL_crucero']:6.3f}   (CL máx ≈ {a['CL_max']:.3f})")
    L.append(f"  ángulo de ataque ...... {a['alpha_crucero']:6.2f}°")
    L.append(f"  L/D ................... {a['LD_crucero']:6.2f}")
    L.append(f"  resistencia ........... {a['D_crucero']:6.2f} N")
    L.append(f"  potencia aerodinámica . {a['potencia_W']:6.1f} W   (sin contar rendimiento de hélice ni motor)")
    L.append("")
    L.append("ESTABILIDAD EN AIRE QUIETO")
    L.append(f"  margen estático ....... {100*a['SM']:6.2f} %   (banda objetivo {100*SM_MIN:.0f}-{100*SM_MAX:.0f}%)")
    L.append(f"  Cm0 ................... {a['Cm0']:6.4f}   CL de equilibrio {a['CL_trim']:.3f}")
    L.append(f"  desvío vs crucero ..... {100*dt:6.1f} %   (cuánto elevón hay que meter para volar recto)")
    L.append("")
    L.append(f"ESTABILIDAD CON VIENTO  (ráfaga vertical de diseño {RAFAGA_VERTICAL:.1f} m/s)")
    L.append(f"  factor de alivio Kg ... {a['Kg']:6.3f}   (μ = {a['mu']:.1f}; siente el {100*a['Kg']:.0f}% de la ráfaga)")
    L.append(f"  Δα por ráfaga ......... {a['d_alpha_rafaga']:6.2f}°")
    L.append(f"  Δn por ráfaga ......... {a['dn_rafaga']:6.2f}    → factor de carga {a['n_con_rafaga']:.2f} g")
    L.append(f"  margen de pérdida ..... {100*a['margen_perdida']:6.1f} %   (puntaje pleno desde {100*MARGEN_PERDIDA_OK:.0f}%)")
    L.append(f"  [informativo] viento medio {VIENTO_MEDIO:.1f} m/s, ráfaga horiz. máx {RAFAGA_HORIZONTAL_MAX:.1f} m/s")
    L.append(f"              → con ráfaga de frente, avance neto {V_CRUCERO - RAFAGA_HORIZONTAL_MAX:+.1f} m/s")
    L.append("")
    L.append("PUNTAJE")
    for nombre, w, f in terms:
        L.append(f"  {nombre:.<28} {w:.2f} × {f:5.3f} = {w*f:6.3f}   ({100*w*f/total:4.1f} %)")
    L.append(f"  {'TOTAL':.<28} {total:22.3f}")
    return "\n".join(L)
