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
