"""
Guarda los resultados de una corrida en una carpeta propia, con nombres fijos.

    import optimizacion_avion as av
    carpeta = av.guardar_resultados(estados)        # estados = {topologia: EstadoEvolucionAvion}

Cada corrida va a `<CARPETA_RESULTADOS>/<fecha>_<hora>_<escenario>_<familias>/`.
CARPETA_RESULTADOS está FUERA del repositorio, en la computadora: por defecto
`Proyecto final/resultados_optimizador/` (la carpeta que contiene a genetic_wing),
o la que diga la variable de entorno UAV_RESULTADOS, o la que se pase como
`carpeta_base`. Así los resultados no se suben a git. Por ejemplo

    resultados_optimizador/2026-10-19_2130_viento-on_bateria-on_v_tail+pod_boom/
        LEEME.md               qué se corrió (escenario, interruptores, GA) y la tabla final
        tabla_resumen.csv      una fila por familia: puntaje, energía, masa, batería, L/D, ...
        ganadores.json         params TRIMADOS + análisis completo + historial de cada familia
        convergencia.png       mejor puntaje por generación (los infactibles, como violación)
        comparacion.png        barras por familia: energía, masa, batería, L/D, pérdida, SM
        curvas_vuelo.png       resistencia y potencia en vuelo nivelado contra velocidad
        vistas_3d/<familia>.html       vista 3D interactiva (abrir con doble clic)
        lineas_flujo/<familia>.html    líneas de flujo en crucero (VLM), si flujo=True
        xflr5/<familia>/               avión (XML), perfiles (.dat) y condiciones para XFLR5
        tres_vistas/<familia>.png      planta, frente y perfil
        desgloses/<familia>.txt        el desglose completo de la misión (masa, crucero, batería...)

La carpeta nunca se pisa: si ya existe, se agrega un sufijo. La nomenclatura
está explicada en el LEEME.md de CARPETA_RESULTADOS (se escribe solo).
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
from pathlib import Path

import numpy as np

from . import bateria as _bat
from . import mision_avion as _ma
from .geometria_avion import TOPOLOGIAS, construir_avion

# Fuera del repositorio (genetic_wing): al lado, en la carpeta que lo contiene.
CARPETA_RESULTADOS = Path(os.environ.get("UAV_RESULTADOS")
                          or Path(__file__).resolve().parents[2] / "resultados_optimizador")

COLUMNAS = [
    ("familia", "{}"), ("estado", "{}"), ("puntaje", "{:.4f}"), ("generaciones", "{}"),
    ("energia_Wh", "{:.0f}"), ("masa_kg", "{:.2f}"), ("bateria_kg", "{:.2f}"),
    ("envergadura_m", "{:.2f}"), ("winglet_m", "{:.3f}"), ("S_m2", "{:.3f}"), ("AR", "{:.1f}"),
    ("LD_crucero", "{:.2f}"), ("D_crucero_N", "{:.2f}"), ("v_perdida_ms", "{:.2f}"),
    ("SM_pct", "{:.1f}"), ("incidencia_trim_deg", "{:+.2f}"), ("n_rafaga", "{:.2f}"),
    ("Cn_beta", "{:.5f}"),
]


def _escenario() -> str:
    return (f"viento-{'on' if _ma.VIENTO_ACTIVO else 'off'}_"
            f"bateria-{'on' if _ma.BATERIA_ACTIVA else 'off'}")


def _carpeta_nueva(base: Path, familias: list, etiqueta: str | None) -> Path:
    nombre = f"{dt.datetime.now():%Y-%m-%d_%H%M}_{_escenario()}_{'+'.join(familias)}"
    if etiqueta:
        nombre += "_" + "".join(c if c.isalnum() or c in "-_" else "-" for c in etiqueta)
    carpeta, k = base / nombre, 2
    while carpeta.exists():
        carpeta, k = base / f"{nombre}_{k}", k + 1
    carpeta.mkdir(parents=True)
    return carpeta


def _fila(top: str, est, a: dict | None) -> dict:
    s = est.mejor().score
    fila = {"familia": top, "estado": "factible" if _ma.es_factible(s) else _ma.describir_puntaje(s),
            "puntaje": s, "generaciones": est.generation}
    if a is not None:
        fila.update({
            "energia_Wh": _ma.energia_mision_wh(a), "masa_kg": a["masa_total"],
            "bateria_kg": a.get("masa_bateria") or 0.0,
            "envergadura_m": a.get("envergadura_total", a["envergadura"]),   # total, con winglets
            "winglet_m": float(a["params_trimados"].get("winglet_height", 0.0))
            if a["params_trimados"].get("winglet_height", 0.0) >= 0.02 else 0.0,
            "S_m2": a["S"], "AR": a["AR"], "LD_crucero": a["LD_crucero"], "D_crucero_N": a["D_crucero"],
            "v_perdida_ms": a["v_stall"], "SM_pct": 100 * a["SM"],
            "incidencia_trim_deg": a.get("incidencia_trim_deg", float("nan")),
            "n_rafaga": a["n_con_rafaga"], "Cn_beta": a["Cn_beta"],
        })
    return fila


def _fmt(v, f):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "-"
    try:
        return f.format(v)
    except (ValueError, TypeError):
        return str(v)


def _a_json(obj):
    if isinstance(obj, dict):
        return {k: _a_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_a_json(v) for v in obj]
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    if isinstance(obj, float) and not np.isfinite(obj):
        return str(obj)
    return obj


# ---------------------------------------------------------------- gráficos
def _convergencia(estados: dict, ruta: Path) -> None:
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4.8))
    for top, est in estados.items():
        g = [h["generation"] for h in est.historial]
        m = [max(h["parent_scores"]) for h in est.historial]
        fact = [_ma.es_factible(x) for x in m]
        gf = [x for x, f in zip(g, fact) if f]
        mf = [x for x, f in zip(m, fact) if f]
        linea, = ax.plot(gf, mf, marker="o", ms=3.5, label=top)
        n_inf = sum(not f for f in fact)
        if n_inf:
            linea.set_label(f"{top} ({n_inf} gen. sin padre factible)")
    ax.set_xlabel("generación")
    ax.set_ylabel("mejor puntaje (solo factibles)")
    ax.set_title(f"Convergencia — {_escenario()}")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)


def _comparacion(filas: list, ruta: Path) -> None:
    import matplotlib.pyplot as plt
    filas = [f for f in filas if "energia_Wh" in f]
    if not filas:
        return
    paneles = [("energia_Wh", "Energía para el alcance [Wh]"), ("masa_kg", "Masa total [kg]"),
               ("bateria_kg", "Batería [kg]"), ("LD_crucero", "L/D en crucero"),
               ("v_perdida_ms", "Velocidad de pérdida [m/s]"), ("SM_pct", "Margen estático [%]")]
    fig, axs = plt.subplots(2, 3, figsize=(13, 7))
    x = np.arange(len(filas))
    colores = ["#2f6fb0" if f["estado"] == "factible" else "#b0b7c0" for f in filas]
    for ax, (k, titulo) in zip(axs.flat, paneles):
        ax.bar(x, [f[k] for f in filas], color=colores, width=0.6)
        ax.set_xticks(x, [f["familia"] for f in filas], rotation=25, ha="right")
        ax.set_title(titulo, fontsize=10)
        ax.grid(axis="y", alpha=0.3)
        if k == "v_perdida_ms":
            ax.axhline(_ma.V_LENTO, color="#c0392b", ls="--", lw=1)
        if k == "SM_pct":       # banda de margen estático (la misma para todas las familias hoy)
            for lim in sorted({v for t in TOPOLOGIAS for v in TOPOLOGIAS[t]["sm_band"]}):
                ax.axhline(100 * lim, color="#c0392b", ls="--", lw=1)
    fig.suptitle(f"Mejor avión de cada familia — {_escenario()} (gris = infactible)")
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)


def _curvas(analisis: dict, ruta: Path, n: int = 14) -> None:
    """Resistencia y potencia en vuelo nivelado, desde 1.1 x pérdida limpia
    hasta 1.1 x V_MAX, con el avión trimado y la atmósfera de la misión."""
    import aerosandbox as asb
    import matplotlib.pyplot as plt
    atm = _ma._atmosfera()
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.5))
    for top, a in analisis.items():
        if a is None:
            continue
        avion = construir_avion(a["params_trimados"], top)
        rho, S, W = a["rho"], a["S"], a["peso"]
        V = np.linspace(1.1 * np.sqrt(2 * W / (rho * S * a["CL_max_crucero"])), 1.1 * _ma.V_MAX, n)
        D = []
        for v in V:
            CL_req = W / (0.5 * rho * v ** 2 * S)
            alfa = a["alpha_crucero"] + (CL_req - a["CL_crucero"]) / a["CL_alpha_por_grado"]
            r = asb.AeroBuildup(airplane=avion, op_point=asb.OperatingPoint(atmosphere=atm, velocity=v, alpha=alfa)).run()
            D.append(0.5 * rho * v ** 2 * S * _ma._escalar(r["CD"]))
        D = np.array(D)
        axs[0].plot(3.6 * V, D, lw=2, label=top)
        axs[1].plot(3.6 * V, D * V / _bat.ETA_PROPULSIVA_TOTAL, lw=2, label=top)
    for ax, y in zip(axs, ("resistencia = empuje requerido [N]", "potencia eléctrica (sin aviónica) [W]")):
        for v, ls in ((_ma.V_CRUCERO, "-"), (_ma.V_MAX, "--")):
            ax.axvline(3.6 * v, color="#c0392b", lw=0.8, ls=ls, alpha=0.7)
        ax.set_xlabel("velocidad [km/h]")
        ax.set_ylabel(y)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    fig.suptitle("Vuelo nivelado (línea llena: crucero de diseño; punteada: velocidad máxima)")
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)


# Luz casi toda ambiente: las mallas de AeroSandbox tienen triángulos con la
# normal invertida (la mitad espejada del ala) y con luz direccional se ven
# manchas que no son geometría.
_LUZ = dict(ambient=0.75, diffuse=0.35, specular=0.05, roughness=0.9)

# Colores por tipo de componente en la vista 3D.
_COLORES_3D = {"ala": "#2f6fb0", "cola": "#e08a2e", "fuselaje": "#8a96a3", "boom": "#5b6570"}


def _tipo_componente(nombre: str, es_primera_ala: bool) -> str:
    n = nombre.lower()
    if es_primera_ala:
        return "ala"
    if "boom" in n:
        return "boom"
    return "cola"


def lineas_info(a: dict | None, puntaje: float | None = None) -> list:
    """Datos del avión para mostrar al lado de la vista 3D."""
    if a is None:
        return ["avion INFACTIBLE: ver el desglose"]
    L = []
    if puntaje is not None:
        L.append(f"puntaje {_ma.describir_puntaje(puntaje)}")
    L += [f"energia para {_bat.ALCANCE_KM:.0f} km: {_ma.energia_mision_wh(a):.0f} Wh",
          f"masa {a['masa_total']:.2f} kg" + (f"  (bateria {a['masa_bateria']:.2f} kg)" if a.get("masa_bateria") else ""),
          f"envergadura {a.get('envergadura_total', a['envergadura']):.2f} m (total)   S {a['S']:.3f} m2   AR {a['AR']:.1f}",
          f"L/D crucero {a['LD_crucero']:.1f}   D {a['D_crucero']:.2f} N",
          f"perdida {a['v_stall']:.2f} m/s (con flap)   SM {100*a['SM']:.1f} %",
          f"incidencia de cola (trim) {a.get('incidencia_trim_deg', float('nan')):+.2f} grados",
          f"rafaga n = {a['n_con_rafaga']:.2f}   Cn_beta {a['Cn_beta']:.4f} /grado"]
    return L


def figura_3d(avion, titulo: str = "", info: list | None = None, resolucion: int = 24):
    """Vista 3D interactiva (plotly) con un color por tipo de componente (ala,
    cola, fuselaje, vigas), escala 1:1 en los tres ejes y un recuadro con los
    datos del avión. Reemplaza a `avion.draw(backend="plotly")`, cuya barra de
    colores no significa nada (pinta todas las caras con intensidad 0)."""
    import plotly.graph_objects as go
    fig = go.Figure()
    vistos = set()
    for i, w in enumerate(avion.wings):
        P, F = w.mesh_body(method="tri", chordwise_resolution=resolucion, mesh_surface=True,
                           mesh_tips=True, mesh_trailing_edge=True, mesh_symmetric=True)
        tipo = _tipo_componente(w.name, i == 0)
        P, F = np.asarray(P), np.asarray(F)
        fig.add_trace(go.Mesh3d(x=P[:, 0], y=P[:, 1], z=P[:, 2], i=F[:, 0], j=F[:, 1], k=F[:, 2],
                                color=_COLORES_3D[tipo], flatshading=False, name=w.name,
                                legendgroup=tipo, showlegend=tipo not in vistos, lighting=_LUZ))
        vistos.add(tipo)
    for f_ in avion.fuselages:
        P, F = f_.mesh_body(method="tri", tangential_resolution=resolucion)
        tipo = "boom" if "boom" in f_.name.lower() else "fuselaje"
        P, F = np.asarray(P), np.asarray(F)
        fig.add_trace(go.Mesh3d(x=P[:, 0], y=P[:, 1], z=P[:, 2], i=F[:, 0], j=F[:, 1], k=F[:, 2],
                                color=_COLORES_3D[tipo], flatshading=False, name=f_.name,
                                legendgroup=tipo, showlegend=tipo not in vistos, lighting=_LUZ))
        vistos.add(tipo)
    # CG de diseño
    x_cg = float(avion.xyz_ref[0])
    fig.add_trace(go.Scatter3d(x=[x_cg], y=[0], z=[0], mode="markers+text", text=["CG"],
                               marker=dict(size=5, color="#c0392b"), name="CG"))
    fig.update_layout(
        title=titulo,
        scene=dict(aspectmode="data", xaxis_title="x [m] (hacia la cola)", yaxis_title="y [m]",
                   zaxis_title="z [m]", camera=dict(eye=dict(x=-1.3, y=-1.3, z=0.8))),
        legend=dict(x=0.0, y=1.0),
        margin=dict(l=0, r=0, t=50, b=0))
    if info:
        fig.add_annotation(text="<br>".join(info), xref="paper", yref="paper", x=1.0, y=1.0,
                           xanchor="right", yanchor="top", showarrow=False, align="left",
                           font=dict(family="monospace", size=12),
                           bgcolor="rgba(255,255,255,0.85)", bordercolor="#8a96a3", borderwidth=1)
    return fig


def figura_flujo(params: dict, topologia: str, titulo: str = "", spanwise: int = 4,
                 chordwise: int = 6, n_pasos: int = 300):
    """Líneas de flujo alrededor del avión (VLM de AeroSandbox), en el punto de
    CRUCERO de la misión: el avión trimado, al alpha de crucero, con la
    atmósfera del escenario (viento on/off).

    Los paneles se pintan con la circulación Γ de cada vórtice [m²/s] (cuánta
    sustentación genera esa zona; Γ alta = más carga) y las líneas de flujo
    muestran la estela y los torbellinos de punta. Es SOLO para visualizar: el
    VLM es potencial e inviscido y no ve el fuselaje (se dibuja en gris como
    referencia); el CD que da es solo inducido. Los números del optimizador
    salen de AeroBuildup (ver el desglose). Devuelve (figura, dict con CL y CDi
    del VLM), o (None, motivo) si el avión es infactible."""
    import aerosandbox as asb
    import plotly.graph_objects as go
    a = _ma.analizar_mision_avion(params, topologia)
    if a is None:
        return None, {"motivo": _ma.describir_puntaje(_ma.evaluar_mision_avion(params, topologia))}
    avion = construir_avion(a["params_trimados"], topologia)
    op = asb.OperatingPoint(atmosphere=_ma._atmosfera(), velocity=_ma.V_CRUCERO, alpha=a["alpha_crucero"])
    vlm = asb.VortexLatticeMethod(airplane=avion, op_point=op,
                                  spanwise_resolution=spanwise, chordwise_resolution=chordwise)
    r = vlm.run()
    vlm.calculate_streamlines(n_steps=n_pasos)

    # Paneles: cada cuadrilátero en dos triángulos, coloreado por Γ.
    fl, bl = np.asarray(vlm.front_left_vertices), np.asarray(vlm.back_left_vertices)
    br, fr = np.asarray(vlm.back_right_vertices), np.asarray(vlm.front_right_vertices)
    n = len(fl)
    P = np.concatenate([fl, bl, br, fr])
    idx = np.arange(n)
    I = np.concatenate([idx, idx])
    J = np.concatenate([idx + n, idx + 2 * n])
    K = np.concatenate([idx + 2 * n, idx + 3 * n])
    gamma = np.asarray(vlm.vortex_strengths, float)
    fig = go.Figure()
    fig.add_trace(go.Mesh3d(x=P[:, 0], y=P[:, 1], z=P[:, 2], i=I, j=J, k=K,
                            intensity=np.concatenate([gamma, gamma]), intensitymode="cell",
                            colorscale="Viridis", name="superficies (VLM)",
                            colorbar=dict(title="circulación Γ<br>[m²/s]", x=1.0),
                            lighting=_LUZ, flatshading=False))
    for f_ in avion.fuselages:                     # el VLM no lo ve: solo de referencia
        Pf, Ff = f_.mesh_body(method="tri", tangential_resolution=20)
        Pf, Ff = np.asarray(Pf), np.asarray(Ff)
        fig.add_trace(go.Mesh3d(x=Pf[:, 0], y=Pf[:, 1], z=Pf[:, 2], i=Ff[:, 0], j=Ff[:, 1], k=Ff[:, 2],
                                color=_COLORES_3D["fuselaje"], opacity=0.35, name=f"{f_.name} (no entra al VLM)",
                                showlegend=True, lighting=_LUZ))
    S = np.asarray(vlm.streamlines)                # (n_lineas, 3, n_pasos)
    xs, ys, zs = [], [], []
    for k in range(S.shape[0]):
        xs += list(S[k, 0, :]) + [None]
        ys += list(S[k, 1, :]) + [None]
        zs += list(S[k, 2, :]) + [None]
    fig.add_trace(go.Scatter3d(x=xs, y=ys, z=zs, mode="lines", name="líneas de flujo",
                               line=dict(color="rgba(150, 60, 220, 0.6)", width=2)))

    CL_vlm, CDi_vlm = float(np.atleast_1d(r["CL"])[0]), float(np.atleast_1d(r["CD"])[0])
    datos = {"CL_vlm": CL_vlm, "CDi_vlm": CDi_vlm, "CL_requerido": a["CL_crucero"],
             "alpha_deg": a["alpha_crucero"]}
    e = CL_vlm ** 2 / (np.pi * a["AR"] * CDi_vlm) if CDi_vlm > 0 else float("nan")
    info = [f"crucero {3.6*_ma.V_CRUCERO:.0f} km/h, alpha {a['alpha_crucero']:.2f} grados, "
            f"rho {a['rho']:.3f} kg/m3",
            f"CL VLM {CL_vlm:.3f}  (el peso pide {a['CL_crucero']:.3f})",
            f"CD inducido VLM {CDi_vlm:.5f}   e de Oswald {e:.2f}",
            f"CD total (AeroBuildup) {a['CD_crucero']:.5f}",
            "VLM inviscido, sin fuselaje: solo para visualizar"]
    fig.update_layout(
        title=titulo or f"{topologia} — líneas de flujo en crucero",
        scene=dict(aspectmode="data", xaxis_title="x [m] (hacia la cola)", yaxis_title="y [m]",
                   zaxis_title="z [m]", camera=dict(eye=dict(x=-1.4, y=-1.2, z=0.7))),
        legend=dict(x=0.0, y=1.0), margin=dict(l=0, r=0, t=50, b=0))
    fig.add_annotation(text="<br>".join(info), xref="paper", yref="paper", x=0.88, y=1.0,
                       xanchor="right", yanchor="top", showarrow=False, align="left",
                       font=dict(family="monospace", size=12),
                       bgcolor="rgba(255,255,255,0.85)", bordercolor="#8a96a3", borderwidth=1)
    return fig, datos


_LEEME_BASE = """# Resultados del optimizador de avión

Cada corrida guarda acá una carpeta propia. La escribe `optimizacion_avion/resultados.py`
(`av.guardar_resultados(estados)`, que llaman la sección 11b del notebook y
`evaluacion_bateria_350km/correr_escenarios.py`). Esta carpeta está FUERA del repositorio a
propósito: los resultados quedan en la computadora y no se suben a git. Se puede cambiar con la
variable de entorno `UAV_RESULTADOS` o con `CARPETA_RESULTADOS` en la sección 0 del notebook.

## Nombre de cada carpeta

    <fecha>_<hora>_viento-<on|off>_bateria-<on|off>_<familias>[_<etiqueta>]
    2026-10-19_2130_viento-on_bateria-on_v_tail+pod_boom
    2026-10-20_0915_viento-on_bateria-on_pod_boom_eta070

- fecha y hora en que se guardó (se ordenan solas);
- escenario: los interruptores VIENTO_ACTIVO y BATERIA_ACTIVA;
- familias corridas, unidas con `+`;
- etiqueta opcional (`guardar_resultados(..., etiqueta="eta070")`) para marcar una prueba.

Una carpeta existente nunca se pisa: si el nombre se repite se agrega `_2`, `_3`, ...

## Qué hay adentro (siempre los mismos nombres)

| Archivo | Qué es |
|---|---|
| `LEEME.md` | Qué se corrió (escenario, modo de puntaje, misión, versión, parámetros del GA) y la tabla final |
| `tabla_resumen.csv` | Una fila por familia: estado, puntaje, energía, masa, batería, envergadura total, largo de winglet, S, AR, L/D, D, pérdida, SM, incidencia de trim, ráfaga, Cn_beta |
| `ganadores.json` | Por familia: params TRIMADOS (los que van a CAD/CFD), análisis completo e historial del GA |
| `convergencia.png` | Mejor puntaje por generación (solo generaciones con algún padre factible) |
| `comparacion.png` | Barras por familia: energía, masa, batería, L/D, pérdida y margen estático (gris = infactible) |
| `curvas_vuelo.png` | Resistencia y potencia en vuelo nivelado contra velocidad |
| `vistas_3d/<familia>.html` | Vista 3D con un color por componente, el CG y los datos del avión |
| `lineas_flujo/<familia>.html` | Líneas de flujo en crucero (VLM): paneles por circulación y estela. Solo visualización |
| `tres_vistas/<familia>.png` | Planta, frente, perfil y perspectiva |
| `desgloses/<familia>.txt` | Desglose completo de la misión |
| `xflr5/<familia>/` | Para XFLR5: `<familia>_avion.xml` (avión trimado, sin fuselaje, masa en el CG), `perfiles/*.dat` y `condiciones.txt` (velocidad, densidad, masa, CG, alpha y los pasos para importarlo) |

Los .html se abren con doble clic en el navegador (necesitan internet la primera vez para
cargar plotly). Para llevar un ganador a CAD o CFD, desde la carpeta genetic_wing:

    python herramientas/exportar_cad_avion.py --params "<esta carpeta>/<corrida>/ganadores.json" --topologia <familia>
    python exportar_cfd_avion.py --params "<esta carpeta>/<corrida>/ganadores.json" --topologia <familia>
"""


def _escribir_leeme_base(base: Path) -> None:
    """Deja (o actualiza) el LEEME.md que explica la nomenclatura en la carpeta base."""
    ruta = base / "LEEME.md"
    if not ruta.exists() or ruta.read_text(encoding="utf-8") != _LEEME_BASE:
        ruta.write_text(_LEEME_BASE, encoding="utf-8")


def _tres_vistas(avion, titulo: str, ruta: Path) -> None:
    import matplotlib.pyplot as plt
    axs = avion.draw_three_view(show=False)
    fig = np.asarray(axs).flat[0].get_figure()
    fig.suptitle(titulo)
    fig.savefig(ruta, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------- principal
def guardar_resultados(estados: dict, carpeta_base: str | Path | None = None,
                       etiqueta: str | None = None, curvas: bool = True,
                       parametros_ga: dict | None = None, flujo: bool = True) -> Path:
    """Escribe todo lo de una corrida en una carpeta nueva y la devuelve.

    estados       {familia: EstadoEvolucionAvion} (lo que arma el notebook o
                  devuelve competencia.correr_competencia)
    carpeta_base  por defecto CARPETA_RESULTADOS (fuera del repositorio)
    etiqueta      texto opcional que se agrega al nombre de la carpeta
    curvas        False saltea las curvas de vuelo nivelado (~15 corridas de
                  AeroBuildup por familia)
    parametros_ga dict opcional que se anota en el LEEME (paciencia, etc.)
    flujo         False saltea las líneas de flujo (VLM, ~20 s y ~3 MB por familia)"""
    import matplotlib
    matplotlib.use("Agg")

    familias = [t for t in TOPOLOGIAS if t in estados]
    base = Path(carpeta_base) if carpeta_base else CARPETA_RESULTADOS
    base.mkdir(parents=True, exist_ok=True)
    _escribir_leeme_base(base)
    carpeta = _carpeta_nueva(base, familias, etiqueta)
    for sub in ("vistas_3d", "tres_vistas", "desgloses") + (("lineas_flujo",) if flujo else ()):
        (carpeta / sub).mkdir()

    analisis, filas, ganadores = {}, [], {}
    for top in familias:
        est = estados[top]
        mejor = est.mejor()
        a = _ma.analizar_mision_avion(mejor.params, top)
        analisis[top] = a
        filas.append(_fila(top, est, a))
        params = a["params_trimados"] if a is not None else mejor.params
        ganadores[top] = {"puntaje": mejor.score, "estado": filas[-1]["estado"],
                          "generaciones": est.generation, "params": params,
                          "analisis": a, "historial": est.historial}
        (carpeta / "desgloses" / f"{top}.txt").write_text(
            _ma.desglose_mision_avion(mejor.params, top) + "\n", encoding="utf-8")
        avion = construir_avion(params, top)
        fig = figura_3d(avion, f"{top} — {_escenario()}", lineas_info(a, mejor.score))
        fig.write_html(carpeta / "vistas_3d" / f"{top}.html", include_plotlyjs="cdn")
        try:
            _tres_vistas(avion, f"{top} — {_escenario()}", carpeta / "tres_vistas" / f"{top}.png")
        except Exception as e:                      # el dibujo no debe tirar abajo el guardado
            print(f"[{top}] no se pudo dibujar las tres vistas: {e!r}")
        try:
            from .xflr5 import exportar_xflr5
            exportar_xflr5(mejor.params, top, carpeta / "xflr5" / top)
        except Exception as e:
            print(f"[{top}] no se pudo exportar a XFLR5: {e!r}")
        if flujo and a is not None:
            try:
                fig_f, _ = figura_flujo(mejor.params, top, f"{top} — líneas de flujo en crucero — {_escenario()}")
                fig_f.write_html(carpeta / "lineas_flujo" / f"{top}.html", include_plotlyjs="cdn")
            except Exception as e:
                print(f"[{top}] no se pudieron calcular las líneas de flujo: {e!r}")

    (carpeta / "ganadores.json").write_text(
        json.dumps(_a_json(ganadores), indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    with open(carpeta / "tabla_resumen.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[c for c, _ in COLUMNAS], extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)

    _convergencia(estados, carpeta / "convergencia.png")
    _comparacion(filas, carpeta / "comparacion.png")
    if curvas and any(a is not None for a in analisis.values()):
        _curvas(analisis, carpeta / "curvas_vuelo.png")

    # LEEME de la corrida
    orden = sorted(filas, key=lambda f: -f["puntaje"] if np.isfinite(f["puntaje"]) else np.inf)
    L = [f"# Corrida {carpeta.name}", "",
         f"- Fecha: {dt.datetime.now():%Y-%m-%d %H:%M}",
         f"- Familias: {', '.join(familias)}",
         f"- Escenario: VIENTO_ACTIVO = {_ma.VIENTO_ACTIVO}, BATERIA_ACTIVA = {_ma.BATERIA_ACTIVA}",
         f"- Puntaje: PUNTAJE_MODO = '{_ma.PUNTAJE_MODO}', TRIM_RESUELTO = {_ma.TRIM_RESUELTO}, "
         f"RANKING_INFACTIBLES = {_ma.RANKING_INFACTIBLES}",
         f"- Misión: crucero {3.6*_ma.V_CRUCERO:.0f} km/h, máxima {3.6*_ma.V_MAX:.0f} km/h, "
         f"lento {_ma.V_LENTO:.0f} m/s, alcance {_bat.ALCANCE_KM:.0f} km, "
         f"eta propulsiva {_bat.ETA_PROPULSIVA_TOTAL:.2f}"]
    try:
        from . import VERSION
        L.append(f"- Versión del optimizador: {VERSION}")
    except ImportError:
        pass
    if parametros_ga:
        L.append("- GA: " + ", ".join(f"{k} = {v}" for k, v in parametros_ga.items()))
    L += ["", "## Mejor avión de cada familia (ordenado por puntaje)", "",
          "| " + " | ".join(c for c, _ in COLUMNAS) + " |", "|" + "---|" * len(COLUMNAS)]
    for f_ in orden:
        L.append("| " + " | ".join(_fmt(f_.get(c), fmt) for c, fmt in COLUMNAS) + " |")
    L += ["", "## Archivos", "",
          "- `tabla_resumen.csv`: la tabla de arriba.",
          "- `ganadores.json`: params TRIMADOS (los que se exportan a CAD/CFD), análisis e historial.",
          "- `convergencia.png`, `comparacion.png`" + (", `curvas_vuelo.png`" if curvas else "") + ".",
          "- `vistas_3d/<familia>.html`: vista 3D interactiva (doble clic, se abre en el navegador).",
          "- `lineas_flujo/<familia>.html`: líneas de flujo en crucero (VLM, solo visualización)." if flujo else "",
          "- `xflr5/<familia>/`: el avión para XFLR5 (`<familia>_avion.xml`, `perfiles/*.dat`, `condiciones.txt` con los pasos).",
          "- `tres_vistas/<familia>.png`: planta, frente y perfil.",
          "- `desgloses/<familia>.txt`: el desglose completo de la misión.", "",
          "Para exportar un ganador a CAD (desde genetic_wing): `python herramientas/exportar_cad_avion.py --params "
          f"\"{carpeta / 'ganadores.json'}\" --topologia <familia>`"]
    (carpeta / "LEEME.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"Resultados guardados en {carpeta}")
    return carpeta
