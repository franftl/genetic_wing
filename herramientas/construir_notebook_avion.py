"""Genera Optimizador_<VERSION>.ipynb (la version sale de optimizacion_avion/__init__.py). Se versiona este script además del
.ipynb para poder regenerar el notebook limpio (sin outputs viejos) cuando
haga falta, y para que el contenido de las celdas tenga historial de cambios
legible en git (un .ipynb no lo tiene)."""
import json
import re
from pathlib import Path

# Una sola fuente de verdad: VERSION en optimizacion_avion/__init__.py.
VERSION = re.search(r'^VERSION\s*=\s*"([^"]+)"',
                    (Path(__file__).resolve().parents[1] / "optimizacion_avion" / "__init__.py").read_text(encoding="utf-8"),
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

## La misión tiene TRES puntos de vuelo

> **crucero de diseño a 80 km/h** con 3 kg de carga útil, **velocidad máxima de 120 km/h** (restricción dura y término de puntaje), y **poder volar a 10 m/s** (36 km/h) para reconocimiento, despegue y aterrizaje.

El crucero bajó de 120 a 80 km/h el 18/09/2026 (Research Note 15): el alcance eléctrico se maximiza a resistencia mínima, que para este avión cae cerca de 70–80 km/h. Entre la máxima y el vuelo lento hay una relación de velocidades de **3.33 : 1**, o sea un **factor 11 en coeficiente de sustentación**, y por eso los puntos entran juntos a la función objetivo: piden alas **opuestas**. Si se optimizara solo la velocidad, el optimizador convergería a un ala de cuerda mínima que no puede volar lento — un óptimo perfectamente válido del problema equivocado.

Para calibrar cuán exigente es: el **RQ-7B Shadow** tiene máxima/crucero = 1.54:1 y el **Bayraktar TB2**, 1.71:1 — y despegan de pista o catapulta, no en vuelo lento sostenido.

Con los interruptores de la sección 0 se suman el **viento de los sitios** (aire de 1.056 kg/m³, ráfaga de 4.63 m/s, turbulencia) y la **batería dimensionada por alcance** (350 km).

## Las seis topologías (familias)

| topología | descripción | referencia real |
|---|---|---|
| `convencional` | fuselaje + cola cruciforme | baseline estándar de diseño |
| `t_tail` | fuselaje + cola en T | planeadores; horizontal fuera del downwash |
| `v_tail` | fuselaje + cola en V | familia MQ-1 Predator |
| `doble_boom` | dos vigas + doble deriva | familia RQ-7 Shadow / ScanEagle |
| `pod_boom` | motovelero: góndola corta + viga fina de cola + cola convencional | planeadores / motoveleros (Stemme S10, ASK 21) |
| `fuselaje_continuo` | fuselaje continuo: diámetro casi constante, afinado solo cerca de la cola (sin góndola ni viga fina) | fuselaje tubular de largo alcance |

**Un resultado teórico que conviene tener a la vista al leer los resultados:** McGeer & Kroo ([J. Aircraft 20(11), 1983](https://ntrs.nasa.gov/citations/19840028263)) muestran que a envergadura dada, y con las restricciones de trimado y estabilidad puestas, la configuración convencional con cola trasera está **muy cerca del óptimo**, y ni el canard ni el tándem la superan salvo casos marginales. O sea: no hay que esperar que una topología exótica gane por goleada. Lo que separa a los candidatos es resistencia parásita, peso estructural y CL_max. Por eso **no** se incluyeron canard ni box-wing: el canard limita el CL_max del ala principal justo cuando es el recurso más escaso, y el box-wing necesita una separación vertical que a 7 kg de construcción artesanal no paga.

## Qué cambió respecto de la versión anterior de este notebook

1. **Parametrización mucho más fina:** ala de 5 estaciones (cuerda, borde de ataque, torsión y diedro estación por estación) **con winglets**, **envergadura variable** (2.0–3.5 m), y fuselaje con morro de forma libre y boat-tail en vez del cono truncado que había. De ~20 a **46–51 parámetros** según la topología.
2. **Incidencia de cola.** Antes iba con `twist = 0` fijo, y eso no era una simplificación sino un error: sin incidencia el avión no tiene con qué trimarse, y el desvío de trim llegaba al 113%. Ahora los candidatos salen con **Cm de crucero = 0.0000**.
3. **Flaps**, modelados deflectando la geometría del perfil y evaluándola con NeuralFoil al Reynolds real del vuelo lento — no con un ΔCL de tabla (ver sección 7).
4. **CL_max a su propio Reynolds.** Antes se estimaba al Re de crucero y se usaba para todo; el CL_max cae ~6% (hasta 11%) al pasar de Re 6.7e5 a 2e5, justo donde el diseño está más apretado.
5. **Catálogo de 19 perfiles** (los 12 del ala volante con los mismos índices, más 7 de alta sustentación).

## Cómo correrlo

Sección **0** (interruptores), **1 y 2** para configurar y sembrar; después **3** (una generación por vez) o **4** (automático). Las secciones **5 a 11** analizan el resultado. Costo: varios segundos por candidato con batería (cada candidato se analiza 2–3 veces para cerrar el lazo masa de batería ↔ resistencia); la competencia completa lleva **horas**.
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

# optimizacion_avion es autocontenido (desde V55 lo que heredo del ala volante
# esta en optimizacion_avion/base_ala/): alcanza con que el paquete este al
# lado de este notebook.
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
| `FAMILIAS` | Qué familias (topologías) se corren: una lista, por ejemplo `["pod_boom"]` o `["v_tail", "pod_boom"]`, o `"todas"` (por defecto solo `["v_tail"]`). Opciones: `convencional`, `t_tail`, `v_tail`, `doble_boom`, `pod_boom` (góndola + viga), `fuselaje_continuo`. |
| `POBLACION_INICIAL` | Cuántos diseños se evalúan al arrancar (las semillas más mutantes, cruces y comodines). Default 30. Con solo 2 semillas el GA arrancaba casi a ciegas. |
| `N_PADRES` | Cuántos de los mejores se conservan como padres en cada generación (μ). Default 6. |
| `CORRIDA_RAPIDA` | `True`: 8 generaciones de paciencia y máximo 20 (~15–30 min por familia). `False`: 10 / 60, puede tardar **horas** por familia, porque con batería cada candidato cuesta el doble. |
| `GUARDAR_RESULTADOS` | `True`: al final (sección 11b) guarda tablas, gráficos, vistas 3D, líneas de flujo y desgloses en `<CARPETA_RESULTADOS>/<fecha>_<escenario>_<familias>/`. |
| `CARPETA_RESULTADOS` | Dónde se guardan, **fuera del repositorio**. `None` = `Proyecto final/resultados_optimizador/` (al lado de `genetic_wing`); o cualquier ruta de la computadora. |

Los supuestos de la batería (eficiencia propulsiva, reserva, celda, aviónica) son los de abajo; **ninguno está medido**, en particular `ETA_PROPULSIVA_TOTAL`.
""")

code(r"""
import optimizacion_avion.bateria as bat

# ------------------------------ INTERRUPTORES ------------------------------
VIENTO = True            # lo de imarzeniuk (viento de los sitios)
BATERIA = True           # bateria dimensionada por alcance
# Familias a correr: lista con cualquiera de convencional, t_tail, v_tail, doble_boom, pod_boom (gondola + viga),
# fuselaje_continuo; o "todas"
FAMILIAS = ["v_tail"]
POBLACION_INICIAL = 30   # diseños evaluados al arrancar (semillas + mutantes + cruces + comodines)
N_PADRES = 6             # padres que sobreviven cada generación (mu)
CORRIDA_RAPIDA = True    # True: paciencia 8 / max 20 generaciones. False: 10 / 60 (horas)
GUARDAR_RESULTADOS = True   # carpeta <CARPETA_RESULTADOS>/<fecha>_<escenario>_<familias>/ al final (seccion 11b)
CARPETA_RESULTADOS = None   # None = av.CARPETA_RESULTADOS (fuera del repo); o p. ej. r"C:\Users\...\Resultados UAV"
SET_SEMILLAS = None      # None = las del escenario; o un set de la carpeta semillas/ (p. ej. "bateria_350km")
SEMILLA_AZAR = 2026      # fija el azar del GA: misma corrida, mismo resultado

# ------------------- SUPUESTOS DE LA BATERIA (bateria.py) -------------------
bat.ALCANCE_KM = 350.0               # [km] a velocidad de crucero constante
bat.ETA_PROPULSIVA_TOTAL = 0.65      # helice x motor x ESC en crucero (SUPUESTO)
bat.POTENCIA_AVIONICA_W = 10.0       # [W] autopiloto + telemetria + camara
bat.RESERVA_ENERGIA = 0.20           # [-] sobre la energia de crucero
bat.CELDA_POR_DEFECTO = "molicel_m65a"   # molicel_m65a | lg_m58t | samsung_50g | molicel_p42a
bat.CELDAS_EN_SERIE = 12             # 12S (solo informativo: la masa sale de la energia)

# ------------------- ENVERGADURA MAXIMA (requisito) -------------------
# Envergadura TOTAL (con winglets) <= esto, por la evaluacion de riesgo SORA que pide la
# operacion BVLOS en Argentina (mas de 3 m sube un escalon el riesgo en tierra).
mis.ENVERGADURA_MAX_M = 3.0             # [m]

# ------------------------------ APLICAR ------------------------------
mis.VIENTO_ACTIVO = VIENTO
mis.BATERIA_ACTIVA = BATERIA
mis.PUNTAJE_MODO = "mision"      # "mision" (energia para el alcance + requisitos) | "legado" (11 terminos de antes)
mis.TRIM_RESUELTO = True         # la incidencia de cola se calcula para Cm = 0 en crucero

# ---- Semillas validas para el escenario elegido ----
# Las de semillas.json (7 kg, 8.2 L) quedan INVALIDAS con batería (~12 kg, ~2 L mas de
# fuselaje) y con el aire liviano del sitio. La regla para elegirlas vive en un solo
# lugar (competencia.semillas_para_escenario), la misma que usan los scripts. Se
# necesitan DOS por topologia: el cruce BLX entre dos padres iguales no explora nada.
import random
if SET_SEMILLAS is None:
    SEMILLAS = av.semillas_para_escenario()
else:
    import semillas as biblioteca_semillas
    SEMILLAS = biblioteca_semillas.cargar(SET_SEMILLAS)

TOPOLOGIAS_A_CORRER = list(av.TOPOLOGIAS) if FAMILIAS == "todas" else list(FAMILIAS)
_desconocidas = [t for t in TOPOLOGIAS_A_CORRER if t not in av.TOPOLOGIAS]
if _desconocidas or not TOPOLOGIAS_A_CORRER:
    raise ValueError(f"FAMILIAS invalidas: {_desconocidas or 'lista vacia'}. Opciones: {list(av.TOPOLOGIAS)} o 'todas'")

print(f"VIENTO_ACTIVO = {mis.VIENTO_ACTIVO}   BATERIA_ACTIVA = {mis.BATERIA_ACTIVA}   "
      f"CORRIDA_RAPIDA = {CORRIDA_RAPIDA}")
print(f"Familias a correr: {', '.join(TOPOLOGIAS_A_CORRER)}")
print(f"Resultados en: {CARPETA_RESULTADOS or av.CARPETA_RESULTADOS}")
if mis.BATERIA_ACTIVA:
    print(f"Bateria: {bat.ALCANCE_KM:.0f} km a {3.6*mis.V_CRUCERO:.0f} km/h, eta {bat.ETA_PROPULSIVA_TOTAL:.2f}, "
          f"reserva {100*bat.RESERVA_ENERGIA:.0f}%, celda {bat.CELDA_POR_DEFECTO} "
          f"({bat.energia_especifica_pack():.0f} Wh/kg a nivel pack)")
print(f"Envergadura total maxima: {mis.ENVERGADURA_MAX_M:.1f} m (requisito, SORA)")
print(f"Semillas: {'las del escenario' if SET_SEMILLAS is None else SET_SEMILLAS}   azar fijo: {SEMILLA_AZAR}")
for t in av.TOPOLOGIAS:
    print(f"  semillas {t:<14}: {len(SEMILLAS.get(t, []))}")
""")

# ---------------------------------------------------------------- 2
md(r"""
## 1. Configuración: la misión y el criterio de parada

El puntaje tiene dos modos (`mis.PUNTAJE_MODO`, sección 0). El de trabajo es **`"mision"`** (desde V51.2):

$$\text{score} = 1.0\,\frac{E_{ref}}{E_{alcance}} \;+\; \underbrace{1.0\,f_{lento} + 0.5\,f_{vmax}}_{\text{pendientes de decisión}}$$

- **Objetivo:** $E_{alcance}$ es la energía de batería (con reserva) para volar `bat.ALCANCE_KM` a 80 km/h con la resistencia de la misión (la turbulenta, con viento). Con batería activa ya incluye el peso de la propia batería, así que la masa entra sola. Reemplaza a los términos de eficiencia, masa y turbulencia, que contaban lo mismo varias veces.
- **Pendientes** (misma forma y peso que antes, hasta decidirlos con Quintana y Felipe): margen de vuelo lento hasta el objetivo de 20 % ($v_{stall} \le 8.33$ m/s) y resistencia a 120 km/h. Tasa de cambio actual: 0.1 m/s menos de pérdida vale ~6 % de energía.
- **Trim resuelto** (`mis.TRIM_RESUELTO`): la incidencia de la cola se calcula para que el avión vuele en crucero con $C_m = 0$; el valor del candidato es solo el punto de partida. Para exportar o dibujar se usa `av.params_trimados(...)`.

**Requisitos pasa / no pasa** (si falla alguno el candidato queda infactible, rankeado por cuánto viola): estructura que cierre, volumen útil en el fuselaje, sostenerse a 120 km/h, **volar a 10 m/s con el flap abajo**, margen estático **dentro de la banda** de la topología, $C_{n\beta} \ge$ `CN_BETA_MIN` y $C_{l\beta} \le -$`CL_BETA_MIN` (0.0005 /grado, supuesto), margen de pérdida con la ráfaga ≥ 20 %, incidencia de trim dentro del rango de diseño, **envergadura total ≤ 3.0 m** (`mis.ENVERGADURA_MAX_M`, winglets incluidos: por la evaluación de riesgo SORA que pide el vuelo BVLOS en Argentina), y con viento ráfaga del sitio ≤ carga límite (3.0 g).

**Infactibles rankeados** (V51.3, reglas de Deb): un avión que no cumple no vale −inf sino un número por debajo de −1000 que ordena por cuánto viola; así el GA puede llegar a la zona factible aunque las semillas no lo sean, y la paciencia no corre mientras no haya ningún padre factible. Los prints lo muestran como "infactible: etapa (violación)".

El modo **`"legado"`** es la suma de 11 términos de antes (12 con viento), para comparar contra corridas viejas (con `TRIM_RESUELTO = False` reproduce el modelo anterior).
""")

code(r"""
# --- Criterio de parada ---
# Subidos respecto de la version anterior (8/40): el espacio de diseno paso
# de ~20 parametros por topologia a 46-51, y con mas dimensiones el GA
# necesita mas generaciones para explotar una direccion buena antes de que
# la racha sin mejora lo corte.
# CORRIDA_RAPIDA (seccion 0): 8 / 20; si no, 10 / 60. Las familias salen de FAMILIAS (seccion 0).
if CORRIDA_RAPIDA:
    # 8 y no 4: con requisitos pasa/no pasa, ~1 de cada 10 hijos es factible y
    # 4 generaciones sin mejora cortaban antes de tiempo (corrida del 19/10).
    PACIENCIA, MAX_GENERACIONES = 8, 20
else:
    PACIENCIA, MAX_GENERACIONES = 10, 60

# --- Cuantos hijos por generacion, por topologia ---
N_CROSSBRED, N_WILDCARD = 7, 3

print("MISION -- TRES PUNTOS DE VUELO")
print(f"  crucero (diseno) ...... {3.6*mis.V_CRUCERO:.0f} km/h ({mis.V_CRUCERO:.2f} m/s)")
print(f"  velocidad maxima ...... {3.6*mis.V_MAX:.0f} km/h ({mis.V_MAX:.2f} m/s)")
print(f"  vuelo lento ........... {mis.V_LENTO:.0f} m/s ({3.6*mis.V_LENTO:.0f} km/h)")
print(f"  relacion maxima/lento . {mis.V_MAX/mis.V_LENTO:.2f} : 1"
      f"   -> factor {(mis.V_MAX/mis.V_LENTO)**2:.1f} en CL")
print(f"  margen sobre perdida .. {mis.MARGEN_SOBRE_PERDIDA:.2f}"
      f"  -> v_stall objetivo <= {mis.V_STALL_OBJETIVO:.2f} m/s")
print(f"  carga util ............ {mis.MASA_PAYLOAD:.1f} kg")
print(f"  rafaga vertical ....... {mis._rafaga_vertical():.2f} m/s (en crucero)")
print()
print(f"PUNTAJE (modo '{mis.PUNTAJE_MODO}', trim resuelto: {mis.TRIM_RESUELTO})")
if mis.PUNTAJE_MODO == "mision":
    print(f"  alcance {mis.PESO_ALCANCE} x E_ref/E  (E_ref = {mis.ENERGIA_REFERENCIA_WH:.0f} Wh)")
    print(f"  pendientes: vuelo lento {mis.PESO_LENTO} | velocidad maxima {mis.PESO_VELMAX}")
    print(f"  requisitos: SM en banda, margen de perdida >= {100*mis.MARGEN_PERDIDA_OK:.0f}%, "
          f"Cn_beta >= {mis.CN_BETA_MIN}, Cl_beta <= -{mis.CL_BETA_MIN} [/grado]")
else:
    print(f"  eficiencia {mis.PESO_EFICIENCIA} | masa {mis.PESO_MASA} | estabilidad {mis.PESO_ESTABILIDAD}"
          f" | rafaga {mis.PESO_RAFAGA} | margen {mis.PESO_MARGEN}")
    print(f"  trim {mis.PESO_TRIM} | direccional {mis.PESO_DIRECCIONAL} | lateral {mis.PESO_LATERAL}"
          f" | VUELO LENTO {mis.PESO_LENTO}")
    print(f"  velocidad maxima {mis.PESO_VELMAX} | envergadura {mis.PESO_ENVERGADURA}"
          + (f" | turbulencia {mis.PESO_TURBULENCIA}" if mis.VIENTO_ACTIVO else ""))
print()
print(f"Envergadura TOTAL (con winglets): variable en [{av.BOUNDS_ALA['envergadura'][0]:.1f}, "
      f"{av.BOUNDS_ALA['envergadura'][1]:.1f}] m; el ala se achica lo que ocupen los winglets")
print(f"Parar tras {PACIENCIA} generaciones sin mejora, o al llegar a {MAX_GENERACIONES}.")
""")

# ---------------------------------------------------------------- 3
md(r"""
## 2. Población semilla

Las semillas salen de `av.semillas_para_escenario()` según los interruptores de la sección 0: con batería, `evaluacion_bateria_350km/semillas_bateria.json`; con viento y sin batería, los ganadores con y sin viento; sin ninguno, las de Felipe en `optimizacion_avion/semillas.json`. Con `SET_SEMILLAS` se puede usar cualquier set de la carpeta `semillas/`. Lo que sigue describe las semillas de Felipe, que genera `gen_semillas.py` (también en el paquete, para que el proceso sea reproducible y no un número mágico). El procedimiento: se define a mano una base de ala, fuselaje y flap (con criterio de diseño, sin pretensión de optimalidad) y después se **afinan numéricamente por bisección** solo dos parámetros — `cg_frac_mac` hasta que el margen estático caiga en el medio de la banda, y la **incidencia del estabilizador** hasta que el $C_m$ de crucero sea ~0, o sea hasta que el avión quede trimado sin elevador. El resto es trabajo del GA.

Hay **dos semillas por topología**, a propósito en lados opuestos del compromiso central de esta misión:

- **A**: ala grande (b ≈ 3.1 m, S ≈ 1.02 m²) con perfiles de **alta sustentación** (fx63137 / naca6412). Vuela lento con holgura, pero con la misión original (crucero a 120 km/h) andaba por L/D ≈ 7.3.
- **B**: ala más chica (b ≈ 2.85 m, S ≈ 0.82 m²) con camber **moderado** (naca6412 / naca4412) y un flap que sí rinde. **L/D ≈ 10.4** en ese crucero — bastante mejor — y todavía vuela a 10 m/s.

Que la B le gane a la A en L/D ya dice algo antes de optimizar: el ala grande se paga caro en crucero y el perfil de alta sustentación no es gratis. Esa es la pelea que el GA tiene que resolver.

Sembrar variado no es cosmético: BLX-alfa entre dos padres con el **mismo** valor en una dimensión devuelve siempre ese valor, así que una dimensión donde las dos semillas coinciden queda sin explorar.
""")

code(r"""
# `estados` es el objeto central del notebook: un loop evolutivo
# independiente por topologia, todos con la misma funcion objetivo.
estados, filas = {}, []

for t in TOPOLOGIAS_A_CORRER:
    seeds = SEMILLAS[t]

    def objetivo(params, _t=t):
        return av.evaluar_mision_avion(params, _t)

    estados[t] = av.iniciar_evolucion_avion(seeds, t, objetivo, POBLACION_INICIAL, N_PADRES)

    for i, c in enumerate(estados[t].parents):
        # Un score por debajo de -1000 es un avion INFACTIBLE: -1000 menos lo que
        # viola (ver "estado" y "falla"). Los factibles valen mas de 0.
        a = av.analizar_con_motivo(c.params, t)
        base = {"topologia": t, "semilla": i, "score": c.score, "estado": av.describir_puntaje(c.score)}
        if not isinstance(a, dict):
            filas.append({**base, "falla": str(a)}); continue
        filas.append({
            **base, "falla": "; ".join(mis.requisitos_incumplidos(a)) or "-",
            "b_m": a.get("envergadura_total", a["envergadura"]), "S_m2": a["S"], "AR": a["AR"],
            "masa_kg": a["masa_total"], "L/D": a["LD_crucero"],
            "v_stall": a["v_stall"], "SM_%": 100*a["SM"],
            "Cm_cru": a["Cm_crucero"], "V_H": a["V_H"],
        })
    _h0 = estados[t].historial[0]
    print(f"[{t}] {_h0['n_semillas']} semillas -> {_h0['n_poblacion_inicial']} diseños evaluados, {_h0['n_factibles_iniciales']} factibles; padres: {[av.describir_puntaje(c.score) for c in estados[t].parents]}")

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
    print(f"Mejor score: {av.describir_puntaje(_est.mejor().score)}   racha {_est.non_improving_streak}/{PACIENCIA}")

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
    random.seed(SEMILLA_AZAR + list(av.TOPOLOGIAS).index(t) + gen_inicial)   # reproducible

    if av.deberia_parar(est, paciencia=PACIENCIA, max_generaciones=MAX_GENERACIONES):
        print(f"[{t}] ya estaba detenido en la generacion {est.generation}. "
              f"Volve a correr la seccion 2 para empezar de cero.")
        continue

    print(f"\n{'='*68}\n[{t}] optimizando\n{'='*68}")
    while not av.deberia_parar(est, paciencia=PACIENCIA, max_generaciones=MAX_GENERACIONES):
        est, hijos = av.correr_generacion_avion(
            est, av.generar_hijos_avion, _obj,
            n_crossbred=N_CROSSBRED, n_wildcard=N_WILDCARD)
        # Se lee del historial: la racha queda en 0 tambien mientras no hay ningun padre
        # factible (la paciencia no corre), y eso no es una mejora.
        marca = "  <-- mejoro" if est.historial[-1].get("mejoro") else ""
        print(f"  gen {est.generation:3d}   mejor score = {av.describir_puntaje(est.mejor().score):>10}   "
              f"racha {est.non_improving_streak}/{PACIENCIA}{marca}")

    estados[t] = est
    Path("resultados").mkdir(exist_ok=True)
    av.guardar_checkpoint(est, Path("resultados") / f"checkpoint_avion_{t}.json")
    motivo = (f"no mejoro en {PACIENCIA} generaciones seguidas"
              if est.non_improving_streak >= PACIENCIA else "se alcanzo MAX_GENERACIONES")
    print(f"  detenido en la generacion {est.generation} porque {motivo} "
          f"({est.generation - gen_inicial} generaciones en esta corrida).")

print(f"\nTiempo total: {time.time()-_t0:.0f} s")
if mis.FALLAS_ANALISIS:
    print(f"Candidatos descartados por errores numericos (por tipo): {dict(mis.FALLAS_ANALISIS)}")
print()
print(av.tabla_resultados(estados))
""")

# ---------------------------------------------------------------- 6
md(r"""
## 5. Convergencia comparada

Todas las curvas en los mismos ejes. Es la forma más directa de ver **si la diferencia final entre topologías es real o es ruido**. Si terminan todas pegadas y oscilando, la competencia no está resolviendo nada y hace falta más paciencia o más hijos por generación — que es un resultado legítimo de reportar, y además es lo que predice McGeer & Kroo (ver la introducción).
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
## 6. El diseño ganador, en una sola tabla

Una única tabla con la geometría del ganador y lo que el modelo dice de él: ala, fuselaje y cola, masa, crucero, vuelo lento, estabilidad y batería. Reemplaza a las tablas sueltas de misión, comparación y batería, que mostraban casi lo mismo.

Para leerla: el **margen de vuelo lento** (100 % = justo en el objetivo de pérdida) y el volumen de cola $V_H$ (referencia 0.5–0.7 para esta clase, Scholz, INCAS Bulletin 13(3), 2021) son los dos números que más conviene mirar. Ninguno es una restricción dura; sirven para decidir si el resultado cayó en territorio conocido.

Las **derivadas de amortiguamiento** ($C_{n_r}$ y compañía) se calculan y se reportan pero **no se puntúan ni se restringen**: no hay una banda bibliográfica para esta clase de avión y poner un umbral inventado sería peor que no ponerlo. Lo esperable es $C_{n_r} < 0$; un valor chico en módulo es la señal de alarma para Dutch roll.
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
        "E_Wh": av.energia_mision_wh(a),
        "L/D_cru": a["LD_crucero"], "D_N": a["D_crucero"], "P_W": a["potencia_W"],
        "v_stall": a["v_stall"], "margen_lento_%": 100*a["margen_lento"],
        "SM_%": 100*a["SM"], "Cm_cru": a["Cm_crucero"], "inc_trim": a["incidencia_trim_deg"],
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
from optimizacion_avion.graficos_avion import tabla_ganador, graficar_vuelo_lento

ranking = sorted(estados.items(), key=lambda kv: -kv[1].mejor().score)
top_ganadora, est_ganador = ranking[0]
mejor = est_ganador.mejor()

print("Score por topología: " + "  |  ".join(f"{t} {e.mejor().score:.3f}" for t, e in ranking))
print(f"\nGanador: {top_ganadora}  (referencia real: {av.TOPOLOGIAS[top_ganadora]['referencia_real']})\n")
display(tabla_ganador(mejor.params, top_ganadora, mejor.score).style.hide(axis="index"))
""")

# ---------------------------------------------------------------- 8
md(r"""
## 7. Vuelo lento: sustentación vs ángulo de ataque, con y sin flap

A la izquierda, el CL del avión en función del ángulo de ataque a 10 m/s, **con el flap retraído y con el flap desplegado, superpuestos**. A la derecha, el CL que hace falta para sostener el peso en función de la velocidad: donde esa curva corta al CL máximo de cada configuración están la **velocidad de pérdida** y, a $1.2\,V_p$, la **velocidad de despegue**.

Es el mismo modelo que puntúa a los candidatos. La recta de sustentación sale de AeroBuildup; el flap suma el CL a $\alpha = 0$ medido con NeuralFoil en una sección con flap (escalado por la fracción de superficie que lleva flap); y el CL máximo de cada curva es el que usa el optimizador. La transición a la pérdida es solo la forma de la curva: el modelo **no** predice lo que pasa después de ella.

> **Limitación honesta:** el flap es plain (sin ranura ni Fowler), el único que el modelo puede sostener. Ver sección 10.
""")

code(r"""
fig, resumen_vl = graficar_vuelo_lento(mejor.params, top_ganadora, titulo=f"Vuelo lento — {top_ganadora}")
plt.show()
display(pd.DataFrame(resumen_vl))
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

# Vista propia: un color por componente (ala, cola, fuselaje), escala 1:1 y los datos
# del avion. (avion.draw(backend="plotly") de AeroSandbox pone una barra de colores
# que no representa nada.)
_a = av.analizar_mision_avion(mejor.params, top_ganadora)
avion = av.construir_avion(av.params_trimados(mejor.params, top_ganadora), top_ganadora)   # con la incidencia de trim
av.figura_3d(avion, f"{top_ganadora} (ganador)", av.lineas_info(_a, mejor.score)).show()
""")

# ---------------------------------------------------------------- 9b
md(r"""
## 8b. Líneas de flujo del ganador (VLM)

El avión **trimado** en el punto de **crucero** de la misión (su alpha, 80 km/h, la densidad del escenario), resuelto con el método de red de vórtices (VLM) de AeroSandbox. Los paneles se pintan con la **circulación Γ** de cada vórtice [m²/s]: dónde el ala genera más sustentación. Las líneas violetas son líneas de flujo: se ven la estela y el torbellino de punta.

**Es solo para visualizar.** El VLM es potencial e inviscido: no ve el fuselaje (se dibuja en gris como referencia), no capta toda la sustentación de los perfiles con mucha curvatura, y el CD que da es solo el inducido. Los números del optimizador salen de AeroBuildup (el recuadro muestra los dos). Tarda ~20 s. Para ver otra familia, cambiá `FAMILIA_FLUJO`.
""")

code(r"""
FAMILIA_FLUJO = top_ganadora          # o cualquiera de TOPOLOGIAS_A_CORRER, p. ej. "pod_boom"

fig_flujo, datos_flujo = av.figura_flujo(estados[FAMILIA_FLUJO].mejor().params, FAMILIA_FLUJO)
if fig_flujo is None:
    print(f"[{FAMILIA_FLUJO}] el mejor avion es infactible: {datos_flujo['motivo']}")
else:
    fig_flujo.show()
""")


# ---------------------------------------------------------------- 12
md(r"""
## 9. Exportar el diseño ganador
""")

code(r"""
a = av.analizar_mision_avion(mejor.params, top_ganadora)
p = a["params_trimados"]      # el avion que se analizo: incidencia de cola resuelta para Cm = 0

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
        "rafaga_vertical_ms": mis._rafaga_vertical(),   # 4.63 con viento, 3.0 sin
        "densidad_kg_m3": float(a["rho"]),
        "viento_activo": bool(mis.VIENTO_ACTIVO),
        "bateria_activa": bool(mis.BATERIA_ACTIVA),
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

Path("resultados").mkdir(exist_ok=True)
ruta = Path("resultados") / f"avion_design_params_{top_ganadora}.json"
ruta.write_text(json.dumps(salida, indent=2, default=float), encoding="utf-8")
print(f"Guardado en {ruta.resolve()}")
print(json.dumps(salida, indent=2, default=float)[:2500])
""")

# ---------------------------------------------------------------- 12b
md(r"""
## 11b. Guardar los resultados de esta corrida

Crea `<CARPETA_RESULTADOS>/<fecha>_<hora>_<escenario>_<familias>/` **fuera del repositorio** (por defecto `Proyecto final/resultados_optimizador/`) con: `LEEME.md` (qué se corrió y la tabla final), `tabla_resumen.csv`, `ganadores.json` (params **trimados**, listos para `exportar_cad_avion.py`), `convergencia.png`, `comparacion.png`, `curvas_vuelo.png`, `vistas_3d/<familia>.html`, `lineas_flujo/<familia>.html`, `tres_vistas/<familia>.png`, `desgloses/<familia>.txt` y `xflr5/<familia>/` (el avión en XML, los perfiles `.dat` y las condiciones de crucero, para abrirlo en XFLR5). Nunca pisa una carpeta anterior. La nomenclatura está en el `LEEME.md` de esa carpeta.
""")

code(r"""
if GUARDAR_RESULTADOS:
    carpeta = av.guardar_resultados(
        estados, carpeta_base=CARPETA_RESULTADOS,
        etiqueta=None,            # p. ej. etiqueta="prueba_eta070"
        flujo=True,               # False saltea las lineas de flujo (~20 s y ~3 MB por familia)
        parametros_ga={"paciencia": PACIENCIA, "max_generaciones": MAX_GENERACIONES,
                       "poblacion_inicial": POBLACION_INICIAL, "n_padres": N_PADRES,
                       "hijos_por_generacion": N_CROSSBRED + N_WILDCARD, "semilla_azar": SEMILLA_AZAR,
                       "semillas": SET_SEMILLAS or "las del escenario"})
else:
    print("GUARDAR_RESULTADOS = False (seccion 0): no se guardo nada.")
""")

# ---------------------------------------------------------------- 13
md(r"""
## 10. Lo que este modelo TODAVÍA no hace

Conviene tenerlo escrito para no confundir *"no está implementado"* con *"salió que no importa"*:

- **Exportación a CAD, con un límite.** `exportar_cad_avion.py` y `fusion_generar_avion.py` llevan el avión completo (ala, fuselaje, cola) a Fusion: el primero escribe las secciones 3D en `avion_geometry_cad.json` y el segundo las dibuja dentro de Fusion (ver también `exportar_cfd_avion.py`, que escribe el caso de cálculo y compara el drag con un CFD). Lo que **no** hay: el script de Fusion se escribió sin poder ejecutarlo en Fusion, así que la parte de la API (revolución del fuselaje, espejado, unión de cuerpos) está sin probar hasta que se corra; no hay hélice ni spinner; y `exportar_cad.py` / `fusion_generar_ala.py` siguen siendo solo para el ala volante.
- **El flap es solo plain.** Sin flap ranurado ni Fowler (ver sección 7).
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

destino = Path(__file__).resolve().parents[1] / f"Optimizador_{VERSION}.ipynb"
destino.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"Escrito: {destino}  ({destino.stat().st_size/1024:.1f} KB, {len(cells)} celdas)")
