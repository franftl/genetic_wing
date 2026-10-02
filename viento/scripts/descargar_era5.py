"""
Descarga la serie horaria ERA5 de cada sitio (Open-Meteo, sin API key) y la
guarda en datos_crudos/<sitio>_era5_horario.csv. Después recalcula el resumen
estadístico datos/<sitio>_era5_resumen.json con la MISMA lógica que se usó
para generar las fichas, así cualquiera del grupo puede reproducirlas.

Uso (desde la carpeta scripts/):
    python descargar_era5.py            # descarga + resumen
    python procesar_viento.py           # regenera fichas, tablas y figuras

Requiere: requests, numpy.  (pip install requests numpy)
Para cambiar de sitio o período, editar SITIOS / PERIODO.
Open-Meteo limita las consultas por minuto: el script espera entre sitios.
"""
import csv
import json
import math
import time
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent.parent
CRUDOS = BASE / "datos_crudos"
DATOS = BASE / "datos"

PERIODO = ("2016-01-01", "2025-12-31")
SITIOS = {
    "canadon_leon": (-46.56, -67.62),
    "puesto_hernandez": (-37.27, -69.08),
}
VARS = ["wind_speed_10m", "wind_speed_100m", "wind_gusts_10m", "wind_direction_10m",
        "wind_direction_100m", "temperature_2m", "surface_pressure"]


def url(lat, lon, ini, fin):
    return ("https://archive-api.open-meteo.com/v1/archive"
            f"?latitude={lat}&longitude={lon}&start_date={ini}&end_date={fin}"
            f"&hourly={','.join(VARS)}&wind_speed_unit=ms&models=era5"
            "&timezone=America%2FArgentina%2FBuenos_Aires")


def pct(s, p):
    i = (len(s) - 1) * p / 100
    lo, hi = math.floor(i), math.ceil(i)
    return s[lo] + (s[hi] - s[lo]) * (i - lo)


def r3(x):
    return round(float(x), 3)


def stats(a):
    v = np.array([x for x in a if x is not None and not (isinstance(x, float) and math.isnan(x))], float)
    s = np.sort(v)
    return dict(n=len(v), media=r3(v.mean()), desvio=r3(v.std(ddof=1)), p05=r3(pct(s, 5)), p25=r3(pct(s, 25)),
                p50=r3(pct(s, 50)), p75=r3(pct(s, 75)), p90=r3(pct(s, 90)), p95=r3(pct(s, 95)), p99=r3(pct(s, 99)),
                p999=r3(pct(s, 99.9)), max=r3(s[-1]), min=r3(s[0]))


def lite(v):
    if not v:
        return dict(media=None, p50=None, p90=None, p95=None, max=None, n=0)
    s = np.sort(np.array(v, float))
    return dict(media=r3(s.mean()), p50=r3(pct(s, 50)), p90=r3(pct(s, 90)), p95=r3(pct(s, 95)), max=r3(s[-1]), n=len(s))


def analizar(H):
    """Misma lógica que el análisis original (validado contra una muestra)."""
    n = len(H["time"])
    ws10, ws100, g10 = H["wind_speed_10m"], H["wind_speed_100m"], H["wind_gusts_10m"]
    d100, T, P = H["wind_direction_100m"], H["temperature_2m"], H["surface_pressure"]
    missing = sum(1 for i in range(n) if ws10[i] is None or ws100[i] is None or g10[i] is None)
    LN = math.log(10)
    alpha, alpha_all = [], [None] * n
    for i in range(n):
        if ws10[i] is not None and ws100[i] is not None and ws10[i] >= 3 and ws100[i] > 0:
            a = math.log(ws100[i] / ws10[i]) / LN
            alpha.append(a); alpha_all[i] = a
    alpha_med = pct(sorted(alpha), 50)
    ws120 = []
    for i in range(n):
        a = alpha_all[i] if alpha_all[i] is not None else alpha_med
        a = min(max(a, -0.1), 0.6)
        ws120.append(None if ws100[i] is None else ws100[i] * 1.2 ** a)
    gf = [g10[i] / ws10[i] for i in range(n) if ws10[i] is not None and ws10[i] >= 3 and g10[i] is not None]
    rho = [P[i] * 100 / (287.05 * (T[i] + 273.15)) for i in range(n) if T[i] is not None and P[i] is not None]
    hr = [int(t[11:13]) for t in H["time"]]
    mo = [int(t[5:7]) for t in H["time"]]
    yr = [int(t[0:4]) for t in H["time"]]
    years = sorted(set(yr))

    def by(keys, keyarr, arr):
        return [lite([arr[i] for i in range(n) if keyarr[i] == k and arr[i] is not None]) for k in keys]

    horas, meses = list(range(24)), list(range(1, 13))
    ws_dia = [ws120[i] for i in range(n) if 8 <= hr[i] <= 19 and ws120[i] is not None]
    g_dia = [g10[i] for i in range(n) if 8 <= hr[i] <= 19 and g10[i] is not None]

    def hist(arr, w, nb):
        h = [0] * nb
        for x in arr:
            if x is None:
                continue
            h[min(int(x // w), nb - 1)] += 1
        return h

    clases = [0, 4, 8, 12, 16, 20, 1e9]
    rosa = [dict(n=0, suma=0.0, porClase=[0] * 6, vals=[]) for _ in range(16)]
    for i in range(n):
        if d100[i] is None or ws120[i] is None:
            continue
        s = int(((d100[i] + 11.25) % 360) // 22.5)
        R = rosa[s]; R["n"] += 1; R["suma"] += ws120[i]; R["vals"].append(ws120[i])
        c = 0
        while ws120[i] >= clases[c + 1]:
            c += 1
        R["porClase"][c] += 1
    tot = sum(R["n"] for R in rosa)
    rosa_out = [dict(sector_deg=k * 22.5, frecuencia=r3(R["n"] / tot), media=r3(R["suma"] / R["n"]) if R["n"] else None,
                     p90=r3(pct(sorted(R["vals"]), 90)) if R["n"] else None, porClase=R["porClase"]) for k, R in enumerate(rosa)]
    umbrales = [3, 5, 8, 10, 12, 14, 15, 16.7, 18, 20, 25]

    def exc(a):
        v = [x for x in a if x is not None]
        return [dict(umbral=u, fraccion=r3(sum(1 for x in v if x > u) / len(v))) for u in umbrales]

    return dict(
        horas=n, horas_faltantes=missing,
        ws10=stats(ws10), ws100=stats(ws100), ws120=stats(ws120), rafaga10=stats(g10),
        ws120_diurno_08_19=stats(ws_dia), rafaga10_diurno_08_19=stats(g_dia),
        alpha={**stats(alpha), "nota": "horas con ws10>=3 m/s"},
        alpha_de_medias=r3(math.log(sum(x or 0 for x in ws100) / sum(x or 0 for x in ws10)) / LN),
        factor_rafaga=stats(gf), densidad=stats(rho), temperatura=stats(T), presion_sup=stats(P),
        excedencia_ws120=exc(ws120), excedencia_ws120_diurno=exc(ws_dia), excedencia_rafaga10=exc(g10),
        mensual=dict(ws10=by(meses, mo, ws10), ws120=by(meses, mo, ws120), rafaga10=by(meses, mo, g10)),
        diurno=dict(ws10=by(horas, hr, ws10), ws120=by(horas, hr, ws120), rafaga10=by(horas, hr, g10),
                    alpha=by(horas, hr, alpha_all)),
        alphaMes=by(meses, mo, alpha_all),
        anual=dict(ws120=by(years, yr, ws120), rafaga10=by(years, yr, g10)), years=years,
        hist_ws120_05=hist(ws120, 0.5, 90), hist_ws120_diurno_05=hist(ws_dia, 0.5, 90),
        hist_ws10_05=hist(ws10, 0.5, 90), hist_rafaga10_05=hist(g10, 0.5, 110), rosa=rosa_out,
    )


def main():
    import requests
    CRUDOS.mkdir(exist_ok=True)
    DATOS.mkdir(exist_ok=True)
    for k, (sitio, (lat, lon)) in enumerate(SITIOS.items()):
        if k:
            time.sleep(65)  # límite por minuto de Open-Meteo
        u = url(lat, lon, *PERIODO)
        print(f"Descargando {sitio} ...")
        j = requests.get(u, timeout=300).json()
        if j.get("error"):
            raise RuntimeError(j.get("reason"))
        H = j["hourly"]
        with open(CRUDOS / f"{sitio}_era5_horario.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["hora_local"] + VARS)
            for i, t in enumerate(H["time"]):
                w.writerow([t] + [H[v][i] for v in VARS])
        res = dict(fuente="ERA5 via Open-Meteo archive API", url=u, lat_pedida=lat, lon_pedida=lon,
                   lat_grilla=j["latitude"], lon_grilla=j["longitude"], elevacion_modelo_m=j["elevation"],
                   periodo=list(PERIODO), **analizar(H))
        (DATOS / f"{sitio}_era5_resumen.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        print(f"  {len(H['time'])} horas -> datos_crudos/{sitio}_era5_horario.csv")


if __name__ == "__main__":
    main()
