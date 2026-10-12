# Research Note 17 — Selección de baterías para 350 km (2026-10-12)

**Estado:** propuesta para evaluar. Rama `bateria-350km`. Los números salen del modelo de la rama (`optimizacion_avion/bateria.py`) y de corridas cortas del optimizador que **no convergieron**; sirven para decidir el orden de magnitud y la celda, no para dimensionar el pack final.

## 1. Requisito y qué pide

Volar **350 km a 80 km/h constantes** (4.375 h), con `viento` activo. Es lo que dejó fija la misión de la Research Note 15 (crucero a 80 km/h, donde el alcance eléctrico es máximo).

Primera estimación a mano (300 km, v_tail del 18/09, 7.4 kg): 96 W aerodinámicos / 0.65 = 148 W eléctricos → ~700 Wh → ~4 kg de batería, más de la mitad del avión. Eso ya mostraba que el problema es la **energía**, no la potencia.

Con la batería dentro del lazo de diseño (la batería pesa → sube la resistencia → hace falta más batería), las corridas cortas de v_tail y pod_boom dan:

| | v_tail | pod_boom |
|---|---|---|
| Masa total del avión | 12.3 kg | 13.0 kg |
| Potencia eléctrica en crucero | 224 W | 243 W |
| Energía requerida (con 20 % de reserva) | ~1.18 kWh | ~1.28 kWh |
| Masa de batería (modelo) | 4.3 kg (35 %) | 4.6 kg (36 %) |
| Corriente en crucero / en despegue | 5 A / ~36 A | 6 A / ~39 A |

Conclusión del requisito: **~1.2 kWh y ~4.5 kg**, con corrientes bajas. Se necesita una celda de **alta energía específica**; la capacidad de entregar corriente importa poco.

## 2. Decisiones y por qué

**Química: Li-ion cilíndrica (21700), no LiPo.** La ventaja de la LiPo es la corriente (C-rate alto). Acá el pack pide ~5 A en crucero y ~40 A en despegue, y un pack de 5 celdas en paralelo entrega entre 50 y 130 A continuos según la celda. Sin necesidad de potencia, conviene la celda con más Wh/kg, más barata por Wh y más robusta mecánicamente. (Las cifras de LiPo, ~150–200 Wh/kg a nivel pack, son rangos típicos de la discusión previa y no se re-verificaron.)

**Formato: 21700 en vez de 18650.** Es el mismo formato de las celdas de los Tesla Model 3/Y; las 2170/4680 *de Tesla* no se venden sueltas, pero Molicel, LG y Samsung fabrican 21700 comerciales con más capacidad por celda que una 18650.

**Tensión: 12S.** Con 24S la corriente baja a la mitad, pero los motores de 24S del mercado son de carga pesada (10–15 kgf de empuje), muy sobredimensionados para ~5–6 kgf. A 12S hay mucha oferta de motores y ESC y un BMS estándar. Alternativa: 14S, ver §4.

**Empuje de despegue.** Con T/W = 0.45 sobre el avión de 12–13 kg salen **5.5–5.8 kgf** (≈36–39 A a 12S). El 3.0–3.7 kgf de la primera estimación era para el avión de 7.4 kg sin batería explícita.

## 3. Comparación de celdas

Datos de hoja de datos (aboutenergy.io, Voltt Battery Library). Pack 12S dimensionado para **1.18 kWh**; masa de pack = masa de celdas × 1.15 (níquel, BMS, cableado, funda).

| Celda | Ah | g | Wh/kg celda | I continua | Configuración | Energía instalada | Masa de pack | Corriente del pack |
|---|---|---|---|---|---|---|---|---|
| **Molicel M65A** | 6.5 | 74.5 | **314** | 26 A (4C) | 12S5P (60) | 1404 Wh | **5.1 kg** | 130 A |
| LG M58T | 5.57 | 73.2 | 273 | 12.5 A | 12S5P (60) | 1200 Wh | 5.1 kg | 62 A |
| Samsung 50G | 4.85 | 69.5 | 253 | 9.7 A | 12S6P (72) | 1268 Wh | 5.8 kg | 58 A |
| Molicel P42A | 4.2 | 70 | 216 | 45 A (10.7C) | 12S7P (84) | 1270 Wh | 6.8 kg | 315 A |

Lectura:
- **M65A es la mejor** en masa por energía (314 Wh/kg) y además deja 130 A de margen. Con la misma cantidad de celdas (60) que la M58T entrega 17 % más energía.
- La **M58T** es la alternativa razonable si la M65A no se consigue: misma masa de pack con menos energía instalada (1200 Wh, justo sobre lo requerido) y la mitad del margen de corriente (62 A, aún 1.6× el despegue).
- La **50G** y sobre todo la **P42A** pesan 0.6–1.6 kg más. La P42A es una celda de potencia: su 45 A por celda no se aprovecha acá.

## 4. Redondeo del pack: cuidado con los 4.3 kg

El modelo usa una masa **continua** (energía / 273 Wh/kg = 4.3 kg). Un pack real es discreto: el 12S5P de M65A pesa **5.1 kg** y tiene 19 % más energía de la necesaria; un **12S4P** pesa 4.1 kg pero da 1123 Wh, o sea ~334 km, no 350.

Por eso conviene no atarse a 12S: un **13S4P** (52 celdas, 1217 Wh, ~4.5 kg, ≈363 km) o un **14S4P** (56 celdas, 1310 Wh, ~4.8 kg, ≈390 km) calzan mejor. 14S es una tensión de ESC y motor habitual. Hay que elegir el motor y el ESC primero y cerrar la serie después.

## 5. Sensibilidad (sin contar la realimentación por peso, que amplifica un poco más)

| Supuesto | Valor | Energía/masa de batería vs. base |
|---|---|---|
| Rendimiento propulsivo | 0.55 / **0.65** / 0.75 | +17 % / base / −13 % |
| Reserva de energía | 10 % / **20 %** / 30 % | −8 % / base / +8 % |

El rendimiento propulsivo (hélice × motor × ESC) es el supuesto que más mueve el resultado y **no está medido**: se afina apenas haya hélice y motor elegidos (`bateria.ETA_PROPULSIVA_TOTAL`).

## 6. Recomendación y pendientes

**Recomendación provisoria:** celda **Molicel M65A (21700)**, pack de ~1.2–1.4 kWh en 12S5P o 13–14S4P (4.5–5 kg), con M58T como respaldo.

Pendientes antes de comprar:
1. **Verificar las hojas de datos del fabricante.** Los valores de la tabla vienen de una biblioteca de terceros.
2. **Medir/estimar el rendimiento hélice+motor+ESC** y volver a correr (`ETA_PROPULSIVA_TOTAL`).
3. **Disponibilidad, precio e importación** a Argentina; el envío de baterías de litio es mercancía peligrosa. No se investigó.
4. **Diseño del pack:** BMS de la serie elegida, soldadura de las tiras, protección térmica, ubicación (≈2.0–2.3 L de volumen) y su efecto sobre el CG, que el modelo no ve.
5. **Corridas completas del optimizador** (las de acá son de 12 generaciones y siguen mejorando).
6. **Lo que el modelo no incluye:** ascenso/descenso aparte, viento de frente, degradación y curva de descarga de la celda. La reserva del 20 % los cubre de forma gruesa.
