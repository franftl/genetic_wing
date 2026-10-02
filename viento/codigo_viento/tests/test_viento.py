"""
Pruebas de verificación del paquete viento_uav.  Correr con:
    python -m pytest tests -q          (desde la carpeta codigo_viento)

Cada prueba compara contra un resultado que se conoce de antemano.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import viento_uav as vu  # noqa: E402


# ------------------------------------------------------------------ fichas
def test_fichas_cargan_y_coinciden_con_el_informe():
    cl = vu.cargar_ficha("canadon_leon")
    ph = vu.cargar_ficha("puesto_hernandez")
    assert cl.rho_diseno == pytest.approx(1.14, abs=0.005)
    assert ph.rho_diseno == pytest.approx(1.056, abs=0.005)
    assert cl.U_ds("diseno") == pytest.approx(4.63, abs=0.01)
    assert cl.viento_120("p95", solo_dia=True) == pytest.approx(16.3, abs=0.05)
    assert cl.factor_cola == pytest.approx(1.25)


def test_dryden_moderada_a_120m():
    d = vu.dryden_baja_altura(30 * 0.514444, 120.0)
    assert d["sigma_w"] == pytest.approx(1.543, abs=0.002)
    assert d["sigma_u"] == pytest.approx(2.035, abs=0.005)
    assert d["Lw"] == pytest.approx(120.0, abs=0.1)
    assert d["Lu"] == pytest.approx(275.0, abs=0.5)


# ------------------------------------------------------------------ misión
def test_ida_y_vuelta_coincide_con_formula_cerrada():
    V, W = 22.2, 10.0
    assert vu.factor_ida_vuelta(V, W) == pytest.approx(1 / (1 - (W / V) ** 2), rel=1e-9)
    assert vu.factor_ida_vuelta(V, 0.0) == pytest.approx(1.0)
    assert vu.factor_ida_vuelta(V, V + 1) == float("inf")
    # Con viento cruzado puro también se pierde tiempo (hay que corregir el rumbo)
    assert vu.factor_ida_vuelta(V, W, 90.0) == pytest.approx(V / np.sqrt(V ** 2 - W ** 2), rel=1e-9)


def test_operabilidad_reproduce_tabla_del_informe():
    cl = vu.cargar_ficha("canadon_leon")
    ph = vu.cargar_ficha("puesto_hernandez")
    assert vu.operabilidad(cl, 60 / 3.6)["fraccion_operable"] == pytest.approx(0.585, abs=0.01)
    assert vu.operabilidad(cl, 22.0, corregido=True)["fraccion_operable"] == pytest.approx(0.629, abs=0.01)
    assert vu.operabilidad(ph, 60 / 3.6)["fraccion_operable"] == pytest.approx(0.920, abs=0.01)


def test_chequeo_rafaga_reproduce_la_cuenta_de_mision_avion():
    # Mismos números que ganadores.json (convencional) con rho = 1.225 y 3 m/s
    a = dict(W=73.895, S=0.97525, c=0.34529, CLa=0.09701, V=80 / 3.6)
    r = vu.chequeo_rafaga(a["W"], a["S"], a["c"], a["CLa"], CL_max=1.4417, V=a["V"], U_ds=3.0, rho=1.225)
    assert r["Kg"] == pytest.approx(0.4871, abs=0.002)
    assert r["d_alpha"] == pytest.approx(3.762, abs=0.01)
    assert r["dn"] == pytest.approx(1.457, abs=0.01)


# ------------------------------------------------------------------ campos
def test_rafaga_coseno_perfil():
    rf = vu.RafagaCoseno(U_ds=4.0, H=10.0, X0=5.0)
    P = np.array([[4.9, 0, 120], [5.0, 0, 120], [15.0, 0, 120], [25.0, 0, 120], [25.1, 0, 120]])
    w = rf.velocidad(P)[:, 2]
    assert np.allclose(w, [0, 0, 4.0, 0, 0], atol=1e-12)


def test_dryden_sintetizado_tiene_la_intensidad_pedida():
    d = vu.dryden_baja_altura(30 * 0.514444, 120.0)
    tb = vu.TurbulenciaDryden(**d, longitud=60000, dx=1.0, semilla=1)
    X = np.c_[np.arange(0, 60000, 1.0), np.zeros(60000), np.full(60000, 120.0)]
    uvw = tb.velocidad(X)
    assert uvw[:, 2].std() == pytest.approx(d["sigma_w"], rel=0.02)
    # La escala de correlación de w: para Dryden, la autocorrelación cae
    # bastante a una distancia ~L_w (no es un valor exacto, se chequea el orden)
    w = uvw[:, 2] - uvw[:, 2].mean()
    lag = int(d["Lw"])
    rho_L = np.mean(w[:-lag] * w[lag:]) / w.var()
    assert 0.0 < rho_L < 0.6


def test_cortante_es_cero_a_la_altura_de_referencia():
    c = vu.CortanteVertical(U10=8.0, alfa=0.2, rumbo_deg=180, h_ref=30.0)
    P = np.array([[0, 0, 30.0], [0, 0, 5.0]])
    uvw = c.velocidad(P)
    assert np.allclose(uvw[0], 0.0)
    assert uvw[1, 0] > 0   # más abajo hay MENOS viento de frente -> perturbación hacia +X


# ------------------------------------------------------------------ VLM (necesita AeroSandbox)
asb = pytest.importorskip("aerosandbox")


def _ala_simple():
    af = asb.Airfoil("naca2412")
    ala = asb.Wing(name="ala", symmetric=True, xsecs=[
        asb.WingXSec(xyz_le=[0, 0, 0], chord=0.30, airfoil=af),
        asb.WingXSec(xyz_le=[0.05, 1.2, 0], chord=0.18, airfoil=af)])
    return asb.Airplane(wings=[ala], xyz_ref=[0.08, 0, 0])


def test_vlm_rafaga_uniforme_equivale_a_subir_alpha():
    from viento_uav import vlm_viento as vv
    av = _ala_simple()
    V, w, a0, rho = 20.0, 2.0, 2.0, 1.2
    con_rafaga = vv.correr_vlm(av, V, a0, rho, campo=vu.RafagaUniforme(w=w))
    # Ojo: con la ráfaga el módulo de la velocidad también crece; se compara
    # contra el mismo módulo y el ángulo girado.
    V_eq = np.hypot(V * np.cos(np.radians(a0)), V * np.sin(np.radians(a0)) + w)
    a_eq = np.degrees(np.arctan2(V * np.sin(np.radians(a0)) + w, V * np.cos(np.radians(a0))))
    equivalente = vv.correr_vlm(av, V_eq, a_eq, rho)
    assert con_rafaga["L"] == pytest.approx(equivalente["L"], rel=0.01)
    assert con_rafaga["M_raiz"] == pytest.approx(equivalente["M_raiz"], rel=0.01)


def test_vlm_sin_viento_no_cambia_nada():
    from viento_uav import vlm_viento as vv
    av = _ala_simple()
    a = vv.correr_vlm(av, 20.0, 3.0, 1.2)
    b = asb.VortexLatticeMethod(airplane=av, op_point=asb.OperatingPoint(
        atmosphere=vv.atmosfera_con_densidad(1.2), velocity=20.0, alpha=3.0),
        spanwise_resolution=8, chordwise_resolution=6).run()
    assert a["L"] == pytest.approx(float(b["L"]), rel=1e-9)


def test_vlm_rafaga_coseno_pico_cerca_de_la_formula_sin_alivio():
    """Ráfaga larga (H >> cuerda): el pico de ΔL del VLM tiene que acercarse
    a ΔL = q S CL_alpha * atan(U/V), es decir, la ráfaga 'quieta' (Kg = 1)."""
    from viento_uav import vlm_viento as vv
    av = _ala_simple()
    V, rho, U, H = 20.0, 1.2, 3.0, 40.0
    r1 = vv.correr_vlm(av, V, 0.0, rho)["L"]
    r2 = vv.correr_vlm(av, V, 4.0, rho)["L"]
    dLda = (r2 - r1) / 4.0
    W = vv.correr_vlm(av, V, 2.0, rho)["L"]
    sim = vv.simular_paso(av, V, rho, W, vu.RafagaCoseno(U_ds=U, H=H), X_inicio=-2, X_fin=2 * H + 4,
                          n_pasos=41, alpha=2.0)
    dL_pico = np.max(sim["L"]) - sim["base"]["L"]
    esperado = dLda * np.degrees(np.arctan(U / V))
    assert dL_pico == pytest.approx(esperado, rel=0.06)


def test_respuesta_dinamica_reproduce_el_factor_Kg_de_FAR23():
    """Con el avión libre de subir y el retardo de Küssner/Wagner, la ráfaga
    CS-23 (H = 12.5 c) tiene que dar un factor de carga parecido a la fórmula
    con Kg, que se dedujo justamente de ese modelo."""
    from viento_uav import vlm_viento as vv
    av = _ala_simple()
    V, rho, U = 20.0, 1.2, 4.0
    W = 0.55 * 0.5 * rho * V ** 2 * av.s_ref          # CL de crucero 0.55
    r1, r2 = (vv.correr_vlm(av, V, a, rho)["L"] for a in (0.0, 4.0))
    CLa_grado = (r2 - r1) / 4.0 / (0.5 * rho * V ** 2 * av.s_ref)
    kg = vu.chequeo_rafaga(W, av.s_ref, av.c_ref, CLa_grado, CL_max=1.5, V=V, U_ds=U, rho=rho)
    din = vv.barrido_H(av, V, rho, W, U, [12.5 * av.c_ref], n_muestras_vlm=30)[0]
    assert din["n_max"] == pytest.approx(kg["n_max"], rel=0.12)
    # y una ráfaga muy larga casi no carga (el avión sube con ella)
    largo = vv.barrido_H(av, V, rho, W, U, [200.0], n_muestras_vlm=30)[0]
    assert largo["n_max"] < din["n_max"]
