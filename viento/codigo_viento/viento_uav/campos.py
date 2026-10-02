"""
Campos de viento: funciones que dicen "qué velocidad tiene el aire en este
punto, en este instante". No saben nada del avión.

CONVENCIÓN (ejes tierra, solidarios a la ruta):
    X  hacia adelante, en la dirección de vuelo
    Y  hacia la derecha
    Z  hacia arriba (altura sobre el terreno)
    u  componente según X  (u > 0 = viento de cola, u < 0 = de frente)
    v  componente según Y
    w  componente según Z  (w > 0 = ráfaga ascendente)

Todos los campos representan PERTURBACIONES respecto del aire en el que vuela
el avión. El viento medio no va acá: un viento uniforme no cambia la
aerodinámica, solo la velocidad respecto del suelo (eso está en mision_viento).

Interfaz común:
    campo.velocidad(P, t) -> array (N, 3) con [u, v, w] en cada punto
    P: array (N, 3) de puntos [X, Y, Z] en ejes tierra; t: tiempo [s]
"""
from __future__ import annotations

import numpy as np


class Campo:
    def velocidad(self, P: np.ndarray, t: float = 0.0) -> np.ndarray:
        raise NotImplementedError

    def __add__(self, otro: "Campo") -> "CampoSuma":
        return CampoSuma(self, otro)


class CampoNulo(Campo):
    def velocidad(self, P, t=0.0):
        return np.zeros((np.atleast_2d(P).shape[0], 3))


class CampoSuma(Campo):
    """Superposición de campos: rafaga + turbulencia + cortante, etc."""

    def __init__(self, *campos: Campo):
        self.campos = []
        for c in campos:
            self.campos += c.campos if isinstance(c, CampoSuma) else [c]

    def velocidad(self, P, t=0.0):
        return sum(c.velocidad(P, t) for c in self.campos)


class RafagaUniforme(Campo):
    """Viento constante en todo el espacio (u, v, w). Útil para verificar:
    una ráfaga vertical uniforme w debe dar lo mismo que subir alpha en atan(w/V)."""

    def __init__(self, u=0.0, v=0.0, w=0.0):
        self.vec = np.array([u, v, w], float)

    def velocidad(self, P, t=0.0):
        return np.tile(self.vec, (np.atleast_2d(P).shape[0], 1))


class RafagaCoseno(Campo):
    """Ráfaga discreta 1-coseno, fija en el espacio (el avión la atraviesa).

        w(s) = U_ds/2 * (1 - cos(pi s / H)),   0 <= s <= 2H,   s = X - X0

    U_ds : amplitud [m/s] (ficha.U_ds('diseno') = 4.63 m/s)
    H    : distancia desde el borde de la ráfaga hasta el máximo [m]
           (CS-23: H = 12.5 * cuerda media; barrer hasta ~L_w)
    X0   : dónde empieza la ráfaga [m]
    direccion : 'vertical' (w), 'lateral' (v) o 'longitudinal' (u)
    """

    def __init__(self, U_ds: float, H: float, X0: float = 0.0, direccion: str = "vertical"):
        self.U_ds, self.H, self.X0 = float(U_ds), float(H), float(X0)
        self.idx = {"longitudinal": 0, "lateral": 1, "vertical": 2}[direccion]

    def perfil(self, s):
        s = np.asarray(s, float)
        dentro = (s >= 0) & (s <= 2 * self.H)
        return np.where(dentro, 0.5 * self.U_ds * (1 - np.cos(np.pi * s / self.H)), 0.0)

    def velocidad(self, P, t=0.0):
        P = np.atleast_2d(P)
        out = np.zeros((P.shape[0], 3))
        out[:, self.idx] = self.perfil(P[:, 0] - self.X0)
        return out


class CortanteVertical(Campo):
    """Gradiente vertical del viento horizontal (ley de potencia), como
    PERTURBACIÓN respecto del viento a la altura de referencia h_ref:

        U(Z) = U10 * (Z/10)^alfa ;   campo = U(Z) - U(h_ref)

    U10       : viento a 10 m [m/s]
    alfa      : exponente (ficha: ~0.10 de día, ~0.25 de noche)
    rumbo_deg : ángulo entre la dirección hacia donde va el viento y la ruta
                (0 = viento de cola, 180 = de frente, 90 = de la izquierda)
    h_ref     : altura a la que se refiere la velocidad del avión [m]
    Útil para despegue/aterrizaje: el avión baja y el viento de frente cae.
    """

    def __init__(self, U10: float, alfa: float, rumbo_deg: float = 180.0, h_ref: float = 30.0, z_min: float = 0.5):
        self.U10, self.alfa, self.h_ref, self.z_min = U10, alfa, h_ref, z_min
        r = np.radians(rumbo_deg)
        self.dir = np.array([np.cos(r), -np.sin(r), 0.0])

    def U(self, Z):
        Z = np.maximum(np.asarray(Z, float), self.z_min)
        return self.U10 * (Z / 10.0) ** self.alfa

    def velocidad(self, P, t=0.0):
        P = np.atleast_2d(P)
        dU = self.U(P[:, 2]) - self.U(self.h_ref)
        return dU[:, None] * self.dir[None, :]


class TurbulenciaDryden(Campo):
    """Turbulencia continua de Dryden, 'congelada' en el espacio (hipótesis de
    Taylor) y uniforme en envergadura. Se sintetiza en el dominio de la
    frecuencia espacial con los espectros de Dryden:

        Phi_u(W) = sigma_u^2 * 2 Lu/pi / (1 + (Lu W)^2)
        Phi_w(W) = sigma_w^2 * Lw/pi * (1 + 3 (Lw W)^2) / (1 + (Lw W)^2)^2
        (Phi_v igual que Phi_w con Lv, sigma_v)

    con W [rad/m]. La serie resultante tiene la desviación estándar pedida.

    longitud : largo del tramo de aire generado [m] (fuera se repite)
    dx       : paso espacial [m] (menor que la cuerda / 2 para resolver bien)
    semilla  : para que la turbulencia sea reproducible
    """

    def __init__(self, sigma_u, sigma_v, sigma_w, Lu, Lv, Lw,
                 longitud: float = 4000.0, dx: float = 0.25, semilla: int | None = 0):
        self.p = dict(sigma_u=sigma_u, sigma_v=sigma_v, sigma_w=sigma_w, Lu=Lu, Lv=Lv, Lw=Lw)
        n = int(2 ** np.ceil(np.log2(longitud / dx)))
        self.dx, self.n = dx, n
        self.X = np.arange(n) * dx
        rng = np.random.default_rng(semilla)
        W = 2 * np.pi * np.fft.rfftfreq(n, d=dx)          # rad/m
        dW = W[1] - W[0]

        def sintetizar(phi):
            amp = np.sqrt(phi * dW)                        # forma espectral; la escala se ajusta después
            fases = rng.uniform(0, 2 * np.pi, len(W))
            espectro = amp * np.exp(1j * fases)
            espectro[0] = 0.0
            serie = np.fft.irfft(espectro, n=n) * n
            return serie

        def normalizar(serie, sigma):
            s = serie.std()
            return serie * (sigma / s) if s > 0 else serie

        phi_u = 2 * Lu / np.pi / (1 + (Lu * W) ** 2)
        phi_v = Lv / np.pi * (1 + 3 * (Lv * W) ** 2) / (1 + (Lv * W) ** 2) ** 2
        phi_w = Lw / np.pi * (1 + 3 * (Lw * W) ** 2) / (1 + (Lw * W) ** 2) ** 2
        # La forma del espectro sale de Dryden; la amplitud se fija exactamente
        # al sigma pedido (evita depender de convenciones de normalización).
        self.serie = np.stack([normalizar(sintetizar(phi_u), sigma_u),
                               normalizar(sintetizar(phi_v), sigma_v),
                               normalizar(sintetizar(phi_w), sigma_w)], axis=1)

    @classmethod
    def desde_ficha(cls, ficha, altura_m: float = 120.0, nivel: str = "moderada",
                    norma: str = "MIL-F-8785C", **kw) -> "TurbulenciaDryden":
        d = ficha.dryden(altura_m, nivel, norma)
        return cls(d["sigma_u"], d["sigma_v"], d["sigma_w"], d["Lu"], d["Lv"], d["Lw"], **kw)

    def velocidad(self, P, t=0.0):
        P = np.atleast_2d(P)
        x = np.mod(P[:, 0], self.n * self.dx)
        i0 = np.floor(x / self.dx).astype(int)
        f = (x / self.dx - i0)[:, None]
        i1 = (i0 + 1) % self.n
        return (1 - f) * self.serie[i0] + f * self.serie[i1]
