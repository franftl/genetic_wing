"""Genera Optimizador_<VERSION>.ipynb (la version sale de optimizacion_avion/__init__.py). Se versiona este script además del
.ipynb para poder regenerar el notebook limpio (sin outputs viejos) cuando
haga falta, y para que el contenido de las celdas tenga historial de cambios
legible en git (un .ipynb no lo tiene)."""
import json
import re
from pathlib import Path

# Una sola fuente de verdad: VERSION en optimizacion_avion/__init__.py.
VERSION = re.search(r'^VERSION\s*=\s*"([^"]+)"',
                    (Path(__file__).parent / "optimizacion_avion" / "__init__.py").read_text(encoding="utf-8"),
                    re.M).group(1)

cells = []


def _lineas(texto):
    """nbformat exige que cada elemento de `source` termine en \\n (salvo el
    ultimo). Sin eso Jupyter concatena todo en una sola linea y el codigo ni
    siquiera parsea."""
    return texto.strip("\n").splitlines(keepends=True)


def md(texto):
    cells.append({"cell_type": "markdown", "metadata": {}, "source": _lineas(texto.replace("@@VERSION@@", VERSION))})


def code(texto):
    cells.append({"cell_type": "code", "execution_count": None, "metadata": {},
                  "outputs": [], "source": _lineas(texto)})


# ---------------------------------------------------------------- 0
md(r"""
# UAV FP — Optimizador @@VERSION@@: competencia entre topologías de avión de ala fija

> **Versión @@VERSION@@.** Cambios sobre esta versión: `@@VERSION@@.1`, `@@VERSION@@.2`… Si se agrega o modifica un módulo, pasa a la versión siguiente. Ver `VERSIONES.md`.

Hermano de **`01_Optimizacion_Ala.ipynb`**. Aquel optimiza **una sola** topología (el ala volante); este hace **competir cinco topologías de avión completo** bajo la **misma misión**, para responder una pregunta que el notebook 01 no puede: *¿es el ala volante la mejor configuración para esta misión, o lo era solamente porque era la única que estábamos evaluando?*

La lógica estable vive en **`optimizacion_avion/`**; este notebook es el panel de control.

## La misión tiene DOS puntos de vuelo

> **crucero a 120 km/h** con 3 kg de carga útil, **y además poder volar a 10 m/s** (36 km/h) para reconocimiento, despegue y aterrizaje.

Eso es una relación de velocidades de **3.33 : 1**, o sea un **factor 11 en coeficiente de sustentación**. Los dos puntos entran juntos a la función objetivo, y no es un capricho: piden alas **opuestas**. Con el peso de este avión (~72 N):

| optimizando… | superficie de ala que pide | cuerda media |
|---|---|---|
| solo crucero a 120 km/h | 0.21 – 0.35 m² | 10 – 16 cm |
| poder volar a 10 m/s | 0.77 – 1.63 m² | 35 – 74 cm |

Un factor 2 a 8 en superficie. Si se cambiara la velocidad **sin** meter el vuelo lento, el optimizador convergería a un ala de cuerda mínima que no puede cumplir la misión — un óptimo perfectamente válido del problema equivocado.

Para calibrar cuán exigente es: el **RQ-7B Shadow** tiene máxima/crucero = 1.54:1 y el **Bayraktar TB2**, 1.71:1 — y despegan de pista o catapulta, no en vuelo lento sostenido. Nuestro 3.33:1 es ambicioso, aunque el déficit real de CL es chico.

## Las cinco topologías

| topología | descripción | referencia real |
|---|---|---|
| `convencional` | fuselaje + cola cruciforme | baseline estándar de diseño |
| `t_tail` | fuselaje + cola en T | planeadores; horizontal fuera del downwash |
| `v_tail` | fuselaje + cola en V | familia MQ-1 Predator |
| `doble_boom` | dos vigas + doble deriva | familia RQ-7 Shadow / ScanEagle |
| `pod_boom` | fuselaje continuo: diámetro casi constante, afinado solo cerca de la cola (sin góndola ni viga fina) | fuselaje tubular de largo alcance |

**Un resultado teórico que conviene tener a la vista al leer los resultados:** McGeer & Kroo ([J. Aircraft 20(11), 1983](https://ntrs.nasa.gov/citations/19840028263)) muestran que a envergadura dada, y con las restricciones de trimado y estabilidad puestas, la configuración convencional con cola trasera está **muy cerca del óptimo**, y ni el canard ni el tándem la superan salvo casos marginales. O sea: no hay que esperar que una topología exótica gane por goleada. Lo que separa a los candidatos es resistencia parásita, peso estructural y CL_max. Por eso **no** se incluyeron canard ni box-wing: el canard limita el CL_max del ala principal justo cuando es el recurso más escaso, y el box-wing necesita una separación vertical que a 7 kg de construcción artesanal no paga.

## Qué cambió respecto de la versión anterior de este notebook

1. **Parametrización mucho más fina:** ala de 5 estaciones (cuerda, borde de ataque, torsión y diedro estación por estación) **con winglets**, **envergadura variable** (2.0–3.5 m), y fuselaje con morro de forma libre y boat-tail en vez del cono truncado que había. De ~20 a **46–51 parámetros** según la topología.
2. **Incidencia de cola.** Antes iba con `twist = 0` fijo, y eso no era una simplificación sino un error: sin incidencia el avión no tiene con qué trimarse, y el desvío de trim llegaba al 113%. Ahora los candidatos salen con **Cm de crucero = 0.0000**.
3. **Flaps**, modelados deflectando la geometría del perfil y evaluándola con NeuralFoil al Reynolds real del vuelo lento — no con un ΔCL de tabla (ver sección 9).
4. **CL_max a su propio Reynolds.** Antes se estimaba al Re de crucero y se usaba para todo; el CL_max cae ~6% (hasta 11%) al pasar de Re 6.7e5 a 2e5, justo donde el diseño está más apretado.
5. **Catálogo de 19 perfiles** (los 12 del ala volante con los mismos índices, más 7 de alta sustentación).

## Cómo correrlo

Secciones **1 y 2** para configurar y sembrar; después **3** (una generación por vez) o **4** (automático). Las secciones **5 a 11** analizan el resultado. Costo: ~0.8 s por candidato evaluado; una corrida completa de las cinco topologías está en el orden de **25–45 min**.
""")

# ---------------------------------------------------------------- 1
code(r"""
# Autorecarga: si se editan los .py del paquete mientras el notebook esta
# abierto, Jupyter NO los recarga solo. Estas dos lineas hacen que cada celda
# use la version actual del disco. (Si aparece un AttributeError del tipo
# "module has no attribute ...", es exactamente eso: reinicia el kernel.)
%load_ext autoreload
%autoreload 2

import sys
from pathlib import Path

# optimizacion_avion IMPORTA de optimizacion_ala (perfiles, propiedades de
# material, criterio de parada), asi que los dos paquetes tienen que estar
# al lado de este notebook.
sys.path.insert(0, str(Path.cwd()))

import optimizacion_avion as av
import optimizacion_avion.mision_avion as mis
import optimizacion_avion.geometria_avion as geo

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import json
import time

print(f"Optimizador {av.VERSION}")
print("Topologias en competencia:")
for nombre, info in av.TOPOLOGIAS.items():
    n_par = len(av.BOUNDS_POR_TOPOLOGIA[nombre])
    lo, hi = info["sm_band"]
    print(f"  {nombre:<14} {n_par:2d} parametros   banda SM [{100*lo:.0f}%, {100*hi:.0f}%]")
    print(f"  {'':<14} {info['nombre']}")
    print(f"  {'':<14} ref: {info['referencia_real']}")
""")

# ---------------------------------------------------------------- 1b
md(r"""
## 0. Interruptores de la rama `bateria-350km`

Todo lo que se puede querer mover está en esta celda; hay que correrla **antes** de la sección 1.

| Interruptor | Qué hace |
|---|---|
| `VIENTO` | `True`: la misión se evalúa con el aire y la ráfaga reales de los sitios (lo de imarzeniuk, `viento.py`). `False`: aire estándar y ráfaga de 3 m/s. |
| `BATERIA` | `True`: la batería se dimensiona para el `ALCANCE_KM` a velocidad de crucero **todo el vuelo**, y su masa entra al peso del avión (`bateria.py`). `False`: vuelve el modelo viejo, con la batería dentro de `MASA_SISTEMAS = 1.5 kg`. |
| `CORRIDA_RAPIDA` | `True`: 4 generaciones de paciencia, máximo 12, y solo v_tail y pod_boom (~15 min por topología). `False`: la competencia completa (10 / 60 / cinco topologías) y puede tardar **horas**, porque con batería cada candidato cuesta el doble. |

Los supuestos de la batería (eficiencia propulsiva, reserva, celda, aviónica) son los de abajo; **ninguno está medido**, en particular `ETA_PROPULSIVA_TOTAL`.
""")

code(r"""
import optimizacion_avion.bateria as bat

# ------------------------------ INTERRUPTORES ------------------------------
VIENTO = True            # lo de imarzeniuk (viento de los sitios)
BATERIA = True           # bateria dimensionada por alcance
CORRIDA_RAPIDA = True    # False = competencia completa (horas)

# ------------------- SUPUESTOS DE LA BATERIA (bateria.py) -------------------
bat.ALCANCE_KM = 350.0               # [km] a velocidad de crucero constante
bat.ETA_PROPULSIVA_TOTAL = 0.65      # helice x motor x ESC en crucero (SUPUESTO)
bat.POTENCIA_AVIONICA_W = 10.0       # [W] autopiloto + telemetria + camara
bat.RESERVA_ENERGIA = 0.20           # [-] sobre la energia de crucero
bat.CELDA_POR_DEFECTO = "molicel_m65a"   # molicel_m65a | lg_m58t | samsung_50g | molicel_p42a
bat.CELDAS_EN_SERIE = 12             # 12S (solo informativo: la masa sale de la energia)

# ------------------- PENALIZACION DE ENVERGADURA (fabricacion) -------------------
mis.ENVERGADURA_MANUFACTURA_MAX = 2.0   # [m] por encima de esto se penaliza
mis.ENVERGADURA_MANUFACTURA_TOL = 0.4   # [m] ancho de la caida gaussiana
mis.PESO_ENVERGADURA = 0.3

# ------------------------------ APLICAR ------------------------------
mis.VIENTO_ACTIVO = VIENTO
mis.BATERIA_ACTIVA = BATERIA

# ---- Semillas validas para el escenario elegido ----
# Las de semillas.json (7 kg, 8.2 L) quedan INVALIDAS con batería (~12 kg, ~2 L mas de
# fuselaje) y con el aire liviano del sitio. Se necesitan DOS por topologia: el cruce
# BLX entre dos padres iguales no explora nada.
RAIZ = Path.cwd()
if BATERIA:
    _crudas = json.load(open(RAIZ / "evaluacion_bateria_350km" / "semillas_bateria.json"))
elif VIENTO:
    _gv = json.load(open(RAIZ / "optimizacion_avion" / "ganadores_viento.json"))
    _gs = json.load(open(RAIZ / "optimizacion_avion" / "ganadores.json"))
    _crudas = {t: [_gv[t]["params"], _gs[t]["params"]] for t in av.TOPOLOGIAS}
else:
    _crudas = None      # se usan las de semillas.json tal cual
if _crudas is not None:
    av.SEEDS_POR_TOPOLOGIA.update(
        {t: [geo.clamp_to_bounds_avion(p, t) for p in ps] for t, ps in _crudas.items()})

print(f"VIENTO_ACTIVO = {mis.VIENTO_ACTIVO}   BATERIA_ACTIVA = {mis.BATERIA_ACTIVA}   "
      f"CORRIDA_RAPIDA = {CORRIDA_RAPIDA}")
if mis.BATERIA_ACTIVA:
    print(f"Bateria: {bat.ALCANCE_KM:.0f} km a {3.6*mis.V_CRUCERO:.0f} km/h, eta {bat.ETA_PROPULSIVA_TOTAL:.2f}, "
          f"reserva {100*bat.RESERVA_ENERGIA:.0f}%, celda {bat.CELDA_POR_DEFECTO} "
          f"({bat.energia_especifica_pack():.0f} Wh/kg a nivel pack)")
print(f"Envergadura: penalizada por encima de {mis.ENVERGADURA_MANUFACTURA_MAX:.1f} m "
      f"(tol {mis.ENVERGADURA_MANUFACTURA_TOL:.1f} m, peso {mis.PESO_ENVERGADURA})")
for t in av.TOPOLOGIAS:
    print(f"  semillas {t:<14}: {len(av.SEEDS_POR_TOPOLOGIA[t])}")
""")

# ---------------------------------------------------------------- 2
md(r"""
## 1. Configuración: la misión y el criterio de parada

El **score** son nueve términos pesados y normalizados:

$$\text{score} = 1.0\,f_{ef} + 0.3\,f_{masa} + 1.5\,f_{estab} + 0.4\,f_{ráfaga} + 0.4\,f_{margen} + 0.3\,f_{trim} + 0.3\,f_{direcc} + 0.3\,f_{lat} + 1.0\,f_{lento}$$

El último es nuevo y pesa como la estabilidad, porque el vuelo lento es un **requisito de misión**, no un lujo. Por debajo de 10 m/s el candidato ya se descarta por restricción dura; el término premia el margen **por encima** de eso, para que el optimizador no se quede pegado al borde de la restricción.

**Restricciones duras** (descartan el candidato, no le bajan el puntaje): que la estructura no cierre, que no se sostenga a 120 km/h, **que no pueda volar a 10 m/s ni con el flap abajo**, margen estático negativo, $C_{n\beta} \le 0$, $C_{l\beta} \ge 0$, o que la ráfaga de diseño lo ponga en pérdida en crucero.

> Un cambio menor pero que importa: el término de **trim** ahora se mide sobre el $C_m$ **en crucero**, no sobre $|CL_{trim} - CL_{crucero}|/CL_{crucero}$ como antes. A 120 km/h el CL de crucero es ~0.1, así que dividir por él convertía diferencias chicas en desvíos enormes y el término se saturaba en cero para todos los candidatos, sin discriminar entre ellos.
""")

code(r"""
# --- Criterio de parada ---
# Subidos respecto de la version anterior (8/40): el espacio de diseno paso
# de ~20 parametros por topologia a 46-51, y con mas dimensiones el GA
# necesita mas generaciones para explotar una direccion buena antes de que
# la racha sin mejora lo corte.
# CORRIDA_RAPIDA (seccion 0): 4 / 12 y solo v_tail + pod_boom; si no, 10 / 60 y las cinco.
if CORRIDA_RAPIDA:
    PACIENCIA, MAX_GENERACIONES = 4, 12
    TOPOLOGIAS_A_CORRER = ["v_tail", "pod_boom"]
else:
    PACIENCIA, MAX_GENERACIONES = 10, 60
    TOPOLOGIAS_A_CORRER = list(av.TOPOLOGIAS.keys())

# --- Cuantos hijos por generacion, por topologia ---
N_CROSSBRED, N_WILDCARD = 7, 3

print("MISION -- DOS PUNTOS DE VUELO")
print(f"  crucero ............... {3.6*mis.V_CRUCERO:.0f} km/h ({mis.V_CRUCERO:.2f} m/s)")
print(f"  vuelo lento ........... {mis.V_LENTO:.0f} m/s ({3.6*mis.V_LENTO:.0f} km/h)")
print(f"  relacion de velocidades {mis.V_CRUCERO/mis.V_LENTO:.2f} : 1"
      f"   -> factor {(mis.V_CRUCERO/mis.V_LENTO)**2:.1f} en CL")
print(f"  margen sobre perdida .. {mis.MARGEN_SOBRE_PERDIDA:.2f}"
      f"  -> v_stall objetivo <= {mis.V_STALL_OBJETIVO:.2f} m/s")
print(f"  carga util ............ {mis.MASA_PAYLOAD:.1f} kg")
print(f"  rafaga vertical ....... {mis._rafaga_vertical():.2f} m/s (en crucero)")
print()
print("PESOS DEL SCORE")
print(f"  eficiencia {mis.PESO_EFICIENCIA} | masa {mis.PESO_MASA} | estabilidad {mis.PESO_ESTABILIDAD}"
      f" | rafaga {mis.PESO_RAFAGA} | margen {mis.PESO_MARGEN}")
print(f"  trim {mis.PESO_TRIM} | direccional {mis.PESO_DIRECCIONAL} | lateral {mis.PESO_LATERAL}"
      f" | VUELO LENTO {mis.PESO_LENTO}")
print()
print(f"Envergadura: VARIABLE en [{av.BOUNDS_ALA['envergadura'][0]:.1f}, "
      f"{av.BOUNDS_ALA['envergadura'][1]:.1f}] m  (antes estaba fija en 2.2 m)")
print(f"Parar tras {PACIENCIA} generaciones sin mejora, o al llegar a {MAX_GENERACIONES}.")
""")

# ---------------------------------------------------------------- 3
md(r"""
## 2. Población semilla

Las semillas viven en `optimizacion_avion/semillas.json` y las genera `gen_semillas.py`, que también está en el paquete para que el proceso sea reproducible y no un número mágico. El procedimiento: se define a mano una base de ala, fuselaje y flap (con criterio de diseño, sin pretensión de optimalidad) y después se **afinan numéricamente por bisección** solo dos parámetros — `cg_frac_mac` hasta que el margen estático caiga en el medio de la banda, y la **incidencia del estabilizador** hasta que el $C_m$ de crucero sea ~0, o sea hasta que el avión quede trimado sin elevador. El resto es trabajo del GA.

Hay **dos semillas por topología**, a propósito en lados opuestos del compromiso central de esta misión:

- **A**: ala grande (b ≈ 3.1 m, S ≈ 1.02 m²) con perfiles de **alta sustentación** (fx63137 / naca6412). Vuela lento con holgura, pero en crucero anda por L/D ≈ 7.3.
- **B**: ala más chica (b ≈ 2.85 m, S ≈ 0.82 m²) con camber **moderado** (naca6412 / naca4412) y un flap que sí rinde. **L/D ≈ 10.4** — bastante mejor — y todavía vuela a 10 m/s.

Que la B le gane a la A en L/D por ~40% ya dice algo antes de optimizar: a 120 km/h el ala grande se paga caro y el perfil de alta sustentación no es gratis. Esa es la pelea que el GA tiene que resolver.

Sembrar variado no es cosmético: BLX-alfa entre dos padres con el **mismo** valor en una dimensión devuelve siempre ese valor, así que una dimensión donde las dos semillas coinciden queda sin explorar.
""")

code(r"""
# `estados` es el objeto central del notebook: un loop evolutivo
# independiente por topologia, todos con la misma funcion objetivo.
estados, filas = {}, []

for t in TOPOLOGIAS_A_CORRER:
    seeds = av.SEEDS_POR_TOPOLOGIA[t]

    def objetivo(params, _t=t):
        return av.evaluar_mision_avion(params, _t)

    estados[t] = av.iniciar_evolucion_avion(seeds, t, objetivo)

    for i, c in enumerate(estados[t].parents):
        a = av.analizar_mision_avion(c.params, t)
        if a is None:
            filas.append({"topologia": t, "semilla": i, "score": c.score}); continue
        filas.append({
            "topologia": t, "semilla": i, "score": c.score,
            "b_m": a["envergadura"], "S_m2": a["S"], "AR": a["AR"],
            "masa_kg": a["masa_total"], "L/D": a["LD_crucero"],
            "v_stall": a["v_stall"], "SM_%": 100*a["SM"],
            "Cm_cru": a["Cm_crucero"], "V_H": a["V_H"],
        })
    print(f"[{t}] {len(seeds)} semillas -> padres: {[round(c.score, 4) for c in estados[t].parents]}")

pd.DataFrame(filas).round(3)
""")

# ---------------------------------------------------------------- 4
md(r"""
## 3. Modo paso a paso — una generación de una topología

Para mirar de cerca qué está proponiendo el GA en una familia concreta. Cambiá `TOPOLOGIA_ACTIVA` y corré la celda tantas veces como quieras; el estado queda en `estados[TOPOLOGIA_ACTIVA]`, así que no se pierde nada al pasar de una topología a otra.
""")

code(r"""
TOPOLOGIA_ACTIVA = TOPOLOGIAS_A_CORRER[0]   # convencional | t_tail | v_tail | doble_boom | pod_boom (la que este en TOPOLOGIAS_A_CORRER)

_est = estados[TOPOLOGIA_ACTIVA]

def _objetivo(params, _t=TOPOLOGIA_ACTIVA):
    return av.evaluar_mision_avion(params, _t)

if av.deberia_parar(_est, paciencia=PACIENCIA, max_generaciones=MAX_GENERACIONES):
    print(f"[{TOPOLOGIA_ACTIVA}] Ya se cumplio el criterio de parada en la generacion "
          f"{_est.generation} (racha {_est.non_improving_streak}/{PACIENCIA}).")
else:
    _est, hijos = av.correr_generacion_avion(
        _est, av.generar_hijos_avion, _objetivo,
        n_crossbred=N_CROSSBRED, n_wildcard=N_WILDCARD)
    estados[TOPOLOGIA_ACTIVA] = _est

    print(f"=== [{TOPOLOGIA_ACTIVA}] Generacion {_est.generation} ===")
    print(f"Mejor score: {_est.mejor().score:.4f}   racha {_est.non_improving_streak}/{PACIENCIA}")

    # Solo unas pocas columnas: con ~50 parametros la tabla completa es
    # ilegible. El candidato entero esta en h["candidate"].params.
    cols = ["envergadura", "root_chord", "cg_frac_mac", "flap_defl_deg",
            "perfil_raiz", "perfil_punta", "fuselaje_largo"]
    tabla = pd.DataFrame([
        {"origin": h.get("origin", "?"), "score": h["candidate"].score,
         **{k: h["candidate"].params.get(k) for k in cols}}
        for h in hijos
    ]).sort_values("score", ascending=False)
    display(tabla.round(4))
""")

# ---------------------------------------------------------------- 5
md(r"""
## 4. Modo automático — la competencia completa

Corre **cada topología por separado** hasta su criterio de parada, continuando desde donde haya quedado la sección 3. Cada familia evoluciona en su propia subpoblación; no hay ningún intercambio entre ellas durante la corrida.

El equivalente en una línea, para correr **fuera** del notebook:

```python
resultados = av.correr_competencia(paciencia=10, max_generaciones=60)
print(av.tabla_resultados(resultados))
```

Esa función siembra de cero cada vez. La celda de abajo, en cambio, **continúa** los `estados` que ya tenés en memoria.
""")

code(r"""
_t0 = time.time()

for t in TOPOLOGIAS_A_CORRER:
    def _obj(params, _t=t):
        return av.evaluar_mision_avion(params, _t)

    est = estados[t]
    gen_inicial = est.generation

    if av.deberia_parar(est, paciencia=PACIENCIA, max_generaciones=MAX_GENERACIONES):
        print(f"[{t}] ya estaba detenido en la generacion {est.generation}. "
              f"Volve a correr la seccion 2 para empezar de cero.")
        continue

    print(f"\n{'='*68}\n[{t}] optimizando\n{'='*68}")
    while not av.deberia_parar(est, paciencia=PACIENCIA, max_generaciones=MAX_GENERACIONES):
        est, hijos = av.correr_generacion_avion(
            est, av.generar_hijos_avion, _obj,
            n_crossbred=N_CROSSBRED, n_wildcard=N_WILDCARD)
        marca = "  <-- mejoro" if est.non_improving_streak == 0 else ""
        print(f"  gen {est.generation:3d}   mejor score = {est.mejor().score:10.4f}   "
              f"racha {est.non_improving_streak}/{PACIENCIA}{marca}")

    estados[t] = est
    av.guardar_checkpoint(est, Path(f"checkpoint_avion_{t}.json"))
    motivo = (f"no mejoro en {PACIENCIA} generaciones seguidas"
              if est.non_improving_streak >= PACIENCIA else "se alcanzo MAX_GENERACIONES")
    print(f"  detenido en la generacion {est.generation} porque {motivo} "
          f"({est.generation - gen_inicial} generaciones en esta corrida).")

print(f"\nTiempo total: {time.time()-_t0:.0f} s")
print()
print(av.tabla_resultados(estados))
""")

# ---------------------------------------------------------------- 6
md(r"""
## 5. Convergencia comparada

Las cinco curvas en los mismos ejes. Es la forma más directa de ver **si la diferencia final entre topologías es real o es ruido**. Si terminan todas pegadas y oscilando, la competencia no está resolviendo nada y hace falta más paciencia o más hijos por generación — que es un resultado legítimo de reportar, y además es lo que predice McGeer & Kroo (ver la introducción).
""")

code(r"""
plt.figure(figsize=(8, 5))
for t, est in sorted(estados.items(), key=lambda kv: -kv[1].mejor().score):
    gens = [h["generation"] for h in est.historial]
    mejores = [max(h["parent_scores"]) for h in est.historial]
    plt.plot(gens, mejores, marker="o", markersize=3.5, label=f"{t}  (final {est.mejor().score:.3f})")

plt.xlabel("Generación")
plt.ylabel("Mejor score")
plt.title("Convergencia por topología — misma misión, mismos pesos")
plt.legend()
plt.grid(alpha=0.3)
plt.show()
""")

# ---------------------------------------------------------------- 7
md(r"""
## 6. Tabla comparativa de los ganadores

Una fila por topología, con las magnitudes que de verdad separan a los candidatos. Vale la pena mirar sobre todo tres cosas: la **superficie de ala** que eligió cada una (que es el compromiso central de esta misión), el **margen de vuelo lento**, y el **volumen de cola** $V_H$ — si alguna cayó muy fuera del rango de referencia (0.5–0.7), conviene revisar los bounds de esa topología antes de creerle el resultado.
""")

code(r"""
filas = []
for t, est in estados.items():
    a = av.analizar_mision_avion(est.mejor().params, t)
    if a is None:
        continue
    filas.append({
        "topologia": t, "score": est.mejor().score,
        "b_m": a["envergadura"], "S_m2": a["S"], "AR": a["AR"],
        "masa_kg": a["masa_total"], "%estr": 100*a["fraccion_estructural"],
        "L/D_cru": a["LD_crucero"], "D_N": a["D_crucero"], "P_W": a["potencia_W"],
        "v_stall": a["v_stall"], "margen_lento_%": 100*a["margen_lento"],
        "SM_%": 100*a["SM"], "Cm_cru": a["Cm_crucero"],
        "V_H": a["V_H"], "V_V": a["V_V"],
        "Cn_r": a["Cn_r"],
    })
df = pd.DataFrame(filas).sort_values("score", ascending=False).round(3)
display(df)
print("Referencia de volumen de cola para esta clase: V_H 0.5-0.7, V_V 0.02-0.05")
print("(Scholz, INCAS Bulletin 13(3), 2021). No son restricciones: se reportan")
print("para poder decir si el resultado cayo en territorio conocido.")
""")

code(r"""
# Bateria de cada ganador (solo si BATERIA = True en la seccion 0)
filas_b = []
for t, est in estados.items():
    a = av.analizar_mision_avion(est.mejor().params, t)
    if a is None or not a.get("bateria"):
        continue
    b = a["bateria"]; pk = b["pack"]; d = b["despegue"]
    filas_b.append({
        "topologia": t, "masa_total_kg": a["masa_total"], "bateria_kg": a["masa_bateria"],
        "bateria_%": 100*b["fraccion_masa_bateria"], "pack": f"{pk['S']}S{pk['P']}P",
        "capacidad_Ah": pk["capacidad_Ah"], "energia_Wh": b["energia_requerida_wh"],
        "volumen_L": b["volumen_bateria_l"], "alcance_km": b["alcance_logrado_km"],
        "P_cruc_W": b["potencia_electrica_crucero_W"], "I_cruc_A": b["corriente_crucero_A"],
        "empuje_despegue_kgf": d["empuje_kgf"], "I_despegue_A": d["corriente_A"],
        "I_max_pack_A": pk["corriente_continua_max_A"],
    })
if filas_b:
    display(pd.DataFrame(filas_b).sort_values("bateria_kg").round(2))
    print("Alcance a velocidad de crucero TODO el vuelo; la reserva cubre despegue, ascenso y aterrizaje.")
    print("Despegue: disco actuador con T/W = 0.45, helice de 15 pulgadas (informativo, no puntua).")
else:
    print("BATERIA = False: no hay modelo de bateria en este escenario.")
""")

# ---------------------------------------------------------------- 8
md(r"""
## 7. Análisis de misión completo de cada ganador

Desglose término por término: masa calculada pieza por pieza, los dos puntos de vuelo, las tres reglas de oro de estabilidad estática, las derivadas de amortiguamiento y el aporte de cada término al score.

Sobre las **derivadas de amortiguamiento** ($C_{l_p}$, $C_{n_r}$, $C_{n_p}$, $C_{l_r}$): se calculan y se reportan, pero **no se puntúan ni se restringen**. La razón es honesta — no tenemos una banda de referencia bibliográfica para ellas en esta clase de avión, y poner un umbral inventado sería peor que no ponerlo. Lo esperable es $C_{l_p} < 0$ y $C_{n_r} < 0$ (los dos amortiguan); un $C_{n_r}$ chico en valor absoluto es la señal de alarma para Dutch roll.
""")

code(r"""
for t, est in sorted(estados.items(), key=lambda kv: -kv[1].mejor().score):
    print(av.desglose_mision_avion(est.mejor().params, t))
    print("\n" + "="*78 + "\n")
""")

# ---------------------------------------------------------------- 9
md(r"""
## 8. Vista 3D del ganador
""")

code(r"""
top_ganadora, est_ganador = max(estados.items(), key=lambda kv: kv[1].mejor().score)
mejor = est_ganador.mejor()

print(f"Ganador: {top_ganadora}  (score {mejor.score:.4f})")
print(f"  {av.TOPOLOGIAS[top_ganadora]['nombre']}")
print(f"  referencia real: {av.TOPOLOGIAS[top_ganadora]['referencia_real']}")

avion = av.construir_avion(mejor.params, top_ganadora)
avion.draw(backend="plotly")
""")

# ---------------------------------------------------------------- 10
md(r"""
## 9. El modelo de flap, y el compromiso que descubre

Lo habitual en diseño preliminar es sumar un $\Delta CL_{max}$ de tabla según el tipo de flap (Raymer/Roskam: plain ~0.9, ranurado ~1.3, Fowler ~1.9). Esas tablas están medidas a Reynolds de avión grande ($10^6$–$10^7$) y este avión vuela lento a Re ≈ $2\times10^5$. La bibliografía ([ICAS 2010, paper 246](https://icas.org/icas_archive/ICAS2010/PAPERS/246.PDF)) dice que a Re bajo la curva con flap se vuelve no lineal y el $CL_{max}$ cae, pero **no publica un factor de corrección**.

En vez de inventarlo, acá el incremento se **mide**: se deflecta la geometría del perfil y se la evalúa con NeuralFoil al Reynolds real del vuelo lento — el mismo modelo que se usa en todo el resto del pipeline.

La celda de abajo muestra el resultado, que tiene una consecuencia de diseño que no es obvia: **el perfil de alta sustentación y el flap compiten, no se suman.** Sobre un perfil ya muy cambado, deflectar mucho un flap grande lo separa antes en vez de darle más sustentación — el e423 a 40° da *menos* CL_max que limpio. Es física real del modelo, no un artefacto, y es uno de los compromisos que el optimizador tiene que resolver.

> **Limitación honesta:** deflectar el contorno modela bien un flap **plain** (sin ranura). Un flap ranurado o Fowler tiene física que esto no captura (la ranura reenergiza la capa límite; el Fowler además agranda la superficie), así que ofrecerlos sería prometer un $CL_{max}$ que el modelo no puede sostener. El flap plain es además el realista para construcción artesanal.
""")

code(r"""
from optimizacion_avion.perfiles_avion import cargar_perfil_avion, perfil_con_flap

alphas = np.linspace(0, 24, 49)
Re_lento = 1.8e5
deflexiones = [0, 10, 20, 30, 40]
perfiles = ["naca2412", "naca4412", "fx63137", "e423", "s1223"]

fig, ax = plt.subplots(figsize=(7.5, 4.5))
tabla = []
for n in perfiles:
    af = cargar_perfil_avion(n)
    fila = {"perfil": n}
    ys = []
    for d in deflexiones:
        a2 = perfil_con_flap(af, d, 0.28)
        cl = float(np.max(a2.get_aero_from_neuralfoil(alpha=alphas, Re=Re_lento, mach=0.03)["CL"]))
        fila[f"{d}deg"] = round(cl, 3)
        ys.append(cl)
    tabla.append(fila)
    ax.plot(deflexiones, ys, marker="o", label=n)

ax.set_xlabel("Deflexión de flap [grados]")
ax.set_ylabel("CL máx de la sección")
ax.set_title(f"Flap del 28% de cuerda a Re = {Re_lento:,.0f}")
ax.legend(); ax.grid(alpha=0.3)
plt.show()

display(pd.DataFrame(tabla))
print("Los perfiles muy cambados (e423, s1223) PIERDEN CL_max si se los deflecta")
print("mucho: ya estan al borde de la separacion. El optimo de deflexion baja")
print("a medida que sube el camber del perfil base.")
""")

# ---------------------------------------------------------------- 11
md(r"""
## 10. El catálogo de perfiles a los dos Reynolds

Los índices 0 a 11 son **los mismos** que en el ala volante (no se pueden reordenar sin cambiarle el significado a todos los diseños ya guardados de aquel notebook); del 12 al 18 son los de alta sustentación agregados para esta misión.

El orden sigue siendo por $C_{m0}$ y eso no es cosmético: el GA cruza índices con BLX-alfa, o sea que **interpola**, y para que interpolar tenga sentido los índices vecinos tienen que ser diseños vecinos. En el tramo nuevo ese orden coincide además con $CL_{max}$ creciente, que es lo que uno quiere que recorra una mutación cuando el binding constraint es el vuelo lento.

**Lo que la tabla no dice:** el $L/D$ máximo de los perfiles nuevos es altísimo, pero ocurre a CL alto. En crucero a 120 km/h el CL del ala es ~0.1–0.3, y ahí un perfil muy cambado es un mal negocio. No hay que leer la tabla como "los de abajo son mejores": son mejores **para volar lento** y peores para crucero.
""")

code(r"""
print(av.resumen_catalogo_avion(re_lento=2.0e5, re_crucero=6.7e5))
""")

# ---------------------------------------------------------------- 12
md(r"""
## 11. Exportar el diseño ganador
""")

code(r"""
a = av.analizar_mision_avion(mejor.params, top_ganadora)
p = mejor.params

salida = {
    "topologia": top_ganadora,
    "descripcion": av.TOPOLOGIAS[top_ganadora]["nombre"],
    "referencia_real": av.TOPOLOGIAS[top_ganadora]["referencia_real"],
    "generation": est_ganador.generation,
    "score": mejor.score,
    "_mision": {
        "velocidad_crucero_kmh": 3.6 * mis.V_CRUCERO,
        "velocidad_lenta_ms": mis.V_LENTO,
        "margen_sobre_perdida": mis.MARGEN_SOBRE_PERDIDA,
        "carga_util_kg": mis.MASA_PAYLOAD,
        "rafaga_vertical_ms": mis.RAFAGA_VERTICAL,
        "banda_margen_estatico": list(av.SM_BANDS[top_ganadora]),
    },
    "parametros": {k: round(float(v), 5) for k, v in sorted(p.items())},
    "perfiles": {
        "raiz": av.indice_a_nombre_avion(p["perfil_raiz"]),
        "medio": av.indice_a_nombre_avion(p["perfil_medio"]),
        "punta": av.indice_a_nombre_avion(p["perfil_punta"]),
        "posicion_del_medio_frac_semienvergadura": p["perfil_pos_medio"],
        "_nota": "perfiles REALES de la base UIUC; las secciones intermedias son mezclas lineales",
    },
    "resultados": {k: (float(a[k]) if isinstance(a[k], (int, float, np.floating)) else a[k])
                   for k in ("masa_total", "fraccion_estructural", "envergadura", "S", "AR",
                             "LD_crucero", "D_crucero", "potencia_W", "alpha_crucero",
                             "v_stall", "margen_lento", "CL_max_lento", "CL_lento",
                             "SM", "Cm_alpha_por_grado", "Cm_crucero",
                             "Cn_beta", "Cl_beta", "Cl_p", "Cn_r", "Cn_p", "Cl_r",
                             "V_H", "V_V", "margen_perdida")},
}

if a.get("bateria"):
    salida["bateria"] = json.loads(json.dumps(a["bateria"], default=float))
    salida["_mision"]["alcance_km"] = a["bateria"]["alcance_objetivo_km"]
    salida["_mision"]["viento_activo"] = bool(a.get("viento_activo"))

ruta = Path(f"avion_design_params_{top_ganadora}.json")
ruta.write_text(json.dumps(salida, indent=2, default=float))
print(f"Guardado en {ruta.resolve()}")
print(json.dumps(salida, indent=2, default=float)[:2500])
""")

# ---------------------------------------------------------------- 13
md(r"""
## 12. Lo que este modelo TODAVÍA no hace

Conviene tenerlo escrito para no confundir *"no está implementado"* con *"salió que no importa"*:

- **Exportación a CAD, con un límite.** `exportar_cad_avion.py` y `fusion_generar_avion.py` llevan el avión completo (ala, fuselaje, cola) a Fusion: el primero escribe las secciones 3D en `avion_geometry_cad.json` y el segundo las dibuja dentro de Fusion (ver también `exportar_cfd_avion.py`, que escribe el caso de cálculo y compara el drag con un CFD). Lo que **no** hay: el script de Fusion se escribió sin poder ejecutarlo en Fusion, así que la parte de la API (revolución del fuselaje, espejado, unión de cuerpos) está sin probar hasta que se corra; no hay hélice ni spinner; y `exportar_cad.py` / `fusion_generar_ala.py` siguen siendo solo para el ala volante.
- **El flap es solo plain.** Sin flap ranurado ni Fowler (ver sección 9).
- **La masa de las vigas es declarada**, no dimensionada por flexión. Aplica al `doble_boom` (el `pod_boom` ya no tiene viga: es un fuselaje continuo). `boom_diametro` ya existe como variable geométrica y afecta la resistencia, pero no se usa para dimensionar: sería el próximo paso natural.
- **Torsión y flutter del ala no se ven.** Con la envergadura ahora **libre** esto importa más que antes: el criterio de rigidez en flexión frena el alargamiento, pero un ala muy esbelta puede ser inviable por torsión mucho antes.
- **Las superficies de cola no tienen larguero dimensionado**, solo masa de recubrimiento.
- **Las derivadas de amortiguamiento no se convierten en modos dinámicos** (frecuencia y amortiguamiento de Dutch roll). Para eso harían falta los momentos de inercia: el modelo de masa sabe *cuánto* pesa cada pieza, no *cómo está distribuida*.
- **No hay superficies de control más allá del flap.** Ni elevador, ni ruddervators, ni alerones: se evalúa la estabilidad de la configuración, no su controlabilidad ni la resistencia de trim con elevador deflectado.
- **Batería (rama `bateria-350km`).** Con `BATERIA = True` hay un modelo de energía: la masa de batería sale del alcance pedido a velocidad de crucero constante. Lo que **no** modela: ascenso y descenso aparte, viento de frente, degradación de la celda ni la curva de descarga (la reserva del 20 % cubre todo eso de forma gruesa). El rendimiento propulsivo (0.65) es un supuesto, no un dato de hélice y motor. Con `BATERIA = False` vuelve el problema de antes: `MASA_SISTEMAS` es una constante de 1.5 kg que incluye la batería y el modelo no ve que la autonomía cae.
""")

nb = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.11"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

destino = Path(__file__).parent / f"Optimizador_{VERSION}.ipynb"
destino.write_text(json.dumps(nb, indent=1, ensure_ascii=False))
print(f"Escrito: {destino}  ({destino.stat().st_size/1024:.1f} KB, {len(cells)} celdas)")
