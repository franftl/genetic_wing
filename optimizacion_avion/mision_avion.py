"""
Función objetivo de MISIÓN -- ahora con DOS puntos de vuelo.

==========================================================================
LA MISIÓN CAMBIÓ (2026-09-17), Y NO ES UN CAMBIO DE UN NÚMERO
==========================================================================
Antes: crucero a 60 km/h con 3 kg de carga útil. Ahora:

    crucero a 120 km/h  Y ADEMÁS  poder volar a 10 m/s (36 km/h)
    para reconocimiento, despegue y aterrizaje

Eso es una relación de velocidades de 3.33:1, o sea un factor 11 en
coeficiente de sustentación. Y NO se puede implementar cambiando solo
`V_CRUCERO`, porque los dos puntos de vuelo piden alas OPUESTAS. Con el
peso de este avión (~72 N):

    optimizando SOLO crucero a 120 km/h  -> S ~ 0.21-0.35 m2 (cuerda 10-16 cm)
    para poder volar a 10 m/s            -> S ~ 0.77-1.63 m2 (cuerda 35-74 cm)

Un factor 2 a 8 en superficie. Si se cambiara la velocidad sin meter el
vuelo lento, el optimizador convergería a un ala de cuerda mínima que no
puede cumplir la misión -- un óptimo perfectamente válido del problema
equivocado. Por eso los dos puntos entran juntos.

Para referencia, esa relación de velocidades es EXIGENTE comparada con los
UAV reales de esta clase: RQ-7B Shadow tiene máxima/crucero = 1.54:1 y el
Bayraktar TB2, 1.71:1 (y despegan de pista o catapulta, no en vuelo lento
sostenido). Es ambicioso pero no imposible -- el déficit real es chico.

==========================================================================
EL MODELO DE FLAP, Y POR QUÉ NO ES UNA TABLA
==========================================================================
Lo habitual en diseño preliminar es sumar un dCL_max de tabla según el tipo
de flap (Raymer/Roskam: plain ~0.9, ranurado ~1.3, Fowler ~1.9). Esas tablas
están medidas a Reynolds de avión grande (10^6-10^7) y este avión vuela
lento a Re ~2x10^5. La bibliografía dice que a Re bajo el flap se degrada
(ICAS 2010 paper 246, NACA 2412 con flap 30%c a Re 61k-260k) pero no publica
un factor de corrección.

Acá el incremento se MIDE: se deflecta la geometría del perfil y se la
evalúa con NeuralFoil al Reynolds real del vuelo lento -- el mismo modelo
que se usa en todo el resto del pipeline. Medido así, un flap plain del 25%
a 30 grados da dCL_max ~0.43-0.58 según el perfil, bastante por debajo del
0.9 de tabla: exactamente la degradación por bajo Reynolds que la
bibliografía describe en palabras. Ver `perfiles_avion.perfil_con_flap`
para la limitación (solo modela flap PLAIN, no ranurado ni Fowler).

==========================================================================
EL REYNOLDS DEL CL_max -- un error que estaba y se corrigió
==========================================================================
La versión anterior estimaba el CL_max al Reynolds de CRUCERO y lo usaba
para todo. Medido sobre el catálogo, el CL_max cae en promedio 6% (hasta
11% en algún perfil) al pasar de Re 6.7e5 (crucero) a Re 2e5 (vuelo lento).
Usar el de crucero para juzgar el vuelo lento es optimista justo donde el
diseño está más apretado. Ahora cada punto de vuelo usa SU Reynolds.

==========================================================================
ESTRUCTURA DEL PUNTAJE
==========================================================================
    score = w_ef  * f_eficiencia   (resistencia en crucero)
          + w_ma  * f_masa
          + w_es  * f_estabilidad  (margen estático en banda)
          + w_ra  * f_rafaga
          + w_mg  * f_margen       (margen de pérdida con ráfaga, en crucero)
          + w_tr  * f_trim
          + w_di  * f_direccional  (Cn_beta)
          + w_la  * f_lateral      (Cl_beta)
          + w_le  * f_lento        (NUEVO: cuánto margen sobra en vuelo lento)

RESTRICCIONES DURAS: estructura que no cierra, no sostenerse a 120 km/h, no
poder volar a 10 m/s ni con flap, margen estático negativo, Cn_beta <= 0,
Cl_beta >= 0, o entrar en pérdida con la ráfaga de diseño en crucero.

==========================================================================
ACTUALIZACIÓN 2026-09-18 -- TRES PUNTOS DE VUELO, Y VOLUMEN DE FUSELAJE
==========================================================================
Dos cambios de misión, decididos con el usuario después de correr la
competencia de 5 topologías y de un análisis de autonomía con batería (ver
Research Note 15):

1. CRUCERO DE DISEÑO BAJA A 80 km/h. El análisis de alcance mostró que
   pedir 300 km volando a 120 km/h exige ~8.6 kg de batería sobre un avión
   de ~7 kg en seco (la resistencia inducida por el propio peso de la
   batería hace que el problema case sea divergente). El alcance eléctrico
   R = E*eta/D se maximiza a resistencia mínima, que para este avión cae
   cerca de 70-80 km/h, no a 120. V_CRUCERO pasa a ser el punto de DISEÑO:
   ahí se miden la eficiencia (D_crucero), la estabilidad estática y de
   ráfaga, y el trim.

2. VELOCIDAD MÁXIMA a 120 km/h SIGUE SIENDO UN REQUISITO, pero cambia de
   rol: ya no es el punto de diseño, es la velocidad que el avión tiene que
   poder alcanzar (potencia disponible / estructura) para no quedar
   indefenso ante ráfagas o viento de frente. V_MAX entra como una
   restricción dura (CL a V_MAX por debajo de CL_max) Y como un término de
   puntaje adicional (PESO_VELMAX) que premia baja resistencia ahí también
   -- el usuario pidió explícitamente que 120 km/h "también pese en el
   score", no que sea solo un gate binario.

3. VOLUMEN MÍNIMO DE FUSELAJE. El diagnóstico numérico sobre las semillas
   existentes mostró que 7 de 10 no entran el volumen de carga útil +
   batería + aviónica a una utilización de empaquetado razonable (55%) --
   sobre todo doble_boom y pod_boom, que por diseño llevan un fuselaje/góndola
   corto. Se agrega como restricción dura geométrica, siguiendo la
   formulación estándar de MDO (Hajdik, Adler & Martins, AIAA 2023-3589):

       g(x) = V_requerido - eta_vol * V_geometrico(fuselaje) <= 0

   con VOLUMEN_UTIL_MIN_L y FACTOR_UTILIZACION_VOLUMEN declarados más abajo
   como constantes fáciles de mover. V_geometrico sale de
   `avion.fuselages[0].volume()` (el fuselaje/góndola principal, SIN
   contar las vigas del doble boom, que no cargan payload).

4. WINGLETS: no se fuerza ninguna condición nueva -- el usuario decidió
   dejar que el GA elija, ahora con la misión recalculada. A 80 km/h el CL
   de crucero es más alto que a 120 km/h y más cercano al cruce V_CR (ver
   Research Note 15), así que el trade-off del winglet es menos
   desfavorable que antes, pero sigue siendo una decisión del optimizador,
   no una restricción geométrica.

5. VIENTO DE LOS SITIOS (2026-10-02, ver Research Note 16 y viento.py). Con
   VIENTO_ACTIVO = True la misión se evalúa con el aire y la ráfaga reales
   de los sitios candidatos (peor caso de Cañadón León y Puesto Hernández):
   - densidad del aire 1.056 kg/m3 en vez de 1.225 (en las fórmulas y en
     AeroBuildup), y el Reynolds con la viscosidad del sitio;
   - ráfaga vertical de diseño 4.63 m/s en vez de 3.0;
   - restricción dura: si la ráfaga lleva el ala más allá de la carga
     ÚLTIMA (N_ULTIMO), el candidato se descarta;
   - término nuevo de puntaje: eficiencia en turbulencia continua
     (PESO_TURBULENCIA), la resistencia extra que genera volar en aire
     turbulento.
   Con VIENTO_ACTIVO = False el optimizador da exactamente los mismos
   resultados que antes de este cambio.
"""

from __future__ import annotations

import aerosandbox as asb
import numpy as np

from optimizacion_ala.estructura import G, MASA_PAYLOAD, MASA_SISTEMAS, N_LIMITE, N_ULTIMO

from . import viento as _viento

from .estructura_avion import converger_masa_avion
from .geometria_avion import (
    SM_BANDS, construir_avion, geometria_flap, referencias_ala, volumenes_de_cola,
)
from .perfiles_avion import perfil_con_flap, perfil_en_fraccion_avion

# =====================================================================
# LA MISIÓN
# =====================================================================
V_CRUCERO = 80.0 / 3.6        # [m/s] = 22.22 m/s -- punto de DISEÑO (mejor L/D / alcance)
V_MAX = 120.0 / 3.6           # [m/s] = 33.33 m/s -- velocidad máxima exigida (rafagas/viento), YA NO es el punto de diseño
V_LENTO = 10.0                # [m/s] reconocimiento / despegue / aterrizaje
# Margen sobre la velocidad de pérdida al que se quiere poder volar lento.
# 1.20 es un compromiso: 1.3 es lo clásico de aproximación, 1.15 sería
# volar prácticamente al borde. Se declara acá para poder moverlo de un lugar.
MARGEN_SOBRE_PERDIDA = 1.20
V_STALL_OBJETIVO = V_LENTO / MARGEN_SOBRE_PERDIDA   # 8.33 m/s

# Viento del sitio (ver encabezado, punto 5). En False: aire a nivel del mar
# y ráfaga de 3 m/s, exactamente como antes del 2026-10-02.
VIENTO_ACTIVO = True

RAFAGA_VERTICAL = 3.0         # [m/s] ráfaga SIN viento del sitio; con viento: viento.RAFAGA_VERTICAL_SITIO
VIENTO_MEDIO = _viento.VIENTO_MEDIO_SITIO              # [m/s] antes 3.1 -- informativo, no entra en cuentas
RAFAGA_HORIZONTAL_MAX = _viento.VIENTO_FUERTE_SITIO    # [m/s] antes 14.4 -- informativo, no entra en cuentas

NU_AIRE = 1.5e-5              # viscosidad cinemática [m2/s] a nivel del mar

_A_LO, _A_HI = 1.0, 5.0
_B_LO, _B_HI = -3.0, 3.0
_PBAR_PERT = 0.05
_RBAR_PERT = 0.05



def _atmosfera() -> asb.Atmosphere:
    return _viento.ATMOSFERA_SITIO if VIENTO_ACTIVO else asb.Atmosphere(altitude=0)


def _rafaga_vertical() -> float:
    return _viento.RAFAGA_VERTICAL_SITIO if VIENTO_ACTIVO else RAFAGA_VERTICAL


def _nu_aire(atm: asb.Atmosphere) -> float:
    """NU_AIRE escalada a la atmósfera dada (aire más liviano -> nu mayor -> Re menor)."""
    return NU_AIRE * float(atm.kinematic_viscosity() / asb.Atmosphere(altitude=0).kinematic_viscosity())


# =====================================================================
# CRITERIOS
# =====================================================================
SM_TOLERANCIA = 0.02
DN_RAFAGA_OK = 0.5
DN_TOLERANCIA = 0.5
MARGEN_PERDIDA_OK = 0.20
FACTOR_CLMAX_3D = 0.90

# Penalización de resistencia por llevar flap, con el flap RETRAÍDO en
# crucero. NeuralFoil NO la ve: a deflexión cero las coordenadas del perfil
# son las mismas, así que la ranura, el juego de la bisagra y los escalones
# son invisibles para un modelo basado en el contorno. Hay que declararla.
# Anclaje: NACA TR 664 midió ~15% más de resistencia mínima con flap
# RANURADO retraído, y aclara que sellar la ranura reduce bastante ese
# número. Un flap plain sellado, que es lo que modelamos, está bien por
# debajo: se adopta 4% del CD, escalado por la fracción de envergadura con
# flap. Es el número MENOS respaldado del modelo y conviene decirlo.
PENAL_CD_FLAP = 0.04

CN_BETA_REFERENCIA = 0.0015
CL_BETA_REFERENCIA = 0.0015

# =====================================================================
# VOLUMEN MÍNIMO DE FUSELAJE -- variable fácil de mover (ver encabezado, punto 3)
# =====================================================================
# Anclaje del volumen requerido: 3.0 kg de carga útil a 0.5 kg/L (densidad de
# empaque del Penguin B UAV, 20 L / 10 kg) = 6.0 L, + bateria (~0.5 L con
# densidad de pack tipica 2.0-2.15 kg/L) + aviónica (1.67 L estimados) =
# 8.17 L. Se redondea a 8.2 L. Ver Research Note 15 para el detalle.
VOLUMEN_UTIL_MIN_L = 8.2      # [L] volumen útil requerido (payload + bateria + aviónica)
# Fracción del volumen GEOMÉTRICO del fuselaje que es realmente aprovechable
# como carga (el resto son paredes, largueros, acceso, holguras de montaje).
# No hay un valor publicado en Roskam/Raymer/Torenbeek para UAV de esta
# escala -- se adopta 0.55 como supuesto de ingeniería declarado y punto de
# partida para análisis de sensibilidad, no como un número medido.
FACTOR_UTILIZACION_VOLUMEN = 0.55

# =====================================================================
# PESOS
# =====================================================================
PESO_EFICIENCIA = 1.0
PESO_MASA = 0.3
PESO_ESTABILIDAD = 1.5
PESO_RAFAGA = 0.4
PESO_MARGEN = 0.4
PESO_TRIM = 0.3
PESO_DIRECCIONAL = 0.3
PESO_LATERAL = 0.3
# El vuelo lento es un REQUISITO de misión, no un lujo: pesa como la
# estabilidad. Por debajo de V_LENTO el candidato ya se descarta por
# restricción dura; este término premia el margen POR ENCIMA de eso, para
# que el optimizador no se quede pegado al borde de la restricción.
PESO_LENTO = 1.0
# NUEVO: velocidad máxima (120 km/h) como requisito que también puntúa, no
# solo como restricción dura -- pedido explícito del usuario. Pesa menos que
# el crucero de diseño porque a 120 km/h la resistencia es inherentemente
# más alta (CL bajo, régimen de perfil) y no es donde el avión pasa la
# mayor parte de la misión.
PESO_VELMAX = 0.5
# Turbulencia (solo con VIENTO_ACTIVO): el término es 1 / (1 + resistencia
# extra por turbulencia). El peso NO es una preferencia: se elige para que un
# 1 % de resistencia por turbulencia cueste en el puntaje lo mismo que un 1 %
# de resistencia de crucero en el término de eficiencia
# (PESO_EFICIENCIA * D_REFERENCIA / D_crucero ~ 1.0 * 3.2 / 4.3 ~ 0.75).
PESO_TURBULENCIA = 0.75

# Referencias de escala. D_REFERENCIA se recalibró 2026-09-18 para el nuevo
# crucero de diseño a 80 km/h (antes 120 km/h, D_REFERENCIA=5.0 N).
# D_REFERENCIA_VMAX es la referencia análoga para el punto de 120 km/h, que
# ahora es más rápido que el de diseño y por lo tanto más exigente en
# resistencia.
D_REFERENCIA = 3.2            # [N] a 80 km/h
D_REFERENCIA_VMAX = 7.0       # [N] a 120 km/h
MASA_REFERENCIA = 7.0         # [kg]


def _escalar(v) -> float:
    return float(np.atleast_1d(v)[0])


def _meseta(valor, lo, hi, tol):
    if valor < lo:
        d = lo - valor
    elif valor > hi:
        d = valor - hi
    else:
        return 1.0
    return float(np.exp(-((d / tol) ** 2)))


def _cl_max_seccion(af, Re: float, mach: float) -> float:
    alphas = np.linspace(0.0, 22.0, 45)
    cl = np.asarray(af.get_aero_from_neuralfoil(alpha=alphas, Re=Re, mach=mach)["CL"])
    if not np.all(np.isfinite(cl)):
        return float("nan")
    return float(np.max(cl))


def _clmax_2d_limpio(params: dict, Re: float, mach: float) -> float:
    """CL máximo de la sección LIMPIA, tomando el MÍNIMO de los tres perfiles
    ancla: el ala entra en pérdida cuando la PRIMERA sección llega a su
    límite, no cuando llega la mejor. Conservador a propósito."""
    vals = []
    for frac in (0.0, float(params.get("perfil_pos_medio", 0.5)), 1.0):
        v = _cl_max_seccion(perfil_en_fraccion_avion(params, frac), Re, mach)
        if not np.isfinite(v):
            return float("nan")
        vals.append(v)
    return min(vals)


def _delta_clmax_flap(params: dict, Re: float, mach: float) -> float:
    """Incremento de CL_max del ALA por deflectar el flap.

    Método estándar de diseño preliminar:

        dCL_max_ala = dCl_max_2D * (S_con_flap / S_ref)

    Dos detalles que importan y que una primera versión de esta función hacía
    mal:

    1. El dCl_max 2D se mide en una sección que EFECTIVAMENTE LLEVA FLAP --
       concretamente, en el medio del tramo con flap. Antes se evaluaba el
       perfil deflectado en las tres anclas (raíz, medio, punta) y se tomaba
       el mínimo; como el flap típicamente NO llega a la punta, eso aplicaba
       una deflexión a una sección que en el avión real está limpia, y después
       el mínimo la elegía. Resultado: el flap casi no sumaba nada, por un
       error de contabilidad y no por física.

    2. El término LIMPIO ya es conservador (mínimo de las tres anclas), así
       que la conservación por "la punta entra en pérdida primero" ya está
       contabilizada ahí y no hay que contarla dos veces acá."""
    fl = geometria_flap(params)
    if not fl["tiene_flap"]:
        return 0.0
    frac_media = 0.5 * (float(params["flap_inicio_frac"]) + float(params["flap_fin_frac"]))
    af = perfil_en_fraccion_avion(params, frac_media)
    limpio = _cl_max_seccion(af, Re, mach)
    con = _cl_max_seccion(perfil_con_flap(af, fl["deflexion"], fl["cuerda_frac"]), Re, mach)
    if not (np.isfinite(limpio) and np.isfinite(con)):
        return 0.0
    return max(con - limpio, 0.0) * fl["frac_superficie"]


def _clmax_ala(params: dict, Re: float, velocidad: float, con_flap: bool) -> float:
    """CL máximo del ALA en un punto de vuelo (su Reynolds y su velocidad),
    con o sin flap deflectado.

    OJO con el Mach: se toma del PUNTO DE VUELO, no de si el flap está
    desplegado. Parece obvio pero una primera versión lo ataba a `con_flap`,
    con lo cual el CL_max limpio se evaluaba a Mach de crucero aun cuando se
    lo estaba usando para juzgar el vuelo lento, y las dos ramas no eran
    comparables entre sí.

    SOBRE EL `max(..., 0)` DEL INCREMENTO DE FLAP. Medido con NeuralFoil, un
    flap grande muy deflectado sobre un perfil YA muy cambado puede BAJAR el
    CL_max en vez de subirlo -- la sección ya está al borde de la separación
    y agregarle curvatura efectiva la separa antes. Ejemplo medido a Re
    166k con flap del 33%:

        e423:   limpio 1.961 | 20 grados 2.286 | 30 grados 2.068 | 40 grados 1.636
        s1223:  limpio 2.235 | 20 grados 2.456 | 30 grados 2.421 | 40 grados 2.066
        naca4412: limpio 1.411 | 20 grados 1.722 | 30 grados 1.788 | 40 grados 1.773

    O sea que el perfil de alta sustentación y el flap COMPITEN: no se suman.
    Es un resultado físico real del modelo, no un artefacto, y es uno de los
    compromisos interesantes que el optimizador va a tener que resolver.
    El `max(..., 0)` representa que, si desplegar el flap a esa deflexión
    empeora las cosas, en la práctica no se lo despliega -- no que el efecto
    no exista."""
    limpio = _clmax_2d_limpio(params, Re, velocidad / 340.0)
    if not np.isfinite(limpio):
        return float("nan")
    d = _delta_clmax_flap(params, Re, velocidad / 340.0) if con_flap else 0.0
    return FACTOR_CLMAX_3D * limpio + d


def analizar_mision_avion(params: dict, topologia: str) -> dict | None:
    sm_min, sm_max = SM_BANDS[topologia]
    try:
        # --- 1. Masa ----------------------------------------------------
        est = converger_masa_avion(params, topologia)
        if est is None:
            return None
        W = est["peso_total"]

        avion = construir_avion(params, topologia)

        # --- 1b. Volumen mínimo de fuselaje (restricción geométrica dura) --
        # g(x) = V_requerido - eta_vol * V_geometrico <= 0 (Hajdik/Adler/
        # Martins AIAA 2023-3589). V_geometrico sale del fuselaje/góndola
        # PRINCIPAL (fuselages[0], ver construir_avion): nunca las vigas del
        # doble boom, que no cargan payload.
        vol_geo_L = float(avion.fuselages[0].volume()) * 1000.0
        if vol_geo_L * FACTOR_UTILIZACION_VOLUMEN < VOLUMEN_UTIL_MIN_L:
            return None

        S = float(avion.s_ref)
        c_ref = float(avion.c_ref)
        b_ref = float(avion.b_ref)
        atm = _atmosfera()
        rho = float(atm.density())
        nu = _nu_aire(atm)
        q = 0.5 * rho * V_CRUCERO ** 2

        Re_crucero = V_CRUCERO * c_ref / nu
        Re_lento = V_LENTO * c_ref / nu
        Re_vmax = V_MAX * c_ref / nu

        # --- 2. Punto de vuelo LENTO (nuevo) ----------------------------
        # Se evalúa PRIMERO porque es la restricción que más aprieta: si el
        # candidato no puede volar lento, no hay razón para gastar corridas
        # de AeroBuildup en su crucero.
        CL_max_lento = _clmax_ala(params, Re_lento, V_LENTO, con_flap=True)
        if not np.isfinite(CL_max_lento) or CL_max_lento <= 0:
            return None
        v_stall = float(np.sqrt(2.0 * W / (rho * S * CL_max_lento)))
        if v_stall >= V_LENTO:
            return None   # no puede volar a 10 m/s ni con el flap abajo
        # Margen relativo respecto del objetivo (1.0 = justo en el objetivo).
        margen_lento = (V_LENTO - v_stall) / max(V_LENTO - V_STALL_OBJETIVO, 1e-6)

        # --- 3. Crucero -------------------------------------------------
        CL_max_crucero = _clmax_ala(params, Re_crucero, V_CRUCERO, con_flap=False)
        if not np.isfinite(CL_max_crucero) or CL_max_crucero <= 0:
            return None
        CL_crucero = W / (q * S)
        if CL_crucero >= CL_max_crucero:
            return None

        pts = []
        for a in (_A_LO, _A_HI):
            r = asb.AeroBuildup(airplane=avion,
                                op_point=asb.OperatingPoint(atmosphere=atm, velocity=V_CRUCERO, alpha=a)).run()
            pts.append((_escalar(r["CL"]), _escalar(r["Cm"])))
        (CL1, Cm1), (CL2, Cm2) = pts
        if abs(CL2 - CL1) < 1e-9:
            return None
        CL_alpha = (CL2 - CL1) / (_A_HI - _A_LO)
        Cm_alpha = (Cm2 - Cm1) / (_A_HI - _A_LO)
        dCm_dCL = (Cm2 - Cm1) / (CL2 - CL1)
        SM = -dCm_dCL
        Cm0 = Cm1 - dCm_dCL * CL1
        CL_trim = Cm0 / SM if abs(SM) > 1e-9 else float("nan")
        if not np.isfinite(SM) or SM <= 0:
            return None

        alpha_crucero = _A_LO + (CL_crucero - CL1) / CL_alpha

        r = asb.AeroBuildup(airplane=avion,
                            op_point=asb.OperatingPoint(atmosphere=atm, velocity=V_CRUCERO, alpha=alpha_crucero)).run()
        CD = _escalar(r["CD"])
        frac_inducida = _escalar(r["D_induced"]) / _escalar(r["D"])
        CL_real = _escalar(r["CL"])
        Cm_crucero = _escalar(r["Cm"])
        if CD <= 0 or not np.isfinite(CD):
            return None

        # Penalización por llevar flap, con el flap retraído (ver PENAL_CD_FLAP).
        fl = geometria_flap(params)
        CD = CD * (1.0 + PENAL_CD_FLAP * fl["frac_superficie"]) if fl["tiene_flap"] else CD
        D_crucero = q * S * CD
        LD = CL_real / CD

        # --- 3b. Velocidad máxima (120 km/h) -----------------------------
        # Ya NO es el punto de diseño (ver encabezado, punto 2): entra como
        # restricción dura (¿el ala se sostiene ahí sin entrar en pérdida?)
        # y como término de puntaje adicional (PESO_VELMAX), no como el
        # crucero. Se reutiliza la pendiente CL_alpha medida en crucero para
        # ubicar el alpha de V_MAX por extrapolación lineal -- aproximación
        # razonable en preliminar: el Mach sigue siendo bajo (<0.1) en todo
        # el rango 80-120 km/h, así que la pendiente no cambia mucho.
        q_vmax = 0.5 * rho * V_MAX ** 2
        CL_max_vmax = _clmax_ala(params, Re_vmax, V_MAX, con_flap=False)
        if not np.isfinite(CL_max_vmax) or CL_max_vmax <= 0:
            return None
        CL_vmax = W / (q_vmax * S)
        if CL_vmax >= CL_max_vmax:
            return None   # no se sostiene a 120 km/h -- restricción dura

        alpha_vmax = _A_LO + (CL_vmax - CL1) / CL_alpha
        r_vmax = asb.AeroBuildup(airplane=avion,
                                 op_point=asb.OperatingPoint(atmosphere=atm, velocity=V_MAX, alpha=alpha_vmax)).run()
        CD_vmax = _escalar(r_vmax["CD"])
        CD_vmax = CD_vmax * (1.0 + PENAL_CD_FLAP * fl["frac_superficie"]) if fl["tiene_flap"] else CD_vmax
        if CD_vmax <= 0 or not np.isfinite(CD_vmax):
            return None
        D_vmax = q_vmax * S * CD_vmax

        # --- 4. Ráfaga en crucero ---------------------------------------
        CL_alpha_rad = np.degrees(CL_alpha)   # [1/deg] * 57.3 = [1/rad]
        mu = 2.0 * (W / S) / (rho * c_ref * CL_alpha_rad * G)
        Kg = 0.88 * mu / (5.3 + mu)
        rafaga = _rafaga_vertical()
        d_alpha = np.degrees(np.arctan(Kg * rafaga / V_CRUCERO))
        dCL_rafaga = CL_alpha * d_alpha
        dn_rafaga = dCL_rafaga * q * S / W
        margen_perdida = (CL_max_crucero - (CL_crucero + dCL_rafaga)) / CL_max_crucero
        if margen_perdida <= 0.0:
            return None
        # Con la ráfaga del sitio: si lleva el ala más allá de la carga ÚLTIMA
        # con la que se dimensiona la estructura, el ala se rompería.
        if VIENTO_ACTIVO and 1.0 + dn_rafaga > N_ULTIMO:
            return None

        # --- 4b. Turbulencia continua (ver viento.py) ---------------------
        sigma_n = _viento.sigma_n_turbulencia(W / S, CL_alpha_rad, rho, V_CRUCERO)
        extra_turbulencia = _viento.resistencia_extra_turbulencia(frac_inducida, sigma_n, V_CRUCERO)

        # --- 5. Estabilidad látero-direccional estática -----------------
        pts_beta = []
        for b in (_B_LO, _B_HI):
            r_b = asb.AeroBuildup(
                airplane=avion,
                op_point=asb.OperatingPoint(atmosphere=atm, velocity=V_CRUCERO, alpha=alpha_crucero, beta=b)).run()
            pts_beta.append((_escalar(r_b["Cl"]), _escalar(r_b["Cn"])))
        (Cl_lo, Cn_lo), (Cl_hi, Cn_hi) = pts_beta
        if not all(np.isfinite(v) for v in (Cl_lo, Cl_hi, Cn_lo, Cn_hi)):
            return None
        Cl_beta = (Cl_hi - Cl_lo) / (_B_HI - _B_LO)
        Cn_beta = (Cn_hi - Cn_lo) / (_B_HI - _B_LO)
        if Cn_beta <= 0.0 or Cl_beta >= 0.0:
            return None

        # --- 6. Derivadas de amortiguamiento ----------------------------
        p0 = _PBAR_PERT * 2.0 * V_CRUCERO / b_ref
        r0 = _RBAR_PERT * 2.0 * V_CRUCERO / b_ref
        rp_hi = asb.AeroBuildup(airplane=avion, op_point=asb.OperatingPoint(
            atmosphere=atm, velocity=V_CRUCERO, alpha=alpha_crucero, p=p0)).run()
        rp_lo = asb.AeroBuildup(airplane=avion, op_point=asb.OperatingPoint(
            atmosphere=atm, velocity=V_CRUCERO, alpha=alpha_crucero, p=-p0)).run()
        Cl_p = (_escalar(rp_hi["Cl"]) - _escalar(rp_lo["Cl"])) / (2.0 * _PBAR_PERT)
        Cn_p = (_escalar(rp_hi["Cn"]) - _escalar(rp_lo["Cn"])) / (2.0 * _PBAR_PERT)
        rr_hi = asb.AeroBuildup(airplane=avion, op_point=asb.OperatingPoint(
            atmosphere=atm, velocity=V_CRUCERO, alpha=alpha_crucero, r=r0)).run()
        rr_lo = asb.AeroBuildup(airplane=avion, op_point=asb.OperatingPoint(
            atmosphere=atm, velocity=V_CRUCERO, alpha=alpha_crucero, r=-r0)).run()
        Cl_r = (_escalar(rr_hi["Cl"]) - _escalar(rr_lo["Cl"])) / (2.0 * _RBAR_PERT)
        Cn_r = (_escalar(rr_hi["Cn"]) - _escalar(rr_lo["Cn"])) / (2.0 * _RBAR_PERT)

        mac, s_ref_w, b_ref_w, _ = referencias_ala(params)
        vol = volumenes_de_cola(params, topologia)

        return {
            "topologia": topologia,
            # masa
            "masa_total": est["masa_total"], "masa_estructura": est["masa_estructura"],
            "masa_larguero": est["masa_larguero"], "masa_piel_ala": est["masa_piel_ala"],
            "masa_winglet": est["masa_winglet"], "masa_flap": est["masa_flap"],
            "masa_cola": est["masa_cola"], "masa_fuselaje": est["masa_fuselaje"],
            "masa_boom": est["masa_boom"], "fraccion_estructural": est["fraccion_estructural"],
            "flecha_punta_mm": est["flecha_punta_mm"], "manda_rigidez": est["manda_rigidez"],
            # geometría
            "envergadura": b_ref_w, "S": S, "AR": b_ref_w ** 2 / max(S, 1e-9),
            "MAC": mac, "carga_alar": W / S, "peso": W,
            "V_H": vol["V_H"], "V_V": vol["V_V"],
            # crucero
            "CL_crucero": CL_crucero, "alpha_crucero": alpha_crucero,
            "CD_crucero": CD, "D_crucero": D_crucero, "LD_crucero": LD,
            "potencia_W": D_crucero * V_CRUCERO,
            "Re_crucero": Re_crucero, "CL_max_crucero": CL_max_crucero,
            # velocidad máxima
            "CL_vmax": CL_vmax, "CL_max_vmax": CL_max_vmax, "D_vmax": D_vmax,
            "CD_vmax": CD_vmax, "alpha_vmax": alpha_vmax,
            "vol_geo_fuselaje_L": vol_geo_L, "vol_util_fuselaje_L": vol_geo_L * FACTOR_UTILIZACION_VOLUMEN,
            # vuelo lento
            "v_stall": v_stall, "V_LENTO": V_LENTO, "Re_lento": Re_lento,
            "CL_max_lento": CL_max_lento, "margen_lento": margen_lento,
            "CL_lento": W / (0.5 * rho * V_LENTO ** 2 * S),
            "tiene_flap": fl["tiene_flap"], "flap_frac_superficie": fl["frac_superficie"],
            "flap_deflexion": fl["deflexion"], "flap_cuerda_frac": fl["cuerda_frac"],
            # CG y estabilidad
            "cg_frac_mac": float(params.get("cg_frac_mac", 0.20)),
            "SM": SM, "Cm_alpha_por_grado": Cm_alpha, "Cm_crucero": Cm_crucero,
            "Cm0": Cm0, "CL_trim": CL_trim, "CL_alpha_por_grado": CL_alpha,
            "sm_min": sm_min, "sm_max": sm_max,
            "Cl_beta": Cl_beta, "Cn_beta": Cn_beta,
            "Cl_p": Cl_p, "Cn_p": Cn_p, "Cl_r": Cl_r, "Cn_r": Cn_r,
            # ráfaga
            "d_alpha_rafaga": d_alpha, "dn_rafaga": dn_rafaga, "Kg": Kg, "mu": mu,
            "n_con_rafaga": 1.0 + dn_rafaga, "margen_perdida": margen_perdida,
            # viento del sitio
            "viento_activo": VIENTO_ACTIVO, "rho": rho, "rafaga_vertical": rafaga,
            "frac_inducida": frac_inducida, "sigma_n_turbulencia": sigma_n,
            "extra_turbulencia": extra_turbulencia,
            "D_turbulento": D_crucero * (1.0 + extra_turbulencia),
        }
    except Exception:
        return None


def _terminos(a: dict) -> list:
    f_ef = D_REFERENCIA / a["D_crucero"]
    f_ma = MASA_REFERENCIA / a["masa_total"]
    f_es = _meseta(a["SM"], a["sm_min"], a["sm_max"], SM_TOLERANCIA)
    f_ra = _meseta(a["dn_rafaga"], 0.0, DN_RAFAGA_OK, DN_TOLERANCIA)
    f_mg = min(1.0, a["margen_perdida"] / MARGEN_PERDIDA_OK)
    # TRIM: se mide sobre el Cm EN CRUCERO, no sobre |CL_trim - CL_crucero|
    # como antes. A 120 km/h el CL de crucero es ~0.1, así que dividir por él
    # convertía diferencias chiquitas en desvíos enormes y el término se
    # saturaba en cero para todos los candidatos, sin discriminar. El Cm en
    # crucero mide lo mismo (cuánto momento hay que compensar con elevador)
    # sin dividir por un número chico.
    f_tr = float(np.exp(-((a["Cm_crucero"] / 0.02) ** 2)))
    f_di = min(1.0, a["Cn_beta"] / CN_BETA_REFERENCIA)
    f_la = min(1.0, -a["Cl_beta"] / CL_BETA_REFERENCIA)
    f_le = min(1.0, max(a["margen_lento"], 0.0))
    f_vm = D_REFERENCIA_VMAX / a["D_vmax"]
    terminos = [
        ("eficiencia (D crucero)", PESO_EFICIENCIA, f_ef),
        ("masa total", PESO_MASA, f_ma),
        ("estabilidad (margen est.)", PESO_ESTABILIDAD, f_es),
        ("rafaga (suavidad)", PESO_RAFAGA, f_ra),
        ("margen de perdida", PESO_MARGEN, f_mg),
        ("equilibrio en crucero", PESO_TRIM, f_tr),
        ("direccional (Cn_beta)", PESO_DIRECCIONAL, f_di),
        ("lateral (Cl_beta)", PESO_LATERAL, f_la),
        ("vuelo lento (10 m/s)", PESO_LENTO, f_le),
        ("velocidad maxima (120 km/h)", PESO_VELMAX, f_vm),
    ]
    if VIENTO_ACTIVO:
        terminos.append(("turbulencia (eficiencia)", PESO_TURBULENCIA, 1.0 / (1.0 + a["extra_turbulencia"])))
    return terminos


def evaluar_mision_avion(params: dict, topologia: str) -> float:
    a = analizar_mision_avion(params, topologia)
    if a is None:
        return -np.inf
    return float(sum(w * f for _, w, f in _terminos(a)))


def desglose_mision_avion(params: dict, topologia: str) -> str:
    a = analizar_mision_avion(params, topologia)
    if a is None:
        return ("Candidato INVALIDO: no cierra estructuralmente, no entra el volumen util "
                f"minimo ({VOLUMEN_UTIL_MIN_L:.1f} L) en el fuselaje, no se sostiene a "
                f"{3.6*V_MAX:.0f} km/h, no puede volar a 10 m/s ni con flap, es inestable, "
                "o entra en perdida con la rafaga de diseno.")
    terms = _terminos(a)
    total = sum(w * f for _, w, f in terms)
    L = []
    L.append(f"=== [{topologia}] MISION: crucero (diseno) {3.6*V_CRUCERO:.0f} km/h + "
             f"vuelo lento {V_LENTO:.0f} m/s + maxima {3.6*V_MAX:.0f} km/h, "
             f"con {MASA_PAYLOAD:.1f} kg de carga util ===")
    L.append("")
    L.append(f"VOLUMEN DE FUSELAJE  geometrico {a['vol_geo_fuselaje_L']:6.2f} L  x "
             f"{FACTOR_UTILIZACION_VOLUMEN:.0%} util. = {a['vol_util_fuselaje_L']:6.2f} L util  "
             f"(requerido >= {VOLUMEN_UTIL_MIN_L:.1f} L)")
    L.append("")
    L.append("MASA (calculada, no declarada)")
    L.append(f"  carga util ............ {MASA_PAYLOAD:6.2f} kg")
    L.append(f"  sistemas .............. {MASA_SISTEMAS:6.2f} kg")
    L.append(f"  estructura ............ {a['masa_estructura']:6.2f} kg")
    L.append(f"     larguero {a['masa_larguero']:.3f} | piel ala {a['masa_piel_ala']:.3f} | "
             f"winglet {a['masa_winglet']:.3f} | flap {a['masa_flap']:.3f}")
    L.append(f"     cola {a['masa_cola']:.3f} | fuselaje {a['masa_fuselaje']:.3f} | boom {a['masa_boom']:.3f}")
    L.append(f"  TOTAL ................. {a['masa_total']:6.2f} kg   ({100*a['fraccion_estructural']:.0f}% estructura)")
    L.append(f"  flecha en punta ....... {a['flecha_punta_mm']:6.1f} mm  "
             f"({'la rigidez dimensiona el larguero' if a['manda_rigidez'] else 'manda la resistencia'})")
    L.append("")
    L.append("GEOMETRIA")
    L.append(f"  envergadura ........... {a['envergadura']:6.2f} m   (variable de diseno)")
    L.append(f"  superficie ............ {a['S']:6.3f} m2   AR = {a['AR']:.1f}   MAC = {a['MAC']:.3f} m")
    L.append(f"  carga alar ............ {a['carga_alar']:6.1f} N/m2")
    L.append(f"  volumen de cola ....... V_H = {a['V_H']:.3f}   V_V = {a['V_V']:.4f}"
             f"   (ref. clase: V_H 0.5-0.7, V_V 0.02-0.05)")
    L.append("")
    L.append(f"CRUCERO a {3.6*V_CRUCERO:.0f} km/h   (Re = {a['Re_crucero']:,.0f})")
    L.append(f"  CL necesario .......... {a['CL_crucero']:6.3f}   (CL max limpio {a['CL_max_crucero']:.3f})")
    L.append(f"  angulo de ataque ...... {a['alpha_crucero']:6.2f} grados")
    L.append(f"  L/D ................... {a['LD_crucero']:6.2f}")
    L.append(f"  resistencia ........... {a['D_crucero']:6.2f} N")
    L.append(f"  potencia aerodinamica . {a['potencia_W']:6.1f} W   (sin rendimiento de helice ni motor)")
    L.append("")
    L.append(f"VELOCIDAD MAXIMA a {3.6*V_MAX:.0f} km/h   (requisito, ya NO punto de diseno)")
    L.append(f"  CL necesario .......... {a['CL_vmax']:6.3f}   (CL max limpio {a['CL_max_vmax']:.3f})")
    L.append(f"  resistencia ........... {a['D_vmax']:6.2f} N")
    L.append(f"  potencia aerodinamica . {a['D_vmax']*V_MAX:6.1f} W   (sin rendimiento de helice ni motor)")
    L.append("")
    L.append(f"VUELO LENTO a {a['V_LENTO']:.0f} m/s   (Re = {a['Re_lento']:,.0f})")
    if a["tiene_flap"]:
        L.append(f"  flap .................. {100*a['flap_cuerda_frac']:.0f}% de cuerda, "
                 f"{100*a['flap_frac_superficie']:.0f}% de la superficie, {a['flap_deflexion']:.0f} grados")
    else:
        L.append("  flap .................. SIN FLAP")
    L.append(f"  CL necesario .......... {a['CL_lento']:6.3f}   (CL max con flap {a['CL_max_lento']:.3f})")
    L.append(f"  velocidad de perdida .. {a['v_stall']:6.2f} m/s   "
             f"(objetivo <= {V_STALL_OBJETIVO:.2f} para volar a {a['V_LENTO']:.0f} con margen {MARGEN_SOBRE_PERDIDA:.2f})")
    L.append(f"  margen de vuelo lento . {100*a['margen_lento']:6.1f} %   (100% = justo en el objetivo)")
    L.append("")
    L.append("ESTABILIDAD ESTATICA")
    L.append(f"  Cm_alpha .............. {a['Cm_alpha_por_grado']:8.5f} /grado   (< 0 exigido)")
    L.append(f"  margen estatico (SM) .. {100*a['SM']:6.2f} %   (banda {100*a['sm_min']:.0f}-{100*a['sm_max']:.0f}%)")
    L.append(f"  CG .................... {100*a['cg_frac_mac']:6.2f} % de la MAC")
    L.append(f"  Cm en crucero ......... {a['Cm_crucero']:8.5f}   (0 = trimado sin elevador)")
    L.append(f"  Cn_beta ............... {a['Cn_beta']:8.5f} /grado   (> 0 exigido)")
    L.append(f"  Cl_beta ............... {a['Cl_beta']:8.5f} /grado   (< 0 exigido)")
    L.append("")
    L.append("AMORTIGUAMIENTO (informativo)")
    L.append(f"  Cl_p {a['Cl_p']:8.4f}   Cn_r {a['Cn_r']:8.4f}   "
             f"Cn_p {a['Cn_p']:8.4f}   Cl_r {a['Cl_r']:8.4f}   [/rad]")
    L.append("")
    if a["viento_activo"]:
        L.append("VIENTO DEL SITIO  (peor caso Canadon Leon / Puesto Hernandez, ver viento.py)")
        L.append(f"  densidad del aire ..... {a['rho']:6.3f} kg/m3   (nivel del mar: 1.225)")
        L.append(f"  turbulencia ........... sigma_n = {a['sigma_n_turbulencia']:.3f}  -> "
                 f"+{100*a['extra_turbulencia']:.1f} % de resistencia  (D = {a['D_turbulento']:.2f} N)")
        L.append("")
    L.append(f"RAFAGA VERTICAL DE DISENO {a['rafaga_vertical']:.2f} m/s  (en crucero)")
    L.append(f"  Kg = {a['Kg']:.3f}  (mu = {a['mu']:.1f})   d_alpha = {a['d_alpha_rafaga']:.2f} grados")
    L.append(f"  dn = {a['dn_rafaga']:.2f}  -> factor de carga {a['n_con_rafaga']:.2f} g   "
             f"(estructura: limite {N_LIMITE:.1f}, ultima {N_ULTIMO:.1f})")
    L.append(f"  margen de perdida ..... {100*a['margen_perdida']:6.1f} %   (puntaje pleno desde {100*MARGEN_PERDIDA_OK:.0f}%)")
    L.append("")
    L.append("PUNTAJE")
    for nombre, w, f in terms:
        L.append(f"  {nombre:.<28} {w:.2f} x {f:5.3f} = {w*f:6.3f}   ({100*w*f/total:4.1f} %)")
    L.append(f"  {'TOTAL':.<28} {total:22.3f}")
    return "\n".join(L)
