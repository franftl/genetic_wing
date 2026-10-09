# Resumen: el viento de los sitios en la optimización

**Branch:** `viento` · **Fecha:** 2026-10-02 · **Autora:** Ivna

Antes, el optimizador diseñaba el avión como si volara en un día calmo a nivel del mar, y el viento solo se usaba para evaluar los ganadores *después*. Con estos cambios, **el viento real de los sitios entra mientras se diseña**: cada candidato se juzga con el aire y las ráfagas del peor caso de Cañadón León y Puesto Hernández.

El detalle técnico está en la [Research Note 16](<../documentos_de_decision/Research Note 16 - Viento de los sitios en la optimizacion (2026-10-02).md>).

---

## 1. Qué se agregó

### Caracterización de viento (carpeta `viento/`)
- Fichas de los dos sitios con datos ERA5 (`fichas/*.yaml`), tablas, figuras e informe (`caracterizacion_viento.pdf`).
- Paquete `codigo_viento/viento_uav`: campos de viento, VLM con viento, respuesta dinámica a ráfagas, operabilidad.
- `optimizar_con_viento.py`: corre la competencia con viento y la compara con la del 18/09.
- `resultados_optimizacion/`: tabla y gráficos "sin viento vs con viento".

### Viento dentro del optimizador (`optimizacion_avion/`)

| Archivo | Tipo | Qué cambia |
|---|---|---|
| `mision_avion.py` | modificado | Interruptor `VIENTO_ACTIVO`. Con `True`: aire del sitio, ráfaga real, regla de rotura y término de turbulencia |
| `viento.py` | nuevo | Datos de los sitios y modelo de turbulencia |
| `ganadores_viento.json` | nuevo | Ganadores con viento. `ganadores.json` no se tocó |

El resto del optimizador (geometría, estructura, algoritmo genético, perfiles, semillas, `competencia.py`, notebook) quedó intacto. Con y sin viento se arranca desde las mismas semillas de Felipe (`semillas.json`). También se agregaron dos líneas al `README.md` y la Research Note 16.

---

## 2. Qué cambia al evaluar un avión (con `VIENTO_ACTIVO = True`)

| | Antes | Ahora | Por qué |
|---|---|---|---|
| Densidad del aire | 1.225 kg/m³ | **1.056 kg/m³** | Aire real de Puesto Hernández (el más liviano) |
| Ráfaga vertical de diseño | 3.0 m/s | **4.63 m/s** | 3σ de turbulencia moderada en los sitios |
| Regla nueva | — | Se descarta si la ráfaga supera n = 4.5 | El ala se rompería |
| Término nuevo | — | Turbulencia, peso 0.75 | Resistencia extra por volar en aire turbulento |

**Cómo se eligió el peso:** 0.75 hace que un 1 % de resistencia por turbulencia cueste en el puntaje lo mismo que un 1 % de resistencia común, así que no es un peso arbitrario. Se evaluó también un término para la estructura frente a la ráfaga, y se descartó: reforzar el ala cuesta 1–5 g, porque el larguero ya está dimensionado por rigidez.

**Compatibilidad:** con `VIENTO_ACTIVO = False` el optimizador da *exactamente* los mismos resultados que el código original. Está verificado con los 5 ganadores del 18/09 en `viento/codigo_viento/tests/test_optimizador_viento.py`; pasan las 18 pruebas.

---

## 3. Resultados

> **Pendiente:** estos números son de la corrida que arrancaba desde los ganadores del 18/09. Hay que volver a correr `optimizar_con_viento.py` con las semillas de Felipe.

| Cola en V (ganadora) | Sin viento (18/09) | Con viento |
|---|---|---|
| Superficie alar | 0.91 m² | 1.10 m² (**+21 %**) |
| Envergadura | 2.89 m | 3.36 m |
| Velocidad de pérdida en el sitio | 8.95 m/s (al límite para volar a 10) | 8.29 m/s (margen cómodo) |
| Masa | 7.41 kg | 7.82 kg |
| L/D en crucero | 17.6 | 17.1 (−3 %) |

- **El viento cambia el diseño:** con aire más liviano, el diseño sin viento quedaba al límite en vuelo lento. El optimizador agranda el ala un 15–30 % para recuperarlo (en 4 de 5 topologías).
- **La cola en V sigue ganando.**
- La **turbulencia** cuesta poco (+1.5–2 % de resistencia) y la **ráfaga** no compromete la estructura (n ≈ 3.1–3.3).

---

## 4. Cómo usarlo

- **Con o sin viento:** `VIENTO_ACTIVO` en `optimizacion_avion/mision_avion.py`.
- **Comparación completa** (~30–45 min): `python viento/optimizar_con_viento.py`
- **Solo rehacer la tabla y los gráficos:** `python viento/optimizar_con_viento.py --solo-comparar`
- **Notebook `02_Optimizacion_Avion.ipynb`:** corre con viento si `VIENTO_ACTIVO = True`. Ojo: la celda de exportación anota la ráfaga como `mis.RAFAGA_VERTICAL` (3.0), aunque con viento se usa 4.63.
- **Pruebas:** `python -m pytest viento/codigo_viento/tests -q`

---

## 5. Pendiente / para charlar con el grupo

- **Piloto automático:** si va a ajustar la velocidad según el viento, conviene sumar al puntaje la energía por misión con viento de frente.
- **Término de ráfaga existente (`PESO_RAFAGA`):** hoy vale ~0 para todos los diseños y no discrimina entre ellos.
- **Carga límite:** la ráfaga del sitio da n ≈ 3.1–3.3, apenas arriba de `N_LIMITE = 3.0`. Decidir si se sube.
- **Pod-boom:** el algoritmo cortó en la generación 9; volver a correrlo con más paciencia.
- **Notebook:** corregir la etiqueta de la ráfaga en la celda de exportación.
