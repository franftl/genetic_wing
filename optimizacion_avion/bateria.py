"""
Dimensionamiento de la batería por ALCANCE (2026-10-12).

Hasta ahora la batería era una parte de `MASA_SISTEMAS` (1.5 kg para motor +
ESC + hélice + batería + servos + piloto), sin relación con la autonomía que
pide la misión. Ese número no puede ser cierto para un alcance largo: el
análisis de la Research Note 15 ya mostraba que 300 km eléctricos piden varios
kg de batería. Este módulo hace explícita esa relación:

    D (crucero, N)  --->  energía necesaria  --->  masa de batería  --->  más peso
          ^                                                                 |
          +-----------------------------------------------------------------+

La batería se dimensiona para sostener la VELOCIDAD DE CRUCERO durante TODO el
vuelo (sin tramos de ascenso/descenso aparte; la reserva cubre despegue,
aterrizaje y contingencias), así que el tiempo de vuelo es simplemente
`ALCANCE / V_CRUCERO`.

Todo lo que se puede querer mover después está arriba, como constantes
nombradas. Los supuestos NO validados están marcados.

    E_necesaria = (D_efectiva * V / ETA_PROPULSIVA_TOTAL + P_AVIONICA) * t
    E_batería   = E_necesaria * (1 + RESERVA_ENERGIA)
    m_batería   = E_batería / ENERGIA_ESPECIFICA_PACK      (Wh/kg a nivel pack)

Dónde sale cada número (conversación de diseño del 2026-10, fuentes abajo):
  * ETA_PROPULSIVA_TOTAL = 0.65. La cadena hélice (~0.75 en crucero) x
    motor (~0.85) x ESC (~0.95) da 0.61: 0.65 supone componentes algo mejores
    que esos típicos (es un supuesto OPTIMISTA, ~6 % menos batería que con
    0.61). Reemplazar por el dato medido de la hélice/motor elegidos apenas
    se tenga.
  * La masa de batería es CONTINUA (sale de la energía) para que el puntaje
    no tenga escalones; el pack real (`dimensionar_pack`) se arma en grupos
    de CELDAS_EN_SERIE celdas y puede pesar hasta un grupo más (~1 kg con
    12S de 21700). Es informativo y se muestra en el desglose.
  * Celdas: datos de hoja de datos agregados por aboutenergy.io (ver CELDAS).
    El pack agrega FACTOR_MASA_PACK = 1.15 (níquel soldado, BMS, cableado,
    funda), que es un supuesto de ingeniería.
"""
from __future__ import annotations

import math

# =====================================================================
# REQUISITO DE MISIÓN
# =====================================================================
ALCANCE_KM = 350.0               # [km] a velocidad de crucero constante

# =====================================================================
# SUPUESTOS FÁCILES DE MOVER
# =====================================================================
# Rendimiento propulsivo total (hélice x motor x ESC) EN CRUCERO. Es la
# "eficiencia probable" del pedido: cambiar acá y todo se recalcula.
ETA_PROPULSIVA_TOTAL = 0.65
# Consumo fijo de aviónica/payload eléctrico (autopiloto, telemetría, cámara).
POTENCIA_AVIONICA_W = 10.0       # [W]  (supuesto)
# Reserva sobre la energía de crucero: aterrizaje fallido, viento, profundidad
# de descarga no utilizable, envejecimiento de la celda.
RESERVA_ENERGIA = 0.20           # [-]
# Masa de sistemas SIN batería (motor + ESC + hélice + servos + piloto
# automático). Antes MASA_SISTEMAS = 1.5 kg incluía la batería; acá se
# supone ~0.5 kg de ese total era batería. SUPUESTO sin medir.
MASA_SISTEMAS_SIN_BATERIA = 1.0  # [kg]
# Overhead de armado del pack respecto de la masa de celdas solas.
FACTOR_MASA_PACK = 1.15          # [-]
# Densidad volumétrica del pack (celda cilíndrica 21700 ~0.97 Wh/mL; el
# empaque hexagonal y el overhead la bajan a ~600 Wh/L). Sirve para exigirle
# al fuselaje el volumen extra que ocupa la batería.
ENERGIA_VOLUMETRICA_PACK_WH_L = 600.0
# El volumen mínimo de fuselaje (VOLUMEN_UTIL_MIN_L = 8.2 L) ya incluía ~0.5 L
# de batería; se descuenta antes de sumar el volumen real de la batería.
VOLUMEN_BATERIA_INCLUIDO_L = 0.5

# Configuración eléctrica del pack (solo informativa: la masa sale de la
# energía, no de cómo se reparta en serie/paralelo).
CELDAS_EN_SERIE = 12             # 12S -> 44 V nominales con celdas de 3.6-3.7 V
CELDA_POR_DEFECTO = "molicel_m65a"

# Datos de celdas 21700 (hojas de datos; aboutenergy.io Voltt Battery Library).
#   capacidad [Ah], tensión nominal [V], masa [g], corriente continua máx [A]
CELDAS = {
    "molicel_m65a": dict(Ah=6.5, V=3.60, g=74.5, I_cont=26.0),   # 314 Wh/kg, 4C
    "lg_m58t":      dict(Ah=5.57, V=3.59, g=73.2, I_cont=12.5),  # 273 Wh/kg, 2.2C
    "samsung_50g":  dict(Ah=4.85, V=3.63, g=69.5, I_cont=9.7),   # 253 Wh/kg, 2C
    "molicel_p42a": dict(Ah=4.2, V=3.60, g=70.0, I_cont=45.0),   # 216 Wh/kg, 10.7C
}

# Despegue (informativo, NO entra en el puntaje): empuje estático pedido como
# fracción del peso y potencia por teoría de disco actuador.
RELACION_EMPUJE_PESO_DESPEGUE = 0.45   # [-] (0.4-0.5 típico de UAV eléctrico)
DIAMETRO_HELICE_M = 0.38               # [m] ~15" (supuesto)
FIGURA_DE_MERITO = 0.65                # [-] eficiencia estática de la hélice
ETA_MOTOR_ESC_DESPEGUE = 0.80          # [-]

# Cierre del lazo masa de batería <-> resistencia (ver mision_avion).
MASA_BATERIA_INICIAL_KG = 3.6          # [kg] punto de arranque (cerca de lo que sale con Li-ion de 270 Wh/kg)
TOL_MASA_BATERIA_KG = 0.10             # [kg] ~2.5 % de la masa de batería -> error de alcance <= ~2.5 %
MAX_PASADAS = 3
# Si el punto fijo pide más batería que esto, el lazo diverge (la resistencia
# crece más rápido que lo que aporta la batería): el avión no puede volar el
# alcance. Cota de seguridad, muy por encima de cualquier diseño razonable.
MASA_BATERIA_MAX_KG = 50.0


# =====================================================================
# FUNCIONES
# =====================================================================
def energia_especifica_celda(celda: str | None = None) -> float:
    """[Wh/kg] a nivel celda."""
    c = CELDAS[celda or CELDA_POR_DEFECTO]
    return c["Ah"] * c["V"] / (c["g"] / 1000.0)


def energia_especifica_pack(celda: str | None = None) -> float:
    """[Wh/kg] a nivel pack (celda / overhead)."""
    return energia_especifica_celda(celda) / FACTOR_MASA_PACK


def potencia_electrica_crucero(D_efectiva: float, V: float) -> float:
    """[W] que salen de la batería en crucero."""
    return D_efectiva * V / ETA_PROPULSIVA_TOTAL + POTENCIA_AVIONICA_W


def energia_requerida_wh(D_efectiva: float, V: float, alcance_km: float | None = None) -> float:
    """[Wh] que debe tener la batería (con reserva) para el alcance pedido."""
    alcance = ALCANCE_KM if alcance_km is None else alcance_km
    t_h = alcance * 1000.0 / V / 3600.0
    return potencia_electrica_crucero(D_efectiva, V) * t_h * (1.0 + RESERVA_ENERGIA)


def masa_bateria_para(D_efectiva: float, V: float, celda: str | None = None) -> float:
    """[kg] de pack para sostener el alcance con esa resistencia."""
    return energia_requerida_wh(D_efectiva, V) / energia_especifica_pack(celda)


def volumen_bateria_l(masa_kg: float, celda: str | None = None) -> float:
    """[L] que ocupa un pack de esa masa."""
    return masa_kg * energia_especifica_pack(celda) / ENERGIA_VOLUMETRICA_PACK_WH_L


def resistencia_a_peso(D0: float, frac_inducida: float, W0: float, W: float) -> float:
    """Reescala la resistencia de crucero de un peso W0 a otro W, a geometría
    fija: la parte inducida va con W^2, el resto (perfil, parásita) se deja
    igual. Es la clausura analítica barata entre pasadas aerodinámicas."""
    return D0 * ((1.0 - frac_inducida) + frac_inducida * (W / W0) ** 2)


def cerrar_masa_bateria(D0: float, frac_inducida: float, W0: float, masa_resto_kg: float,
                        masa_bat_usada: float, V: float, celda: str | None = None,
                        g: float = 9.80665) -> float:
    """Punto fijo m_bat = f(D(W(m_bat))) con la aerodinámica de UNA pasada
    reescalada analíticamente. `masa_resto_kg` es todo lo que no es batería.
    Devuelve inf si diverge (pide más de MASA_BATERIA_MAX_KG)."""
    m = masa_bat_usada
    for _ in range(60):
        W = (masa_resto_kg + m) * g
        D = resistencia_a_peso(D0, frac_inducida, W0, W)
        m_nueva = masa_bateria_para(D, V, celda)
        if not math.isfinite(m_nueva) or m_nueva > MASA_BATERIA_MAX_KG:
            return float("inf")
        if abs(m_nueva - m) < 1e-5:
            return m_nueva
        m = 0.5 * m + 0.5 * m_nueva      # amortiguado
    return m


def dimensionar_pack(energia_wh: float, celda: str | None = None,
                     S: int | None = None) -> dict:
    """Configuración DISCRETA (S x P celdas) que cubre `energia_wh`."""
    celda = celda or CELDA_POR_DEFECTO
    S = S or CELDAS_EN_SERIE
    c = CELDAS[celda]
    wh_celda = c["Ah"] * c["V"]
    P = max(1, math.ceil(energia_wh / (S * wh_celda)))
    n = S * P
    return {
        "celda": celda, "S": S, "P": P, "n_celdas": n,
        "tension_nominal_V": S * c["V"],
        "capacidad_Ah": P * c["Ah"],
        "energia_wh": n * wh_celda,
        "masa_celdas_kg": n * c["g"] / 1000.0,
        "masa_pack_kg": n * c["g"] / 1000.0 * FACTOR_MASA_PACK,
        "corriente_continua_max_A": P * c["I_cont"],
    }


def estimar_despegue(peso_N: float, rho: float, pack: dict) -> dict:
    """Empuje y corriente de despegue (teoría de disco actuador). Informativo."""
    T = RELACION_EMPUJE_PESO_DESPEGUE * peso_N
    A = math.pi * (DIAMETRO_HELICE_M / 2.0) ** 2
    P_ideal = T ** 1.5 / math.sqrt(2.0 * rho * A)
    P_elec = P_ideal / FIGURA_DE_MERITO / ETA_MOTOR_ESC_DESPEGUE
    I = P_elec / pack["tension_nominal_V"]
    return {
        "empuje_N": T, "empuje_kgf": T / 9.80665, "potencia_electrica_W": P_elec,
        "corriente_A": I, "corriente_ok": I <= pack["corriente_continua_max_A"],
    }
