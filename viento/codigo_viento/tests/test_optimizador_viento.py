"""
Verificaciones del viento dentro del optimizador (optimizacion_avion).

    python -m pytest viento/codigo_viento/tests -q
"""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

pytest.importorskip("aerosandbox")
from optimizacion_avion import mision_avion as ma   # noqa: E402
from optimizacion_avion import viento as vto         # noqa: E402

GANADORES = json.loads((REPO / "optimizacion_avion" / "ganadores.json").read_text(encoding="utf-8"))


@pytest.fixture
def sin_viento():
    ma.VIENTO_ACTIVO = False
    yield
    ma.VIENTO_ACTIVO = True


def test_sin_viento_reproduce_la_corrida_de_felipe(sin_viento):
    """VIENTO_ACTIVO = False da exactamente los scores de ganadores.json."""
    for t, g in GANADORES.items():
        assert ma.evaluar_mision_avion(g["params"], t) == pytest.approx(g["score"], rel=1e-12)


def test_constantes_coinciden_con_las_fichas():
    """Si se actualizan las fichas, este test avisa que hay que actualizar viento.py."""
    d = vto.condiciones_desde_fichas(REPO / "viento")
    for k, v in d.items():
        assert getattr(vto, k) == pytest.approx(v, rel=2e-3), k


def test_con_viento_se_aplican_las_condiciones_del_sitio():
    t = "convencional"
    ma.VIENTO_ACTIVO = False
    a0 = ma.analizar_mision_avion(GANADORES[t]["params"], t)
    ma.VIENTO_ACTIVO = True
    a = ma.analizar_mision_avion(GANADORES[t]["params"], t)
    assert a["rho"] == pytest.approx(vto.RHO_SITIO, rel=1e-6)
    # v_pérdida escala con 1/sqrt(rho); la diferencia chica restante es el CL_max a otro Reynolds
    assert a["v_stall"] == pytest.approx(a0["v_stall"] * np.sqrt(1.225 / vto.RHO_SITIO), rel=5e-3)
    assert a["rafaga_vertical"] == pytest.approx(vto.RAFAGA_VERTICAL_SITIO)
    assert a["n_con_rafaga"] > a0["n_con_rafaga"]
    assert 0.0 < a["extra_turbulencia"] < 0.05
    assert "turbulencia (eficiencia)" in [n for n, _, _ in ma._terminos(a)]


def test_espectro_dryden_integra_sigma2():
    om = np.logspace(-5, 5, 20000)
    assert np.trapezoid(vto.espectro_dryden_w(om, 1.5, 120.0, 22.2), om) == pytest.approx(1.5 ** 2, rel=1e-3)


def test_mas_carga_alar_menos_sacudida():
    args = dict(CL_alpha_rad=4.5, rho=1.1, V=22.2)
    assert vto.sigma_n_turbulencia(100.0, **args) < vto.sigma_n_turbulencia(60.0, **args)


def test_turbulencia_contra_simulacion_dinamica():
    """El modelo analítico vs la simulación dinámica con VLM (Küssner/Wagner)
    del paquete viento_uav, sobre turbulencia de Dryden sintetizada. La
    simulación larga (1.5 km) dio sigma_n = 0.224 para el ganador cola en V;
    acá se usa un tramo corto para que el test sea rápido."""
    sys.path.insert(0, str(REPO / "viento" / "codigo_viento"))
    from viento_uav import vlm_viento as vv
    from viento_uav.campos import TurbulenciaDryden
    from optimizacion_avion.geometria_avion import construir_avion
    t = "v_tail"
    g = GANADORES[t]
    a = g["analisis"]
    V = ma.V_CRUCERO
    turb = TurbulenciaDryden(0.0, 0.0, vto.SIGMA_W, 275.0, 275.0, vto.L_W, longitud=400, dx=0.25, semilla=1)
    s = vv.simular_rafaga_dinamica(construir_avion(g["params"], t), V, vto.RHO_SITIO, a["peso"], turb,
                                   0.0, 100.0, n_muestras_vlm=120, tiempo_extra=0.0)
    sim = s["dn"][s["t"] > 2.0].std()
    modelo = vto.sigma_n_turbulencia(a["carga_alar"], np.degrees(a["CL_alpha_por_grado"]), vto.RHO_SITIO, V)
    assert sim == pytest.approx(modelo, rel=0.15)
