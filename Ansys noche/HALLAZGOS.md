# Hallazgos de la noche CFD (2026-10-28)

_Archivo vivo: se va actualizando durante la corrida. Plan: `herramientas/PLAN_NOCHE_CFD.md`. Lanzado 00:35, límite 08:30._

## Estado
- 00:35 — lanzado `herramientas/correr_noche.ps1 -Limite 08:30` (malla grande con estela → barrido SST/Transition SST → calibración).
- Antes de arrancar: sin procesos `fluent.exe` huérfanos, equipo enchufado, suspensión en AC = nunca, 575 GB libres.
- Logs: `resultados/cfd_run/log_noche_master.txt`, `log_noche_malla.txt`, `log_noche_cfd_*.txt`, `log_noche_calibracion.txt`.
- Malla grande en curso al momento de escribir esto; todavía no hay resultados.

## Hallazgos
1. **Cuelgue de `mallar_fluent.py` con ruta relativa (00:35–01:11, ~35 min perdidos).** `correr_noche.ps1` pasa `--step encl_grande.step` (relativo) y el script lanza Fluent con `cwd=resultados/cfd_run`; Fluent no encuentra el archivo y se queda esperando sin error (CPU ≈ 0, el log no pasa de "Fluent version 2024 R1"). Con ruta absoluta la importación de `encl_red_v2.step` tarda 19 s. Arreglo: `mallar_fluent.py` hace `.resolve()` de `--step` y `--estela` y sale con mensaje si no existen. (Probado con `encl_red_v2.step`; el grande se ve en la corrida.)
3. **Malla grande OK (01:16):** `malla_grande.msh.h5`, 2 559 801 celdas (183 k hex, 563 k poly, 1.81 M prismas), ortogonalidad mínima 0.0686, aspecto máx. 3194, 288 s. Dominio x [−5000, 11850], y [0, 6700], z [±5300] mm. **La estela probablemente no refinó:** celdas e hexaedros casi idénticos a la v5 (2.56 M / 0.18 M) pese a la caja de 200 mm; sin verificar con medición de tamaño de celda.
4. En el solver: `transition-sst` es un nombre válido en Fluent 24.1 y `m_walls` pasa a velocity-inlet sin error (ambos estaban sin verificar).
5. **Bugs de turbulencia de entrada (01:27):** con Transition SST la opción es `"Intermittency, Intensity and Viscosity Ratio"`; la razón de viscosidades se llama `turbulent_viscosity_ratio_real` (con el nombre viejo fallaba sin avisar, también en las corridas k-ω anteriores; el default ya era 10). Corregido en `correr_cfd_fluent.py::_set_viento`. Barrido relanzado 01:28.
6. **Transition SST, α = 0°, malla grande (parcial, ~13 s/it):** it 100 L 71.1 / D 6.20; it 200 71.4 / 6.14; it 300 71.55 / 6.13; it 400 71.3 / 6.15 N (avión completo). CD ≈ 0.0228 (S = 1.2134 m²) vs 0.0284 de la CFD vieja (k-ω, recinto chico) y 0.0148 del modelo; CL ≈ 0.225 vs 0.244 vieja y 0.240 modelo. Oscila ±0.4 %, por lo que el criterio de 0.3 % no corta; el grupo puede gastar hasta 800 it (~2.9 h) en este ángulo. Provisional hasta que el script lo marque.
   **CORRECCIÓN y cierre (04:29):** el CD de arriba (0.0228) estaba mal calculado. Resultado oficial del script, 800 it (máximo), **NO convergió** (oscila ±0.4 % en L, ±0.7 % en D): L 71.48 N, D 6.153 N, **CL 0.2260, CD 0.01945**, L/D 11.6, y+ medio 0.671, 13.1 s/it. CD baja de 0.0284 (CFD vieja) a 0.0195 (modelo 0.0148) → **H2 apoyada, con la salvedad de que el punto no convergió.** CL(0°) casi igual a la CFD vieja y al modelo (0.226 / 0.244 / 0.240).
7. **Transition SST, α = 4°, malla grande (05:19): CONVERGIÓ** (200 it, 12.5 s/it, var L 0.14 %, var D 0.25 %): L 266.6 N, D 10.33 N, **CL 0.8429, CD 0.03265**, L/D 25.8, y+ medio 0.63 (máx 3.05). Contra modelo 0.639 / 0.0176 y CFD vieja 0.358 / 0.0492.
   - **H1 (recinto/tapas aplastan la pendiente): apoyada** — con el recinto grande la pendiente pasa de 0.285× a ≈ 1.55× la del modelo (dCL/dα = (0.843 − 0.226)/4 = 0.154 /° vs 0.099 /°).
   - **Pero sobrepasa al modelo y no lo explico:** 0.154 /° es mayor que lo que da una ala de este alargamiento por teoría clásica; revisar antes de concluir que el modelo subestima (posibles causas a mirar: tapas velocity-inlet que fuerzan el flujo inclinado en todo el borde, cola/fuselaje, sólo dos ángulos). Con CL(1.21°) y un tercer ángulo se ve si es lineal.
   - CD a α = 4° baja de 0.0492 a 0.0326, pero a igual CL (0.84) el modelo daría bastante más: no comparable punto a punto; comparar a igual CL con el script de calibración.
8. **k-ω SST, α = 4°, malla grande (06:00): CONVERGIÓ** (300 it, 9.3 s/it; L y D idénticos entre it 200 y 300, estado estacionario): L 261.6 N, D 13.44 N, **CL 0.8269, CD 0.04248**, L/D 19.5, y+ medio 0.75. Separación de efectos a 4° (mismo recinto grande): SST → Transition SST cambia CL 0.827 → 0.843 (+2 %) y CD 0.0425 → 0.0327 (−23 %). Recinto chico → grande (SST) cambia CL 0.358 → 0.827 y CD 0.0492 → 0.0425. Conclusión parcial: **el CL lo gobierna el recinto/tapas (H1); el CD lo gobierna sobre todo el modelo de turbulencia (H2) y algo el recinto (H3 débil).** El sobrepaso de CL respecto del modelo (0.83–0.84 vs 0.639) persiste con ambos modelos, así que no es de turbulencia.
9. **Transition SST, α = 1.21° (crucero), malla grande (07:40): CONVERGIÓ** (400 it, 12.8 s/it): L 130.96 N, D 6.680 N, **CL 0.4140, CD 0.02112**, L/D 19.6, y+ medio 0.65. Modelo: CL 0.361, CD 0.01766 (L 114.2 N, D 5.59 N). CFD/modelo: L +14.7 %, D +19.5 %. Con 0° (0.226), 1.21° (0.414) y 4° (0.843) la curva es lineal: 0.155 /° y 0.154 /° (modelo 0.099 /°). Es decir que a crucero la diferencia es moderada (+15 % en L) porque ahí las dos curvas casi se cruzan; a 4° el CFD da +32 % de CL.
10. **Transition SST, α = 8° (08:00): CONVERGIÓ** en 150 it (12.1 s/it): L 454.9 N, D 21.01 N, **CL 1.4382, CD 0.06641**, L/D 21.7, y+ medio 0.67. Sigue la recta (0.843 + 4 × 0.149 ≈ 1.44): **sin pérdida en este rango**. Un CL de 1.44 con este perfil/alargamiento a 8° es físicamente dudoso y no lo pude contrastar con el modelo (no está corrido a 8°); apunta, junto con la pendiente de 0.154 /°, a que la CFD sobre-sustenta (hipótesis: tapas velocity-inlet que imponen el flujo inclinado en todo el borde del dominio → circulación inducida mayor que en campo libre). Para probarlo: repetir 4° con tapas `pressure-far-field` o rotando el avión en vez de inclinar el viento.
11. 08:00 arrancó el grupo k-ω SST (0°, 1.21°, 8°); con 30 min hasta el límite probablemente el script lo corte por tiempo.
2. Relanzada la noche a las 01:11. Los `fluent.exe`/`cx2410.exe` huérfanos de las pruebas se cerraron por PID.

12. **Cierre de la corrida (08:24, antes del límite de 08:30):** el script cortó solo ("no alcanza el tiempo para alfa 1.21" del grupo SST) y corrió la calibración. Último punto: **k-ω SST, α = 0°, recinto grande: CONVERGIÓ** (200 it, 9.4 s/it): L 73.72 N, D 8.979 N, CL 0.2331, **CD 0.02838**, L/D 8.2, y+ medio 0.77. Es igual (CD 0.0284) a la CFD vieja con recinto chico → **H3 rechazada**: a igual modelo el recinto no cambia el CD de α = 0°.
13. Huérfanos: quedaba un `fluent.exe` (PID 28632) y su `cx2410.exe` de la 01:27; cerrados por PID al revisar. 0 procesos de Fluent vivos.
14. Gráficos y tabla (09:50): `comparacion_cfd_aerobuildup.png` y `tabla_cfd_aerobuildup.csv` en esta carpeta, hechos con `herramientas/graficar_hallazgos_noche.py` (CFD hueca = no convergió; incluye la CFD vieja de recinto chico y AeroBuildup a los mismos α).

## Tabla CFD vs AeroBuildup (mismo α)
| Serie | α | Conv. | CL cfd | CL AB | ΔCL | CD cfd | CD AB | CD cfd/AB |
|---|---|---|---|---|---|---|---|---|
| Transition SST, recinto grande | 0 | no | 0.226 | 0.240 | −5.8 % | 0.01945 | 0.01475 | 1.32 |
| Transition SST, recinto grande | 1.21 | sí | 0.414 | 0.361 | +14.8 % | 0.02112 | 0.01765 | 1.20 |
| Transition SST, recinto grande | 4 | sí | 0.843 | 0.639 | +31.9 % | 0.03265 | 0.03004 | 1.09 |
| Transition SST, recinto grande | 8 | sí | 1.438 | 1.022 | +40.7 % | 0.06641 | 0.05948 | 1.12 |
| k-ω SST, recinto grande | 0 | sí | 0.233 | 0.240 | −2.8 % | 0.02838 | 0.01475 | 1.92 |
| k-ω SST, recinto grande | 4 | sí | 0.827 | 0.639 | +29.4 % | 0.04248 | 0.03004 | 1.41 |
| k-ω SST, recinto chico (vieja) | 0 / 1.21 / 4 | sí | 0.244 / 0.279 / 0.358 | | +2 / −23 / −44 % | 0.0284 / 0.0334 / 0.0492 | | 1.93 / 1.89 / 1.64 |

Calibración (`resultados/calibracion_cfd.json`, solo convergidos): Transition SST (3 pts): CL_cfd = 1.549·CL_ab − 0.146; CD_cfd = CD_ab + 0.00228 + 0.00209·CL² (rms 8.5 cuentas). SST (2 pts): solo indicativa. **No usar para corregir el optimizador todavía** (pocos puntos y la pendiente de CL no está explicada).

## Hipótesis (ver PLAN_NOCHE_CFD.md §2 y §8)
- **H1 recinto/tapas aplastan la pendiente de CL — CONFIRMADA** (CL(4°) 0.358 → 0.827 al pasar al recinto grande). Pero la CFD ahora **sobre-sustenta** (+32 % a 4°, +41 % a 8° sobre AeroBuildup; pendiente 0.154 /° vs 0.099 /°): ni el modelo ni la CFD están validados a α ≥ 4°.
- **H2 exceso de CD por modelo totalmente turbulento — CONFIRMADA en lo principal:** Transition SST baja el CD a 1.09–1.32× AeroBuildup (SST: 1.41–1.92×). A α = 0° el punto no convergió (±0.9 % en D).
- **H3 estela/dominio agregan resistencia espuria — RECHAZADA** (CD(0°) SST idéntico en ambos recintos). Nota: la estela refinada probablemente no se aplicó.

## Pendiente / próximos pasos
1. Probar la sobre-sustentación: 4° con tapas `pressure-far-field` o con el avión rotado en vez del viento inclinado (árbol de decisión §8 del plan, rama "CL ≈ 0.36" no aplica; esta es una rama nueva).
2. Verificar si la estela se refinó (medir tamaño de celda en x ∈ [0, 4.5] m).
3. Criterio de convergencia sobre media móvil (Transition SST oscila ±0.4 %).
4. Corridas faltantes del plan: SST a 1.21° y 8°; Transition SST a −2°; α = 0° de Transition SST convergido.
5. Git no funciona en este entorno: archivos nuevos/modificados para commitear a mano (ver abajo).
