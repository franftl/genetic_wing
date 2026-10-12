# Evaluación: batería para 350 km + viento + penalización de envergadura

Rama `bateria-350km`, armada sobre `origin/viento` (lo de imarzeniuk). Todo lo
nuevo de evaluación vive en esta carpeta; el código que cambió está en
`optimizacion_avion/` (lista abajo). Nada de esto está en `main`.

## Qué se pidió y dónde quedó

| Pedido | Dónde está | Cómo se apaga / se mueve |
|---|---|---|
| Batería para 350 km a velocidad de crucero **todo el vuelo**, con una eficiencia modificable | `optimizacion_avion/bateria.py` (nuevo) + lazo en `mision_avion.analizar_mision_avion` | `mision_avion.BATERIA_ACTIVA = False`; `bateria.ETA_PROPULSIVA_TOTAL` (0.65), `ALCANCE_KM` (350) |
| Lo de imarzeniuk (viento de los sitios) superpuesto con un true/false | `mision_avion.VIENTO_ACTIVO` (ya estaba en su rama, se conserva) | `True` / `False` |
| Penalización de envergadura > 2 m (fabricación) | `mision_avion.py`: término `envergadura (fabricacion)` | `ENVERGADURA_MANUFACTURA_MAX` (2.0 m), `ENVERGADURA_MANUFACTURA_TOL` (0.4 m), `PESO_ENVERGADURA` (0.3) |
| Sweep monótono (ninguna sección más adelantada que la anterior, hacia atrás o hacia adelante) | `geometria_avion.py` (`le_offset` en ±0.14, proyección monótona) | — |
| Más estaciones de discretización en el ala | `geometria_avion.py`: 11 estaciones de cálculo (`N_ESTACIONES_LOFT`) sobre las 5 de diseño | `N_ESTACIONES_LOFT` |

Los dos interruptores son independientes: `(VIENTO, BATERIA)` da 4 escenarios.
Con `BATERIA_ACTIVA = False` vuelve el modelo anterior (batería dentro de
`MASA_SISTEMAS = 1.5 kg`); se verificó que con ambos en `False` el puntaje de las
semillas coincide al 6.º decimal con el código previo a `viento` más los
cambios de envergadura/sweep/discretización.

## Cómo se dimensiona la batería

```
E_necesaria = (D_efectiva · V / η + P_aviónica) · t          t = 350 km / 80 km/h = 4.375 h
E_batería   = E_necesaria · (1 + reserva)
m_batería   = E_batería / (Wh/kg del pack)
```

* `D_efectiva` es la resistencia de crucero del propio candidato (con la
  turbulencia del sitio si `VIENTO_ACTIVO`). La batería pesa → sube el peso →
  sube la resistencia inducida → hace falta más batería. El lazo se cierra con
  2–3 pasadas aerodinámicas completas por candidato (la resistencia se
  reescala analíticamente entre pasadas, `bateria.resistencia_a_peso`), así que
  **evaluar un candidato cuesta ~2× más que antes** (~5–7 s).
* La batería ocupa volumen: se le suma al volumen mínimo de fuselaje (el 8.2 L
  original ya incluía 0.5 L de batería).
* Salida informativa (no puntúa): configuración del pack S×P, capacidad en Ah,
  corriente de crucero, y empuje/corriente de despegue (disco actuador) con un
  chequeo contra la corriente continua que aguanta el pack.

### Supuestos (todos son constantes con nombre en `bateria.py`; ninguno está medido)

| Constante | Valor | De dónde sale |
|---|---|---|
| `ETA_PROPULSIVA_TOTAL` | 0.65 | hélice ~0.75 × motor ~0.85 × ESC ~0.95 en crucero. **Cambiar por el dato real de la hélice/motor elegidos** |
| `POTENCIA_AVIONICA_W` | 10 W | autopiloto + telemetría + cámara (estimación) |
| `RESERVA_ENERGIA` | 20 % | aterrizaje fallido, descarga no utilizable, envejecimiento. Cubre también el despegue y el ascenso, que no se modelan aparte |
| `MASA_SISTEMAS_SIN_BATERIA` | 1.0 kg | motor + ESC + hélice + servos + piloto. El 1.5 kg anterior incluía la batería; se supuso que ~0.5 kg era batería |
| `FACTOR_MASA_PACK` | 1.15 | níquel soldado, BMS, cableado, funda sobre la masa de celdas |
| `ENERGIA_VOLUMETRICA_PACK_WH_L` | 600 Wh/L | celda 21700 ≈ 0.97 Wh/mL, bajada por empaque y overhead |
| `CELDA_POR_DEFECTO` / `CELDAS_EN_SERIE` | Molicel M65A / 12S | ver tabla de celdas |

### Celdas 21700 consideradas (hojas de datos, aboutenergy.io)

| Celda | Ah | g | Wh/kg (celda) | I continua | Para este caso |
|---|---|---|---|---|---|
| Molicel M65A | 6.5 | 74.5 | 314 | 26 A (4C) | la mejor masa y sobra corriente |
| LG M58T | 5.57 | 73.2 | 273 | 12.5 A | masa parecida, menos margen de corriente |
| Samsung 50G | 4.85 | 69.5 | 253 | 9.7 A | más pesada por Wh |
| Molicel P42A | 4.2 | 70 | 216 | 45 A (10.7C) | corriente de sobra, pero la más pesada por Wh |

Cambiar `CELDA_POR_DEFECTO` en `bateria.py` recalcula todo.

## Cómo correrlo

Desde la raíz del repo (necesita `aerosandbox`, `scipy`, `numpy`):

```
# 1) semillas válidas para la misión con batería (ya vienen generadas: semillas_bateria.json)
python evaluacion_bateria_350km/reparar_semillas.py

# 2) competencia en el escenario que quieras
python evaluacion_bateria_350km/correr_escenarios.py --viento on  --bateria on
python evaluacion_bateria_350km/correr_escenarios.py --viento off --bateria on
python evaluacion_bateria_350km/correr_escenarios.py --viento on  --bateria on --topologias v_tail --paciencia 4 --max-gen 12   # corrida corta
```

Los resultados quedan en `resultados/` (JSON completo + tabla `.md`).
La competencia completa con batería es lenta (2× el costo por candidato):
estimar varias horas para las 5 topologías.

## Qué cambió en el código

* `optimizacion_avion/bateria.py` — **nuevo**: modelo de energía/masa/pack/despegue.
* `optimizacion_avion/mision_avion.py` — merge con `viento` + término de
  envergadura + `BATERIA_ACTIVA`; `analizar_mision_avion` ahora es un lazo sobre
  `_analizar_pasada` (la función de antes, con `masa_bateria` opcional).
* `optimizacion_avion/estructura_avion.py` — `converger_masa_avion` acepta
  `masa_sistemas` y `masa_extra` (por defecto, idéntico a antes).
* `optimizacion_avion/geometria_avion.py` — sweep monótono y 11 estaciones.
* `evaluacion_bateria_350km/` — este material.


## Resultados de la corrida corta (viento ON, batería ON, 350 km)

Solo **v_tail** (la ganadora hasta ahora) y **pod_boom**, 12 generaciones cada una,
`--paciencia 4`. **No convergieron**: el puntaje seguía subiendo al cortar. Sirven
para ver órdenes de magnitud, no como diseño final. Tabla completa en
`resultados/resumen_corridas_cortas.md`; JSON con parámetros y análisis en
`resultados/ganadores_*.json`.

| | v_tail | pod_boom |
|---|---|---|
| Masa total | 12.26 kg | 12.98 kg |
| Batería | 4.31 kg (35 %) | 4.64 kg (36 %) |
| Pack (celda M65A) | 12S5P, 60 celdas, 32.5 Ah, ~2 L | 12S5P, 60 celdas, 32.5 Ah, ~2.1 L |
| Alcance logrado | 350 km | 348 km |
| Potencia eléctrica en crucero | 224 W (5.2 A a 12S) | 243 W (5.6 A) |
| Despegue (informativo) | 5.5 kgf, ~36 A (el pack aguanta 130 A) | 5.8 kgf, ~39 A |
| Envergadura / S / AR | 3.54 m / 1.29 m² / 9.7 | 3.45 m / 1.59 m² / 7.5 |
| L/D crucero / V pérdida | 19.6 / 9.45 m/s | 19.1 / 9.10 m/s |

Lo que muestra:

1. **350 km cuestan ~4.3–4.6 kg de batería** con Li-ion de ~270 Wh/kg a nivel pack,
   y el avión pasa de ~7.4–7.8 kg a **12–13 kg**. El tamaño del ala, el fuselaje
   y la estructura crecen para llevar eso.
2. **La corriente no es el problema**: ~5 A en crucero, ~36–39 A en despegue
   contra 130 A que da el pack. La energía manda, no la potencia.
3. **La penalización de envergadura no frena nada**: la meseta gaussiana (tol
   0.4 m) vale ~0 desde ~2.8 m, así que 3.0, 3.4 y 3.5 m cuestan lo mismo
   (≈ −0.3 de puntaje) y el optimizador se queda con la envergadura que mejora
   L/D. Si la idea es de verdad desalentar > 2 m, hay que ensanchar
   `ENVERGADURA_MANUFACTURA_TOL` (o pasar a una penalización lineal) y/o subir
   `PESO_ENVERGADURA`.
4. Los números dependen de `ETA_PROPULSIVA_TOTAL = 0.65` y de la reserva del 20 %
   (la batería escala casi linealmente con ambos).

## Cosas a tener en cuenta

* **Los puntajes no son comparables entre escenarios** (el de `viento` sin
  batería, 5.96, vs. los de acá): cambia el peso del avión, la penalización de
  envergadura resta y los términos de referencia no se recalibraron.
* Las semillas de `semillas.json` quedan inválidas con batería (11 kg y 1.5–2 L
  más de fuselaje); por eso `semillas_bateria.json`. Una por topología sale de
  los ganadores con viento (reparados: fuselaje más grande, ala más grande,
  CG y cola re-afinados cuando hizo falta) y la otra de los ganadores sin viento
  o, si no se pudo reparar, de una variante de la primera.
* Al fusionar con `main` va a haber conflicto en `mision_avion.py` (también lo
  tocó `viento`); la rama ya trae la resolución.
* No se modelan ascenso, descenso ni viento de frente: la reserva del 20 % es lo
  único que los cubre.
