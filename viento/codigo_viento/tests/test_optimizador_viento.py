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


@pytest.fixture(autouse=True)
def interruptores():
    """Cada test arranca SIN batería (los ganadores del 18/09 son de antes del
    modelo de batería) y al final se restauran los valores que había."""
    previo = (ma.VIENTO_ACTIVO, ma.BATERIA_ACTIVA)
    ma.BATERIA_ACTIVA = False
    yield
    ma.VIENTO_ACTIVO, ma.BATERIA_ACTIVA = previo


def test_sin_viento_no_usa_ningun_dato_del_sitio(monkeypatch):
    """Con VIENTO_ACTIVO = False el resultado no depende de NADA de viento.py.

    Antes este test comparaba contra los scores guardados en ganadores.json,
    pero esos scores son del modelo del 18/09: después cambiaron cosas que no
    son el viento (penalización de envergadura, borde de fuga de 2 mm, pod_boom
    continuo) y el test fallaba sin que el viento tuviera la culpa. Lo que hay
    que garantizar es la propiedad: se cambian todos los datos del sitio por
    valores absurdos y el puntaje sin viento no se mueve ni un bit."""
    ma.VIENTO_ACTIVO = False
    params = {t: g["params"] for t, g in GANADORES.items() if t in ("v_tail", "convencional")}
    def huella(p, t):
        a = ma.analizar_mision_avion(p, t)
        assert a is not None
        return (ma.puntaje_de_analisis(a), a["D_crucero"], a["SM"], a["v_stall"], a["masa_total"])
    antes = {t: huella(p, t) for t, p in params.items()}
    assert any(np.isfinite(h[0]) for h in antes.values())
    monkeypatch.setattr(vto, "ATMOSFERA_SITIO", vto.atmosfera_con_densidad(0.7))
    monkeypatch.setattr(vto, "RAFAGA_VERTICAL_SITIO", 25.0)
    monkeypatch.setattr(vto, "SIGMA_W", 9.0)
    monkeypatch.setattr(vto, "SIGMA_U", 9.0)
    for t, p in params.items():
        assert huella(p, t) == antes[t]


def test_constantes_coinciden_con_las_fichas():
    """Si se actualizan las fichas, este test avisa que hay que actualizar viento.py."""
    d = vto.condiciones_desde_fichas(REPO / "viento")
    for k, v in d.items():
        assert getattr(vto, k) == pytest.approx(v, rel=2e-3), k


def test_con_viento_se_aplican_las_condiciones_del_sitio(monkeypatch):
    t = "convencional"
    monkeypatch.setattr(ma, "N_RAFAGA_ADMISIBLE", 99.0)   # acá se miden las condiciones, no el corte
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
    # La turbulencia entra en la energía de la misión (resistencia turbulenta).
    assert ma.energia_mision_wh(a) > ma.energia_mision_wh({**a, "D_turbulento": a["D_crucero"]})


def test_rafaga_del_sitio_se_compara_contra_la_carga_limite(monkeypatch):
    """Con viento, un diseño cuya ráfaga supera N_RAFAGA_ADMISIBLE se descarta,
    y por defecto ese límite es la carga LÍMITE de la estructura (no la última)."""
    assert ma.N_RAFAGA_ADMISIBLE == ma.N_LIMITE
    t = "convencional"
    ma.VIENTO_ACTIVO = True
    monkeypatch.setattr(ma, "N_RAFAGA_ADMISIBLE", 99.0)
    a = ma.analizar_mision_avion(GANADORES[t]["params"], t)
    assert a is not None
    monkeypatch.setattr(ma, "N_RAFAGA_ADMISIBLE", a["n_con_rafaga"] - 0.01)
    assert ma.analizar_mision_avion(GANADORES[t]["params"], t) is None


# ---------------------------------------------------------------- puntaje por misión (V51.2)
def test_trim_resuelto_deja_cm_nulo_y_es_el_avion_que_se_exporta():
    ma.VIENTO_ACTIVO = False         # diseño del 18/09, sin viento
    t = "v_tail"
    a = ma.analizar_mision_avion(GANADORES[t]["params"], t)
    assert a is not None and a["trim_resuelto"]
    assert abs(a["Cm_crucero"]) <= ma.TRIM_TOL_CM
    p = ma.params_trimados(GANADORES[t]["params"], t)
    assert p[ma.clave_incidencia(t)] == pytest.approx(a["incidencia_trim_deg"])
    # el avión trimado vuelve a dar el mismo trim (punto fijo)
    a2 = ma.analizar_mision_avion(p, t)
    assert a2["incidencia_trim_deg"] == pytest.approx(a["incidencia_trim_deg"], abs=0.05)


def test_requisito_incumplido_queda_infactible(monkeypatch):
    ma.VIENTO_ACTIVO = False         # diseño del 18/09, sin viento
    t = "v_tail"
    a = ma.analizar_mision_avion(GANADORES[t]["params"], t)
    assert ma.requisitos_incumplidos(a) == []
    assert np.isfinite(ma.puntaje_de_analisis(a))
    monkeypatch.setattr(ma, "CN_BETA_MIN", a["Cn_beta"] * 2)
    assert ma.requisitos_incumplidos(a)
    s = ma.puntaje_de_analisis(a)
    assert not ma.es_factible(s) and np.isfinite(s)      # infactible, rankeado por violación
    assert "requisitos" in ma.describir_puntaje(s)


def test_objetivo_es_la_energia_del_alcance():
    """En modo misión, menos energía para el alcance = más puntaje (a igualdad del resto)."""
    ma.VIENTO_ACTIVO = False         # diseño del 18/09, sin viento
    t = "v_tail"
    a = ma.analizar_mision_avion(GANADORES[t]["params"], t)
    peor = {**a, "D_crucero": a["D_crucero"] * 1.05, "D_turbulento": a["D_turbulento"] * 1.05}
    assert ma.energia_mision_wh(peor) > ma.energia_mision_wh(a)
    assert ma.puntaje_de_analisis(peor) < ma.puntaje_de_analisis(a)


def test_modo_legado_conserva_los_terminos_de_antes(monkeypatch):
    monkeypatch.setattr(ma, "PUNTAJE_MODO", "legado")
    monkeypatch.setattr(ma, "N_RAFAGA_ADMISIBLE", 99.0)   # diseño sin viento: acá solo importan los términos
    ma.VIENTO_ACTIVO = True
    t = "v_tail"
    a = ma.analizar_mision_avion(GANADORES[t]["params"], t)
    nombres = [n for n, _, _ in ma._terminos(a)]
    assert len(nombres) == 12 and "turbulencia (eficiencia)" in nombres


def test_espectro_dryden_integra_sigma2():
    om = np.logspace(-5, 5, 20000)
    assert vto._trapezoid(vto.espectro_dryden_w(om, 1.5, 120.0, 22.2), om) == pytest.approx(1.5 ** 2, rel=1e-3)


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
