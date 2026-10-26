# UAV FP (tesis ITBA) — contexto del proyecto para Claude

Optimizador de avión de ala fija con AeroSandbox (AeroBuildup + NeuralFoil) y algoritmo genético. Idioma de trabajo: español.
Rama de trabajo: `bateria-350km` (se empuja también a `main`). La rama `viento` no se toca.

## Estructura
- `optimizacion_avion/` — paquete (geometría, misión, estructura, batería, manufactura, gráficos). `VERSION` en `__init__.py`.
- `optimizacion_ala/`, `viento/` — otros proyectos del repo (no mover: `viento` depende de las rutas).
- `herramientas/` — `exportar_cad_avion.py` (JSON de geometría en mm), `exportar_cfd_avion.py` (caso CFD), `fusion_generar_avion.py` (script de Fusion), `construir_notebook_avion.py` (genera `Optimizador_<VERSION>.ipynb`), `fluent_pipeline.py` (borrador PyFluent).
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
- Fluent reporta fuerzas en ejes de la malla; sustentación y resistencia se obtienen rotando al viento: D = Fx·cosα + Fz·sinα, L = −Fx·sinα + Fz·cosα.
- Pendiente: dominio nuevo (mínimo: 5 m aguas arriba, 10 m aguas abajo del avión, 5 m laterales y verticales; `python herramientas/fluent_pipeline.py --solo-chequeo` lo verifica), capas límite (primera capa 0.015 mm, crecimiento 1.2, ~30 capas), Transition SST con 0.1 % de intensidad, α = 0 / 1.21 / 4°, ala sola, medir ángulos de las secciones en Fusion (raíz +4.0°, punta −4.45°).
- `herramientas/fluent_pipeline.py` es un borrador SIN PROBAR (nombres de comandos de PyFluent a ajustar a la versión de Ansys).

## Git
Commits con trailer `Co-Authored-By: Claude`. Empujar `bateria-350km` y `bateria-350km:main`.
