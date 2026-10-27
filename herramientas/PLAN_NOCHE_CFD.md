# Plan de la noche: CFD con recinto grande y Transition SST

_Escrito el 2026-10-27. Está pensado para que lo suba a una sesión nueva de Claude y la sesión lo ejecute de punta a punta
sin preguntar. Todo lo que hace falta saber está acá; los detalles de PyFluent/Fluent 24.1 están en
`herramientas/NOTAS_FLUENT.md` (leerlo primero). Idioma de trabajo: español. Reglas del repo en `CLAUDE.md`._

---------------------------------------------------------------------------------------------------------------------

## 0. Qué hay que hacer, en una frase

Mallar un recinto grande (con estela refinada) alrededor del mismo avión (v_tail, medio modelo) y correr un barrido de ángulo de
ataque con **Transition SST**, para saber si las diferencias contra el modelo del optimizador (AeroBuildup) vienen de
(a) el recinto chico y (b) el modelo de turbulencia totalmente turbulento. Dejar todo corriendo toda la noche y
tener a la mañana resultados + un gráfico superpuesto con el modelo.

## 1. Estado de partida (lo que ya se sabe)

Malla actual: `resultados/cfd_run/malla_v5.msh.h5` (Fluent 24.1, 2.56 M celdas, 24 capas desde 0.025 mm ×1.2, y+ medio 0.77,
ortogonalidad mínima 0.067). Zonas: `m_inlet` (velocity inlet), `m_outlet` (pressure outlet), `m_symmetry` (y = 0),
`m_walls` (tapas del recinto, simetría), `m_plane` (avión, única pared no-slip). Medio modelo: Fluent reporta la mitad
de las fuerzas, hay que multiplicar por 2. Ejes: x atrás, y derecha, z arriba. Viento: `(cos α, 0, sin α)`.

Barrido ya hecho (k-ω SST, TI 0.1 %, V = 22.22 m/s, ρ = 1.056, μ = 1.7433e-5; S = 1.2134 m², MAC = 0.3859 m):

| α | L [N] | D [N] | CL | CD | CL del modelo (AeroBuildup) | CD del modelo a igual CL |
|---|---|---|---|---|---|---|
| 0° | 77.3 | 9.00 | 0.244 | 0.0284 | 0.240 | 0.0148 |
| 1.21° | 88.3 | 10.55 | 0.279 | 0.0334 | 0.361 | 0.0156 |
| 4° | 113.2 | 15.57 | 0.358 | 0.0492 | 0.639 | 0.0176 |

Comparación (script `herramientas/comparar_cfd_modelo.py`, salida `resultados/cfd_run/comparacion_cfd_modelo.png/.json`):

* **Sustentación:** a α = 0 coincide con el modelo. El incremento de CL respecto de α = 0 es **0.285 × el del modelo**, igual en
  1.21° y en 4° (0.286 y 0.285). Es un factor muy constante → parece un artefacto del montaje (el viento se inclina en la
  entrada, pero las tapas de arriba y abajo del recinto son simetría y obligan al flujo a quedar horizontal; el dominio
  mide 8.3 × 2.5 × 3 m).
* **Resistencia:** la CFD da 136 / 177 / 316 cuentas de drag (1 cuenta = 1e-4) más que el modelo a igual CL en 0° / 1.21° / 4°.
  No es un factor ni un offset: crece con α. A α = 0 (sin entrada inclinada) ya hay 1.9× la resistencia del modelo.
* El modelo del optimizador usa NeuralFoil con transición laminar-turbulenta; la CFD actual es k-ω SST totalmente
  turbulento, y a Re(MAC) = 5.2e5 esa diferencia puede ser grande. **Esto es lo que hay que probar.**
* El modelo del repo es AeroBuildup, no VLM. El script de comparación agrega también un VLM puro (no viscoso) como referencia.

## 2. Hipótesis a contrastar y qué resultado las confirma

| # | Hipótesis | Prueba | Se confirma si |
|---|---|---|---|
| H1 | El recinto chico + tapas de simetría aplastan la pendiente de CL | Recinto grande, k-ω SST (o Transition SST), α = 4° | CL(4°) ≈ 0.55–0.65 (cerca de AeroBuildup 0.639) en vez de 0.358 |
| H2 | El exceso de resistencia viene de modelo totalmente turbulento | Transition SST, α = 0° | CD(0°) baja de 0.0284 hacia 0.015–0.020 |
| H3 | La estela sin refinar o el dominio chico agregan resistencia espuria | Comparar CD entre recinto chico y grande al mismo modelo | CD cambia con el recinto a igual modelo |

Para separar H1 de H2 la matriz tiene que incluir el recinto grande **y** los dos modelos (SST y Transition SST) en al menos
un ángulo (α = 0° o 4°).

## 3. Lo que necesito del usuario antes de arrancar (unico bloqueo posible)

El recinto es un STEP que el usuario genera en su CAD (`encl_red_v2.step` fue hecho así: caja con el avión como cavidad,
**medio modelo**, plano y = 0 como cara de simetría). Hace falta un STEP nuevo, por ejemplo `encl_grande.step`, en la raíz del repo.
Si al empezar la sesión **no está**, ver §3.2.

### 3.1 Medidas del recinto nuevo (metros; el avión ocupa x ∈ [0, 1.849], y ∈ [0, 1.674], z ∈ [−0.073, 0.317])

| Cara | Valor | Criterio |
|---|---|---|
| Entrada (x mín) | x = −5 | 5 m aguas arriba (≥ 2.7 envergaduras) |
| Salida (x máx) | x = +11.85 | 10 m aguas abajo del borde de fuga más atrás |
| Simetría | y = 0 | |
| Lateral (y máx) | y = 6.7 | 5 m más allá de la punta del ala |
| Tapas | z = ±5.3 | ~5 m arriba y abajo |

Volumen ≈ 1200 m³. No es un problema: con celda máxima 600–800 mm el espacio lejano cuesta unos pocos miles de celdas;
lo caro son los prismas y la estela.

`python herramientas/fluent_pipeline.py --solo-chequeo` (con `--step encl_grande.step` si hace falta) verifica distancias mínimas.

### 3.2 Si el STEP nuevo no está

1. Decirlo al usuario en la primera línea, **sin esperar**: correr igual la Fase A del plan (§5) con `malla_v5.msh.h5`.
2. La Fase A contesta H2 pero no H1/H3. Dejar anotado en el informe de la mañana que H1/H3 quedan pendientes del STEP.
3. No inventar un STEP editando `encl_red_v2.step` a mano.

## 4. Cambios de código que hay que hacer **antes** de las corridas largas

(Pensados para no perder una noche por un detalle: probar cada uno con ≤ 5 iteraciones.)

1. **Transition SST en `correr_cfd_fluent.py`.** La bandera `--transicion` hace `vi.model = "transition-sst"`; **ese nombre no está
   verificado en Fluent 24.1**. Verificar leyendo `s.setup.models.viscous.model.allowed_values()` (o por TUI:
   `define/models/viscous/transition-sst? yes`) y ajustar. Comprobar que la intensidad de entrada (0.1 %) y la razón
   de viscosidades (10) se aplican. Confirmar con `s.setup.models.viscous.get_state()`.
2. **Guardar caso y datos después de cada α** (`file/write-case-data` en `resultados/cfd_run/noche/`). Hoy se pierde todo
   si el script muere: la corrida de la mañana lo demostró. Permite además retomar la noche si algo falla.
3. **Parada por convergencia de fuerzas en vez de número fijo de iteraciones.** Hoy se corre un número fijo y se desactivó el
   criterio por residuales (con el default 1e-3 Fluent cortaba a las 5–10 iteraciones). Implementar: iterar en bloques de 50 y cortar
   cuando L y D de las últimas 3 lecturas varían < 0.3 %, con un máximo (p. ej. 800) y un piso (p. ej. 250). Guardar la historia
   de L y D de cada bloque en el JSON (sirve para mostrar que convergió).
4. **Refinamiento de estela en `mallar_fluent.py`** (hoy no existe). Opciones, de más simple a más fina: (a) bajar `--tam-max`
   a 300 mm; (b) agregar una caja de densidad (BOI) o una `size function`/`local sizing` en la región
   x ∈ [0, ~3 m detrás del borde de fuga], y ∈ [0, ~2 m], z ∈ [−0.5, 0.5] con celda objetivo **100–150 mm**. Presupuesto: 3 m × 2 m × 1 m =
   6 m³; a 100 mm son 6 M celdas (demasiado), a 150 mm son ~1.8 M, a 200 mm ~0.75 M. **Presupuesto total del caso: ≤ 5 M celdas.**
   Si no se logra la BOI en PyFluent 0.27, usar solo (a) y dejarlo explicado en el informe.
5. **Registrar el tiempo por iteración** de cada bloque en el JSON para estimar lo que falta.
6. **Salida en `resultados/cfd_run/noche/`** (mallas con etiqueta `grande_v1`, `grande_v2`...; resultados `barrido_noche_<modelo>.json`).

## 5. Matriz de corridas (en orden de prioridad)

Estimación de costos medidos: con 2.56 M celdas y 8 procesos, k-ω SST tarda **~10 s por iteración** (la primera
corrida de la mañana marcó ~3 s, la segunda 10 s: tomar 10 s como valor realista). Para 4 M de celdas contar ~15 s, y Transition SST es ~30–40 %
más caro (4 ecuaciones). Una iteración de Transition SST con 4 M celdas ≈ 20 s → 400 iteraciones ≈ 2.2 h por ángulo. **En una noche
(~8–10 h) entran unos 3 a 4 ángulos.** No prometer más.

**Fase A (no necesita el STEP nuevo):** malla `malla_v5.msh.h5`, Transition SST.

| Orden | Corrida | Para qué | Tiempo estimado |
|---|---|---|---|
| A1 | Transition SST, α = 0° | H2 (¿baja el CD?) | ~1.5–2 h |
| A2 | Transition SST, α = 4° (continuando desde A1 en la misma sesión) | ver si la pendiente cambia | ~1.5 h |

**Fase B (con el STEP nuevo):** malla grande, mallar primero (~10–20 min, ver §6).

| Orden | Corrida | Para qué |
|---|---|---|
| B0 | Mallar y revisar (celdas ≤ 5 M, ortogonalidad mín. > 0.05, y+ ≈ 1) | Calidad |
| B1 | Transition SST, α = 0° | H2 + CD base |
| B2 | Transition SST, α = 4° | **H1** (¿CL ≈ 0.6?) |
| B3 | Transition SST, α = 1.21° (crucero) | Punto de diseño |
| B4 | Si sobra tiempo: α = 8°, luego α = −2° | Curva completa |

Si el STEP existe, **B tiene prioridad sobre A**; A solo sirve como plan B o mientras se malla. No correr A y B a la vez
(8 procesos cada una pelean los mismos núcleos y el doble de RAM; la máquina empieza a paginar). Si hace falta una corrida de control
con k-ω SST en el recinto grande (para separar H1 de H2), correrla **a α = 4° en la sesión B2** con 250 iteraciones, solo si
queda tiempo antes de las 9 am.

Orden de ángulos dentro de una sesión: ascendente con arranque en caliente (cada ángulo parte de la solución del anterior);
el primero necesita más iteraciones (700) que los siguientes (≈ 400).

## 6. Pasos concretos, comandos y chequeos

Entorno (PowerShell o Git Bash, desde la raíz del repo): **PyFluent 0.27 en `C:\Users\felip\venv_pyfluent`**
(el `.venv` del proyecto tiene PyFluent 0.43 y no soporta Fluent 24.1). El Python del proyecto sí tiene aerosandbox/matplotlib.

0. **Antes de empezar (5 min):**
   * `Get-Process fluent*` / mirar el Administrador de tareas: matar solo los procesos propios que queden huérfanos, **por PID**
     (nunca `taskkill /IM`; el clasificador de permisos lo niega y puede matar sesiones ajenas). Ver NOTAS_FLUENT.md §procesos huérfanos.
   * Espacio en disco: la malla pesa ~250 MB y cada caso+datos ~1–1.5 GB; reservar ≥ 10 GB en `resultados/cfd_run/noche/`.
   * **Pedirle al usuario que desactive suspensión/hibernación y que no apague** (Configuración → Sistema → Energía: “Nunca”).
     Si el equipo se duerme, la noche se pierde. Dejarlo enchufado.
1. **Malla grande** (si hay STEP):
   ```
   C:\Users\felip\venv_pyfluent\Scripts\python.exe -u herramientas\mallar_fluent.py --step encl_grande.step --etiqueta grande_v1 --procesos 8 --tam-max 600
   ```
   (con las modificaciones de §4.4). Revisar `malla_grande_v1.json`: celdas, ortogonalidad mínima (> 0.05), razón de aspecto.
   Si la malla tiene > 5 M de celdas o ortogonalidad < 0.05, bajar el tamaño de la estela o `--capas` (24 → 20) antes de seguir.
   Los parámetros del avión **no cambian**: `--primera-capa 0.025 --capas 24 --crecimiento 1.2 --tam-avion 8`.
2. **Chequeo de y+ del caso nuevo** (10 min, k-ω SST, 45 iteraciones):
   `...\python.exe -u herramientas\chequear_yplus.py resultados\cfd_run\malla_grande_v1.msh.h5` → debe dar media ≈ 0.8 y máx < 5.
3. **Prueba de 5 iteraciones** de `correr_cfd_fluent.py` con `--transicion` en un α (confirma el nombre del modelo, que aparezcan 4 ecuaciones
   en los residuales y que los reportes de L y D funcionen).
4. **Corrida de la noche** (en segundo plano, con `nohup`; el script ya escribe el JSON después de cada ángulo):
   ```
   nohup C:\Users\felip\venv_pyfluent\Scripts\python.exe -u herramientas\correr_cfd_fluent.py \
       --malla resultados\cfd_run\malla_grande_v1.msh.h5 --alfas 0 4 1.21 8 --transicion --ti 0.1 \
       --iter-primera 700 --iter 400 --limite 08:30 --etiqueta noche_grande_tsst > resultados\cfd_run\log_noche.txt 2>&1 &
   ```
   (`--limite HH:MM` ya existe: no empieza un ángulo que no alcance a terminar antes. Poner la hora a la que el usuario va a
   despertar. Ojo: el script ordena los ángulos de menor a mayor, así que 1.21 correrá antes de 4; está bien, el arranque en caliente
   funciona igual con saltos chicos.)
5. **Vigilar sin gastar contexto:** un `until grep -q "listo\|Traceback" log...; do sleep 60; done` en segundo plano, y mirar el log solo si avisa.
   Revisar a la media hora que **las iteraciones por segundo sean las esperadas** y que los residuales bajen (si no, parar y diagnosticar:
   no dejar correr una noche entera una corrida rota).
6. **Mañana:** comparar con el modelo y graficar:
   ```
   python herramientas\comparar_cfd_modelo.py resultados\cfd_run\barrido_noche_grande_tsst.json
   ```
   (hoy el script lee el JSON completo; ajustar `ruta` por argumento, ya lo acepta). Agregar al gráfico la curva de la corrida
   vieja (recinto chico, k-ω SST) para que se vea el cambio. Los puntos que no se hicieron no se inventan.

## 7. Criterios para dar un resultado por bueno

* Residuales (continuidad, velocidades, k, ω y los de transición) bajan al menos 3 órdenes o se estabilizan.
* L y D de los últimos 100 iteraciones varían < 0.5 %. **Si no, decirlo en el informe** (p. ej. a α alto la capa límite puede oscilar).
* y+ medio ≈ 1 en la malla grande; si sube a > 3 la primera capa hay que bajarla.
* En el informe separar “resultado convergido” de “no convergido”. No presentar como resultado un punto que no pasó los chequeos.

## 8. Cómo interpretar los resultados (árbol de decisión)

* **CL(4°) cerca de 0.6 y CD(0°) cae hacia 0.015–0.02** → la CFD vieja estaba distorsionada por el recinto y por la turbulencia total. La CFD
  nueva valida el modelo. Concluir que no hace falta corrección; documentar en `CLAUDE.md`.
* **CL(4°) cerca de 0.6 pero CD sigue alto** → el recinto era el problema de CL; el CD alto es físico (o de la malla) → investigar
  resistencia por componente (ala, fuselaje, cola) con `report forces` por zona, y comparar con `AeroBuildup` por cuerpo
  (`_componentes` en `exportar_cfd_avion.py`).
* **CL(4°) sigue ≈ 0.36** → no era el recinto; revisar la entrada inclinada (¿se aplica la componente z?), las tapas (cambiarlas a
  `pressure-far-field` o a `velocity-inlet` con la misma componente) y la incidencia real del avión (rotar el avión en lugar de inclinar el viento).
* **CD cae a un valor muy bajo y L/D > 25** → desconfiar: Transition SST con 0.1 % de intensidad es optimista a Re bajo; repetir con
  0.3–0.5 % para ver la sensibilidad (anotarlo como corrida opcional).
* Si hay un factor de corrección constante y limpio (como el 0.285 de hoy), **solo proponerlo** si sobrevive al recinto grande.

## 9. Trampas conocidas (resumen; detalle en NOTAS_FLUENT.md)

* `taskkill /IM fluent.exe` está denegado; usar PID. Los `fluent.exe` huérfanos siguen ocupando licencia y núcleos.
* Hay que usar el venv `venv_pyfluent` (PyFluent 0.27) y `product_version="24.1.0"`.
* Los argumentos de TUI son listas; `manage.type(["zona"], "tipo")`. El menú `mesh` no existe hasta cargar una malla.
* Poner `s.tui.solve.monitors.residual.criterion_type("none")`, si no Fluent corta la iteración a los pocos pasos (la corrida de la mañana lo sufrió).
* `entrada.turbulence.turbulent_viscosity_ratio` no existe para k-ω; con Transition SST los nombres pueden ser distintos: listarlos con `child_names`.
* Fluent reporta las fuerzas del **medio modelo**: multiplicar por 2 y rotar al viento.
* El script de comparación y el de gráficos viven en el Python del proyecto (matplotlib); el de PyFluent no lo tiene.
* **Git no funciona en este entorno** (el `.git` apunta a un worktree de otra máquina): no intentar commit/push; avisar al usuario y listar los archivos nuevos.

## 10. Informe de la mañana (formato)

1. Qué corrió y qué no (con la hora a la que se cortó y por qué).
2. Tabla: α, L, D, CL, CD, L/D, iteraciones, convergió sí/no, para cada corrida; al lado, el modelo (AeroBuildup) y la CFD vieja.
3. El gráfico `comparacion_cfd_modelo.png` actualizado (con CFD vieja, CFD nueva, AeroBuildup y VLM).
4. Qué hipótesis (H1/H2/H3) se confirmaron, rechazaron o quedan abiertas, usando §8.
5. Actualizar `CLAUDE.md` (estado CFD) y `herramientas/NOTAS_FLUENT.md` (aprendizajes nuevos: nombres de la API, tiempos por iteración, tamaños de malla).
6. Dejar el estado en `resultados/cfd_run/noche/` ordenado: mallas, casos/datos, JSON, PNG, logs. Nada de procesos Fluent vivos al final.
