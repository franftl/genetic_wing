"""
Procesa los resúmenes de viento ERA5 (ya calculados) y genera:
  - fichas/<sitio>.yaml        parámetros listos para cargar desde el código
  - tablas/<sitio>_*.csv       tablas mensuales, diurnas, rosa, excedencia
  - tablas/operabilidad.csv    fracción de horas operables vs velocidad de crucero
  - figuras/*.png              gráficos para la tesis

Entrada: datos/*.json (salida de descargar_era5.py o del resumen original).
Uso:     python procesar_viento.py   (desde la carpeta scripts/)
"""
import csv
import json
import math
from pathlib import Path

import numpy as np
import yaml
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.special import gamma as G

BASE = Path(__file__).resolve().parent.parent
DATOS = BASE / "datos"
FICHAS = BASE / "fichas"
TABLAS = BASE / "tablas"
FIGS = BASE / "figuras"
for d in (FICHAS, TABLAS, FIGS):
    d.mkdir(exist_ok=True)

KT = 0.514444          # m/s por nudo
FT = 0.3048            # m por pie
V_CRUCERO_ACTUAL = 60 / 3.6   # m/s, la que usa hoy Version_sept_1/mision.py

SITIOS = {
    "canadon_leon": dict(
        nombre="Cañadón León (Santa Cruz)",
        archivo="canadon_leon_era5_resumen.json",
        color="#2a78d6",
        descripcion_punto="Punto representativo del yacimiento, junto a Cañadón Seco (NE de Santa Cruz, Cuenca del Golfo San Jorge).",
        # Validación contra Comodoro Rivadavia Aero (ver validacion_estaciones_vs_era5.json):
        # ERA5 subestima la cola: p90 obs/ERA5 = 1.21, p99 obs/ERA5 = 1.30.
        factor_cola=1.25,
        estacion_ref="Comodoro Rivadavia Aero (WMO 87860), ~85 km al N, costera",
    ),
    "puesto_hernandez": dict(
        nombre="Puesto Hernández (N de Neuquén / S de Mendoza)",
        archivo="puesto_hernandez_era5_resumen.json",
        color="#eb6834",
        descripcion_punto="Punto ~20 km al NO de Rincón de los Sauces, dentro del área de concesión Puesto Hernández (límite Neuquén–Mendoza).",
        # Validación contra Neuquén Aero: ERA5 sobreestima la media (x1.44) y
        # acierta el p99 (obs 9.3 vs ERA5 10.1); ráfagas máximas obs ~10% mayores.
        factor_cola=1.10,
        estacion_ref="Neuquén Aero (WMO 87715), ~180 km al SE, en valle",
    ),
}

VAL = json.loads((DATOS / "validacion_estaciones_vs_era5.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ utilidades
def weibull_momentos(media, desvio):
    k = (desvio / media) ** -1.086
    c = media / G(1 + 1 / k)
    return k, c


def gumbel(maximos, T):
    x = np.array(maximos, float)
    beta = x.std(ddof=1) * math.sqrt(6) / math.pi
    mu = x.mean() - 0.5772 * beta
    return mu - beta * math.log(-math.log(1 - 1 / T))


def dryden(W20_ms, h_m):
    """Intensidades y escalas de Dryden baja altura (h < 1000 ft)."""
    h = h_m / FT
    s_w = 0.1 * W20_ms
    s_u = s_w / (0.177 + 0.000823 * h) ** 0.4
    Lu = h / (0.177 + 0.000823 * h) ** 1.2
    return dict(
        sigma_w_ms=round(s_w, 3), sigma_u_ms=round(s_u, 3), sigma_v_ms=round(s_u, 3),
        MIL_F_8785C=dict(Lu_m=round(Lu * FT, 1), Lv_m=round(Lu * FT, 1), Lw_m=round(h * FT, 1)),
        MIL_HDBK_1797=dict(Lu_m=round(Lu * FT, 1), Lv_m=round(Lu * FT / 2, 1), Lw_m=round(h * FT / 2, 1)),
    )


def factor_ida_vuelta(W, Vc):
    """Tiempo ida+vuelta con viento W alineado con la ruta / tiempo en aire quieto."""
    return 1.0 / (1.0 - (W / Vc) ** 2) if W < Vc else float("inf")


def operabilidad(hist, Vc, escala=1.0, factor_max=1.5):
    """hist: cuentas en bins de 0.5 m/s. Se toma el borde superior del bin (conservador)."""
    W = (np.arange(len(hist)) + 1) * 0.5 * escala
    n = np.array(hist, float)
    tot = n.sum()
    no_avanza = n[W >= Vc].sum() / tot
    ok = n[W <= Vc * math.sqrt(1 - 1 / factor_max)].sum() / tot
    m = W < 0.95 * Vc
    fac_medio = float((n[m] * np.array([factor_ida_vuelta(w, Vc) for w in W[m]])).sum() / n[m].sum())
    return no_avanza, ok, fac_medio


SECT = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"]
MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def escribir_csv(path, filas, cab):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:  # BOM para que Excel lea bien los acentos
        w = csv.writer(f)
        w.writerow(cab)
        w.writerows(filas)


# ------------------------------------------------------------------ estilo
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": "#8a8a85", "axes.labelcolor": "#3d3d3a", "xtick.color": "#5f5e5a",
    "ytick.color": "#5f5e5a", "axes.grid": True, "grid.color": "#e8e6dc", "grid.linewidth": 0.6,
    "axes.titleweight": "bold", "axes.titlesize": 10, "figure.dpi": 150,
})
RAMPA = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#0d366b"]
CLASES = ["0–4", "4–8", "8–12", "12–16", "16–20", ">20"]

resumen_op = []
R = {}

for clave, S in SITIOS.items():
    d = json.loads((DATOS / S["archivo"]).read_text(encoding="utf-8"))
    R[clave] = d
    k, c = weibull_momentos(d["ws120"]["media"], d["ws120"]["desvio"])
    ks, cs = weibull_momentos(d["ws10"]["media"], d["ws10"]["desvio"])
    fc = S["factor_cola"]

    # ---- turbulencia: estimación de W20 del sitio y chequeo por capa límite
    alpha = d["alpha"]["p50"]
    ws10_p99_corr = d["ws10"]["p99"] * fc
    W20_sitio = ws10_p99_corr * (20 * FT / 10) ** alpha
    z0 = 0.03  # estepa patagónica: terreno abierto con pasto/arbusto bajo
    u_star = 0.4 * ws10_p99_corr / math.log(10 / z0)
    sigma_w_capa_limite = 1.25 * u_star
    w_kt = W20_sitio / KT
    categoria = ("ligera" if w_kt <= 17 else "entre ligera y moderada" if w_kt <= 25
                 else "moderada" if w_kt <= 33 else "entre moderada y severa")
    W20_dis = 30 * KT  # moderada para ambos sitios: una sola envolvente de diseño
    dr120 = dryden(W20_dis, 120)
    dr30 = dryden(W20_dis, 30)
    sw_mod = 0.1 * 30 * KT
    sw_lig = 0.1 * 15 * KT

    # ---- rosa
    rosa = sorted(d["rosa"], key=lambda r: -r["frecuencia"])
    top = [f'{SECT[int(r["sector_deg"] / 22.5)]} ({r["frecuencia"] * 100:.0f}%, media {r["media"]:.1f} m/s)' for r in rosa[:3]]

    # ---- operabilidad
    for Vc in (V_CRUCERO_ACTUAL, 20.0, 22.0, 25.0):
        for esc, etiqueta in ((1.0, "ERA5"), (fc, f"ERA5 x{fc}")):
            na, ok, fm = operabilidad(d["hist_ws120_diurno_05"], Vc, esc)
            resumen_op.append([S["nombre"], etiqueta, round(Vc, 1), round(Vc * 3.6), round(na * 100, 1), round(ok * 100, 1), round(fm, 2)])

    # ---- extremos
    gy = [a["max"] for a in d["anual"]["rafaga10"]]

    ficha = {
        "sitio": S["nombre"],
        "descripcion_punto": S["descripcion_punto"],
        "ubicacion": {"lat": d["lat_pedida"], "lon": d["lon_pedida"],
                      "celda_era5": {"lat": d["lat_grilla"], "lon": d["lon_grilla"], "resolucion_deg": 0.25},
                      "cota_terreno_m": d["elevacion_modelo_m"]},
        "fuente_principal": {"dataset": "ERA5 (ECMWF / Copernicus C3S), reanálisis horario",
                             "acceso": "Open-Meteo Historical Weather API (models=era5)",
                             "periodo": f'{d["periodo"][0]} a {d["periodo"][1]}', "horas": d["horas"],
                             "horas_faltantes": d["horas_faltantes"], "url_consulta": d["url"]},
        "unidades": "m/s, m, grados (dirección DE DONDE viene el viento, meteorológica), kg/m3",

        "atmosfera": {
            "densidad_superficie": {k2: d["densidad"][k2] for k2 in ("media", "p05", "p50", "p95", "min", "max")},
            "densidad_a_120m_factor": 0.986,
            "densidad_diseno_kg_m3": round(d["densidad"]["p05"] * 0.986, 3),
            "nota": "rho = p_sup/(R T_2m), aire seco. Para performance usar la baja (p05 x 0.986 a 120 m): el ala necesita más CL.",
            "temperatura_C": {k2: d["temperatura"][k2] for k2 in ("media", "p05", "p95", "min", "max")},
        },

        "viento_crucero": {
            "altura_m": 120,
            "metodo": "ERA5 a 100 m extrapolado a 120 m con el alfa horario (V120 = V100 * 1.2^alfa)",
            "todas_las_horas": {k2: d["ws120"][k2] for k2 in ("media", "p50", "p75", "p90", "p95", "p99", "max")},
            "horas_diurnas_08_19": {k2: d["ws120_diurno_08_19"][k2] for k2 in ("media", "p50", "p75", "p90", "p95", "p99", "max")},
            "weibull": {"k": round(k, 3), "c_ms": round(c, 3), "metodo": "momentos"},
            "direcciones_predominantes": top,
            "mes_mas_ventoso": MESES[int(np.argmax([m["media"] for m in d["mensual"]["ws120"]]))],
            "mes_mas_calmo": MESES[int(np.argmin([m["media"] for m in d["mensual"]["ws120"]]))],
            "correccion_cola_recomendada": {"factor": fc, "aplica_a": "percentiles >= p90 y extremos",
                                            "justificacion": f'Validación ERA5 vs estación {S["estacion_ref"]}; ver documento de trazabilidad.'},
        },

        "viento_superficie_10m": {
            "media_p50_p90_p95_p99_max": [d["ws10"][x] for x in ("media", "p50", "p90", "p95", "p99", "max")],
            "weibull": {"k": round(ks, 3), "c_ms": round(cs, 3)},
            "rafaga_10m": {k2: d["rafaga10"][k2] for k2 in ("media", "p50", "p90", "p95", "p99", "max")},
            "rafaga_10m_diurna": {k2: d["rafaga10_diurno_08_19"][k2] for k2 in ("media", "p90", "p95", "p99", "max")},
            "factor_de_rafaga_mediana": d["factor_rafaga"]["p50"],
            "nota": "Ráfaga ERA5 = máxima ráfaga de 3 s de la hora anterior, a 10 m.",
        },

        "gradiente_vertical": {
            "ley": "potencia: U(z) = U_ref * (z / z_ref)^alfa",
            "z_ref_m": 10,
            "alfa_mediana": d["alpha"]["p50"],
            "alfa_p90": d["alpha"]["p90"],
            "alfa_mediodia_13_16h": round(float(np.mean([d["diurno"]["alpha"][h]["p50"] for h in range(13, 17)])), 3),
            "alfa_noche_00_06h": round(float(np.mean([d["diurno"]["alpha"][h]["p50"] for h in range(0, 7)])), 3),
            "nota": "Calculado entre 10 y 100 m de ERA5, horas con V10 >= 3 m/s. De día el aire se mezcla (alfa ~0.10); de noche es estable (alfa ~0.22-0.25).",
            "ley_logaritmica_alternativa": {"z0_m": z0, "nota": "estepa: terreno abierto con pasto/arbusto bajo (clasificación de Davenport)"},
        },

        "turbulencia_continua": {
            "modelo": "Dryden, baja altura (h < 1000 ft) según MIL-F-8785C / MIL-HDBK-1797",
            "W20_estimado_sitio_ms": round(W20_sitio, 2),
            "W20_estimado_sitio_kt": round(W20_sitio / KT, 1),
            "categoria_del_sitio": categoria,
            "como_se_estimo": f"p99 de V10 ERA5 x factor de cola {fc}, llevado a 20 ft con la ley de potencia",
            "chequeo_capa_limite": {"u_estrella_ms": round(u_star, 3), "sigma_w_ms": round(sigma_w_capa_limite, 3),
                                    "formula": "u* = 0.4 U10 / ln(10/z0); sigma_w = 1.25 u*"},
            "diseno_recomendado": "moderada (W20 = 30 kt = 15.4 m/s) para ambos sitios, como envolvente única",
            "a_120m": dr120,
            "a_30m_despegue_aterrizaje": dr30,
        },

        "rafaga_discreta": {
            "forma": "1 - coseno: w(x) = (U_ds/2) (1 - cos(pi x / H)), 0 <= x <= 2H",
            "U_ds_ms": {
                "operacional_2sigma_moderada": round(2 * sw_mod, 2),
                "diseno_3sigma_moderada": round(3 * sw_mod, 2),
                "nominal_3sigma_ligera": round(3 * sw_lig, 2),
                "referencia_CS23_FAR23_a_VC": 15.24,
            },
            "H_m": {"CS23_FAR23": "12.5 * cuerda media (longitud total 25 cuerdas)",
                    "barrido_sugerido": [f"12.5 c_media", round(dr120["MIL_F_8785C"]["Lw_m"], 0)]},
            "alivio_de_rafaga": "Kg = 0.88 mu / (5.3 + mu), mu = 2 (W/S) / (rho c_media CL_alpha g) (FAR 23.341)",
            "nota": "Los 15.24 m/s de CS-23 están pensados para aviones tripulados rápidos; en un UAV de ~17 m/s implican entrar en pérdida, así que la carga queda limitada por CL_max. Ver documento de trazabilidad.",
        },

        "extremos_en_tierra": {
            "rafaga10_max_anual_era5": gy,
            "rafaga10_retorno_10_anios_ms": round(gumbel(gy, 10), 1),
            "rafaga10_retorno_50_anios_ms": round(gumbel(gy, 50), 1),
            "nota": "Gumbel por momentos sobre 10 máximos anuales. Sirve para anclaje/estiba del UAV en tierra, no para vuelo. Con la corrección de cola, sumar ~10-25%.",
        },

        "archivos_relacionados": {
            "resumen_completo": f"datos/{S['archivo']}",
            "tablas": [f"tablas/{clave}_mensual.csv", f"tablas/{clave}_diurno.csv", f"tablas/{clave}_rosa_120m.csv", f"tablas/{clave}_excedencia.csv"],
            "figura": f"figuras/{clave}_panel.png",
        },
    }
    with open(FICHAS / f"{clave}.yaml", "w", encoding="utf-8") as f:
        f.write(f"# Ficha de viento — {S['nombre']}\n# Generada por scripts/procesar_viento.py. No editar a mano: cambiar el script y regenerar.\n\n")
        ficha = json.loads(json.dumps(ficha, default=float))  # numpy -> float nativo
        yaml.safe_dump(ficha, f, sort_keys=False, allow_unicode=True, width=110)

    # ---- tablas
    escribir_csv(TABLAS / f"{clave}_mensual.csv",
                 [[MESES[i], d["mensual"]["ws120"][i]["media"], d["mensual"]["ws120"][i]["p90"], d["mensual"]["ws120"][i]["p95"],
                   d["mensual"]["ws10"][i]["media"], d["mensual"]["rafaga10"][i]["media"], d["mensual"]["rafaga10"][i]["p95"],
                   d["alphaMes"][i]["p50"]] for i in range(12)],
                 ["mes", "V120_media", "V120_p90", "V120_p95", "V10_media", "rafaga10_media", "rafaga10_p95", "alfa_mediana"])
    escribir_csv(TABLAS / f"{clave}_diurno.csv",
                 [[h, d["diurno"]["ws120"][h]["media"], d["diurno"]["ws120"][h]["p90"], d["diurno"]["ws10"][h]["media"],
                   d["diurno"]["rafaga10"][h]["media"], d["diurno"]["rafaga10"][h]["p95"], d["diurno"]["alpha"][h]["p50"]] for h in range(24)],
                 ["hora_local", "V120_media", "V120_p90", "V10_media", "rafaga10_media", "rafaga10_p95", "alfa_mediana"])
    escribir_csv(TABLAS / f"{clave}_rosa_120m.csv",
                 [[SECT[i], r["sector_deg"], r["frecuencia"], r["media"], r["p90"], *r["porClase"]] for i, r in enumerate(d["rosa"])],
                 ["sector", "direccion_deg", "frecuencia", "V120_media", "V120_p90", *[f"horas_{c_}ms" for c_ in CLASES]])
    escribir_csv(TABLAS / f"{clave}_excedencia.csv",
                 [[a["umbral"], a["fraccion"], b["fraccion"], e["fraccion"]] for a, b, e in
                  zip(d["excedencia_ws120"], d["excedencia_ws120_diurno"], d["excedencia_rafaga10"])],
                 ["umbral_ms", "frac_horas_V120_mayor", "frac_horas_diurnas_V120_mayor", "frac_horas_rafaga10_mayor"])

    # ---- figura panel
    col = S["color"]
    fig = plt.figure(figsize=(10, 7.4))
    fig.suptitle(f"Viento en {S['nombre']} — ERA5 2016–2025, 120 m sobre el terreno", fontsize=11, fontweight="bold", x=0.02, ha="left")
    ax = fig.add_subplot(2, 2, 1)
    h = np.array(d["hist_ws120_05"], float)
    x = np.arange(len(h)) * 0.5
    ax.bar(x + 0.25, h / h.sum() / 0.5, width=0.45, color=col, alpha=0.85, linewidth=0)
    xx = np.linspace(0.01, 30, 300)
    ax.plot(xx, (k / c) * (xx / c) ** (k - 1) * np.exp(-(xx / c) ** k), color="#3d3d3a", lw=1.5)
    ax.text(c * 1.25, max(h / h.sum() / 0.5) * 0.9, f"Weibull k={k:.2f}, c={c:.1f} m/s", fontsize=8, color="#3d3d3a")
    ax.axvline(V_CRUCERO_ACTUAL, color="#3d3d3a", ls=":", lw=1)
    ax.text(V_CRUCERO_ACTUAL + 0.3, ax.get_ylim()[1] * 0.55, "crucero actual\n16,7 m/s", fontsize=7.5, color="#3d3d3a")
    ax.set(xlim=(0, 30), xlabel="Velocidad a 120 m [m/s]", ylabel="Densidad de probabilidad", title="Distribución de velocidades")

    ax = fig.add_subplot(2, 2, 2, projection="polar")
    ax.set_theta_zero_location("N"); ax.set_theta_direction(-1)
    th = np.radians([r["sector_deg"] for r in d["rosa"]])
    tot = sum(sum(r["porClase"]) for r in d["rosa"])
    base = np.zeros(16)
    for ci in range(6):
        v = np.array([r["porClase"][ci] for r in d["rosa"]]) / tot * 100
        ax.bar(th, v, width=np.radians(20), bottom=base, color=RAMPA[ci], edgecolor="white", linewidth=0.5, label=f"{CLASES[ci]} m/s")
        base += v
    ax.set_xticks(np.radians(np.arange(0, 360, 45))); ax.set_xticklabels(["N", "NE", "E", "SE", "S", "SO", "O", "NO"])
    ax.set_title("Rosa de vientos (% de horas, de dónde viene)", pad=14)
    ax.legend(loc="upper left", bbox_to_anchor=(1.05, 1.0), fontsize=7, frameon=False, title="120 m", title_fontsize=7)
    ax.tick_params(labelsize=7)

    ax = fig.add_subplot(2, 2, 3)
    mm = np.arange(12)
    ax.plot(mm, [m["media"] for m in d["mensual"]["ws120"]], color=col, lw=2, marker="o", ms=4)
    ax.plot(mm, [m["p90"] for m in d["mensual"]["ws120"]], color=col, lw=2, ls="--", marker="o", ms=4, mfc="white")
    ax.text(11.2, d["mensual"]["ws120"][11]["media"], " media", va="center", fontsize=8)
    ax.text(11.2, d["mensual"]["ws120"][11]["p90"], " p90", va="center", fontsize=8)
    ax.set_xticks(mm); ax.set_xticklabels(MESES, fontsize=7.5)
    ax.set(ylabel="m/s", title="Ciclo anual (120 m)", ylim=(0, None), xlim=(-0.5, 12.5))

    ax = fig.add_subplot(2, 2, 4)
    hh = np.arange(24)
    ax.plot(hh, [m["media"] for m in d["diurno"]["ws120"]], color=col, lw=2)
    ax.plot(hh, [m["p90"] for m in d["diurno"]["ws120"]], color=col, lw=2, ls="--")
    ax.plot(hh, [m["media"] for m in d["diurno"]["rafaga10"]], color="#8a8a85", lw=1.5)
    ax.text(23.3, d["diurno"]["ws120"][23]["media"], " media 120 m", va="center", fontsize=7.5)
    ax.text(23.3, d["diurno"]["ws120"][23]["p90"], " p90 120 m", va="center", fontsize=7.5)
    rmax = max(m["media"] for m in d["diurno"]["rafaga10"]); hmax = int(np.argmax([m["media"] for m in d["diurno"]["rafaga10"]]))
    ax.text(hmax, rmax + 0.5, "ráfaga media a 10 m", ha="center", fontsize=7.5, color="#5f5e5a")
    ax.set(xlabel="Hora local", ylabel="m/s", title="Ciclo diario", ylim=(0, None), xlim=(0, 28))
    ax.set_xticks(range(0, 24, 3))
    fig.text(0.02, 0.01, "Fuente: ERA5 (Copernicus C3S/ECMWF) vía Open-Meteo; 120 m extrapolado desde 100 m con el exponente alfa horario.", fontsize=7, color="#5f5e5a")
    fig.tight_layout(rect=(0, 0.02, 1, 0.96))
    fig.savefig(FIGS / f"{clave}_panel.png")
    plt.close(fig)

escribir_csv(TABLAS / "operabilidad.csv", resumen_op,
             ["sitio", "serie", "V_crucero_ms", "V_crucero_kmh", "pct_horas_diurnas_sin_avance_contra_viento",
              "pct_horas_diurnas_ida_vuelta_menor_1.5x", "factor_tiempo_ida_vuelta_medio"])

# ---- figura comparativa: excedencia diurna y operabilidad
fig, axs = plt.subplots(1, 2, figsize=(10, 3.9))
ax = axs[0]
for clave, S in SITIOS.items():
    h = np.array(R[clave]["hist_ws120_diurno_05"], float)
    W = (np.arange(len(h)) + 1) * 0.5
    exc = 1 - np.cumsum(h) / h.sum()
    ax.plot(W, exc * 100, color=S["color"], lw=2)
    i = np.searchsorted(W, 12)
    ax.text(W[i] + 0.4, exc[i] * 100 + 2, S["nombre"].split(" (")[0], color="#3d3d3a", fontsize=8)
ax.axvline(V_CRUCERO_ACTUAL, color="#3d3d3a", ls=":", lw=1)
ax.text(V_CRUCERO_ACTUAL + 0.3, 80, "crucero\nactual", fontsize=7.5)
ax.set(xlim=(0, 25), ylim=(0, 100), xlabel="Velocidad del viento a 120 m [m/s]", ylabel="% de horas diurnas (08–19 h) que se supera",
       title="¿Cuánto tiempo sopla más que X?")
ax = axs[1]
Vs = np.linspace(12, 30, 37)
for clave, S in SITIOS.items():
    ok = [operabilidad(R[clave]["hist_ws120_diurno_05"], v)[1] * 100 for v in Vs]
    okc = [operabilidad(R[clave]["hist_ws120_diurno_05"], v, S["factor_cola"])[1] * 100 for v in Vs]
    ax.plot(Vs, ok, color=S["color"], lw=2)
    ax.plot(Vs, okc, color=S["color"], lw=1.2, ls="--")
    if clave == "canadon_leon":
        ax.text(Vs[-1] - 0.3, okc[-1] - 7, S["nombre"].split(" (")[0], fontsize=8, color="#3d3d3a", ha="right")
    else:
        ax.text(12.4, 91, S["nombre"].split(" (")[0], fontsize=8, color="#3d3d3a")
ax.axvline(V_CRUCERO_ACTUAL, color="#3d3d3a", ls=":", lw=1)
ax.set(xlim=(12, 30), ylim=(0, 100), xlabel="Velocidad de crucero [m/s]",
       ylabel="% de horas diurnas operables",
       title="Operabilidad: ida y vuelta ≤ 1,5× el tiempo sin viento")
fig.text(0.02, 0.01, "Operabilidad: peor caso, viento alineado con la ruta. Línea llena: ERA5; punteada: ERA5 con corrección de cola (validación contra estaciones).", fontsize=7, color="#5f5e5a")
fig.tight_layout(rect=(0, 0.04, 1, 1))
fig.savefig(FIGS / "comparacion_sitios_operabilidad.png")
plt.close(fig)

# ---- figura validación
fig, axs = plt.subplots(1, 2, figsize=(10, 3.6), sharey=True)
for ax, (nom, c_) in zip(axs, (("Comodoro Rivadavia Aero", "#2a78d6"), ("Neuquen Aero", "#eb6834"))):
    v = VAL[nom]
    ps = ["media", "p50", "p90", "p95", "p99"]
    xo = np.arange(len(ps))
    ax.bar(xo - 0.2, [v["obs"][p] for p in ps], 0.38, color="#3d3d3a", label="Estación (obs.)")
    ax.bar(xo + 0.2, [v["era5_mismas_horas"][p] for p in ps], 0.38, color=c_, label="ERA5 misma celda")
    ax.set_xticks(xo); ax.set_xticklabels(ps)
    ax.set_title(f"{nom.replace('Neuquen', 'Neuquén')} — r = {v['correlacion']}")
    ax.set_ylabel("Viento a 10 m [m/s]")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
fig.suptitle("Validación de ERA5 contra estaciones (2021–2025, mismas horas)", fontsize=10, fontweight="bold", x=0.02, ha="left")
fig.tight_layout()
fig.savefig(FIGS / "validacion_era5_estaciones.png")
plt.close(fig)

for fila in resumen_op:
    print(fila)
print("listo")
