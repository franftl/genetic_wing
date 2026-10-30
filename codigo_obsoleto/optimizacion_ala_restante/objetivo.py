"""
Función objetivo -- lo que la optimización intenta maximizar.

==========================================================================
CAMBIO IMPORTANTE (2026-08-26): se pasó de VLM invíscido a AeroBuildup
==========================================================================
Hasta esta versión el objetivo usaba `asb.VortexLatticeMethod`, que es un
método INVÍSCIDO: su CD es solo resistencia inducida. Como la inducida es
proporcional a CL², el L/D = CL/CD tendía a infinito cuando el CL tendía a
cero, y el GA aprendió a explotarlo: llegó a un "ganador" con L/D = 551 y
CL = 0.022, es decir, un ala que no sustentaba nada.

Ahora se usa `asb.AeroBuildup`, que calcula LAS DOS contribuciones de
resistencia y las suma:

    D_total  =  D_induced  +  D_profile

- D_induced : resistencia inducida (la que ya daba el VLM), del sistema de
              vórtices / sustentación finita.
- D_profile : resistencia de perfil (viscosa: fricción de piel + presión),
              estimada con NeuralFoil por estación de envergadura y a la
              Re local. Es la que faltaba por completo.

No hace falta superponer nada a mano: AeroBuildup ya hace la integración
por estaciones internamente y expone los dos términos por separado en su
resultado (`D_induced`, `D_profile`), que suman exactamente `D`.

POR QUÉ ESTE CAMBIO ES UNA MEJORA EN TODOS LOS EJES (medido acá):

| | VLM invíscido | AeroBuildup |
|---|---|---|
| Tiempo por candidato | 268 ms | **52 ms** (5x más rápido) |
| Resistencia viscosa | no la calcula | sí, vía NeuralFoil |
| L/D del diseño semilla | 86 (irreal) | **17.0** (creíble) |
| L/D del diseño degenerado | 551 (lo premiaba) | **0.58** (lo hunde) |

Ese último renglón es el importante: el diseño que el objetivo viejo
coronaba como el mejor, el nuevo lo manda al fondo del ranking. En la
semilla, la resistencia de perfil resulta ser el **89%** de la resistencia
total -- o sea que el modelo anterior no tenía "un error chico", estaba
ignorando casi toda la resistencia.

NOTA sobre el VLM: no desaparece del proyecto. AeroBuildup no produce un
campo de flujo, así que para VISUALIZAR el flujo (líneas de corriente
sobre el diseño final) el notebook sigue corriendo un VLM sobre el
ganador. La división queda: AeroBuildup para evaluar (rápido y con las dos
resistencias), VLM para dibujar.

==========================================================================
SEGUNDO CAMBIO (2026-08-26): se agregó ESTABILIDAD al objetivo
==========================================================================
El objetivo ya no es solo L/D. Ahora es una suma pesada de dos términos
normalizados:

    score = PESO_LD * (L/D)/LD_REFERENCIA  +  PESO_ESTABILIDAD * p_estab(SM)

donde SM es el margen estático y p_estab() es una meseta que vale 1 dentro
de la banda objetivo. Además, los candidatos con SM <= 0 se descartan de
plano (-inf): un ala volante inestable en cabeceo no vuela sin control
activo, así que no es un diseño peor, no es un diseño.

Para que el margen estático signifique algo hubo que corregir algo que
estaba mal antes: el punto de referencia de momentos estaba en
0.25*root_chord, que para un ala con flecha NO es el cuarto de la MAC.
Ahora `geometria.py` lo ubica sobre la MAC (ver CG_FRAC_MAC).

El compromiso que introduce es real y se ve en los números (mismo diseño,
variando solo la flecha):

| flecha | L/D | SM | p_estab | score |
|---|---|---|---|---|
| 0° | 17.51 | -1.83% | -- | **descartado** |
| 20° | 16.97 | 3.45% | 0.77 | 0.949 |
| 30° | 16.08 | **8.89%** | **1.00** | **1.036** |
| 40° | 14.31 | 15.11% | 0.06 | 0.504 |

El de 30° gana **a pesar de tener menos L/D** que el de 20°, porque es el
único que cae dentro de la banda de estabilidad. Eso es exactamente lo que
se buscaba: que el óptimo sea un compromiso y no un extremo.

LO QUE SIGUE PENDIENTE (Research Note 11): margen de entrada en pérdida,
peso estructural, y barrido de puntos de operación en vez de un alpha fijo
(idealmente evaluando a sustentación fija). También queda pendiente exigir
que el avión pueda EQUILIBRARSE (trim): `calcular_aero()` ya devuelve Cm0 y
CL_trim, pero todavía no entran al score.

FUNCIONES DISPONIBLES (todas con la misma firma -- elegís cuál usar desde
el notebook; `evolucion.py` recibe la que sea como parámetro):

- evaluar_candidato ........... L/D + estabilidad. EL DEFAULT.
- evaluar_candidato_invisido .. el objetivo viejo (VLM solo). Se conserva
                                para poder mostrar el contraste, no para
                                optimizar con él.
- evaluar_candidato_toy ....... no aerodinámica, barata, para probar la
                                mecánica del loop sin esperar al solver.
"""

import aerosandbox as asb
import aerosandbox.numpy as np

from .geometria import _N_ESTACIONES, MASA_TOTAL, construir_avion

# Punto de operación fijo. Pendiente de la Nota 11: esto debería volverse
# un barrido, y además evaluarse a sustentación fija en vez de alpha fijo.
OP_POINT = asb.OperatingPoint(velocity=20, alpha=4)

# Puntos de operación auxiliares para medir la pendiente dCm/dCL por
# diferencias finitas (de ahí sale el margen estático). Deben estar en la zona
# lineal, lejos de la entrada en pérdida.
_ALPHA_LO, _ALPHA_HI = 2.0, 6.0

# =====================================================================
# ESTABILIDAD -- margen estático objetivo
# =====================================================================
# El margen estático (SM) es la distancia entre el punto neutro y el CG,
# expresada como fracción de la MAC:  SM = -dCm/dCL, con momentos tomados
# respecto del CG (que geometria.py ubica en CG_FRAC_MAC de la MAC).
#
#   SM > 0  -> estable en cabeceo (si sube el ángulo, aparece momento de picada)
#   SM = 0  -> neutro
#   SM < 0  -> inestable: no vuela sin control activo
#
# RANGO PARA UN ALA VOLANTE: la literatura de diseño tailless coincide en
# valores MUCHO más chicos que un avión convencional (que usa 10-20%):
#   - ~5% como punto de partida razonable, rango aceptable 0-10%; por debajo
#     de ~2% se vuelve prácticamente incontrolable (discusión de XFLR5).
#   - 10% para principiantes / 5% intermedio / 1% experto (rcplanes.online).
#
# Elegimos apuntar al EXTREMO ESTABLE de ese rango, banda [5%, 10%]:
# nuestro UAV no es acrobático, es una plataforma de monitoreo que tiene que
# volar estable con viento en Vaca Muerta y llevar una cámara; y si más
# adelante se le suma piloto automático (objetivo máximo), un avión más
# estable es más fácil de controlar. El costo es menos autoridad de elevón,
# aceptable para esta misión.
SM_MIN, SM_MAX = 0.05, 0.10  # banda objetivo (fracción de MAC)
SM_TOLERANCIA = 0.03         # escala de decaimiento del puntaje fuera de la banda

# =====================================================================
# EQUILIBRIO (TRIM) -- restriccion de validez, no de puntaje
# =====================================================================
# Ser estable NO alcanza. Un ala volante tambien tiene que poder
# EQUILIBRARSE: que exista un angulo de ataque donde el momento de cabeceo
# sea cero Y la sustentacion sea util. La condicion de equilibrio es
#
#     Cm = Cm0 + (dCm/dCL) * CL = 0     ->     CL_trim = Cm0 / SM
#
# Como ya exigimos SM > 0, para que CL_trim sea POSITIVO hace falta que
# Cm0 > 0. Eso es lo que consiguen el reflejo del perfil (z4, z5) y el
# washout: sin ellos, un ala con flecha tiene Cm0 negativo y solo se
# equilibra a sustentacion negativa, o sea volando invertida.
#
# POR QUE SE AGREGO (2026-08-26): con estabilidad en el score pero sin esta
# restriccion, el optimizador encontro un "ganador" con SM = 8.36% (perfecto,
# dentro de la banda), L/D = 31.4 (excelente)... y Cm0 = -0.067, CL_trim =
# -0.80. Un avion imposible: estable, eficiente, y que no vuela. Es la misma
# clase de agujero que el L/D = 551 del objetivo invisido -- el optimizador
# encuentra lo que no le pediste explicitamente.
CL_TRIM_MIN, CL_TRIM_MAX = 0.10, 1.00

# ---------------------------------------------------------------------
# PONDERACIÓN entre performance y estabilidad
# ---------------------------------------------------------------------
# Los dos términos se normalizan antes de pesarse, para que los pesos
# signifiquen lo que parece que significan:
#   - L/D se divide por LD_REFERENCIA (un L/D "bueno" para esta ala).
#   - El puntaje de estabilidad ya vive en [0, 1] por construcción.
PESO_LD = 1.0
PESO_ESTABILIDAD = 0.5   # la estabilidad puede aportar hasta ~1/3 del score total
LD_REFERENCIA = 30.0     # calibrado con lo observado: el GA llegaba a L/D ~33


def _escalar(v) -> float:
    """AeroSandbox a veces devuelve arrays de un elemento según cómo se
    haya construido el caso; esto normaliza a float."""
    return float(np.atleast_1d(v)[0])


def _ahusamiento_valido(params: dict) -> bool:
    """La cuerda tiene que decrecer (o mantenerse) de raíz a punta -- si
    no, la geometría es rara/inválida (cuerda más ancha en la punta que en
    el medio, etc.)."""
    cuerdas = [params["root_chord"]] + [params[f"chord_{i}"] for i in range(1, _N_ESTACIONES)]
    return all(cuerdas[i] >= cuerdas[i + 1] for i in range(len(cuerdas) - 1))


def _puntaje_estabilidad(SM: float) -> float:
    """Puntaje en [0, 1] según el margen estático.

    Es una MESETA, no un pico: vale exactamente 1.0 en toda la banda
    [SM_MIN, SM_MAX] y decae con forma gaussiana fuera de ella. Esto es
    deliberado -- dentro de la banda no hay gradiente, así que el optimizador
    entra a la banda y desde ahí dedica todo su esfuerzo a maximizar L/D, en
    vez de gastar diseño persiguiendo un valor "óptimo" de estabilidad que en
    realidad no existe: cualquier punto de la banda es igual de aceptable."""
    if SM < SM_MIN:
        d = SM_MIN - SM
    elif SM > SM_MAX:
        d = SM - SM_MAX
    else:
        return 1.0
    return float(np.exp(-((d / SM_TOLERANCIA) ** 2)))


def calcular_aero(params: dict) -> dict | None:
    """Corre AeroBuildup y devuelve los coeficientes desglosados, o None si
    la geometría es inválida o el solver falla.

    Devuelve CD_inducido y CD_perfil por separado además del total, para
    que el notebook pueda mostrar de dónde viene la resistencia de cada
    candidato -- que es justamente lo que no se veía en la versión
    anterior y permitió que el objetivo estuviera roto sin que se notara.
    """
    try:
        if not _ahusamiento_valido(params):
            return None
        avion = construir_avion(params)
        r = asb.AeroBuildup(airplane=avion, op_point=OP_POINT).run()

        q_S = OP_POINT.dynamic_pressure() * avion.s_ref  # para pasar de fuerza a coeficiente
        CL, CD = _escalar(r["CL"]), _escalar(r["CD"])
        if CD <= 0 or not np.isfinite(CL) or not np.isfinite(CD):
            return None

        # --- Estabilidad: pendiente dCm/dCL por diferencias finitas ---
        puntos = []
        for a in (_ALPHA_LO, _ALPHA_HI):
            ra = asb.AeroBuildup(
                airplane=avion, op_point=asb.OperatingPoint(velocity=OP_POINT.velocity, alpha=a)
            ).run()
            puntos.append((_escalar(ra["CL"]), _escalar(ra["Cm"])))
        (CL1, Cm1), (CL2, Cm2) = puntos
        if not np.isfinite(CL1) or not np.isfinite(CL2) or abs(CL2 - CL1) < 1e-9:
            return None
        dCm_dCL = (Cm2 - Cm1) / (CL2 - CL1)
        SM = -dCm_dCL
        Cm0 = Cm1 - dCm_dCL * CL1              # Cm extrapolado a CL = 0
        CL_trim = Cm0 / SM if abs(SM) > 1e-9 else float("nan")
        if not np.isfinite(SM):
            return None

        return {
            "CL": CL,
            "CD": CD,
            "CD_inducido": _escalar(r["D_induced"]) / q_S,
            "CD_perfil": _escalar(r["D_profile"]) / q_S,
            "Cm": _escalar(r["Cm"]),
            "LD": CL / CD,
            "SM": SM,
            "Cm0": Cm0,
            "CL_trim": CL_trim,
            "puntaje_estabilidad": _puntaje_estabilidad(SM),
        }
    except Exception:
        return None


def evaluar_candidato(params: dict) -> float:
    """Score = L/D, con resistencia inducida + viscosa (AeroBuildup).
    MÁS ALTO ES MEJOR. -inf en geometría inválida o falla del solver, para
    que los candidatos malos se hundan solos en el ranking en vez de
    romper el loop.

    A diferencia del objetivo invíscido anterior, este tiene un máximo
    interior real: como CD = CD0 + k·CL² con CD0 > 0, el L/D se anula
    tanto cuando CL -> 0 como cuando CL es muy grande, y es máximo en un
    CL intermedio. Ese es el comportamiento físico, y es lo que cierra el
    agujero que el GA venía explotando."""
    aero = calcular_aero(params)
    if aero is None:
        return -np.inf
    # Un ala volante con margen estático negativo es inestable en cabeceo: no
    # vuela sin control activo. Se descarta de plano en vez de penalizarse,
    # porque no es un diseño peor, no es un diseño.
    if aero["SM"] <= 0:
        return -np.inf
    # Tiene que poder equilibrarse a sustentacion positiva y util. Sin esto el
    # optimizador entrega alas estables y eficientes que solo vuelan invertidas
    # (ver el bloque EQUILIBRIO arriba).
    if not np.isfinite(aero["CL_trim"]) or not (CL_TRIM_MIN <= aero["CL_trim"] <= CL_TRIM_MAX):
        return -np.inf
    termino_ld = PESO_LD * (aero["LD"] / LD_REFERENCIA)
    termino_estab = PESO_ESTABILIDAD * aero["puntaje_estabilidad"]
    return float(termino_ld + termino_estab)


def evaluar_candidato_invisido(params: dict) -> float:
    """EL OBJETIVO VIEJO -- solo VLM, sin resistencia viscosa. NO USAR PARA
    OPTIMIZAR: está roto por construcción (ver el encabezado de este
    archivo). Se conserva únicamente para poder mostrar el contraste, por
    ejemplo en la defensa: correr el mismo diseño por los dos objetivos y
    mostrar que este premia con L/D = 551 un ala que no sustenta."""
    try:
        if not _ahusamiento_valido(params):
            return -np.inf
        vlm = asb.VortexLatticeMethod(airplane=construir_avion(params), op_point=OP_POINT)
        r = vlm.run()
        CL, CD = _escalar(r["CL"]), _escalar(r["CD"])
        if CD <= 0 or not np.isfinite(CL) or not np.isfinite(CD):
            return -np.inf
        return CL / CD
    except Exception:
        return -np.inf


def evaluar_candidato_toy(params: dict) -> float:
    """Objetivo no aerodinámico, determinístico y barato, solo para probar
    la mecánica del loop (generación de hijos + selección + checkpoint) sin
    esperar al solver. Óptimo conocido dentro de BOUNDS: chord_1
    maximizado, z5 cerca de 0.15, twist_3 cerca de -6."""
    if not _ahusamiento_valido(params):
        return -np.inf
    return (
        params["chord_1"]
        - abs(params["z5"] - 0.15)
        - abs(params["twist_3"] + 6.0)
    )
