# Research Note 15 - Winglets, volumen mínimo de fuselaje y replanteo de la misión

**Fecha:** 2026-09-18

**Pregunta que dispara la nota:** Tras la primera corrida de la competencia entre 5 topologías (convencional, cola en T, cola en V, doble boom, motovelero pod-boom), ningún avión ganador lleva winglets, y varias semillas no parecen tener lugar físico para la carga útil declarada. Además, surgió en paralelo la pregunta de cuánta batería hace falta para 300 km de alcance a 120 km/h. ¿Por qué el optimizador descarta los winglets, hay que forzarlos, cómo se fija un volumen mínimo de fuselaje de forma que sea fácil de ajustar, y qué dice todo esto sobre la misión de diseño?

**Respuesta corta:**
> Los winglets no se estaban "perdiendo" por un error: a 120 km/h el CL de crucero es tan bajo que un winglet es una penalización neta de arrastre (crossover de Maughmer en V≈18.6 m/s / CL≈0.35, muy por debajo de crucero). El análisis de alcance con batería mostró además que pedir 300 km volando a 120 km/h exige ~8.6 kg de batería (más que duplica el peso del avión) porque el alcance eléctrico se maximiza a resistencia mínima, cerca de 70-80 km/h, no a 120. Con el usuario se decidió bajar el crucero de DISEÑO a 80 km/h (ahí se optimiza eficiencia/alcance) y dejar 120 km/h como una velocidad MÁXIMA exigida (ráfagas/viento) que también pesa en el puntaje pero ya no lo domina. Con ese cambio el trade-off del winglet mejora pero se deja que el algoritmo genético decida, sin forzar geometría. Por separado, se confirmó numéricamente que 7 de 10 semillas no entraban el volumen de carga útil a una utilización de empaquetado razonable (55%): se agregó una restricción dura de volumen mínimo de fuselaje, con dos constantes declaradas y fáciles de mover (`VOLUMEN_UTIL_MIN_L`, `FACTOR_UTILIZACION_VOLUMEN` en `mision_avion.py`).

---

## 1. Por qué el optimizador descarta los winglets

### 1.1 El arrastre inducido depende de CL², y CL depende de la velocidad

Con `asb.AeroBuildup` se puede separar `D_induced` de `D_profile`. Para el avión de la topología convencional (semilla A), la fracción de arrastre que es inducido cae fuerte con la velocidad:

| Punto de vuelo | CL | Arrastre inducido / total |
|---|---|---|
| Crucero 120 km/h (misión anterior) | 0.108 | 2.9% |
| 20 m/s | ~0.25 | 18.1% |
| Vuelo lento 10 m/s | ~1.2 | 73.0% |

Un winglet ataca específicamente el arrastre INDUCIDO (redistribuye la circulación en punta de ala para reducir el vórtice de punta). Si el inducido es solo 2.9% del arrastre total, no hay mucho margen para ahorrar, mientras que el winglet igual paga su propio arrastre de perfil (superficie mojada extra) todo el tiempo.

### 1.2 La velocidad de cruce de Maughmer (V_CR)

Maughmer (2003, *"The Design of Winglets for Low-Speed Aircraft"*, Technical Soaring / AIAA) formaliza esto: para cualquier winglet hay una velocidad de cruce V_CR (o el CL equivalente) por debajo de la cual el ahorro de arrastre inducido supera la penalización de arrastre de perfil, y por encima de la cual ocurre lo contrario.

Se calculó V_CR numéricamente para nuestro avión, comparando el mismo diseño con `winglet_height=0.15` contra `winglet_height=0.0` en un barrido de velocidades:

| V [m/s] | D_con - D_sin |
|---|---|
| 10 | -8.6% (ahorra) |
| 16 | ahorra, cada vez menos |
| **18.6** | **≈ 0 (cruce), CL ≈ 0.347** |
| 20-33.3 | penaliza |
| 33.3 (120 km/h) | **+2.72%** |

Con la misión anterior (crucero 120 km/h, CL≈0.108) el punto de diseño estaba muy por encima de V_CR: el winglet SIEMPRE perdía en crucero, y solo ganaba (-8.57% de arrastre) en el punto de vuelo lento, que pesa menos en el puntaje que la eficiencia de crucero. El GA, correctamente, los elimina.

### 1.3 Dos razones adicionales por las que el winglet rinde poco en ESTE avión

- **Envergadura libre compite con el winglet.** Scholz (2018, *"On the Aerodynamic Efficiency of Winglets"*, DGLR) mide que los winglets reales entregan en promedio ~36% del beneficio que daría una extensión de envergadura equivalente en momento flector en la raíz (y hasta apenas 5.3% en el caso peor medido, B737-800). Como nuestra envergadura YA es una variable libre (no estaba antes), el optimizador tiene una palanca más barata que el winglet para el mismo objetivo: alargar el ala.
- **Ya hay cola vertical.** Hepperle (DLR, *"Aerodynamic Design of Winglets"*) señala que el caso donde el winglet realmente paga en estabilidad direccional es cuando REEMPLAZA a una deriva vertical inexistente (ala volante). Nuestras topologías con cola YA tienen deriva vertical (o en V), así que el winglet no está comprando estabilidad direccional adicional, solo aerodinámica pura -- y ahí compite en desventaja con extender envergadura.
- **A bajo Reynolds el winglet se degrada.** A Re 2-7×10⁵ (nuestro rango) aparecen burbujas de separación laminar; la resistencia de perfil aproximadamente se DUPLICA al partir el Reynolds a la mitad (Weierman, tesis MS Wichita State, 2010). Nikolaou et al. (2025, mini-UAV, Re=3.86×10⁵) midieron experimentalmente un winglet con +4.48% de CL_max pero TAMBIÉN +1.29% de CD_min -- el mismo trade-off que estamos viendo acá, medido en un avión real de esta escala.

### 1.4 Decisión

No se fuerza geometría de winglet. Se recalcula el trade-off con la misión nueva (crucero de diseño a 80 km/h, más cerca del cruce V_CR) y se deja que el GA decida -- es la respuesta físicamente honesta, y es la que el usuario eligió.

---

## 2. Volumen mínimo de fuselaje

### 2.1 El problema es real y medible

Con `avion.fuselages[0].volume()` se midió el volumen geométrico de las 10 semillas existentes (2 por topología) y se comparó contra el volumen requerido:

**Volumen requerido** (anclajes de literatura, ver Research Notes previas sobre selección de UAV): 3.0 kg de carga útil a 0.5 kg/L (densidad de empaque declarada del Penguin B UAV, bahía de 20 L para 10 kg de payload) = 6.0 L, más batería (~0.5 L a densidad de pack típica 2.0-2.15 kg/L) más aviónica (1.67 L estimados) = **8.17 L**.

**Resultado sobre las semillas viejas** (antes de este cambio): 7 de 10 no entraban ese volumen a un 55% de utilización de empaquetado -- sobre todo `doble_boom` y `pod_boom`, que por diseño llevan fuselaje/góndola corto, y hasta la semilla "B" (más esbelta) de las topologías con cola.

### 2.2 Formulación de la restricción

Estándar de MDO de aeronaves: la restricción de volumen se trata como una restricción geométrica dura, no como un término suave del puntaje (Hajdik, Adler & Martins, *"Physics-Based Aerostructural Optimization of Conventional and Strut-Braced Wing Aircraft"*, AIAA 2023-3589, sección de restricciones de empaquetado):

```
g(x) = V_requerido - eta_vol * V_geometrico(x) <= 0
```

No hay un `eta_vol` (factor de utilización volumétrica) publicado para UAV de esta escala en Roskam, Raymer o Torenbeek -- las tablas que existen son para aviones tripulados con bahías de carga estandarizadas. Se adopta **0.55** como supuesto de ingeniería declarado (construcción artesanal, con margen para estructura, acceso y montaje), y se lo deja como constante fácil de mover, exactamente como pidió el usuario.

### 2.3 Implementación

En `mision_avion.py`:

```python
VOLUMEN_UTIL_MIN_L = 8.2              # [L] volumen util requerido
FACTOR_UTILIZACION_VOLUMEN = 0.55     # fraccion del volumen geometrico aprovechable
```

Y en `analizar_mision_avion`, apenas se construye la geometría (antes de correr ningún AeroBuildup, para no gastar evaluaciones en un candidato que ya se sabe inválido):

```python
vol_geo_L = float(avion.fuselages[0].volume()) * 1000.0
if vol_geo_L * FACTOR_UTILIZACION_VOLUMEN < VOLUMEN_UTIL_MIN_L:
    return None
```

`fuselages[0]` es siempre el fuselaje o góndola PRINCIPAL (donde va la carga), nunca las vigas del doble boom, que no cargan payload -- eso está garantizado por cómo `construir_avion` arma la lista de fuselajes (ver `geometria_avion.py`).

### 2.4 Consecuencia sobre el espacio de diseño

`doble_boom` y `pod_boom` tienen el fuselaje/góndola corto por diseño (esa es la esencia de la topología: casi toda la superficie mojada de cola vive en la viga, no en un fuselaje largo). Para que sigan siendo candidatos viables, se amplió el bound superior de `fuselaje_diametro` de 0.24 m a **0.32 m** SOLO para esas dos topologías (`BOUNDS_DOBLE_BOOM`, `BOUNDS_POD_BOOM` en `geometria_avion.py`): como el volumen de un cuerpo de revolución crece con el CUADRADO del radio, engordar el fuselaje corto es la palanca más barata que tienen estas topologías para no perder por empaquetamiento, ya que no pueden alargarse tanto como el convencional sin perder la ventaja de arrastre que las hace atractivas. Se regeneraron las semillas (`gen_semillas.py`) con diámetros mayores (0.155→0.20-0.26 m según topología y semilla) para que las 10 semillas sean válidas bajo la restricción nueva.

---

## 3. Alcance con batería y el replanteo de la misión

### 3.1 El bucle de realimentación de masa

Se preguntó: a 120 km/h, con 237 W de consumo y rendimiento estándar de hélice+motor, ¿qué batería hace falta para 300 km? La respuesta no es un cálculo lineal porque más batería pesa, lo que aumenta la resistencia inducida, lo que exige más batería:

```
R = E * eta / D(m_total)          eta = eta_helice * eta_motor * eta_ESC ~ 0.59
m_bateria = R * D / (eta * E_esp * frac_util)      -- iterativo, con relajación
```

Resultado (aeronave convencional, semilla previa, iterando hasta converger):

| Velocidad | Batería p/300 km | Masa total | L/D |
|---|---|---|---|
| 120 km/h | **8.63 kg** | 15.71 kg | 14.8 |
| 90 km/h | 5.60 kg | 12.69 kg | 18.4 |
| 70 km/h | 4.30 kg | 11.39 kg | **21.5 (óptimo)** |
| 50 km/h | 5.08 kg | 12.17 kg | 19.5 |

El alcance eléctrico R = E·η/D se maximiza volando a resistencia mínima, que para este avión cae cerca de 70-80 km/h, no a 120 km/h. Pedir 300 km *a 120 km/h* exige casi 8.6 kg de batería sobre un avión de ~7 kg en seco -- viable desde la celda (200 Wh/kg × 8.63 kg = 1726 Wh alcanzan) pero no desde la misión tal como estaba definida.

### 3.2 Decisión con el usuario

Se separan los roles de velocidad:

- **Crucero de DISEÑO: 80 km/h.** Es donde se optimizan eficiencia (arrastre), estabilidad estática, margen de ráfaga y trim -- el punto donde el avión pasa la mayor parte de la misión y de donde sale el alcance.
- **Velocidad MÁXIMA: 120 km/h**, sigue siendo un requisito (ráfagas / viento en contra), pero cambia de rol: ya NO es el punto de diseño. Entra como restricción dura (que el ala se sostenga ahí sin entrar en pérdida) Y como término adicional de puntaje (`PESO_VELMAX = 0.5`, la mitad del peso de la eficiencia de crucero), porque el usuario pidió explícitamente que 120 km/h también pese en el score, no que sea solo un gate binario.
- **Vuelo lento: 10 m/s**, sin cambios.

Esto convierte la misión de 2 a **3 puntos de vuelo**. Implementado en `mision_avion.py` (ver el encabezado del módulo, sección "ACTUALIZACIÓN 2026-09-18").

---

## 4. Cambios de código -- resumen

| Archivo | Cambio |
|---|---|
| `mision_avion.py` | `V_CRUCERO` baja a 80 km/h (22.2 m/s); nuevo `V_MAX = 120/3.6`; nuevo punto de vuelo a V_MAX con restricción dura + término de puntaje `PESO_VELMAX`; `D_REFERENCIA` recalibrado a 80 km/h, nuevo `D_REFERENCIA_VMAX`; nuevas constantes `VOLUMEN_UTIL_MIN_L=8.2`, `FACTOR_UTILIZACION_VOLUMEN=0.55`; restricción dura de volumen de fuselaje |
| `geometria_avion.py` | `fuselaje_diametro` ampliado a (0.10, 0.32) para `doble_boom` y `pod_boom` |
| `gen_semillas.py` | Diámetros de fuselaje/góndola aumentados en varias semillas para cumplir el volumen mínimo bajo la misión y restricción nuevas |
| `semillas.json` | Regenerado; las 10 semillas (5 topologías x 2) son válidas bajo la misión y restricciones nuevas |
| `__init__.py` | Exporta `V_MAX`, `VOLUMEN_UTIL_MIN_L`, `FACTOR_UTILIZACION_VOLUMEN` |

No se tocó nada de `perfiles_avion.py`, `estructura_avion.py`, `ga_numerico_avion.py`, `evolucion_avion.py` ni `competencia.py` -- el cambio es enteramente de definición de misión y restricciones, no de mecánica del algoritmo.

---

## Fuentes

- Maughmer, M. D. (2003). *The Design of Winglets for Low-Speed Aircraft*. Technical Soaring / AIAA.
- Scholz, D. (2018). *On the Aerodynamic Efficiency of Winglets*. DGLR.
- Hepperle, M. (DLR). *Aerodynamic Design of Winglets*. mh-aerotools.de.
- Weierman, R. (2010). *Winglet Design and Optimization for UAVs*. MS Thesis, Wichita State University.
- Nikolaou, N. et al. (2025). Experimental winglet study on a mini-UAV at Re≈3.86×10⁵.
- Hajdik, H., Adler, E., Martins, J. R. R. A. (2023). *Physics-Based Aerostructural Optimization of Conventional and Strut-Braced Wing Aircraft*. AIAA 2023-3589.
- Zahm, Smith & Louden (1928). NACA Report 291, fineness ratio óptimo de fuselaje.
- Roskam, J. *Airplane Design*, Parts I-VI (empaquetado y fuselaje, referencia general).
- UAV Factory, especificación pública del Penguin B (densidad de empaque payload/volumen de bahía).
- Datos de densidad de pack de batería: Tattu 6S 22000 mAh, celdas Samsung 18650 (hojas de datos de fabricante).
