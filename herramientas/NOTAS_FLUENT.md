# Notas de Fluent / PyFluent (lo aprendido, 2026-10-26/27)

Para futuras corridas con `herramientas/mallar_fluent.py`. Todo se probó contra Fluent 2024 R1 (24.1).

## Receta que funciona (malla `v5`, ~5 min en total)
```
C:\Users\felip\venv_pyfluent\Scripts\python.exe -u herramientas\mallar_fluent.py --etiqueta v5 > resultados\cfd_run\log_v5.txt 2>&1
```
Defaults del script: primera capa 0.025 mm, crecimiento 1.2, 24 capas (9.8 mm), superficie del avión 8 mm (mín. 1 mm por curvatura 12°), 8 procesos, poly-hexcore con celda máxima de 600 mm.

| Malla | Capas | Superficie | Celdas | Ortogonalidad mín. | Aspecto máx. | Tiempo | Veredicto |
|---|---|---|---|---|---|---|---|
| v2 / v3 | 30 × 1.2 desde 0.015 mm | 6 mm | 3.08 M | 0.0035 | 5.5e4 | 8 min | No sirve: las capas crecían sobre las tapas del recinto y las fronteras salían como pared |
| v4 | 30 × 1.2 desde 0.015 mm | 6 mm | 3.03 M | 0.021 | 1.6e4 | 6.7 min | Válida pero cara (75 % prismas) |
| **v5** | **24 × 1.2 desde 0.025 mm** | **8 mm** | **2.56 M** | **0.067** | **2.4e3** | **4.9 min** | **Usar esta** (1.82 M prismas, 0.56 M poliedros, 0.18 M hexaedros) |

Costo: el volumen es casi todo capas límite (≈ caras de pared × nº de capas). Lo que más abarata es bajar las capas (de 30 a 24) y subir el tamaño de superficie; la primera altura casi no cambia el costo pero define el y+.

## y+ (por qué 0.025 mm)
- Estimación a 22.2 m/s, ρ = 1.056, μ = 1.7433e-5, Cf ≈ 0.0045: u_τ ≈ 1.05 m/s, y(y+ = 1) ≈ 0.0157 mm.
- Fluent pone el primer centro de celda a la mitad de la primera altura: con 0.025 mm queda y+ ≈ 0.8 (turbulento); en zona laminar es menor. Con 0.015 mm daba ≈ 0.5, sin ganancia real y con más capas.
- Espesor total 9.8 mm vs. capa límite turbulenta ≈ 0.37·x/Re_x^0.2 ≈ 9-11 mm en la raíz (menos en la punta y si hay laminar); la última capa mide 1.9 mm contra 8 mm de la celda de superficie.
- Verificación con el solver (80 iteraciones, SST, V = 22.22 m/s, α = 0): ver el apartado "y+ medido" más abajo.

## Entorno
- PyFluent 0.43 (el `.venv` del proyecto) **no soporta Fluent 24.1** (mínimo 24.2). Con `AWP_ROOT252` definida elige 2025 R2.
- Entorno aparte para 24.1: `C:\Users\felip\venv_pyfluent` con `ansys-fluent-core==0.27.0` (Python 3.13 OK). Lanzar con `launch_fluent(product_version="24.1.0", mode="meshing", ...)`.
- Correr con `python -u` y log a archivo: sin `-u` no se ve nada hasta que termina. En Git Bash: `nohup ... > log 2>&1 &` y mirar el log con `grep -E "^\[|Error|Traceback"` (el script marca sus pasos con `[  123.4s]`).
- Licencia: el gestor local (`1055@localhost`, servicios `ANSYS, Inc. License Manager CVD` y `FlexNet Licensing Service 64`) tiene que estar arriba (`lmgrd`/`ansyslmd`). Si Fluent dice `Unexpected license problem; exiting`, es de licencia, no de PyFluent. El 2026-10-26 por la noche estaba arriba y funcionó.
- Máquina: Ryzen AI 7 350, 8 núcleos / 16 hilos, 31 GB. 8 procesos andan bien; la malla de 2.6 M celdas usa pocos GB.

### Procesos huérfanos (importante)
- Tras un fallo del script, y a veces también tras terminar bien, queda un `fluent.exe` vivo (ocupa licencia y núcleos). El script ya registra `atexit` con `m.exit()` + `m.force_exit()`, pero conviene revisar siempre al terminar:
  `Get-CimInstance Win32_Process | ? Name -eq fluent.exe` (la línea de comando lleva `-meshing -sifile=...`). Cerrar **solo** los que haya lanzado esta sesión, por PID (`Stop-Process -Id`). No usar `taskkill /IM fluent.exe`: mata también sesiones ajenas.
- Si un lanzamiento falla queda `mpiexec`/`hydra_pmi_proxy` huérfano: cerrarlos antes de reintentar.
- El `cwd` de `launch_fluent` es donde caen las carpetas `FM_*` y los `.trn`.

## Cómo iterar rápido
Relanzar todo el script cuesta ~2.5 min antes de llegar a las capas. Para explorar la API conviene una **sesión persistente**: un script que lanza Fluent una vez y ejecuta, en un bucle, archivos `cN.py` que va dejando una carpeta (con `exec` sobre un diccionario que tiene `m`, `w`, `t`), escribe la salida en `oN.txt` y marca `dN`. Se mandan comandos con un `enviar.sh` que copia el archivo y espera la marca. Ahorró decenas de minutos. Cuidados: generar el volumen invalida el estado del workflow (las tareas se "relee" desde el archivo del volumen); cerrar la sesión (`m.exit()`) antes de lanzar otra, porque ocupa una licencia y 8 núcleos.

## TUI desde PyFluent
- Las rutas con espacios van entre comillas dobles dentro del string (`'"C:/ruta con espacios/x.msh.h5"'`) o usar una ruta sin espacios (para los transcripts se usa `AppData/Local/Temp`).
- `start_transcript` sobre un archivo que existe pregunta si sobrescribe y el comando siguiente se pierde ("menu not found"). Un archivo nuevo en cada llamada (`tui_texto` lo hace).
- **Carrera con el transcript**: algunos comandos (p. ej. `objects.list`) imprimen después de volver; el archivo se lee vacío o incompleto. `tui_texto(..., espera=1.0)` espera dentro de la ventana y reintenta la lectura. Mejor no depender de ese texto si hay otra forma (el nombre del objeto de malla sale del nombre de su zona: `<objeto>:1`).
- Los argumentos de zonas van como lista: `sep_face_zone_by_angle([zona], 45)`, `boundary.manage.type(["m_walls"], "symmetry")` (con un string suelto da `invalid zone`).
- `boundary.manage.merge([ids])` mezcla en la primera zona (avisa "Invalid input. Using default value for 'Merge with'", es inocuo); `boundary.manage.name(id, nombre)` falla si el nombre existe.
- El menú `mesh` del TUI no existe hasta que hay una malla cargada (`dir(m.tui.mesh)` da `menu not found`).
- `m.meshing_utilities` está vacío en 24.1 (es de versiones nuevas). `m.tui.mesh.mesh_info` no existe: usar `mesh.manage.list` (tipos de celda) y `mesh.check_quality`.
- `get_attr("X/allowedValues")` sobre tareas del workflow devuelve siempre `None`: no sirve para descubrir valores. El esquema real está en `v241/fluent/fluent24.1.0/cortex/resources/Meshing.fdl` y los argumentos en `venv_pyfluent/Lib/site-packages/ansys/fluent/core/generated/datamodel_241/meshing.py`. El cliente acepta cualquier clave en `Arguments`; el servidor protesta recién al ejecutar, así que hay que leer el log.
- `mesh.modify.list_skewed_cells` pide zona/valores en un orden que no se pudo fijar (siempre `Invalid zone`); no se usó.

## Geometría (encl_red_v2.step)
- El STEP no trae nombres de caras: entra como **una sola zona** (5360 triángulos). Con 80° la cara de simetría queda pegada al avión; con 45° se separa bien. Se clasifica por caja contenedora (cara plana en x_min / x_max / y = 0 / y_max / z = ±z_max). Resultado: inlet 2 caras, outlet 2, symmetry 82, walls 6, plane 5268 (74 zonas antes de unir; ~50 s porque cada caja es una llamada TUI).
- Las tapas (y_max, z = ±1500) se dejan como `symmetry`: el dominio original las tenía como pared no-slip.
- Dominio v2: x [−1000, 10300], y [0, 2500], z [±1500] mm. El avión ocupa x [0, 1849], y [0, 1674], z [−73, 317]. Sigue siendo chico para aguas abajo (el mínimo recomendado era 10 m detrás del avión): `python herramientas/fluent_pipeline.py --solo-chequeo`.

## Lo que costó descubrir (por qué las mallas v2/v3 estaban mal)
1. **La malla de superficie sale como UNA sola zona** (`<objeto>:1`, 139 mil caras) que hereda todas las etiquetas. Consecuencias: `Update Boundaries` no separa nada (todo el recinto queda como pared no-slip), y las capas de inflación crecen sobre toda la pared, incluidas las 6 caras del recinto (prismas de 17 mm sobre caras de 600 mm → 3 M de celdas, ortogonalidad 0.0035, aspecto 5.5e4).
   **Arreglo**: después de `Generate the Surface Mesh`, separar esa zona por ángulo (45°), clasificar por caja, unir y renombrar con prefijo `m_` (`m_inlet, m_outlet, m_symmetry, m_walls, m_plane`) y recién entonces `Describe Geometry → Update Boundaries → Update Regions`. Tarda ~16 s.
2. **Etiquetas en objetos de malla no funcionan para las capas**: `BlLabelList=["m_plane"]` con `GrowOn="selected-labels"` da "The scope for the Scoped Prism is empty or incorrect" y no crea prismas. Usar **por zona**: `FaceScope={"GrowOn":"selected-zones"}`, `ZoneSelectionList=["m_plane"]`. El log muestra "Created Scoped Prism" y `BLZoneList: ['m_plane']` si el alcance es válido (verificarlo siempre; si falta ese mensaje no hay capas).
3. No tocar `FaceScope/RegionsType` ni `RegionScope`: `named-fluid-regions` da "No valid region was selected" y `named-regions` deja el alcance vacío. Los valores por defecto (todas las regiones fluidas) andan.
4. Para respetar `FirstHeight` hay que poner antes `OffsetMethodType="uniform"` en la tarea padre; la tarea hija toma el nombre de `BLControlName` (`t["capas_avion"]`). Con `smooth-transition` no se respeta la primera altura.
5. `Update Boundaries` deja `m_walls` como pared aunque se le pida `symmetry` (entrada, salida y simetría sí se tipan). Se corrige al final: `m.tui.boundary.manage.type(["m_walls"], "symmetry")` antes de guardar. Verificado en el solver: pared solo `m_plane`.
6. `create_label_per_zone` y `remove_all_labels_on_zones` son de objetos de geometría; sobre la malla no aportan nada para el alcance de capas.

## Referencias de claves (workflow Watertight, 24.1)
- Tamaño local sobre `plane`: `BOIControlName, BOIExecution ("Face Size" / "Curvature"), BOIZoneorLabel="label", BOIFaceLabelList=["plane"], BOISize, BOIMinSize, BOIMaxSize, BOICurvatureNormalAngle, BOIGrowthRate` (no existe `BOICurvatureMinSize`). Con la geometría sí funcionan las etiquetas (se crearon con `objects.labels.create_label_per_zone` sobre el objeto `origin-...`).
- Capas (`AddBoundaryLayers`): `BLControlName, OffsetMethodType, NumberOfLayers, FirstHeight, Rate, FaceScope{RegionsType,GrowOn,FaceScopeMeshObject}, RegionScope, BlLabelList, ZoneSelectionList, LocalPrismPreferences{IgnoreBoundaryLayers,...}`.
- Volumen: `VolumeFill` ("poly-hexcore"), `VolumeFillControls{GrowthRate, TetPolyMaxCellLength, BufferLayers, PeelLayers, HexMinCellLength, HexMaxCellLength, Type, CellSizing}`; ajustes globales de capas en `PrismPreferences` (gap factor 0.25, aspecto máx. 25, "keep first layer height" = no por defecto).
- Con `SeparationRequired="Yes"` y `SeparationAngle` en `GenerateTheSurfaceMeshWTM` el workflow tiene su propia separación por ángulo (no se probó; la usada es la manual, que además clasifica por posición).

## y+ medido (malla v5, `herramientas/chequear_yplus.py`)
k-omega SST, 22.22 m/s, α = 0, 45 iteraciones desde inicialización híbrida (continuidad ~6e-3, **no convergido**, es indicativo), sobre las 78 502 caras de `m_plane`:

| min | mediana | media | p95 | máx |
|---|---|---|---|---|
| 0.03 | 0.67 | 0.77 | 1.68 | 3.35 |

Coincide con la estimación (≈ 0.8). El máximo (3.4) está en zonas de alto esfuerzo (borde de ataque / puntas); es admisible para Transition SST (< 5). Repetirlo con la solución convergida y con α = 4°, donde el y+ en el borde de ataque sube.
- `surface_integrals.facet_min/avg/max` sobre una zona de pared devuelve "1" para cualquier campo (no sirve); usar `s.field_data.get_scalar_field_data(field_name="y-plus", surfaces=["m_plane"], node_value=False, boundary_value=True)` y numpy. El nombre del campo es `y-plus` (no `wall-yplus`); la lista sale de `s.field_info.get_scalar_fields_info()`.
- En el solver: `s.setup.boundary_conditions.<tipo>.keys()` confirma los tipos de zona (velocity_inlet = `m_inlet`, pressure_outlet = `m_outlet`, symmetry = `m_walls` y `m_symmetry`, wall = `m_plane`).

## Lo que sigue
1. Dominio nuevo (aguas abajo ≥ 10 m, laterales/verticales ≥ 5 m): el v2 de 8.3 × 2.5 × 3 m sigue siendo muy chico y la estela no se resuelve (celda máxima 600 mm). Con dominio grande agregar una caja de refinamiento (BOI) en la estela en vez de achicar la celda global.
2. Solver: Transition SST (hay que cambiarlo desde el SST de la prueba), entrada Magnitude and Direction (22.22 m/s, (cos α, 0, sin α)), TI 0.1 %, μ = 1.7433e-5, ρ = 1.056, reportes con lift (−sin α, 0, cos α) y drag (cos α, 0, sin α), área de referencia 0.6067 m² (medio modelo), α = 0 / 1.21 / 4°.
3. Antes de calcular: exportar el `.set` y pasarlo por `python herramientas/fluent_pipeline.py --revisar-set <archivo>`.
4. Si hace falta bajar más el costo: capas 22 con crecimiento 1.25 desde 0.025 mm (~8 mm), o superficie de 10 mm; verificar siempre ortogonalidad mínima (> 0.05) y que el log diga "Created Scoped Prism".
5. En Workbench: la malla `.msh.h5` y los `.cas.h5`/`.dat.h5` se abren desde un sistema Fluent / Fluent Meshing y se ven en Results o CFD-Post.
