"""
VLM con viento no uniforme, sobre cualquier asb.Airplane (por ejemplo, los
que arma optimizacion_avion.geometria_avion.construir_avion, SIN modificarlo).

Cómo funciona: el VLM de AeroSandbox calcula, en cada panel, la velocidad del
aire como  V_inf + (velocidad por rotación del avión). Acá se reemplaza el
OperatingPoint por uno que, en ese mismo lugar, suma la velocidad del campo
de viento evaluada en cada punto. Así el viento entra:
  - en el lado derecho del sistema (condición de no penetración), y
  - en el cálculo de fuerzas (Kutta-Joukowski con la velocidad local),
sin tocar la matriz de influencia (la geometría).

Es un análisis CUASI-ESTACIONARIO: en cada instante el ala "ve" el campo
congelado y responde instantáneamente, con el avión quieto en actitud
(no sube ni cabecea por la ráfaga). Por eso da picos de carga
CONSERVADORES respecto de la fórmula con factor de alivio Kg (FAR 23.341),
que sí considera que el avión empieza a subir con la ráfaga.

Ejes: los puntos del VLM están en ejes geometría de AeroSandbox
(x hacia atrás, y a la derecha, z arriba). Los campos usan ejes tierra
(X adelante, Y derecha, Z arriba), ver campos.py.
"""
from __future__ import annotations

import numpy as np
import aerosandbox as asb

from .campos import Campo, CampoNulo


# ---------------------------------------------------------------------------
# Atmósfera con la densidad del sitio
# ---------------------------------------------------------------------------
def atmosfera_con_densidad(rho: float) -> asb.Atmosphere:
    """Atmósfera estándar a la altitud que da la densidad pedida (bisección)."""
    lo, hi = -2000.0, 12000.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if float(asb.Atmosphere(altitude=mid).density()) > rho:
            lo = mid
        else:
            hi = mid
    return asb.Atmosphere(altitude=0.5 * (lo + hi))


# ---------------------------------------------------------------------------
# OperatingPoint que agrega el viento
# ---------------------------------------------------------------------------
class OperatingPointConViento(asb.OperatingPoint):
    """OperatingPoint de AeroSandbox + campo de viento.

    campo    : objeto de campos.py
    X_avion  : posición (ejes tierra, a lo largo de la ruta) del ORIGEN de la
               geometría del avión [m]
    altura   : altura del origen de la geometría sobre el terreno [m]
    t        : tiempo [s] (para campos que dependen del tiempo)
    """

    def __init__(self, campo: Campo | None = None, X_avion: float = 0.0,
                 altura: float = 120.0, t: float = 0.0, **kwargs):
        super().__init__(**kwargs)
        self.campo = campo if campo is not None else CampoNulo()
        self.X_avion, self.altura, self.t = float(X_avion), float(altura), float(t)

    def puntos_a_tierra(self, points_geom: np.ndarray) -> np.ndarray:
        P = np.asarray(points_geom, float)
        return np.stack([self.X_avion - P[:, 0], P[:, 1], self.altura + P[:, 2]], axis=1)

    def viento_en_ejes_geometria(self, points_geom: np.ndarray) -> np.ndarray:
        uvw = self.campo.velocidad(self.puntos_a_tierra(points_geom), self.t)
        # El viento se SUMA a la velocidad del aire. Ejes tierra -> geometría:
        # X adelante -> x atrás (cambia signo), Y y Z iguales.
        return np.stack([-uvw[:, 0], uvw[:, 1], uvw[:, 2]], axis=1)

    def compute_rotation_velocity_geometry_axes(self, points):
        base = super().compute_rotation_velocity_geometry_axes(points)
        return base + self.viento_en_ejes_geometria(np.asarray(points))


# ---------------------------------------------------------------------------
# Utilidades del VLM
# ---------------------------------------------------------------------------
def _rangos_de_paneles(avion: asb.Airplane, res_envergadura: int, res_cuerda: int) -> list:
    """Índices [ini, fin) de los paneles de cada ala, replicando el mallado del VLM."""
    rangos, i = [], 0
    for w in avion.wings:
        ww = w.subdivide_sections(ratio=res_envergadura) if res_envergadura > 1 else w
        _, faces = ww.mesh_thin_surface(method="quad", chordwise_resolution=res_cuerda, add_camber=True)
        rangos.append((i, i + len(faces)))
        i += len(faces)
    return rangos


def correr_vlm(avion, V, alpha, rho, campo=None, X_avion=0.0, altura=120.0, t=0.0,
               res_envergadura=8, res_cuerda=6, ala_principal=0):
    op = OperatingPointConViento(campo=campo, X_avion=X_avion, altura=altura, t=t,
                                 atmosphere=atmosfera_con_densidad(rho), velocity=V, alpha=alpha)
    vlm = asb.VortexLatticeMethod(airplane=avion, op_point=op,
                                  spanwise_resolution=res_envergadura, chordwise_resolution=res_cuerda)
    r = vlm.run()
    i0, i1 = _rangos_de_paneles(avion, res_envergadura, res_cuerda)[ala_principal]
    F = np.asarray(vlm.forces_geometry)[i0:i1]
    C = np.asarray(vlm.vortex_centers)[i0:i1]
    der = C[:, 1] > 0
    # Momento flector en la raíz de la semiala derecha (alrededor del eje x en y = 0),
    # positivo cuando la sustentación flexiona la punta hacia arriba.
    M_raiz = float(np.sum(F[der, 2] * C[der, 1]))
    # Distribución de carga en envergadura (semiala derecha)
    y = C[der, 1]
    orden = np.argsort(y)
    return {"L": float(r["L"]), "CL": float(r["CL"]), "Cm": float(r["Cm"]),
            "M_raiz": M_raiz, "L_ala": float(np.sum(F[:, 2])),
            "y": y[orden], "Fz": F[der, 2][orden]}


def alpha_de_trim_vlm(avion, V, rho, W, res_envergadura=8, res_cuerda=6) -> float:
    """Ángulo de ataque al que el VLM da L = W (sin viento)."""
    a1, a2 = 0.0, 4.0
    L1 = correr_vlm(avion, V, a1, rho, res_envergadura=res_envergadura, res_cuerda=res_cuerda)["L"]
    L2 = correr_vlm(avion, V, a2, rho, res_envergadura=res_envergadura, res_cuerda=res_cuerda)["L"]
    return a1 + (W - L1) * (a2 - a1) / (L2 - L1)


# ---------------------------------------------------------------------------
# Paso del avión a través de un campo
# ---------------------------------------------------------------------------
def simular_paso(avion, V, rho, W, campo, X_inicio, X_fin, n_pasos=60, alpha=None,
                 altura=120.0, res_envergadura=8, res_cuerda=6):
    """Mueve el avión de X_inicio a X_fin dentro del campo y resuelve el VLM en
    cada posición. Devuelve historias de sustentación y momento en la raíz.

    W     : peso [N]. Si alpha es None se usa el alpha de trim del VLM (L = W),
            así la condición base es consistente con 1 g.
    Salida: dict con X, t, L, dn (= ΔL/W), M_raiz, dM_raiz, y la condición base.
    """
    if alpha is None:
        alpha = alpha_de_trim_vlm(avion, V, rho, W, res_envergadura, res_cuerda)
    base = correr_vlm(avion, V, alpha, rho, res_envergadura=res_envergadura, res_cuerda=res_cuerda)
    X = np.linspace(X_inicio, X_fin, n_pasos)
    L, M, CL = (np.zeros(n_pasos) for _ in range(3))
    for k, Xk in enumerate(X):
        r = correr_vlm(avion, V, alpha, rho, campo=campo, X_avion=Xk, altura=altura, t=(Xk - X_inicio) / V,
                       res_envergadura=res_envergadura, res_cuerda=res_cuerda)
        L[k], M[k], CL[k] = r["L"], r["M_raiz"], r["CL"]
    return {"X": X, "t": (X - X_inicio) / V, "alpha": alpha, "L": L, "CL": CL,
            "dn": (L - base["L"]) / W, "M_raiz": M, "dM_raiz": M - base["M_raiz"],
            "base": base, "W": W, "V": V}


def resumen_paso(sim: dict) -> dict:
    """Valores pico de una simulación: factor de carga y momento en la raíz."""
    i = int(np.argmax(sim["dn"]))
    return {"dn_max": float(sim["dn"][i]), "n_max": 1.0 + float(sim["dn"][i]),
            "dn_min": float(np.min(sim["dn"])),
            "M_raiz_1g": sim["base"]["M_raiz"], "M_raiz_max": float(np.max(sim["M_raiz"])),
            "relacion_M_raiz": float(np.max(sim["M_raiz"]) / sim["base"]["M_raiz"]),
            "CL_max_alcanzado": float(np.max(sim["CL"])), "X_pico": float(sim["X"][i])}


# ---------------------------------------------------------------------------
# Respuesta dinámica: el avión sube con la ráfaga y la sustentación tarda en crecer
# ---------------------------------------------------------------------------
# Aproximaciones clásicas (perfil 2D, s = distancia recorrida en semicuerdas = 2 V t / c):
#   Küssner (entrada en una ráfaga):     psi(s) = 1 - 0.5 e^(-0.13 s) - 0.5 e^(-s)
#   Wagner  (cambio brusco de alpha):    phi(s) = 1 - 0.165 e^(-0.0455 s) - 0.335 e^(-0.3 s)
_KUSSNER = ((0.5, 0.13), (0.5, 1.0))
_WAGNER = ((0.165, 0.0455), (0.335, 0.3))


class _Retardo:
    """Filtro y(s) = u(s) - sum a_i z_i, dz_i = -b_i z_i ds + du (respuesta indicial 1 - sum a_i e^(-b_i s))."""

    def __init__(self, coefs):
        self.coefs, self.z, self.u_prev = coefs, np.zeros(len(coefs)), 0.0

    def paso(self, u, ds):
        du = u - self.u_prev
        self.u_prev = u
        for i, (a, b) in enumerate(self.coefs):
            self.z[i] = self.z[i] * np.exp(-b * ds) + du
        return u - sum(a * z for (a, _), z in zip(self.coefs, self.z))


def simular_rafaga_dinamica(avion, V, rho, W, campo, X_inicio, X_fin, n_muestras_vlm=40,
                            alpha=None, c_ref=None, tiempo_extra=1.0, altura=120.0,
                            res_envergadura=8, res_cuerda=6, retardo_aerodinamico=True):
    """Paso por una ráfaga con el avión LIBRE DE SUBIR (1 grado de libertad
    vertical, sin cabeceo) y con el retardo de la sustentación (Küssner/Wagner).

    Idea: el VLM es lineal en la velocidad que ve cada panel. Entonces:
      1) se calcula con VLM la sustentación cuasi-estática que produce la
         ráfaga en cada posición X (incluye cuándo entra el ala y cuándo la cola);
      2) se calcula con VLM cuánto cambia la sustentación por 1 m/s de
         velocidad vertical uniforme (para el término de 'subir con la ráfaga');
      3) se integra en el tiempo m z'' = ΔL, con ΔL = Küssner[ΔL_ráfaga] - Wagner[ż dL/dw].
    Esto es lo que hay físicamente detrás del factor Kg de FAR 23.341, pero con
    la geometría real del avión en lugar de un perfil 2D.

    No incluye: cabeceo (el avión podría rotar y cambiar alpha), alivio
    inercial del peso del ala sobre el momento flector (conservador),
    ni flexibilidad del ala.
    """
    if alpha is None:
        alpha = alpha_de_trim_vlm(avion, V, rho, W, res_envergadura, res_cuerda)
    c = float(c_ref if c_ref is not None else avion.c_ref)
    kw = dict(res_envergadura=res_envergadura, res_cuerda=res_cuerda)
    base = correr_vlm(avion, V, alpha, rho, **kw)

    # 1) Cuasi-estático: ráfaga sola, muestreada en X
    Xs = np.linspace(X_inicio, X_fin, n_muestras_vlm)
    dLq, dMq = np.zeros(n_muestras_vlm), np.zeros(n_muestras_vlm)
    for k, Xk in enumerate(Xs):
        r = correr_vlm(avion, V, alpha, rho, campo=campo, X_avion=Xk, altura=altura, **kw)
        dLq[k], dMq[k] = r["L"] - base["L"], r["M_raiz"] - base["M_raiz"]

    # 2) Sensibilidad a velocidad vertical uniforme (diferencia centrada, ±0.5 m/s)
    from .campos import RafagaUniforme
    rp = correr_vlm(avion, V, alpha, rho, campo=RafagaUniforme(w=0.5), **kw)
    rm = correr_vlm(avion, V, alpha, rho, campo=RafagaUniforme(w=-0.5), **kw)
    dL_dw, dM_dw = rp["L"] - rm["L"], rp["M_raiz"] - rm["M_raiz"]

    # 3) Integración temporal
    m = W / 9.80665
    T = (X_fin - X_inicio) / V + tiempo_extra
    dt = min(0.25 * c / (2 * V), T / 400)
    t = np.arange(0.0, T + dt, dt)
    ds = 2 * V * dt / c
    Xt = X_inicio + V * t
    gL = np.interp(Xt, Xs, dLq, right=0.0)
    gM = np.interp(Xt, Xs, dMq, right=0.0)
    if retardo_aerodinamico:
        kL, kM, wL, wM = _Retardo(_KUSSNER), _Retardo(_KUSSNER), _Retardo(_WAGNER), _Retardo(_WAGNER)
    zdot = 0.0
    dL, dM, zd = np.zeros_like(t), np.zeros_like(t), np.zeros_like(t)
    for i in range(len(t)):
        pL, pM = -zdot * dL_dw, -zdot * dM_dw
        if retardo_aerodinamico:
            dL[i] = kL.paso(gL[i], ds) + wL.paso(pL, ds)
            dM[i] = kM.paso(gM[i], ds) + wM.paso(pM, ds)
        else:
            dL[i], dM[i] = gL[i] + pL, gM[i] + pM
        zd[i] = zdot
        zdot += dL[i] / m * dt
    return {"t": t, "X": Xt, "alpha": alpha, "dn": dL / W, "L": base["L"] + dL,
            "M_raiz": base["M_raiz"] + dM, "dM_raiz": dM, "zdot": zd,
            "dn_cuasiestatico": gL / W, "base": base, "W": W, "V": V,
            "dL_dw": dL_dw, "CL": (base["L"] + dL) / (0.5 * rho * V ** 2 * avion.s_ref)}


def barrido_H(avion, V, rho, W, U_ds, H_lista, n_muestras_vlm=40, alpha=None, dinamico=True, **kw):
    """Barre la longitud de ráfaga H (1-coseno vertical) y devuelve el pico de
    cada una. La ráfaga crítica es la que maximiza n o M_raiz.

    dinamico=True : avión libre de subir + retardo aerodinámico (recomendado)
    dinamico=False: cuasi-estático, avión fijo (cota superior conservadora;
                    el pico casi no depende de H)
    """
    from .campos import RafagaCoseno
    if alpha is None:
        alpha = alpha_de_trim_vlm(avion, V, rho, W)
    filas = []
    for H in H_lista:
        rf = RafagaCoseno(U_ds=U_ds, H=H, X0=0.0)
        # El avión arranca antes de la ráfaga y termina después (margen de 3 m).
        if dinamico:
            sim = simular_rafaga_dinamica(avion, V, rho, W, rf, X_inicio=-3.0, X_fin=2 * H + 6.0,
                                          n_muestras_vlm=n_muestras_vlm, alpha=alpha, **kw)
        else:
            sim = simular_paso(avion, V, rho, W, rf, X_inicio=-3.0, X_fin=2 * H + 6.0,
                               n_pasos=n_muestras_vlm, alpha=alpha, **kw)
        filas.append({"H": H, **resumen_paso(sim)})
    return filas
