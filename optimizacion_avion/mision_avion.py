"""
Función objetivo de MISIÓN.

==========================================================================
ESTADO ACTUAL (2026-10-19) -- leer esto primero
==========================================================================
Las secciones fechadas de abajo son el HISTORIAL de decisiones y describen
la misión de cada momento. Lo vigente es:

  * TRES puntos de vuelo: crucero de DISEÑO a 80 km/h (V_CRUCERO), velocidad
    máxima 120 km/h (V_MAX, restricción + término de puntaje) y vuelo lento a
    10 m/s (V_LENTO).
  * Vuelo lento: la restricción DURA es v_stall < V_LENTO. El margen de 20 %
    (V_STALL_OBJETIVO = 8.33 m/s) NO se exige: se premia en el puntaje
    (f_lento llega a 1 justo en el objetivo).
  * Interruptores VIENTO_ACTIVO, BATERIA_ACTIVA, PUNTAJE_MODO y TRIM_RESUELTO.
  * Con viento, la ráfaga del sitio no puede superar N_RAFAGA_ADMISIBLE (por
    defecto la carga LÍMITE N_LIMITE = 3.0, ver la actualización 2026-10-19).
  * Puntaje (PUNTAJE_MODO = "mision", V51.2): UN objetivo, la energía para
    volar el alcance (`energia_mision_wh`), + requisitos pasa/no pasa
    (`requisitos_incumplidos`) + dos términos pendientes de decisión (vuelo
    lento, velocidad máxima). Envergadura total <= ENVERGADURA_MAX_M = 3.0 m
    (SORA, requisito desde 2026-10-19). "legado" = los 11-12 términos de
    antes. Ver "PUNTAJE POR MISIÓN" al final de este encabezado.
  * Trim resuelto (TRIM_RESUELTO): la incidencia de cola se calcula para
    Cm = 0 en crucero; `params_trimados` devuelve el avión analizado.
  * Infactibles rankeados por violación (RANKING_INFACTIBLES, V51.3, reglas
    de Deb): ver la clase `Infactible`. `es_factible` / `describir_puntaje`
    para leer un puntaje; `analizar_con_motivo` para saber por qué falla.

==========================================================================
2026-09-17 -- DOS PUNTOS DE VUELO (historial)
==========================================================================

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
          + w_en  * f_envergadura  (NUEVO 2026-09-28: penaliza envergadura > 2.0 m,
                                     dificultad de fabricación artesanal)

RESTRICCIONES DURAS: estructura que no cierra, volumen de fuselaje
insuficiente, no sostenerse a 120 km/h, no poder volar a 10 m/s ni con flap,
margen estático negativo, Cn_beta <= 0, Cl_beta >= 0, entrar en pérdida con
la ráfaga de diseño en crucero, o (con viento) ráfaga por encima de
N_RAFAGA_ADMISIBLE.

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

==========================================================================
ACTUALIZACIÓN 2026-09-28 -- PENALIZACIÓN POR ENVERGADURA (FABRICACIÓN)
==========================================================================
Pedido de Felipe después de revisar el código: una semiala de más de 1 m
(envergadura total > 2.0 m) deja de entrar en una sola pieza en moldes o
mesas de trabajo artesanales, y empalmarla en dos tramos agrega peso de
unión y riesgo de fabricación que el modelo no ve de ninguna otra forma --
ni la masa estructural (`estructura_avion.py`) ni la aerodinámica cobran
nada por esto hoy.

Se implementa como término de PUNTAJE adicional (`f_en`, peso
`PESO_ENVERGADURA`), no como restricción dura: 2.0 m sigue siendo
alcanzable -- de hecho es el límite INFERIOR de `BOUNDS_ALA["envergadura"]`
en `geometria_avion.py`, así que todo el rango de diseño queda por encima
de o en el umbral -- pero por encima cuesta puntaje, con una caída suave
(meseta gaussiana, igual criterio que `_meseta` para estabilidad y ráfaga)
en vez de un salto. Se eligió meseta y no gate duro porque la dificultad de
fabricación es progresiva (1.1 m de semiala no es igual de grave que 1.75 m)
y porque un gate en 2.0 m dejaría in-evaluable de golpe buena parte del
rango ya explorado por corridas anteriores.

==========================================================================
ACTUALIZACIÓN 2026-10-12 -- BATERÍA DIMENSIONADA POR ALCANCE (350 km)
==========================================================================
Con BATERIA_ACTIVA = True (interruptor al lado de VIENTO_ACTIVO) la batería
deja de ser parte de MASA_SISTEMAS y pasa a ser una masa explícita que sale de
la resistencia de crucero del propio candidato: volar bateria.ALCANCE_KM (350)
a V_CRUCERO constante cuesta E = (D*V/eta + P_avionica)*t*(1+reserva), y
m_bat = E / (Wh/kg del pack). Como la batería pesa, el peso sube, la
resistencia inducida sube y hace falta más batería: el lazo se cierra con
`analizar_mision_avion` (varias pasadas aerodinámicas completas, ~2). El volumen
que ocupa la batería se le suma al volumen mínimo de fuselaje.
Todos los supuestos (rendimiento propulsivo 0.65, celda, reserva, overhead del
pack) están como constantes nombradas al principio de bateria.py.
Con BATERIA_ACTIVA = False vuelve el modelo anterior (batería dentro de
MASA_SISTEMAS = 1.5 kg). Ver evaluacion_bateria_350km/LEEME.md.

==========================================================================
ACTUALIZACIÓN 2026-10-19 -- RÁFAGA CONTRA LA CARGA LÍMITE
==========================================================================
Con viento, la ráfaga del sitio se comparaba contra la carga ÚLTIMA
(N_ULTIMO = 4.5). Pero la estructura se dimensiona para N_ULTIMO =
N_LIMITE x 1.5: aceptar una ráfaga hasta 4.5 g era aceptar que el ala llegue
a la rotura sin ningún coeficiente de seguridad. Las cargas de ráfaga de
diseño (FAR/CS 23.333 y 23.341) son cargas LÍMITE, así que se comparan contra
N_LIMITE. Queda como constante (N_RAFAGA_ADMISIBLE) para poder moverla; si se
quiere permitir ráfagas mayores, lo coherente es subir N_LIMITE (lo que
también encarece el larguero), no relajar esta comparación. Sin viento no se
aplica, para que VIENTO_ACTIVO = False siga dando lo mismo que antes.

Además: el lazo de batería informa la masa con la que se hizo la ÚLTIMA
pasada (antes, si no convergía, reportaba una masa distinta de la que se
había usado), y `_analizar_pasada` ya no se traga los errores de programación
(ver `_ERRORES_DE_PROGRAMACION`).

==========================================================================
ACTUALIZACIÓN 2026-10-19 (V51.2) -- PUNTAJE POR MISIÓN Y TRIM RESUELTO
==========================================================================
Una revisión de la ponderación contra lo que pide Quintana (alcance ante
todo: pozos a 60-70 km, 200-300 km de autonomía) mostró que el puntaje de 11
términos no medía la misión:
  - de los ~4.5 puntos, ~3 eran iguales para todos los diseños válidos
    (estabilidad 1.5, margen de pérdida 0.4, lateral 0.3, turbulencia 0.73)
    y otros siempre valían ~0 (ráfaga, envergadura por encima de 2.8 m);
  - eficiencia, masa y turbulencia contaban la misma cosa (la energía) dos o
    tres veces y con referencias de escala viejas (D_REF = 3.2 N con D ~ 6 N);
  - el término de trim, exp(-(Cm/0.02)^2), pesaba más que la aerodinámica:
    Cm = -0.014 costaba lo mismo que ~20 % de resistencia, y castigaba
    cualquier cambio de forma (por ejemplo un winglet que baja la resistencia
    6 %) porque corre el Cm con el CG y la incidencia fijos;
  - correlación de rangos entre el puntaje y la masa para 350 km: 0.5.
Cambios:
  1. OBJETIVO ÚNICO: ENERGIA_REFERENCIA_WH / energia_mision_wh (peso
     PESO_ALCANCE). Con batería, la energía ya incluye el peso de la batería.
  2. REQUISITOS PASA / NO PASA (requisitos_incumplidos): SM dentro de la
     banda, margen de pérdida con ráfaga >= 20 %, Cn_beta >= CN_BETA_MIN,
     Cl_beta <= -CL_BETA_MIN, y que el trim converja.
  3. TRIM RESUELTO: ver la sección 3a de `_analizar_pasada`. Si la
     incidencia necesaria cae fuera de BOUNDS, el candidato es inválido.
Quedan como términos PENDIENTES, con la forma y el peso de antes, el margen de
vuelo lento (Quintana pide ~7 m/s para sensores de metano/IR; el modelo usa
10 m/s), la resistencia a 120 km/h (viento) y la envergadura (límite de
fabricación). El modo "legado" conserva todo lo anterior para comparar.
"""

from __future__ import annotations

import aerosandbox as asb
import numpy as np

from collections import Counter

from optimizacion_ala.estructura import G, MASA_PAYLOAD, MASA_SISTEMAS, N_LIMITE, N_ULTIMO

from . import viento as _viento
from . import bateria as _bat

from .estructura_avion import converger_masa_avion
from .geometria_avion import (
    BOUNDS_POR_TOPOLOGIA, SM_BANDS, TOPOLOGIAS, construir_avion, geometria_flap,
    referencias_ala, volumenes_de_cola,
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

# Batería dimensionada por ALCANCE (2026-10-12, ver bateria.py). En True la masa
# de batería sale de la resistencia de crucero para volar _bat.ALCANCE_KM a
# V_CRUCERO, y entra al peso del avión (lazo cerrado). En False todo vuelve a
# ser exactamente como antes (batería dentro de MASA_SISTEMAS = 1.5 kg).
BATERIA_ACTIVA = True

# Cómo se arma el puntaje (2026-10-19, ver "PUNTAJE POR MISIÓN" en el encabezado):
#   "mision": UN objetivo (energía para volar el alcance) + los requisitos
#             pasa/no pasa como restricciones + los términos todavía pendientes
#             de decisión (vuelo lento, velocidad máxima, envergadura).
#   "legado": la suma ponderada de 11-12 términos de antes, para comparar.
PUNTAJE_MODO = "mision"

# Trim RESUELTO (2026-10-19): la incidencia de la cola (htail o cola en V) se
# calcula para que el avión vuele en crucero con Cm = 0 respecto del CG, y la
# resistencia se mide ahí. El valor de la incidencia que trae el candidato es
# solo el punto de partida. En False vuelve el modelo de antes (incidencia como
# variable de diseño y Cm puntuado en el modo "legado").
TRIM_RESUELTO = True

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

# --- Requisitos PASA / NO PASA (modo "mision") --------------------------
# Antes eran términos del puntaje que, dentro de lo aceptable, valían lo mismo
# para todos (estabilidad 1.5, margen de pérdida 0.4, lateral 0.3...): sumaban
# casi 3 puntos constantes y solo servían como un "casi gate" blando. Ahora
# son restricciones: se cumplen o el candidato queda afuera.
#   * margen estático dentro de la banda de la topología (SM_BANDS);
#   * margen de pérdida con la ráfaga de diseño >= MARGEN_PERDIDA_OK (20 %);
#   * estabilidad direccional y lateral con un mínimo, no solo con el signo.
# CN_BETA_MIN / CL_BETA_MIN son SUPUESTOS a validar: ~0.03 /rad, el extremo
# bajo de lo que se considera aceptable para estabilidad direccional estática
# en aviones livianos. Con el signo solo (> 0) pasaban diseños casi neutros
# (pod_boom con 0.0001 /grado).
CN_BETA_MIN = 0.0005          # [1/grado]  Cn_beta >= esto
CL_BETA_MIN = 0.0005          # [1/grado]  Cl_beta <= -esto

# --- Trim resuelto --------------------------------------------------------
_DI_TRIM = 1.0                # [grados] paso para medir dCm/d(incidencia)
TRIM_TOL_CM = 0.002           # |Cm| aceptado en crucero después de trimar
TRIM_MAX_CORRECCIONES = 2

# Factor de carga máximo admisible para la ráfaga del sitio (solo con
# VIENTO_ACTIVO). Es una carga LÍMITE: ver la actualización 2026-10-19 del
# encabezado. Antes era N_ULTIMO (4.5), sin margen sobre la rotura.
N_RAFAGA_ADMISIBLE = N_LIMITE

# Errores que indican un BUG (clave mal escrita, atributo inexistente, tipo
# equivocado), no un candidato inválido: se dejan subir para que no pase
# inadvertido que TODOS los candidatos dan -inf. Cualquier otra excepción
# (numérica, de NeuralFoil, de AeroSandbox) descarta el candidato y se cuenta
# en FALLAS_ANALISIS, que se puede mirar desde el notebook.
_ERRORES_DE_PROGRAMACION = (KeyError, NameError, AttributeError, ImportError, TypeError)
FALLAS_ANALISIS: Counter = Counter()

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
# LÍMITE DE ENVERGADURA POR FABRICACIÓN -- variable fácil de mover (ver
# encabezado, actualización 2026-09-28)
# =====================================================================
# No es una restricción aerodinámica: por encima de esto, la semiala deja de
# entrar en una sola pieza en los moldes/mesas de trabajo artesanales
# disponibles. Se penaliza con una meseta suave (ver _meseta), no con un gate
# duro -- 2.0 m coincide con el límite INFERIOR de BOUNDS_ALA["envergadura"]
# en geometria_avion.py, así que TODO candidato queda en la zona penalizada
# o justo en el borde; lo que el término hace es preferir, a igualdad de lo
# demás, el extremo angosto de ese rango en vez de tratarlo como gratis.
ENVERGADURA_MANUFACTURA_MAX = 2.0     # [m]  (solo modo "legado"; en "mision" manda ENVERGADURA_MAX_M)
# Ancho de la caída gaussiana (ver _meseta): a envergadura = MAX + TOL el
# término vale exp(-1) = 0.37. 0.4 m es un compromiso deliberado: bastante
# ancho para no castigar de forma abrupta 2.0-2.3 m (siguen siendo diseños
# razonables si el resto de la misión los favorece), pero angosto para que
# 3.0-3.5 m (el otro extremo de BOUNDS_ALA) quede claramente desfavorecido.
ENVERGADURA_MANUFACTURA_TOL = 0.4     # [m]

# =====================================================================
# ENVERGADURA MÁXIMA (requisito pasa / no pasa, 2026-10-19)
# =====================================================================
# Argentina (ANAC, Res. 550/2025) no limita la envergadura: clasifica por masa.
# Pero la misión es BVLOS (pozos a 60-70 km), así que cae en la categoría
# ESPECÍFICA, que exige un sistema de gestión de riesgo documentado ("por
# ejemplo SORA u otro equivalente"). En la tabla de riesgo en tierra de SORA
# la columna la define la dimensión característica (para un ala fija, la
# envergadura total, con winglets): hasta 3 m, BVLOS en zona poco poblada da
# GRC intrínseco 4; por encima, 5 (un escalón más de exigencia, SAIL III ->
# IV con riesgo aéreo bajo). La energía cinética (~3-7 kJ) queda muy por
# debajo del límite de esa columna (34 kJ), así que la envergadura es la que
# decide. Se toma 3.0 m "por ahora", a confirmar con la Parte 102 de las RAAC.
# Se mide sobre el avión COMPLETO (máximo |y| de todas las superficies,
# winglets incluidos), no sobre el parámetro `envergadura` del ala.
ENVERGADURA_MAX_M = 3.0               # [m] envergadura total, puntas de winglet incluidas

# =====================================================================
# OBJETIVO DE LA MISIÓN (modo "mision")
# =====================================================================
# La misión de Quintana es ALCANCE (pozos a 60-70 km, recorridos de ~120 km,
# 200-300 km de autonomía deseada; el requisito vigente es bateria.ALCANCE_KM).
# Con el alcance fijo, el mejor avión es el que necesita MENOS ENERGÍA de
# batería para volarlo: f_alcance = ENERGIA_REFERENCIA_WH / E, con
#   E = (D * V / eta + P_avionica) * t * (1 + reserva)     (bateria.py)
# y D la resistencia de crucero en las condiciones de la misión (con viento,
# la que incluye la turbulencia). Con BATERIA_ACTIVA, D ya es la del avión con
# su batería (lazo cerrado), así que la masa entra sola: un avión más pesado
# pide más sustentación, más inducida y más energía. Reemplaza a los términos
# de eficiencia, masa y turbulencia, que contaban lo mismo dos o tres veces
# (y con referencias de escala viejas: D_REFERENCIA = 3.2 N cuando hoy D ~ 6 N).
ENERGIA_REFERENCIA_WH = 1200.0   # [Wh] ~ lo que piden los aviones de 350 km (Research Note 17)
# Con 1.0 y la referencia de arriba, 1 % menos de energía suma ~0.01 puntos.
# TASA DE CAMBIO con los términos pendientes (para decidir con Quintana):
# 0.1 m/s menos de velocidad de pérdida (PESO_LENTO) vale ~6 % de energía.
PESO_ALCANCE = 1.0

# =====================================================================
# PESOS (modo "legado"; en "mision" solo se usan PESO_LENTO, PESO_VELMAX y
# PESO_ENVERGADURA, que quedan pendientes de decisión)
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
# NUEVO 2026-09-28: envergadura > 2.0 m, dificultad de fabricación artesanal
# (ver ENVERGADURA_MANUFACTURA_MAX/TOL más arriba). Peso moderado, a
# propósito comparable a masa/ráfaga/margen: es un criterio de INTEGRACIÓN
# (¿entra en el taller?), no de misión (¿vuela lo que tiene que volar?), así
# que no debería poder tapar a los términos de performance si el resto del
# candidato es claramente mejor.
PESO_ENVERGADURA = 0.3
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


# =====================================================================
# RANKING DE INFACTIBLES (reglas de Deb, 2026-10-19)
# =====================================================================
# K. Deb, "An efficient constraint handling method for genetic algorithms",
# Comput. Methods Appl. Mech. Engrg. 186 (2000) 311-338:
#   1) un factible le gana a cualquier infactible;
#   2) entre factibles gana el de mejor objetivo;
#   3) entre infactibles gana el que viola MENOS las restricciones.
# Antes todo lo infactible valía -inf: un avión con SM = 9.9 % era tan malo
# como uno que no vuela, y el GA no tenía hacia dónde moverse cuando las
# semillas o los hijos caían fuera de lo factible.
#
# Se codifica en UN número para que el GA no cambie: un infactible vale
#   PUNTAJE_INFACTIBLE_TECHO - 10 * (ETAPA_REQUISITOS - etapa) - 9.99 * v / (1 + v)
# donde `v` es la SUMA de las violaciones normalizadas de todo lo que el avión
# no cumple (1 ~ "violado por bastante"). Desde 2026-10-19 el análisis NO corta
# en la primera restricción que falla: la anota y sigue, así un avión al que
# le falta 0.01 de vuelo lento queda mejor que uno inestable (antes, por
# etapas, era al revés y el GA empeoraba antes de mejorar). `etapa` < 9 queda
# solo para los casos en que el análisis no puede seguir (la masa no
# converge, un CL_max no calculable, la cola no mueve el Cm...); todo lo demás
# es etapa 9. Todo infactible queda por debajo de PUNTAJE_INFACTIBLE_TECHO y
# todo factible por encima de 0; -inf queda para errores numéricos.
RANKING_INFACTIBLES = True          # solo en PUNTAJE_MODO = "mision"
PUNTAJE_INFACTIBLE_TECHO = -1000.0
ETAPAS = {
    0: "estructura que no cierra",
    1: "volumen de fuselaje",
    2: "vuelo lento",
    3: "sustentacion en crucero",
    4: "estabilidad longitudinal (margen estatico <= 0)",
    5: "trim (incidencia de cola fuera de rango)",
    6: "velocidad maxima / resistencia",
    7: "rafaga (perdida o carga limite)",
    8: "estabilidad latero-direccional (signo)",
    9: "requisitos y restricciones",
}
ETAPA_REQUISITOS = 9


class Infactible:
    """Resultado de un análisis que no cumple: en qué etapa falló, por cuánto
    (violación normalizada, >= 0) y por qué. `analizar_mision_avion` lo sigue
    devolviendo como None; lo usa `evaluar_mision_avion` para el ranking."""
    __slots__ = ("etapa", "violacion", "motivo")

    def __init__(self, etapa: int, violacion: float, motivo: str):
        v = float(violacion)
        self.etapa = int(etapa)
        self.violacion = v if np.isfinite(v) and v >= 0 else 10.0
        self.motivo = motivo

    def puntaje(self) -> float:
        v = self.violacion
        return PUNTAJE_INFACTIBLE_TECHO - 10.0 * (ETAPA_REQUISITOS - self.etapa) - 9.99 * v / (1.0 + v)

    def __repr__(self):
        return f"Infactible(etapa {self.etapa}: {ETAPAS[self.etapa]}, violacion {self.violacion:.3f}: {self.motivo})"


def es_factible(puntaje: float) -> bool:
    """True si el puntaje es de un candidato que cumple todo."""
    return bool(np.isfinite(puntaje) and puntaje > PUNTAJE_INFACTIBLE_TECHO)


def describir_puntaje(puntaje: float) -> str:
    """Texto legible de un puntaje: el valor si es factible, o la etapa y la
    violación si es infactible (decodifica lo que arma Infactible.puntaje)."""
    if es_factible(puntaje):
        return f"{puntaje:.4f}"
    if not np.isfinite(puntaje):
        return "invalido (no se pudo analizar)"
    d = PUNTAJE_INFACTIBLE_TECHO - puntaje
    escalon = int(d // 10.0)
    etapa = ETAPA_REQUISITOS - escalon
    frac = min((d - 10.0 * escalon) / 9.99, 0.999999)
    v = frac / (1.0 - frac)
    return f"infactible: {ETAPAS.get(etapa, '?')} (violacion {v:.2f})"


def clave_incidencia(topologia: str) -> str:
    """Parámetro de incidencia de la superficie horizontal de cola de la
    topología: el que se ajusta para trimar (ver TRIM_RESUELTO)."""
    return "v_tail_incidencia_deg" if TOPOLOGIAS[topologia]["cola"] == "v" else "htail_incidencia_deg"


def _analizar_pasada(params: dict, topologia: str, masa_bateria: float | None = None) -> "dict | Infactible | None":
    """Una pasada aerodinámica completa. `masa_bateria=None` es el modelo de
    siempre; con un valor, la batería es una masa explícita de ese tamaño.
    Devuelve el dict del análisis, un `Infactible` (qué chequeo falló y por
    cuánto) o None si no se pudo analizar (error numérico)."""
    sm_min, sm_max = SM_BANDS[topologia]
    try:
        # --- 1. Masa ----------------------------------------------------
        if masa_bateria is None:
            est = converger_masa_avion(params, topologia)
        else:
            est = converger_masa_avion(params, topologia,
                                       masa_sistemas=_bat.MASA_SISTEMAS_SIN_BATERIA,
                                       masa_extra=masa_bateria)
        if est is None:
            return Infactible(0, 1.0, "la masa no converge (o supera 60 kg)")
        W = est["peso_total"]
        # Restricciones que se pueden violar SIN impedir seguir el análisis: se
        # anotan acá (texto, violación normalizada) y se sigue, para que el
        # ranking sume TODAS las violaciones del avión (ver Infactible). Solo
        # cortan antes los casos en que ya no se puede calcular lo que sigue.
        viol = []
        trim_saturado = False

        avion = construir_avion(params, topologia)

        # --- 1b. Volumen mínimo de fuselaje (restricción geométrica dura) --
        # g(x) = V_requerido - eta_vol * V_geometrico <= 0 (Hajdik/Adler/
        # Martins AIAA 2023-3589). V_geometrico sale del fuselaje/góndola
        # PRINCIPAL (fuselages[0], ver construir_avion): nunca las vigas del
        # doble boom, que no cargan payload.
        vol_geo_L = float(avion.fuselages[0].volume()) * 1000.0
        vol_req_L = VOLUMEN_UTIL_MIN_L
        if masa_bateria is not None:
            # el 8.2 L ya traía ~0.5 L de batería: se cambia por el volumen real
            vol_req_L += _bat.volumen_bateria_l(masa_bateria) - _bat.VOLUMEN_BATERIA_INCLUIDO_L
        if vol_geo_L * FACTOR_UTILIZACION_VOLUMEN < vol_req_L:
            viol.append((f"volumen util {vol_geo_L * FACTOR_UTILIZACION_VOLUMEN:.1f} L < {vol_req_L:.1f} L",
                         (vol_req_L - vol_geo_L * FACTOR_UTILIZACION_VOLUMEN) / vol_req_L))

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

        # --- 2. Punto de vuelo LENTO ------------------------------------
        CL_max_lento = _clmax_ala(params, Re_lento, V_LENTO, con_flap=True)
        if not np.isfinite(CL_max_lento) or CL_max_lento <= 0:
            return Infactible(2, 1.0, "CL_max con flap no calculable")
        v_stall = float(np.sqrt(2.0 * W / (rho * S * CL_max_lento)))
        if v_stall >= V_LENTO:   # no puede volar a 10 m/s ni con el flap abajo
            viol.append((f"velocidad de perdida {v_stall:.2f} m/s >= {V_LENTO:.0f} m/s",
                         (v_stall - V_LENTO) / V_LENTO))
        # Margen relativo respecto del objetivo (1.0 = justo en el objetivo).
        margen_lento = (V_LENTO - v_stall) / max(V_LENTO - V_STALL_OBJETIVO, 1e-6)

        # --- 3. Crucero -------------------------------------------------
        CL_max_crucero = _clmax_ala(params, Re_crucero, V_CRUCERO, con_flap=False)
        if not np.isfinite(CL_max_crucero) or CL_max_crucero <= 0:
            return Infactible(3, 1.0, "CL_max de crucero no calculable")
        CL_crucero = W / (q * S)
        if CL_crucero >= CL_max_crucero:
            viol.append((f"CL de crucero {CL_crucero:.2f} >= CL_max {CL_max_crucero:.2f}",
                         (CL_crucero - CL_max_crucero) / CL_max_crucero))

        pts = []
        for a in (_A_LO, _A_HI):
            r = asb.AeroBuildup(airplane=avion,
                                op_point=asb.OperatingPoint(atmosphere=atm, velocity=V_CRUCERO, alpha=a)).run()
            pts.append((_escalar(r["CL"]), _escalar(r["Cm"])))
        (CL1, Cm1), (CL2, Cm2) = pts
        if abs(CL2 - CL1) < 1e-9:
            return Infactible(4, 1.0, "CL no cambia con alpha")
        CL_alpha = (CL2 - CL1) / (_A_HI - _A_LO)
        Cm_alpha = (Cm2 - Cm1) / (_A_HI - _A_LO)
        dCm_dCL = (Cm2 - Cm1) / (CL2 - CL1)
        SM = -dCm_dCL
        Cm0 = Cm1 - dCm_dCL * CL1
        CL_trim = Cm0 / SM if abs(SM) > 1e-9 else float("nan")
        if not np.isfinite(SM):
            return Infactible(4, 10.0, "margen estatico no calculable")
        # SM <= 0 (inestable) no corta: lo cuenta la banda de SM en los
        # requisitos (y en el modo "legado" invalida, ver _restricciones_duras).

        def _crucero(av, alfa):
            return asb.AeroBuildup(airplane=av, op_point=asb.OperatingPoint(
                atmosphere=atm, velocity=V_CRUCERO, alpha=alfa)).run()

        clave_inc = clave_incidencia(topologia)
        incidencia_inicial = float(params[clave_inc])
        alpha_crucero = _A_LO + (CL_crucero - CL1) / CL_alpha

        if not TRIM_RESUELTO:
            r = _crucero(avion, alpha_crucero)
        else:
            # --- 3a. Trim resuelto (ver TRIM_RESUELTO) --------------------
            # Modelo lineal en (alpha, incidencia) alrededor del punto medido:
            #   CL = CL1 + CL_alpha (a - A_LO) + CL_i di
            #   Cm = Cm1 + Cm_alpha (a - A_LO) + Cm_i di
            # Se pide CL = CL_crucero y Cm = 0. CL_i y Cm_i salen de UNA
            # corrida extra con la incidencia corrida _DI_TRIM grados.
            lo_i, hi_i = BOUNDS_POR_TOPOLOGIA[topologia][clave_inc]
            av_i = construir_avion({**params, clave_inc: incidencia_inicial + _DI_TRIM}, topologia)
            r_i = asb.AeroBuildup(airplane=av_i, op_point=asb.OperatingPoint(
                atmosphere=atm, velocity=V_CRUCERO, alpha=_A_LO)).run()
            CL_i = (_escalar(r_i["CL"]) - CL1) / _DI_TRIM
            Cm_i = (_escalar(r_i["Cm"]) - Cm1) / _DI_TRIM
            det = CL_alpha * Cm_i - Cm_alpha * CL_i
            if abs(det) < 1e-12:   # la cola no controla el cabeceo: no se puede trimar
                return Infactible(5, 1.0, "la incidencia de cola no mueve el Cm")
            # Residuos respecto del objetivo, partiendo del punto medido.
            res_CL, res_Cm = CL_crucero - CL1, -Cm1
            d_alpha_t = (res_CL * Cm_i - CL_i * res_Cm) / det
            d_inc = (CL_alpha * res_Cm - Cm_alpha * res_CL) / det
            alpha_crucero, incidencia = _A_LO + d_alpha_t, incidencia_inicial + d_inc
            for k in range(TRIM_MAX_CORRECCIONES + 1):
                if not (lo_i <= incidencia <= hi_i):
                    # Haría falta más incidencia de la que permite el diseño: se
                    # usa la del borde (el avión queda sin trimar) y se anota.
                    viol.append((f"trim pide {incidencia:+.1f} grados de incidencia (rango {lo_i:+.0f} a {hi_i:+.0f})",
                                 max(lo_i - incidencia, incidencia - hi_i) / 5.0))
                    incidencia = min(max(incidencia, lo_i), hi_i)
                    trim_saturado = True
                params = {**params, clave_inc: incidencia}
                avion = construir_avion(params, topologia)
                r = _crucero(avion, alpha_crucero)
                res_CL = CL_crucero - _escalar(r["CL"])
                res_Cm = -_escalar(r["Cm"])
                if trim_saturado or abs(res_Cm) <= TRIM_TOL_CM or k == TRIM_MAX_CORRECCIONES:
                    break
                # Corrección de Newton con las mismas derivadas.
                alpha_crucero += (res_CL * Cm_i - CL_i * res_Cm) / det
                incidencia += (CL_alpha * res_Cm - Cm_alpha * res_CL) / det

        CD = _escalar(r["CD"])
        frac_inducida = _escalar(r["D_induced"]) / _escalar(r["D"])
        CL_real = _escalar(r["CL"])
        Cm_crucero = _escalar(r["Cm"])
        if CD <= 0 or not np.isfinite(CD):
            return Infactible(6, 1.0, "CD de crucero no valido")

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
            return Infactible(6, 1.0, "CL_max a V_MAX no calculable")
        CL_vmax = W / (q_vmax * S)
        if CL_vmax >= CL_max_vmax:   # no se sostiene a 120 km/h -- restricción dura
            viol.append((f"no se sostiene a {3.6*V_MAX:.0f} km/h", (CL_vmax - CL_max_vmax) / CL_max_vmax))

        # Desde el punto de crucero (que con TRIM_RESUELTO ya es el del avión
        # trimado) con la pendiente medida.
        alpha_vmax = alpha_crucero + (CL_vmax - CL_crucero) / CL_alpha
        r_vmax = asb.AeroBuildup(airplane=avion,
                                 op_point=asb.OperatingPoint(atmosphere=atm, velocity=V_MAX, alpha=alpha_vmax)).run()
        CD_vmax = _escalar(r_vmax["CD"])
        CD_vmax = CD_vmax * (1.0 + PENAL_CD_FLAP * fl["frac_superficie"]) if fl["tiene_flap"] else CD_vmax
        if CD_vmax <= 0 or not np.isfinite(CD_vmax):
            return Infactible(6, 1.0, "CD a V_MAX no valido")
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
        # margen_perdida <= 0 (entra en pérdida con la ráfaga) no corta: lo
        # cuenta el requisito de margen >= MARGEN_PERDIDA_OK.
        # Con la ráfaga del sitio: la ráfaga de diseño es una carga LÍMITE y no
        # puede superar la carga límite de la estructura (ver encabezado,
        # actualización 2026-10-19).
        if VIENTO_ACTIVO and 1.0 + dn_rafaga > N_RAFAGA_ADMISIBLE:
            viol.append((f"rafaga del sitio n = {1 + dn_rafaga:.2f} > {N_RAFAGA_ADMISIBLE:.1f}",
                         (1.0 + dn_rafaga - N_RAFAGA_ADMISIBLE) / N_RAFAGA_ADMISIBLE))

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
            return Infactible(8, 1.0, "derivadas laterales no calculables")
        Cl_beta = (Cl_hi - Cl_lo) / (_B_HI - _B_LO)
        Cn_beta = (Cn_hi - Cn_lo) / (_B_HI - _B_LO)
        # Signos inestables (Cn_beta <= 0, Cl_beta >= 0) no cortan: los cuentan
        # los mínimos CN_BETA_MIN / CL_BETA_MIN de los requisitos.

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
        vol = volumenes_de_cola(params, topologia, avion)
        # Envergadura TOTAL (dimensión característica de SORA): el |y| máximo de
        # todas las superficies, winglets incluidos.
        envergadura_total = 2.0 * max(abs(float(xs.xyz_le[1])) for w in avion.wings for xs in w.xsecs)

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
            "envergadura": b_ref_w, "envergadura_total": envergadura_total,
            "S": S, "AR": b_ref_w ** 2 / max(S, 1e-9),
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
            "trim_resuelto": TRIM_RESUELTO, "trim_saturado": trim_saturado,
            "violaciones_analisis": viol, "clave_incidencia": clave_inc,
            "incidencia_inicial_deg": incidencia_inicial,
            "incidencia_trim_deg": float(params[clave_inc]),
            # params con la incidencia de trim: es el avión que se analizó
            # (lo que hay que exportar a CAD/CFD, ver params_trimados).
            "params_trimados": dict(params),
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
            "masa_sistemas": est["masa_sistemas"], "masa_bateria_usada": masa_bateria,
            "vol_geo_L": vol_geo_L, "vol_requerido_L": vol_req_L,
            "frac_inducida": frac_inducida, "sigma_n_turbulencia": sigma_n,
            "extra_turbulencia": extra_turbulencia,
            "D_turbulento": D_crucero * (1.0 + extra_turbulencia),
        }
    except _ERRORES_DE_PROGRAMACION:
        raise
    except Exception as e:      # candidato numéricamente inválido
        FALLAS_ANALISIS[type(e).__name__] += 1
        return None


def analizar_mision_avion(params: dict, topologia: str) -> dict | None:
    """Análisis completo de misión: el dict de resultados, o None si el
    candidato es infactible o no se pudo analizar. Para saber POR QUÉ es
    infactible (etapa y violación), ver `analizar_con_motivo`."""
    a = analizar_con_motivo(params, topologia)
    return a if isinstance(a, dict) and not _restricciones_duras(a) else None


def _restricciones_duras(a: dict) -> list:
    """Restricciones que siempre invalidaron un candidato (también en el modo
    "legado"): las que anota el análisis + entrar en pérdida con la ráfaga,
    margen estático <= 0 y signos látero-direccionales inestables."""
    duras = [t for t, _ in a.get("violaciones_analisis", [])]
    if a["margen_perdida"] <= 0.0:
        duras.append("entra en perdida con la rafaga")
    if a["SM"] <= 0.0:
        duras.append("margen estatico <= 0 (inestable)")
    if a["Cn_beta"] <= 0.0 or a["Cl_beta"] >= 0.0:
        duras.append("estabilidad latero-direccional de signo inestable")
    return duras


def analizar_con_motivo(params: dict, topologia: str) -> "dict | Infactible | None":
    """Como `analizar_mision_avion`, pero un infactible vuelve como
    `Infactible` (etapa, violación, motivo) en vez de None. None queda solo
    para lo que no se pudo analizar.

    Con BATERIA_ACTIVA = False es una sola pasada con el modelo de masas de
    siempre. Con True cierra el lazo batería <-> resistencia: cada pasada corre
    la aerodinámica completa con una masa de batería dada, y de ahí sale (con
    la resistencia reescalada por peso, ver bateria.resistencia_a_peso) la masa
    de batería que corresponde; se repite hasta que deja de cambiar (en la
    práctica 2 pasadas)."""
    if not BATERIA_ACTIVA:
        return _analizar_pasada(params, topologia, None)

    m_b = _bat.MASA_BATERIA_INICIAL_KG
    convergio = False
    for i in range(_bat.MAX_PASADAS):
        a = _analizar_pasada(params, topologia, m_b)
        if not isinstance(a, dict):
            return a
        D_ef = a["D_turbulento"] if VIENTO_ACTIVO else a["D_crucero"]
        m_nueva = _bat.cerrar_masa_bateria(D_ef, a["frac_inducida"], a["peso"],
                                           a["masa_total"] - m_b, m_b, V_CRUCERO)
        if not np.isfinite(m_nueva):
            return Infactible(0, 1.0, f"la bateria para {_bat.ALCANCE_KM:.0f} km diverge "
                                      f"(pide mas de {_bat.MASA_BATERIA_MAX_KG:.0f} kg)")
        if abs(m_nueva - m_b) <= _bat.TOL_MASA_BATERIA_KG:
            convergio = True
            break
        if i == _bat.MAX_PASADAS - 1:
            # Sin pasadas restantes: NO se actualiza m_b, así todo lo que se
            # informa abajo corresponde a la pasada que efectivamente se corrió.
            # El déficit queda a la vista en "alcance_logrado_km" < objetivo.
            break
        m_b = m_nueva

    # Balance de energía con la masa de batería que SE USÓ en la última pasada
    # (m_b es siempre la de `a`, haya convergido o no).
    e_pack = _bat.energia_especifica_pack()
    E_disp = m_b * e_pack
    E_req = _bat.energia_requerida_wh(D_ef, V_CRUCERO)
    pack = _bat.dimensionar_pack(max(E_req, E_disp))
    despegue = _bat.estimar_despegue(a["peso"], a["rho"], pack)
    P_el = _bat.potencia_electrica_crucero(D_ef, V_CRUCERO)
    a["masa_bateria"] = m_b
    a["bateria"] = {
        "alcance_objetivo_km": _bat.ALCANCE_KM,
        "alcance_logrado_km": _bat.ALCANCE_KM * E_disp / E_req,
        "eta_propulsiva": _bat.ETA_PROPULSIVA_TOTAL,
        "potencia_electrica_crucero_W": P_el,
        "corriente_crucero_A": P_el / pack["tension_nominal_V"],
        "energia_requerida_wh": E_req, "energia_disponible_wh": E_disp,
        "energia_especifica_pack_wh_kg": e_pack,
        "masa_bateria_kg": m_b, "fraccion_masa_bateria": m_b / a["masa_total"],
        "convergio": convergio, "masa_bateria_punto_fijo_kg": m_nueva,
        "volumen_bateria_l": _bat.volumen_bateria_l(m_b),
        "pack": pack, "despegue": despegue,
    }
    return a


def energia_mision_wh(a: dict) -> float:
    """[Wh] de batería (con reserva) para volar bateria.ALCANCE_KM a V_CRUCERO
    con la resistencia de la misión (la turbulenta, con viento). Con
    BATERIA_ACTIVA es la del avión con su batería (lazo cerrado); sin batería,
    la del avión con MASA_SISTEMAS fija. Es el objetivo del modo "mision"."""
    if a.get("bateria"):
        return float(a["bateria"]["energia_requerida_wh"])
    D_ef = a["D_turbulento"] if a["viento_activo"] else a["D_crucero"]
    return float(_bat.energia_requerida_wh(D_ef, V_CRUCERO))


def _requisitos_con_violacion(a: dict) -> list:
    """[(texto, violación normalizada)] de los requisitos PASA / NO PASA del
    modo "mision" que el análisis no cumple. Los que ya descartan el candidato
    en `_analizar_pasada` (volumen, vuelo lento, V_MAX, ráfaga, signos de
    estabilidad) no aparecen acá porque ese candidato ni llega."""
    fallas = list(a.get("violaciones_analisis", []))   # volumen, vuelo lento, V_MAX, trim, ráfaga...
    sm, lo, hi = a["SM"], a["sm_min"], a["sm_max"]
    if not (lo <= sm <= hi):
        fallas.append((f"margen estatico {100*sm:.1f}% fuera de la banda {100*lo:.0f}-{100*hi:.0f}%",
                       max(lo - sm, sm - hi) / 0.05))
    if a["margen_perdida"] < MARGEN_PERDIDA_OK:
        fallas.append((f"margen de perdida con rafaga {100*a['margen_perdida']:.1f}% < {100*MARGEN_PERDIDA_OK:.0f}%",
                       (MARGEN_PERDIDA_OK - a["margen_perdida"]) / MARGEN_PERDIDA_OK))
    if a["Cn_beta"] < CN_BETA_MIN:
        fallas.append((f"Cn_beta {a['Cn_beta']:.5f} < {CN_BETA_MIN:.5f} /grado",
                       (CN_BETA_MIN - a["Cn_beta"]) / CN_BETA_MIN))
    if a["Cl_beta"] > -CL_BETA_MIN:
        fallas.append((f"Cl_beta {a['Cl_beta']:.5f} > -{CL_BETA_MIN:.5f} /grado",
                       (a["Cl_beta"] + CL_BETA_MIN) / CL_BETA_MIN))
    b_tot = a.get("envergadura_total", a["envergadura"])
    if b_tot > ENVERGADURA_MAX_M:
        fallas.append((f"envergadura total {b_tot:.2f} m > {ENVERGADURA_MAX_M:.1f} m (SORA)",
                       (b_tot - ENVERGADURA_MAX_M) / 0.3))
    if a.get("trim_resuelto") and not a.get("trim_saturado") and abs(a["Cm_crucero"]) > 5 * TRIM_TOL_CM:
        fallas.append((f"no se pudo trimar (Cm en crucero {a['Cm_crucero']:+.4f})",
                       abs(a["Cm_crucero"]) / (5 * TRIM_TOL_CM) - 1.0))
    return fallas


def requisitos_incumplidos(a: dict) -> list:
    """Textos de los requisitos PASA / NO PASA que el análisis no cumple
    (lista vacía = cumple todo). Ver `_requisitos_con_violacion`."""
    return [t for t, _ in _requisitos_con_violacion(a)]


def _terminos(a: dict) -> list:
    """(nombre, peso, f) de cada término del puntaje, según PUNTAJE_MODO."""
    if PUNTAJE_MODO == "mision":
        return _terminos_mision(a)
    if PUNTAJE_MODO != "legado":
        raise ValueError(f"PUNTAJE_MODO desconocido: {PUNTAJE_MODO!r} (usar 'mision' o 'legado')")
    return _terminos_legado(a)


def _terminos_mision(a: dict) -> list:
    """Modo "mision": un objetivo (energía para el alcance) y los dos términos
    que todavía esperan una decisión de Quintana/Felipe, con la misma forma y
    peso que tenían. Ver ENERGIA_REFERENCIA_WH / PESO_ALCANCE para la tasa de
    cambio entre ellos. La envergadura dejó de ser término (2026-10-19): es el
    requisito ENVERGADURA_MAX_M (SORA)."""
    f_le = min(1.0, max(a["margen_lento"], 0.0))
    f_vm = D_REFERENCIA_VMAX / a["D_vmax"]
    return [
        (f"alcance (energia {_bat.ALCANCE_KM:.0f} km)", PESO_ALCANCE, ENERGIA_REFERENCIA_WH / energia_mision_wh(a)),
        ("PENDIENTE vuelo lento", PESO_LENTO, f_le),
        ("PENDIENTE velocidad maxima", PESO_VELMAX, f_vm),
    ]


def puntaje_de_analisis(a: "dict | Infactible | None") -> float:
    """Puntaje de un análisis ya hecho (lo que sale de `analizar_con_motivo`
    o de `analizar_mision_avion`). Usar esto en vez de sumar `_terminos` a
    mano, que se saltea las restricciones.

    - factible: la suma de los términos (siempre > 0);
    - infactible, en modo "mision" con RANKING_INFACTIBLES: un número por
      debajo de PUNTAJE_INFACTIBLE_TECHO que ordena por cuánto viola (reglas
      de Deb, ver Infactible); si no, -inf;
    - no analizable (None): -inf."""
    rankear = PUNTAJE_MODO == "mision" and RANKING_INFACTIBLES
    if a is None:
        return -np.inf
    if isinstance(a, Infactible):
        return a.puntaje() if rankear else -np.inf
    if PUNTAJE_MODO != "mision" and _restricciones_duras(a):
        return -np.inf
    if PUNTAJE_MODO == "mision":
        fallas = _requisitos_con_violacion(a)
        if fallas:
            if not rankear:
                return -np.inf
            return Infactible(ETAPA_REQUISITOS, sum(v for _, v in fallas),
                              "; ".join(t for t, _ in fallas)).puntaje()
    return float(sum(w * f for _, w, f in _terminos(a)))


def _terminos_legado(a: dict) -> list:
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
    # Envergadura > 2.0 m (fabricación): meseta que vale 1.0 hasta el límite
    # y cae en gaussiana por encima. Reutiliza _meseta con lo=0.0 porque la
    # envergadura nunca puede ser negativa ni (por BOUNDS_ALA) menor a 2.0 m
    # -- la rama "por debajo de lo" de _meseta nunca se activa en la
    # práctica, lo que importa acá es solo la rama "por encima de hi".
    f_en = _meseta(a["envergadura"], 0.0, ENVERGADURA_MANUFACTURA_MAX, ENVERGADURA_MANUFACTURA_TOL)
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
        ("envergadura (fabricacion)", PESO_ENVERGADURA, f_en),
    ]
    if VIENTO_ACTIVO:
        terminos.append(("turbulencia (eficiencia)", PESO_TURBULENCIA, 1.0 / (1.0 + a["extra_turbulencia"])))
    return terminos


def evaluar_mision_avion(params: dict, topologia: str) -> float:
    """Lo que ve el GA. Ver `puntaje_de_analisis` (y `es_factible`,
    `describir_puntaje` para leerlo)."""
    return puntaje_de_analisis(analizar_con_motivo(params, topologia))


def params_trimados(params: dict, topologia: str) -> dict:
    """Los params con la incidencia de cola que trima el avión (TRIM_RESUELTO):
    es el avión que el modelo efectivamente analizó y el que hay que exportar
    a CAD/CFD o dibujar. Si el candidato es inválido, devuelve los params tal
    cual."""
    a = analizar_mision_avion(params, topologia)
    return dict(a["params_trimados"]) if a is not None else dict(params)


def desglose_mision_avion(params: dict, topologia: str) -> str:
    a = analizar_con_motivo(params, topologia)
    if isinstance(a, Infactible):
        return (f"Candidato INFACTIBLE en la etapa {a.etapa} ({ETAPAS[a.etapa]}): {a.motivo}  "
                f"(violacion {a.violacion:.2f})")
    if a is None:
        return ("Candidato INVALIDO: no cierra estructuralmente, no entra el volumen util "
                f"minimo ({VOLUMEN_UTIL_MIN_L:.1f} L) en el fuselaje, no se sostiene a "
                f"{3.6*V_MAX:.0f} km/h, no puede volar a 10 m/s ni con flap, es inestable, "
                "entra en perdida con la rafaga de diseno"
                + (f", o la rafaga del sitio supera {N_RAFAGA_ADMISIBLE:.1f} g." if VIENTO_ACTIVO else "."))
    terms = _terminos(a)
    total = sum(w * f for _, w, f in terms)
    L = []
    L.append(f"=== [{topologia}] MISION: crucero (diseno) {3.6*V_CRUCERO:.0f} km/h + "
             f"vuelo lento {V_LENTO:.0f} m/s + maxima {3.6*V_MAX:.0f} km/h, "
             f"con {MASA_PAYLOAD:.1f} kg de carga util ===")
    L.append("")
    L.append(f"VOLUMEN DE FUSELAJE  geometrico {a['vol_geo_fuselaje_L']:6.2f} L  x "
             f"{FACTOR_UTILIZACION_VOLUMEN:.0%} util. = {a['vol_util_fuselaje_L']:6.2f} L util  "
             f"(requerido >= {a['vol_requerido_L']:.1f} L)")
    L.append("")
    L.append("MASA (calculada, no declarada)")
    L.append(f"  carga util ............ {MASA_PAYLOAD:6.2f} kg")
    L.append(f"  sistemas .............. {a['masa_sistemas']:6.2f} kg"
             + ("   (sin bateria)" if a.get("bateria") else "   (incluye bateria)"))
    if a.get("bateria"):
        L.append(f"  bateria ............... {a['masa_bateria']:6.2f} kg   "
                 f"({100*a['bateria']['fraccion_masa_bateria']:.0f}% de la masa total)")
    L.append(f"  estructura ............ {a['masa_estructura']:6.2f} kg")
    L.append(f"     larguero {a['masa_larguero']:.3f} | piel ala {a['masa_piel_ala']:.3f} | "
             f"winglet {a['masa_winglet']:.3f} | flap {a['masa_flap']:.3f}")
    L.append(f"     cola {a['masa_cola']:.3f} | fuselaje {a['masa_fuselaje']:.3f} | boom {a['masa_boom']:.3f}")
    L.append(f"  TOTAL ................. {a['masa_total']:6.2f} kg   ({100*a['fraccion_estructural']:.0f}% estructura)")
    L.append(f"  flecha en punta ....... {a['flecha_punta_mm']:6.1f} mm  "
             f"({'la rigidez dimensiona el larguero' if a['manda_rigidez'] else 'manda la resistencia'})")
    L.append("")
    L.append("GEOMETRIA")
    L.append(f"  envergadura ........... {a['envergadura']:6.2f} m ala, "
             f"{a.get('envergadura_total', a['envergadura']):.2f} m total con winglets   "
             + (f"(maximo {ENVERGADURA_MAX_M:.1f} m, SORA)" if PUNTAJE_MODO == "mision"
                else f"(penalizada por encima de {ENVERGADURA_MANUFACTURA_MAX:.1f} m, fabricacion)"))
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
    if a.get("bateria"):
        b = a["bateria"]; pk = b["pack"]; dsp = b["despegue"]
        L.append(f"BATERIA para {b['alcance_objetivo_km']:.0f} km a {3.6*V_CRUCERO:.0f} km/h constantes "
                 f"(eta propulsiva {b['eta_propulsiva']:.2f}, ver bateria.py)")
        L.append(f"  potencia electrica .... {b['potencia_electrica_crucero_W']:6.1f} W  "
                 f"({b['corriente_crucero_A']:.1f} A a {pk['tension_nominal_V']:.0f} V)")
        L.append(f"  energia requerida ..... {b['energia_requerida_wh']:6.0f} Wh   "
                 f"disponible {b['energia_disponible_wh']:.0f} Wh   alcance logrado {b['alcance_logrado_km']:.0f} km")
        L.append(f"  pack {pk['celda']} {pk['S']}S{pk['P']}P ({pk['n_celdas']} celdas): "
                 f"{pk['capacidad_Ah']:.1f} Ah, {pk['masa_pack_kg']:.2f} kg, {b['volumen_bateria_l']:.1f} L")
        L.append(f"     (el modelo usa {b['masa_bateria_kg']:.2f} kg continuos; el pack real se arma de a "
                 f"{pk['S']} celdas y puede pesar hasta ~{pk['S'] * _bat.CELDAS[pk['celda']]['g'] / 1000 * _bat.FACTOR_MASA_PACK:.1f} kg mas)")
        if not b["convergio"]:
            L.append(f"  OJO: el lazo bateria<->resistencia NO convergio en {_bat.MAX_PASADAS} pasadas "
                     f"(el punto fijo pedia {b['masa_bateria_punto_fijo_kg']:.2f} kg)")
        L.append(f"  despegue (info) ....... empuje {dsp['empuje_kgf']:.1f} kgf, {dsp['potencia_electrica_W']:.0f} W, "
                 f"{dsp['corriente_A']:.0f} A (pack aguanta {pk['corriente_continua_max_A']:.0f} A: "
                 f"{'OK' if dsp['corriente_ok'] else 'NO ALCANZA'})")
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
    if a.get("trim_resuelto"):
        L.append(f"  incidencia de cola .... {a['incidencia_trim_deg']:+6.2f} grados   (resuelta para Cm = 0; "
                 f"el candidato traia {a['incidencia_inicial_deg']:+.2f})")
    L.append(f"  Cn_beta ............... {a['Cn_beta']:8.5f} /grado   (>= {CN_BETA_MIN:.4f} exigido)")
    L.append(f"  Cl_beta ............... {a['Cl_beta']:8.5f} /grado   (<= -{CL_BETA_MIN:.4f} exigido)")
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
             f"(estructura: limite {N_LIMITE:.1f}, ultima {N_ULTIMO:.1f}"
             + (f"; con viento se exige <= {N_RAFAGA_ADMISIBLE:.1f})" if a["viento_activo"] else ")"))
    L.append(f"  margen de perdida ..... {100*a['margen_perdida']:6.1f} %   (exigido >= {100*MARGEN_PERDIDA_OK:.0f}%)")
    L.append("")
    E = energia_mision_wh(a)
    L.append(f"ENERGIA PARA EL ALCANCE ({_bat.ALCANCE_KM:.0f} km a {3.6*V_CRUCERO:.0f} km/h, con reserva) "
             f"{E:7.0f} Wh   (referencia {ENERGIA_REFERENCIA_WH:.0f} Wh)")
    L.append("")
    if PUNTAJE_MODO == "mision":
        fallas = requisitos_incumplidos(a)
        L.append("REQUISITOS (pasa / no pasa)   " + ("TODOS OK" if not fallas else "INCUMPLE -> infactible (el GA lo ordena por violacion)"))
        for f_ in fallas:
            L.append(f"  NO: {f_}")
        L.append("")
    L.append(f"PUNTAJE  (modo '{PUNTAJE_MODO}')")
    for nombre, w, f in terms:
        L.append(f"  {nombre:.<32} {w:.2f} x {f:5.3f} = {w*f:6.3f}   ({100*w*f/total:4.1f} %)")
    L.append(f"  {'TOTAL':.<32} {total:22.3f}"
             + ("   (pero INCUMPLE requisitos: para el GA es infactible, ver arriba)"
                if PUNTAJE_MODO == "mision" and requisitos_incumplidos(a) else ""))
    return "\n".join(L)
