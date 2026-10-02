"""
Lectura de las fichas de viento por sitio (fichas/*.yaml) y del resumen
estadístico completo (datos/*_era5_resumen.json).

Uso:
    from viento_uav import cargar_ficha
    f = cargar_ficha("canadon_leon")
    f.rho_diseno            # 1.14 kg/m3
    f.U_ds("diseno")        # 4.63 m/s
    f.dryden(120)           # sigmas y escalas de Dryden a 120 m

Las rutas se resuelven respecto de la carpeta "Datos de viento" (dos niveles
arriba de este archivo). Se puede pasar otra con el argumento `base`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

BASE_DATOS = Path(__file__).resolve().parents[2]   # .../Datos de viento
SITIOS = ("canadon_leon", "puesto_hernandez")

KT = 0.514444      # m/s por nudo
FT = 0.3048        # m por pie
W20_NIVELES_KT = {"ligera": 15.0, "moderada": 30.0, "severa": 45.0}


@dataclass
class FichaViento:
    clave: str
    datos: dict                     # contenido completo del YAML
    resumen: dict = field(repr=False, default_factory=dict)   # JSON con histogramas, rosa, etc.

    # ---------------------------------------------------------------- básicos
    @property
    def nombre(self) -> str:
        return self.datos["sitio"]

    @property
    def rho_media(self) -> float:
        return float(self.datos["atmosfera"]["densidad_superficie"]["media"])

    @property
    def rho_diseno(self) -> float:
        """Densidad 'aire fino' (p05 de superficie x 0.986 por los 120 m)."""
        return float(self.datos["atmosfera"]["densidad_diseno_kg_m3"])

    @property
    def factor_cola(self) -> float:
        return float(self.datos["viento_crucero"]["correccion_cola_recomendada"]["factor"])

    @property
    def alfa_cortante(self) -> float:
        return float(self.datos["gradiente_vertical"]["alfa_mediana"])

    @property
    def alfa_cortante_noche(self) -> float:
        return float(self.datos["gradiente_vertical"]["alfa_noche_00_06h"])

    @property
    def alfa_cortante_dia(self) -> float:
        return float(self.datos["gradiente_vertical"]["alfa_mediodia_13_16h"])

    def viento_120(self, estadistico: str = "p95", solo_dia: bool = True, corregido: bool = False) -> float:
        """Viento a 120 m. estadistico: media, p50, p75, p90, p95, p99, max."""
        clave = "horas_diurnas_08_19" if solo_dia else "todas_las_horas"
        v = float(self.datos["viento_crucero"][clave][estadistico])
        if corregido and estadistico not in ("media", "p50", "p75"):
            v *= self.factor_cola
        return v

    # ---------------------------------------------------------------- ráfagas
    def U_ds(self, criterio: str = "diseno") -> float:
        """Amplitud de ráfaga discreta 1-coseno [m/s].
        criterio: 'operacion' (2 sigma, moderada), 'diseno' (3 sigma, moderada),
                  'ligera' (3 sigma, ligera), 'cs23' (15.24 m/s, referencia)."""
        u = self.datos["rafaga_discreta"]["U_ds_ms"]
        mapa = {"operacion": "operacional_2sigma_moderada", "diseno": "diseno_3sigma_moderada",
                "ligera": "nominal_3sigma_ligera", "cs23": "referencia_CS23_FAR23_a_VC"}
        return float(u[mapa[criterio]])

    def dryden(self, altura_m: float = 120.0, nivel: str = "moderada", norma: str = "MIL-F-8785C") -> dict:
        """Intensidades y escalas de Dryden de baja altura (h < 1000 ft).
        Devuelve sigma_u, sigma_v, sigma_w [m/s] y Lu, Lv, Lw [m]."""
        return dryden_baja_altura(W20_NIVELES_KT[nivel] * KT, altura_m, norma)

    # ---------------------------------------------------------------- histogramas
    def histograma_120(self, solo_dia: bool = True):
        """(bordes_superiores [m/s], cuentas) en bins de 0.5 m/s del viento a 120 m."""
        import numpy as np
        h = self.resumen["hist_ws120_diurno_05" if solo_dia else "hist_ws120_05"]
        n = np.asarray(h, float)
        return (np.arange(len(n)) + 1) * 0.5, n

    def rosa_120(self):
        """Lista de sectores: dirección DE DONDE viene [deg], frecuencia, media [m/s]."""
        return [(r["sector_deg"], r["frecuencia"], r["media"]) for r in self.resumen["rosa"]]


def dryden_baja_altura(W20_ms: float, altura_m: float, norma: str = "MIL-F-8785C") -> dict:
    h = max(altura_m, 3.0) / FT
    s_w = 0.1 * W20_ms
    s_u = s_w / (0.177 + 0.000823 * h) ** 0.4
    Lu = h / (0.177 + 0.000823 * h) ** 1.2 * FT
    Lw = h * FT
    if norma.upper().startswith("MIL-HDBK"):
        Lv, Lw = Lu / 2.0, Lw / 2.0
    else:
        Lv = Lu
    return dict(sigma_u=s_u, sigma_v=s_u, sigma_w=s_w, Lu=Lu, Lv=Lv, Lw=Lw)


def cargar_ficha(clave: str, base: str | Path | None = None) -> FichaViento:
    base = Path(base) if base else BASE_DATOS
    ruta = base / "fichas" / f"{clave}.yaml"
    if not ruta.exists():
        raise FileNotFoundError(f"No encuentro {ruta}. Sitios disponibles: {', '.join(SITIOS)}")
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    resumen = {}
    rel = datos.get("archivos_relacionados", {}).get("resumen_completo")
    if rel and (base / rel).exists():
        resumen = json.loads((base / rel).read_text(encoding="utf-8"))
    return FichaViento(clave=clave, datos=datos, resumen=resumen)
