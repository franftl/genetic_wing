# CFD con PyFluent — cómo correrlo y qué falta

Pipeline: `herramientas/fluent_pipeline.py` (**borrador sin probar**: la primera corrida va a pedir ajustes de nombres de comandos de PyFluent según la versión de Ansys; se corrigen iterando con el mensaje de error, idealmente desde VS Code con Claude Code, que ejecuta y corrige en tu PC).

## 1. Requisitos
- Ansys Fluent con licencia, y la variable de entorno de la versión (`AWP_ROOT251`, etc.; el instalador la crea).
- Python en Windows y `pip install ansys-fluent-core`.
- Un STEP con el **dominio fluido** (caja menos el avión), **medio modelo** (plano de simetría en y = 0), en mm. Ejes: x hacia atrás, y a la derecha, z hacia arriba.

## 2. Armar el dominio (hacer esto primero)
Distancias mínimas del avión a las fronteras (avión: x de 0 a 1.79 m, semienvergadura 1.68 m, z de −0.08 a +0.33 m):

| Frontera | Mínimo |
|---|---|
| Aguas arriba | 5 m (3 m aceptable para una prueba) |
| Aguas abajo | 10 m (8 m aceptable) |
| Lateral | 5 m (3 m aceptable) |
| Vertical (arriba y abajo) | 5 m (3 m aceptable) |

Recomendado: x de −5 a 11.8 m, y de 0 a 6.7 m, z de −5.1 a 5.3 m.
Nombrar las caras exteriores: `inlet`, `outlet`, `symmetry` (plano y = 0), y las laterales y tapas como simetría o campo lejano — **no** como pared con no-slip. El avión es `plane`.

Chequeo (no usa Ansys):
```
python herramientas\fluent_pipeline.py --step encl_red_v3.step --solo-chequeo
```
Historial: `encl_red.step` (8.3 × 2.5 × 1.0 m) y `encl_red_v2.step` (11.3 × 2.5 × 3.0 m) quedan chicos en lateral y aguas arriba.

## 3. Correr
Desde PowerShell, en la carpeta del repo:
```
python herramientas\fluent_pipeline.py --step encl_red_v2.step --alpha 1.21 --malla rapida
python herramientas\fluent_pipeline.py --alpha 1.21 --sin-malla --modelo k-omega     # mismo caso con SST puro
python herramientas\fluent_pipeline.py --alpha 0 1.21 4 --sin-malla                  # barrido, reusa la malla
```
Opciones: `--malla rapida|fina`, `--modelo transition-sst|k-omega`, `--iteraciones 1500`, `--procesos 8`, `--gui`.
Salidas en `resultados/cfd_run/`: `malla.msh.h5`, `caso_alpha_X.cas.h5`, `resultados.json` (L, D, CL, CD, L/D del avión completo en ejes del viento).

Qué hace: malla en Fluent Meshing (capas límite sobre `plane`: primera capa 0.015 mm, crecimiento 1.2, 25 capas en la rápida y 30 en la fina; poly-hexcore), después el solver con Transition SST, intensidad de entrada 0.1 %, viscosity ratio 10, V = 22.22 m/s, α por la dirección del viento (cos α, 0, sin α), reportes de L y D con los vectores del sistema del viento, y duplica el medio modelo.
La estela no tiene caja de refinamiento todavía (pendiente: necesita un cuerpo auxiliar en el STEP).

## 4. Qué mirar después de cada corrida
- **y+** en el ala (Contours > Turbulence > Wall Yplus, superficie `plane`): para Transition SST debe ser ≲ 1. La corrida vieja daba 0.3 a 1110.
- **Convergencia:** curvas de L y D planas en las últimas 200 iteraciones; no usar los residuales como único criterio (poner Convergence Criterion en `none`).
- **Intermitencia** sobre el ala (Contours > Turbulence > Intermittency): 1 casi desde el borde de ataque = capa límite turbulenta de punta a punta.
- Fluent reporta fuerzas en ejes de la malla; L y D son las rotadas al viento: D = Fx·cosα + Fz·sinα, L = −Fx·sinα + Fz·cosα. Los coeficientes de Fluent dependen de los Reference Values (medio modelo: área 0.6067 m², longitud 0.3859 m, V = 22.22 m/s, ρ = 1.056).

## 5. Referencia del modelo (AeroBuildup, V53, avión completo, v_tail)
| α [°] | CL | CD | L [N] | D [N] |
|---|---|---|---|---|
| 0 | 0.2399 | 0.01475 | 75.9 | 4.67 |
| 1.21 (crucero) | 0.3610 | 0.01766 | 114.2 | 5.59 |
| 2 | 0.4399 | 0.02041 | 139.2 | 6.46 |
| 4 | 0.6391 | 0.03004 | 202.2 | 9.51 |

Por componente a 1.21°: ala sola L = 115.7 N, D = 4.57 N; ala + fuselaje L = 115.7 N, D = 5.25 N; la cola da ≈ −1.5 N de sustentación.

## 6. Casos corridos (todos con el dominio chico, malla sin capas límite resueltas)
| Caso | α | Modelo de turbulencia | L completo | D completo | Nota |
|---|---|---|---|---|---|
| CFD 1 | 1.21° | k-omega SST, V = 22 m/s, intensidad 5 % | 53.5 N | 8.06 N | resistencia viscosa 4.4 N (55 %) |
| CFD 2 | 1.21° | k-omega SST, V = 22.22 m/s | 54.4 N | 8.18 N | |
| CFD 3 | 1.21° | Transition SST (según el archivo de datos) | 54.6 N | 8.18 N | casi igual: y+ ≫ 1 |

Diferencia con el modelo: L −52 %, D +46 %. No es el ángulo, ni la velocidad, ni la intensidad de turbulencia de entrada.

## 7. Casos que faltan (en este orden)
1. [ ] Dominio nuevo (v3) según la sección 2 y chequeo con `--solo-chequeo`.
2. [ ] Prueba del pipeline con `encl_red_v2.step`, malla rápida, Transition SST, α = 1.21°. Corregir lo que falle y anotar el y+ resultante.
3. [ ] Mismo caso con `--modelo k-omega` (separa el efecto del modelo del de la malla).
4. [ ] Caso 2 con el dominio v3 (separa el efecto del dominio).
5. [ ] Barrido α = 0 / 1.21 / 4° (comparar la pendiente del CL con el modelo: ≈ 0.099 por grado).
6. [ ] Ala sola (sin fuselaje ni cola) contra 115.7 N del modelo.
7. [ ] Malla fina y estudio de independencia de malla (rápida vs fina).
8. [ ] Verificar en Fusion los ángulos de las secciones (raíz +4.0°, punta −4.45°).
9. [ ] Volver a correr el optimizador con V53 y regenerar la geometría con los parámetros nuevos antes de la CFD definitiva.
10. [ ] Tabla comparativa final CFD vs código (L, D, CL, CD, L/D, por componente si se puede).


## 8. Estado al 2026-10-27 y corrida de la noche (recinto grande, los dos modelos)

El pipeline que se usa de verdad es el de Fluent 24.1 + PyFluent 0.27 (`C:\Users\felip\venv_pyfluent`): `herramientas/mallar_fluent.py`
(malla), `herramientas/correr_cfd_fluent.py` (barrido), `herramientas/calibrar_cfd_aerobuildup.py` (comparación y calibración).
Lo aprendido de la API está en `herramientas/NOTAS_FLUENT.md`. `fluent_pipeline.py` queda solo para `--solo-chequeo` y `--revisar-set`.

**Resultados ya obtenidos** (malla v5, recinto chico 8.3 x 2.5 x 3 m con tapas de simetría, k-ω SST, `resultados/cfd_run/barrido_v5_total.json`):
CL = 0.244 / 0.279 / 0.358 a α = 0 / 1.21 / 4° contra 0.240 / 0.361 / 0.639 del modelo. El incremento de CL respecto de α = 0 es 0.285 x
el del modelo en los dos ángulos: parece un artefacto del montaje (las tapas de simetría arriba y abajo mantienen el flujo horizontal).
CD de la CFD = 0.0284 / 0.0334 / 0.0492, con 136-316 cuentas de exceso sobre el modelo a igual CL.

**Qué cambió para la noche**
- `encl_grande.step` (raíz del repo): recinto x [−5, 11.85], y [0, 6.7], z [−5.3, 5.3] m (≈ 1197 m³). Se hizo a partir de `encl_red_v2.step` cambiando solo las
  coordenadas de las 6 caras de la caja (el avión no se tocó); validado con OpenCascade como sólido cerrado, 72 caras, volumen = caja − avión.
- `zona_estela.step`: caja x [−0.3, 4.5], y [0, 1.9], z [−0.5, 0.7] m para refinar la estela (`mallar_fluent.py --estela zona_estela.step --tam-estela 200`).
  **Experimental y sin probar con Fluent** (cuerpo de influencia vía `Import Body of Influence Geometry`); si falla, la malla sale sin estela y lo avisa.
- Las tapas (`m_walls`) pasan a **velocity-inlet con el mismo vector de viento** (`--paredes velocidad`, default). Con `--paredes simetria` se repite lo de antes.
- Celda máxima de 1500 mm en el espacio lejano (`--tam-max 1500`): con 600 mm el recinto grande daría millones de celdas de relleno.
- `correr_cfd_fluent.py`: plan por prioridad (`--plan "transicion:0,4;sst:4;..."`), corte por convergencia de L y D (< 0.3 % en 3 bloques de 50 iteraciones, mínimo 300/150 y máximo 800/450),
  CSV incremental con y+ y tiempo por iteración, retoma lo ya hecho, `--limite HH:MM`.

**Cómo lanzarla** (PowerShell, raíz del repo): `.\herramientas\correr_noche.ps1 -Limite 08:30`. Malla grande (con estela; si falla o pasa de 7 M de celdas, sin estela) → barrido →
calibración. Si no hay malla grande usa `malla_v5` y lo dice. Sale `resultados/cfd_run/noche/noche_grande/resultados.csv` y `resultados/calibracion_cfd.png/.json`.

**Qué esperar.** ≈ 17 s/iteración (SST) y ≈ 25 s (Transition SST) con ~4.5 M de celdas: en una noche entran unos 4-5 ángulos. Si CL(4°) se acerca a 0.6, el problema era el recinto/tapas;
si CD(0°) baja hacia 0.015-0.02 con Transition SST, era el modelo de turbulencia. La función de transformación (`CL_cfd = a·CL_ab + b`, `CD_cfd = CD_ab + d0 + d2·CL²`) solo vale la pena con ≥ 4-5 puntos
convergidos por modelo; con menos, es indicativa. Los casos no convergidos quedan con `convergio = 0` y la calibración los ignora.

**Pendiente de verificar con Fluent** (nunca corrido todavía): nombre `transition-sst` y de la turbulencia de `m_walls` tras cambiarla a velocity-inlet, la estela, y que el segundo grupo del plan (que relee la malla) arranque limpio.

## 9. Resultado de la noche 2026-10-28 (recinto grande, malla_grande.msh.h5, avión completo)
Detalle, gráficos y tabla en `Ansys noche/` (`HALLAZGOS.md`, `comparacion_cfd_aerobuildup.png`, `tabla_cfd_aerobuildup.csv`; script `herramientas/graficar_hallazgos_noche.py`).

| Modelo | α | Conv. | CL | CD | L/D |
|---|---|---|---|---|---|
| Transition SST | 0 | no (800 it) | 0.226 | 0.01945 | 11.6 |
| Transition SST | 1.21 | sí | 0.414 | 0.02112 | 19.6 |
| Transition SST | 4 | sí | 0.843 | 0.03265 | 25.8 |
| Transition SST | 8 | sí | 1.438 | 0.06641 | 21.7 |
| k-ω SST | 0 | sí | 0.233 | 0.02838 | 8.2 |
| k-ω SST | 4 | sí | 0.827 | 0.04248 | 19.5 |

Conclusiones: H1 (recinto chico aplasta el CL) confirmada; H2 (el modelo totalmente turbulento infla el CD) confirmada; H3 rechazada. La CFD nueva sobre-sustenta respecto de AeroBuildup (+15 % a 1.21°, +32 % a 4°, pendiente 0.154 /° vs 0.099 /°): sin explicar. Casos que siguen faltando de la sección 7: ala sola, independencia de malla, SST a 1.21° y 8°.
