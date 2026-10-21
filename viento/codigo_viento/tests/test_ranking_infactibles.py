"""
Ranking de infactibles por violación (reglas de Deb) en optimizacion_avion.

    python -m pytest viento/codigo_viento/tests -q

Son pruebas rápidas: no corren AeroBuildup. Viven acá porque es la única
carpeta de tests del repositorio.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

pytest.importorskip("aerosandbox")
from optimizacion_avion import mision_avion as ma          # noqa: E402
from optimizacion_avion import evolucion_avion as ev       # noqa: E402
from optimizacion_avion.geometria_avion import CandidateAvion  # noqa: E402


@pytest.fixture(autouse=True)
def modo_mision(monkeypatch):
    monkeypatch.setattr(ma, "PUNTAJE_MODO", "mision")
    monkeypatch.setattr(ma, "RANKING_INFACTIBLES", True)


def test_reglas_de_deb():
    factible = 0.5                                       # cualquier puntaje factible es > 0
    lejos = ma.Infactible(2, 0.30, "").puntaje()         # no vuela lento, por mucho
    cerca = ma.Infactible(2, 0.01, "").puntaje()         # no vuela lento, por poco
    mas_avanzado = ma.Infactible(9, 5.0, "").puntaje()   # pasó todo el análisis, falla un requisito
    assert factible > mas_avanzado > cerca > lejos > -np.inf
    assert not any(ma.es_factible(s) for s in (lejos, cerca, mas_avanzado))
    assert ma.es_factible(factible)
    assert ma.puntaje_de_analisis(None) == -np.inf


def test_describir_decodifica_etapa_y_violacion():
    for etapa, v in ((0, 1.0), (2, 0.05), (7, 3.0), (9, 0.4)):
        texto = ma.describir_puntaje(ma.Infactible(etapa, v, "").puntaje())
        assert ma.ETAPAS[etapa] in texto
        assert f"{v:.2f}" in texto


def test_sin_ranking_o_en_modo_legado_vuelve_menos_infinito(monkeypatch):
    inf = ma.Infactible(3, 0.2, "")
    monkeypatch.setattr(ma, "RANKING_INFACTIBLES", False)
    assert ma.puntaje_de_analisis(inf) == -np.inf
    monkeypatch.setattr(ma, "RANKING_INFACTIBLES", True)
    monkeypatch.setattr(ma, "PUNTAJE_MODO", "legado")
    assert ma.puntaje_de_analisis(inf) == -np.inf


def _estado(scores):
    return ev.EstadoEvolucionAvion(topologia="v_tail",
                                   parents=[CandidateAvion("v_tail", {}, s) for s in scores],
                                   non_improving_streak=3)


def test_paciencia_no_corre_sin_padres_factibles():
    """Sin ningún padre factible y sin mejora, la racha se queda quieta."""
    s = ma.Infactible(2, 0.1, "").puntaje()
    nuevo, _ = ev.correr_generacion_avion(_estado([s, s - 1]), lambda a, b, n, w: [], lambda p: s)
    assert nuevo.non_improving_streak == 3


def test_paciencia_corre_con_padres_factibles():
    nuevo, _ = ev.correr_generacion_avion(_estado([1.0, 0.9]), lambda a, b, n, w: [], lambda p: 0.0)
    assert nuevo.non_improving_streak == 4


def test_bajar_la_violacion_cuenta_como_mejora():
    s = ma.Infactible(2, 0.3, "").puntaje()
    mejor = ma.Infactible(2, 0.1, "").puntaje()
    hijos = lambda a, b, n, w: [{"params": {}, "origin": "test", "rationale": ""}]  # noqa: E731
    nuevo, _ = ev.correr_generacion_avion(_estado([s, s]), hijos, lambda p: mejor)
    assert nuevo.non_improving_streak == 0
    assert nuevo.mejor().score == mejor
