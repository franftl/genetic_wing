# Research Note 16 - Viento de los sitios en la optimización

**Fecha:** 2026-10-02

**Pregunta que dispara la nota:** El optimizador diseñaba el avión con aire a nivel del mar y una ráfaga genérica de 3 m/s, y el viento de los sitios (caracterización con ERA5 en `viento/`) solo se usaba para evaluar los ganadores *después*. ¿Cómo hacer que el viento real entre en la optimización, y cambia el diseño?

**Respuesta corta:**
> Con `VIENTO_ACTIVO = True` en `mision_avion.py`, cada candidato se evalúa con el aire y la ráfaga del peor caso de los dos sitios (Cañadón León y Puesto Hernández), y se suma un término de eficiencia en turbulencia. El efecto dominante es la **densidad**: con aire 14 % más liviano, los ganadores del 18/09 entran en pérdida a 9.0–9.5 m/s y les queda poco margen para volar a 10 m/s. El optimizador responde **agrandando el ala** (S +15–30 % y carga alar ~80 → ~67 N/m² en cuatro de las cinco topologías), recupera la pérdida en ~8.3–8.7 m/s y paga con algo más de masa (hasta +0.75 kg) y algo menos de L/D (~3 %). La **cola en V sigue ganando**. La turbulencia cuesta poco (+1.5–2 % de resistencia) y la ráfaga del sitio (n ≈ 3.1–3.3) no compromete la estructura. Con `VIENTO_ACTIVO = False` todo da exactamente lo mismo que antes.

---

## 1. Qué datos de viento se usan

De las fichas `viento/fichas/*.yaml`, el **peor caso** de los dos sitios para que el avión sirva en cualquiera (constantes en `optimizacion_avion/viento.py`):

| Dato | Antes | Ahora | Origen |
|---|---|---|---|
| Densidad del aire | 1.225 kg/m³ | **1.056 kg/m³** | Puesto Hernández (p05 de verano, a 120 m) |
| Ráfaga vertical de diseño | 3.0 m/s | **4.63 m/s** | 3σ de turbulencia moderada (igual en los dos sitios) |
| Viento medio | 3.1 m/s | 8.9 m/s | Cañadón León, diurno a 120 m (informativo) |
| Viento fuerte | 14.4 m/s | 20.4 m/s | Cañadón León, p95 diurno corregido (informativo) |
| Turbulencia continua | — | σ_w = 1.54 m/s, L_w = 120 m | Dryden de baja altura, moderada, 120 m |

El viento medio y el fuerte no entran en ninguna cuenta: sin un piloto automático que ajuste la velocidad al viento (decisión grupal pendiente), el viento de frente le cuesta lo mismo a todos los diseños (+20 % de energía por misión en Cañadón León) y no ayuda a elegir entre ellos.

## 2. Cómo entra en la optimización

Cambios en `mision_avion.py` (todos bajo `VIENTO_ACTIVO`):

1. **Condiciones** (afectan a los términos que ya existían, sin peso propio): densidad del sitio en las fórmulas y en `AeroBuildup` (vía `atmosphere=`), Reynolds con la viscosidad del sitio, y ráfaga de 4.63 m/s.
2. **Restricción dura:** si la ráfaga del sitio lleva el ala más allá de la carga última (`N_ULTIMO = 4.5`), el candidato se descarta.
3. **Término nuevo: eficiencia en turbulencia**, `1 / (1 + resistencia extra)` con `PESO_TURBULENCIA = 0.75`.

### 2.1 Por qué la turbulencia cuesta energía

La sustentación sube y baja con cada ráfaga, y la resistencia inducida crece con el cuadrado de la sustentación: los picos para arriba cuestan más de lo que ahorran los picos para abajo. Como CL = n·CL_crucero, la resistencia inducida aumenta en un factor (1 + σ_n²), con σ_n la desviación estándar del factor de carga. Las ráfagas horizontales suman (σ_u/V)² de resistencia de perfil. σ_n sale de un modelo de un grado de libertad vertical sobre el espectro de Dryden: el avión "acompaña" las ráfagas largas, y solo las cortas le cambian la sustentación. Verificado contra la simulación dinámica con VLM (Küssner/Wagner) de `viento/codigo_viento`: σ_n = 0.224 simulado contra 0.237 del modelo para el ganador cola en V (el modelo es ~6 % conservador).

### 2.2 Cómo se eligieron los pesos

La idea fue no inventar pesos, sino que cada efecto entre con su precio físico en la misma moneda del puntaje:

- **Densidad y ráfaga:** son condiciones, no términos, así que no llevan peso.
- **Turbulencia, 0.75:** es resistencia, y la resistencia ya tiene precio en el término de eficiencia. Con 0.75, un 1 % de resistencia por turbulencia cuesta lo mismo que un 1 % de resistencia de crucero (PESO_EFICIENCIA · D_REF / D ≈ 3.2/4.3).
- **Estructura frente a la ráfaga:** se evaluó un término con peso y se descartó. Reforzar el ala para la ráfaga del sitio cuesta 1–5 g, porque el larguero ya está dimensionado por rigidez (`manda_rigidez = True` en todos los ganadores), así que su peso "justo" era ≈ 0. Queda solo la restricción de carga última.

Se descartaron las corridas de sensibilidad con varios pesos: con pesos derivados así no hay un número arbitrario que barrer.

### 2.3 Semillas

Con el aire del sitio, las 10 semillas de `semillas.json` entran en pérdida a 10.1–10.6 m/s y son inválidas. Con viento, `competencia.py` arranca desde `semillas_viento.json`, que son los ganadores sin viento del 18/09 (válidos en el sitio). `semillas.json` no se tocó.

## 3. Resultados (corrida del 2026-10-02)

`python viento/optimizar_con_viento.py`: paciencia 8, máximo 35 generaciones (igual que la corrida del 18/09), semilla de azar fija. Ganadores en `optimizacion_avion/ganadores_viento.json`; tabla y gráficos en `viento/resultados_optimizacion/`. Los dos diseños se evalúan **con el viento del sitio**:

| Topología | Diseño | Score | S [m²] | b [m] | W/S [N/m²] | Masa [kg] | L/D | V pérdida [m/s] | n ráfaga |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|
| **Cola en V** | sin viento | 5.654 | 0.911 | 2.89 | 79.8 | 7.41 | 17.57 | 8.95 | 3.09 |
| | **con viento** | **5.964** | 1.105 | 3.36 | 69.5 | 7.82 | 17.13 | 8.29 | 3.23 |
| Cola en T | sin viento | 5.335 | 0.987 | 3.00 | 75.7 | 7.62 | 16.67 | 9.25 | 3.16 |
| | con viento | 5.715 | 1.151 | 3.13 | 66.8 | 7.84 | 16.21 | 8.56 | 3.05 |
| Convencional | sin viento | 5.428 | 0.975 | 2.92 | 75.8 | 7.53 | 16.85 | 9.02 | 3.06 |
| | con viento | 5.677 | 1.168 | 3.25 | 67.5 | 8.03 | 16.08 | 8.35 | 3.07 |
| Pod-boom | sin viento | 5.575 | 0.895 | 3.03 | 80.0 | 7.30 | 17.47 | 9.04 | 3.24 |
| | con viento | 5.637 | 0.917 | 3.13 | 78.9 | 7.37 | 17.11 | 8.98 | 3.25 |
| Doble boom | sin viento | 4.632 | 0.978 | 3.38 | 78.8 | 7.86 | 14.21 | 9.47 | 3.26 |
| | con viento | 5.287 | 1.272 | 3.45 | 66.4 | 8.61 | 14.43 | 8.67 | 3.22 |

Los scores con viento incluyen el término de turbulencia (+~0.73), así que **no se comparan en valor absoluto con los del 18/09**: se comparan diseños evaluados en las mismas condiciones, como en la tabla.

**Lectura:**
- **El viento cambia el diseño:** el ala crece para recuperar el vuelo lento con aire liviano. Es el compromiso esperado: más superficie, menos carga alar, un poco más de masa y algo menos de L/D.
- **La cola en V sigue ganando**, ahora con ala de 3.36 m y AR 10.2.
- El orden de las demás cambia: cola en T sube al 2.º lugar y pod-boom baja al 4.º. **Ojo:** pod-boom paró en la generación 9 por paciencia agotada, partiendo de dos semillas idénticas, y es la única que casi no cambió su ala. Probablemente no exploró lo suficiente: conviene re-correrla con más paciencia antes de sacar conclusiones sobre su posición.
- La turbulencia (+1.5–2 %) y la ráfaga (n ≤ 3.3, lejos de 4.5) no discriminan entre diseños.

## 4. Pendientes y limitaciones

- **Piloto automático:** si se decide que ajuste la velocidad al viento, el viento medio pasa a depender del diseño y conviene sumarlo (energía por misión con la estadística real de viento).
- **Término de ráfaga existente (`PESO_RAFAGA`):** premia Δn < 0.5 g, pero todos los diseños tienen Δn ≈ 1.5–2.2, así que vale ~0 para todos y no discrimina, con o sin viento. Revisar su banda.
- **Carga límite:** la ráfaga del sitio da n ≈ 3.1–3.3, algo por encima de `N_LIMITE = 3.0`. Reforzarlo cuesta gramos, pero conviene decidir si se sube `N_LIMITE`.
- **Pod-boom:** re-correr con más paciencia (ver arriba).
- El modelo de turbulencia no incluye cabeceo ni piloto automático (control de altura); ver `viento.py`.
