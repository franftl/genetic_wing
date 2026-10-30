# UAV FP (tesis ITBA) — contexto del proyecto para Claude

Optimizador de avión de ala fija con AeroSandbox (AeroBuildup + NeuralFoil) y algoritmo genético. Idioma de trabajo: español.
Rama de trabajo: `bateria-350km` (se empuja también a `main`). La rama `viento` no se toca.

## Estructura
- `optimizacion_avion/` — paquete (geometría, misión, estructura, batería, manufactura, gráficos). `VERSION` en `__init__.py`.
- `optimizacion_ala/`, `viento/` — otros proyectos del repo (no mover: `viento` depende de las rutas).
- `herramientas/` — `exportar_cad_avion.py` (JSON de geometría en mm), `exportar_cfd_avion.py` (caso CFD), `fusion_generar_avion.py` (script de Fusion), `construir_notebook_avion.py` (genera `Optimizador_<VERSION>.ipynb`), `fluent_pipeline.py` (chequeo de dominio), `mallar_fluent.py` / `correr_cfd_fluent.py` / `calibrar_cfd_aerobuildup.py` / `correr_noche.ps1` (CFD con PyFluent 0.27, ver `herramientas/NOTAS_FLUENT.md`).
- `resultados/` — checkpoints, parámetros ganadores (`avion_design_params_<top>.json`), `avion_geometry_cad.json`, casos `cfd_<top>/`.
- `VERSIONES.md` — regla: una modificación sube el decimal (V53 → V53.1); agregar/modificar un módulo sube el entero. Al subir: cambiar `VERSION`, regenerar el notebook y agregar entrada en `VERSIONES.md`.

## Restricciones de diseño vigentes
- Borde de fuga de 2 mm absolutos en todas las superficies (`manufactura.py`); nariz sin punta (cara plana de 5 mm).
- Envergadura: penalización suave por encima de 2 m (`PESO_ENVERGADURA = 1.5`, `ENVERGADURA_MANUFACTURA_TOL = 0.2`).
- Misión: crucero 22.22 m/s, vuelo lento 10 m/s, despegue = 1.2·Vp, batería para 350 km (Molicel M65A), viento ON.

## Bug corregido en V53 (importante)
`asb.Airfoil.set_TE_thickness` deja la apertura del borde de fuga invertida en varios perfiles repanelados (sd7062, mh80, rg15, e423...). `manufactura.perfil_con_te` ahora abre el borde a mano. Los resultados de V52.x no son comparables con V53; hay que volver a correr el optimizador.

## Estado CFD (Ansys Fluent, medio modelo, plano de simetría y = 0, ejes: x atrás, y derecha, z arriba)
- Caso v_tail, α = 1.21°: CFD (completo) L ≈ 54.6 N, D ≈ 8.18 N contra el modelo L = 114.2 N, D = 5.59 N. Diferencia grande; no es el ángulo, ni la velocidad, ni la intensidad de turbulencia de entrada.
- Hallazgos: y+ en el ala entre 0.3 y 1110 (la mayor parte 100-300), así que Transition SST no resuelve la capa límite. El dominio de `encl_red.step` mide 8.3 × 2.5 × 1.0 m (20.7 m³): lejísimos de ser un campo libre; la zona `walls` puede ser pared con no-slip (verificar).
- Revisión 2026-10-26 (`FFF.set` de la corrida de esa mañana, `--revisar-set`): `walls` es pared NO-SLIP (confirmado); el reporte "lift" apuntaba en y (fuerza lateral); α = 0 (entrada normal), V = 22, TI 5 %, SST sin transición, μ por defecto. Cd = 0.0223 a α = 0 (modelo 0.0148). La geometría del STEP coincide con `avion_geometry_cad.json` (torsiones ±0.4°): no explica la diferencia. `encl_red_v2.step` (−1..10.3 × 0..2.5 × ±1.5 m) sigue chico.
- Fluent reporta fuerzas en ejes de la malla; sustentación y resistencia se obtienen rotando al viento: D = Fx·cosα + Fz·sinα, L = −Fx·sinα + Fz·cosα.
- Malla con capa límite (2026-10-27): `herramientas/mallar_fluent.py` (Fluent 24.1 vía `C:\Users\felip\venv_pyfluent`, PyFluent 0.27) mallá `encl_red_v2.step` en ~5 min: 2.56 M celdas, 24 capas desde 0.025 mm (×1.2, y+ ≈ 0.8), ortogonalidad mínima 0.067, salida en `resultados/cfd_run/malla_v5.msh.h5`. Las mallas v2-v4 estaban mal (fronteras como pared, capas sobre el recinto). y+ medido 0.77 de media (`herramientas/chequear_yplus.py`). Receta, trampas y procesos huérfanos de Fluent en `herramientas/NOTAS_FLUENT.md`.
- Pendiente: dominio nuevo (mínimo: 5 m aguas arriba, 10 m aguas abajo del avión, 5 m laterales y verticales; `python herramientas/fluent_pipeline.py --solo-chequeo` lo verifica) con refinamiento de estela, Transition SST con 0.1 % de intensidad, α = 0 / 1.21 / 4°, ala sola.
- Estado 2026-10-27: barrido k-ω SST en recinto chico da pendiente de CL = 0.285 x la del modelo (artefacto de las tapas de simetría, hipótesis). Preparado `encl_grande.step`, tapas velocity-inlet, Transition SST, `calibrar_cfd_aerobuildup.py` y `herramientas/correr_noche.ps1` (ver sección 8 de `CFD_PYFLUENT.md`). Corrido en la noche del 28 (siguiente punto).
- Noche 2026-10-28 (recinto grande `encl_grande.step`, malla 2.56 M celdas, tapas velocity-inlet, Transition SST, avión completo; detalle en `Ansys noche/HALLAZGOS.md`): CL = 0.226 / 0.414 / 0.843 y CD = 0.0195 / 0.0211 / 0.0327 a α = 0 / 1.21 / 4° (modelo: CL 0.240 / 0.361 / 0.639; CD 0.0148 / 0.0177 / 0.0176, este último a igual CL no comparable). A 4° con k-ω SST: CL 0.827, CD 0.0425. Conclusión: el recinto chico aplastaba el CL (H1) y el modelo totalmente turbulento inflaba el CD (H2). Abierto: la pendiente de CL de la CFD (0.154 /°) supera la del modelo (0.099 /°). En crucero la CFD da L +15 %, D +20 % sobre el modelo. El punto de 0° no convergió (oscila ±0.4 %). La estela refinada probablemente no se aplicó. Bugs corregidos: ruta relativa del STEP colgaba `mallar_fluent.py`; la turbulencia de entrada usaba nombres inválidos (`turbulent_viscosity_ratio_real`; en Transition SST las opciones llevan prefijo "Intermittency, ").
- Cómo correr la CFD y qué casos faltan: ver `CFD_PYFLUENT.md` (actualizarlo al terminar cada caso).
- `herramientas/fluent_pipeline.py` es un borrador SIN PROBAR (nombres de comandos de PyFluent a ajustar a la versión de Ansys).

## Git
Commits con trailer `Co-Authored-By: Claude`. Empujar `bateria-350km` y `bateria-350km:main`.
