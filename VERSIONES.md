# Versiones del optimizador de avión

El nombre del notebook lleva la versión: `Optimizador_V54.2.ipynb`. La versión se define
en un solo lugar, `VERSION` en `optimizacion_avion/__init__.py`; el notebook y su nombre
de archivo salen de ahí (`construir_notebook_avion.py` lo lee al regenerar).

## Regla

| Qué cambia | Cómo se numera | Ejemplo |
|---|---|---|
| Una modificación sobre la versión existente (parámetros, supuestos, ajustes, correcciones) | sube el decimal | V50 → V50.1 → V50.2 |
| Se agrega o se modifica un **módulo** | sube el número | V50 → V51 |

Al subir de versión: cambiar `VERSION`, regenerar el notebook (`python construir_notebook_avion.py`),
y agregar una entrada abajo con qué cambió. El notebook de la versión anterior se conserva
solo si hace falta comparar; si no, se reemplaza.

## V50 (2026-10-13) — versión base

Rama `bateria-350km`. Lo que incluye:

- Batería dimensionada por alcance (350 km a velocidad de crucero constante), con
  eficiencia propulsiva modificable (`optimizacion_avion/bateria.py`, `mision_avion.BATERIA_ACTIVA`).
- Viento de los sitios (`mision_avion.VIENTO_ACTIVO`, de `viento`).
- Penalización de envergadura > 2 m (fabricación), sweep monótono y 11 estaciones en el ala.
- `pod_boom` es un fuselaje continuo (diámetro casi constante, afinado en la cola),
  sin góndola ni viga fina.
- Exportación a CAD y CFD: `exportar_cad_avion.py` + `fusion_generar_avion.py` (Fusion) y
  `exportar_cfd_avion.py` (STL, caso de cálculo y comparación de drag).
- Evaluación y resultados en `evaluacion_bateria_350km/`.

Pendientes conocidos: el script de Fusion no se probó dentro de Fusion; la forma cóncava del
ala (anedro en la raíz, diedro en la punta) sigue permitida por el hueco de la proyección de
elevación; el modelo no incluye hélice ni superficies de control.

## V50.1 (2026-10-15) — script de Fusion mallable en Ansys

Modificación sobre V50 (no toca el optimizador ni el modelo): `fusion_generar_avion.py` v2.

- Un loft por tramo entre secciones vecinas (igual que la interpolación lineal del solver) en vez de
  un solo loft por todas: el loft único hacía sobreimpulso en el ala exterior (tramos de 175 mm y de
  26 mm con ~30° de giro) y Fluent rechazaba el modelo por autointersecciones.
- Borde de fuga a espesor uniforme (`ESPESOR_TE_MM`, 1.0 mm por defecto; `None` lo deja como viene).
- Chequeo de secciones vecinas que se cruzan, limpieza de puntos repetidos, espejo sin fusionar y
  unión final con diagnóstico por cuerpo.
- Versión anterior en `codigo_obsoleto/fusion_generar_avion_v1_un_loft.py`.

Pendiente: probar v2 dentro de Fusion y mallar en Fluent.


## V51 (2026-10-16) — restricciones de manufacturabilidad

Módulo nuevo `optimizacion_avion/manufactura.py`, aplicado en `construir_avion`, así que lo ven
el optimizador, el export CAD/CFD y Fusion con la misma geometría.

- **Borde de fuga de 2 mm absolutos** en todas las superficies (ala, winglets, colas, derivas):
  cada sección usa 2 mm / su cuerda como fracción. Las puntas quedan cerradas por la sección
  terminal, que también tiene 2 mm. NeuralFoil ve el espesor, así que la resistencia de base ya
  entra en el CD.
- **Nariz sin punta**: cara plana de radio 5 mm y ley de potencia `morro_exp` (0.45–1.0) hasta el
  radio del fuselaje, con más secciones cerca de la punta. La ojiva de Von Kármán pura es
  puntiaguda y es para régimen supersónico; a 22 m/s se usa una forma roma truncada.
- `exportar_cad_avion.py` completa solo la diferencia hasta 2 mm (no suma el borde de fuga dos
  veces); `fusion_generar_avion.py` con `ESPESOR_TE_MM = 2.0`.
- Efecto medido en el ganador v_tail (sin re-optimizar): CD crucero 0.0173 → 0.0175, puntaje
  4.91 → 4.85 (~1 %).
- **Hay que volver a correr el GA**: los ganadores anteriores se optimizaron con filo exacto y
  nariz en punta.

## V51.1 (2026-10-19) — correcciones de una revisión completa del código

Modificaciones sobre V51 (ningún módulo nuevo). Cambian resultados: **volver a correr el GA**.

Cambios que mueven el puntaje:

- **Flecha y diedro monótonos incluyendo la raíz.** La proyección dejaba afuera la raíz (= 0) y
  aceptaba `[0, -0.05, 0, +0.10]` (flecha que va para adelante y vuelve). Ahora la secuencia completa
  es monótona (`_proyectar_monotona_desde_cero`, también en el ala volante). Cierra el "hueco de la
  proyección de elevación" que figuraba como pendiente en V50.
- **Una sola forma en planta**: estructura, flap y raíz de los booms interpolan con la misma PCHIP
  que el solver (`geometria_avion.interp_estaciones`); antes usaban interpolación lineal.
- **Ráfaga del sitio contra la carga LÍMITE** (`mision_avion.N_RAFAGA_ADMISIBLE = N_LIMITE = 3.0`),
  no contra la última (4.5), que no dejaba coeficiente de seguridad. Solo con viento. Los ganadores
  con viento del 02/10 (n ≈ 3.1–3.4) quedan inválidos con esta regla. Para volver a lo anterior:
  `mis.N_RAFAGA_ADMISIBLE = 4.5`.

Correcciones de errores:

- Lazo de batería: si no convergía en `MAX_PASADAS`, informaba una masa de batería distinta de la
  usada en el análisis. Ahora informa la usada, y `bateria["convergio"]` lo dice.
- `_analizar_pasada` ya no se traga los errores de programación (KeyError, TypeError, …): suben.
  Los numéricos siguen descartando el candidato y se cuentan en `mision_avion.FALLAS_ANALISIS`.
- Evolución: con menos de 2 semillas da un error claro (antes la primera generación fallaba y la
  corrida terminaba sin avisar); una excepción en una generación ahora se guarda en el checkpoint
  y sube; `reanudar=True` sigue desde un checkpoint.
- Semillas por escenario en un solo lugar (`competencia.semillas_para_escenario`), usada por
  `correr_competencia`, el notebook y los scripts. `correr_escenarios.py --viento on --bateria off`
  usaba una sola semilla y no optimizaba.
- `viento/optimizar_con_viento.py`: fija `BATERIA_ACTIVA` (por defecto off, como la corrida del
  18/09), restaura el valor de `VIENTO_ACTIVO` y no borra topologías de `ganadores_viento.json`.
- `viento_uav.mision_viento`: usa la densidad del análisis (antes suponía 1.225 aunque el análisis
  fuera con viento).
- Notebook: azar fijo (`SEMILLA_AZAR`), `SET_SEMILLAS` para elegir un set de `semillas/`, la
  exportación anota la ráfaga y la densidad que realmente se usaron, y `construir_notebook_avion.py`
  escribe en UTF-8 (en Windows fallaba).
- `gen_semillas.py`: semillas de pod_boom de fuselaje continuo, `--salida`, y la bisección devuelve
  el último punto válido.
- Limpieza: se quitó la góndola + viga del pod_boom (código muerto), se pasó `RUTA_JSON` del
  script de Fusion a "" (tenía una ruta de la PC de Felipe), dependencias completas en
  `requirements.txt`, y se actualizaron docstrings y documentación desactualizados.
- `Optimizador_V51.ipynb` y el viejo `02_Optimizacion_Avion.ipynb` se movieron a `codigo_obsoleto/`.

## V51.2 (2026-10-19) — puntaje por misión y trim resuelto

Modificación sobre V51.1 en `mision_avion.py` (ningún módulo nuevo). Cambia el puntaje: **volver a
correr el GA**; los puntajes no son comparables con los de antes.

- **`PUNTAJE_MODO = "mision"`**: el objetivo es UNO, la energía de batería para volar el alcance
  (`energia_mision_wh`; `PESO_ALCANCE = 1.0`, `ENERGIA_REFERENCIA_WH = 1200`). Reemplaza a eficiencia,
  masa y turbulencia, que contaban lo mismo dos o tres veces con referencias viejas.
- **Requisitos pasa / no pasa** (`requisitos_incumplidos`): margen estático dentro de la banda, margen
  de pérdida con ráfaga ≥ 20 %, `CN_BETA_MIN` y `CL_BETA_MIN` = 0.0005 /grado (supuesto a validar),
  trim convergido. Antes eran términos que valían casi lo mismo para todos los diseños válidos.
- **`TRIM_RESUELTO = True`**: la incidencia de la cola horizontal (o en V) se calcula para Cm = 0 en
  crucero con un modelo lineal en (alpha, incidencia) más hasta dos correcciones de Newton (una corrida
  extra de AeroBuildup y ~1 s más por pasada). Si la incidencia necesaria sale de los BOUNDS, el
  candidato es inválido. `params_trimados()` da el avión analizado; el notebook, los exportadores CAD/CFD
  y los scripts guardan y exportan ese.
- **Pendientes de decisión** (misma forma y peso que antes): vuelo lento, velocidad máxima y
  envergadura. Tasa de cambio actual: 0.1 m/s menos de velocidad de pérdida vale ~6 % de energía.
- `PUNTAJE_MODO = "legado"` conserva los 11-12 términos de antes; con `TRIM_RESUELTO = False` además
  vuelve el modelo de trim anterior.
- Medido sobre los 14 diseños existentes: el trim converge (|Cm| ≤ 0.002); la correlación de rangos
  entre puntaje y energía sube de 0.5 a 0.7 (lo que falta lo pone el término de vuelo lento,
  pendiente). Los pod_boom actuales no pasan `CN_BETA_MIN` (Cn_beta ≈ 0.0001–0.0003 /grado), y el
  pod_boom exportado necesita −7.6° de incidencia para trimar (rango −6° a +2°).
- `Optimizador_V51.1.ipynb` se movió a `codigo_obsoleto/`; `semillas/validar_semillas.py` cuenta como
  válido lo que tiene puntaje finito (o sea, que también cumple los requisitos).

## V51.3 (2026-10-19) — infactibles rankeados por violación (reglas de Deb)

Modificación sobre V51.2 (`mision_avion.py`, `evolucion_avion.py`). Motivo: la primera corrida
rápida con V51.2 cortó por paciencia sin encontrar nada (pod_boom en −inf las 4 generaciones;
v_tail con un solo hijo factible). Con todo lo infactible en −inf el GA no tenía hacia dónde ir.

- **Reglas de Deb (2000):** un factible le gana a cualquier infactible; entre factibles gana el
  mejor objetivo; entre infactibles gana el que viola MENOS. Se codifica en el puntaje: un
  infactible vale `−1000 − 10·(9 − etapa) − 9.99·v/(1+v)`, con `etapa` hasta dónde llegó el
  análisis (0 estructura … 9 requisitos) y `v` la violación normalizada del chequeo que falló.
  El análisis sigue cortando en el primer chequeo que falla (no cuesta más). −inf queda solo
  para errores numéricos. Interruptor `RANKING_INFACTIBLES` (solo en el modo "mision").
- `analizar_con_motivo()` devuelve el `Infactible` (etapa, violación, motivo);
  `analizar_mision_avion()` sigue devolviendo None, así que scripts y exportadores no cambian.
  `es_factible()` y `describir_puntaje()` para leer puntajes; el desglose dice por qué falla.
- **Paciencia:** no corre mientras no haya ningún padre factible (bajar la violación ya cuenta
  como mejora); corta `max_generaciones`.
- Notebook: `CORRIDA_RAPIDA` pasa a paciencia 8 y máximo 20 (con 4 cortaba antes de tiempo), y
  los puntajes infactibles se muestran como "infactible: <etapa> (violación v)".
- Tests nuevos: `viento/codigo_viento/tests/test_ranking_infactibles.py`.

## V52 (2026-10-19) — carpeta de resultados y elección de familias

Módulo nuevo `optimizacion_avion/resultados.py` (por eso sube el número).

- `av.guardar_resultados(estados)` guarda cada corrida en
  `resultados/<fecha>_<hora>_viento-<on|off>_bateria-<on|off>_<familias>[_<etiqueta>]/`, sin pisar
  nunca una anterior: `LEEME.md`, `tabla_resumen.csv`, `ganadores.json` (params trimados),
  `convergencia.png`, `comparacion.png`, `curvas_vuelo.png`, `vistas_3d/<familia>.html`,
  `tres_vistas/<familia>.png`, `desgloses/<familia>.txt`. Nomenclatura en `resultados/LEEME.md`.
- Notebook: en la sección 0, `FAMILIAS` elige qué familias correr (una lista o `"todas"`),
  independiente de `CORRIDA_RAPIDA`, que solo fija paciencia y máximo de generaciones.
  `GUARDAR_RESULTADOS` y la sección 11b nueva guardan la carpeta al final.
- `correr_escenarios.py` valida `--topologias`, guarda la carpeta al terminar (`--sin-guardar` para
  no hacerlo) y no se rompe si el mejor avión de una familia queda infactible.
- `Optimizador_V51.3.ipynb` se movió a `codigo_obsoleto/`.

## V52.1 (2026-10-19) — vista 3D con información

- `av.figura_3d(avion, titulo, info)` reemplaza a `avion.draw(backend="plotly")` de AeroSandbox,
  cuya barra de colores no significaba nada (pinta todas las caras con intensidad 0). Ahora: un
  color por componente (ala, cola, fuselaje, vigas) con leyenda, el CG marcado, escala 1:1 en los
  tres ejes y un recuadro con puntaje, energía, masa, batería, envergadura, S, AR, L/D, pérdida,
  SM, incidencia de trim, ráfaga y Cn_beta (`av.lineas_info(analisis, puntaje)`).
- La usan la sección 8 del notebook, `guardar_resultados` (`vistas_3d/<familia>.html`, ahora
  ~100 KB en vez de ~1.5 MB) y `viento/optimizar_con_viento.py`.

## V52.2 (2026-10-19) — líneas de flujo y resultados fuera del repositorio

- **Líneas de flujo** (sección 8b nueva del notebook, `av.figura_flujo(params, familia)`): el avión
  trimado en el punto de crucero, resuelto con el VLM de AeroSandbox. Paneles pintados por la
  circulación Γ [m²/s], líneas de flujo (estela y torbellino de punta), fuselaje de referencia y un
  recuadro con CL y CD inducido del VLM contra los de AeroBuildup. Solo visualización: el VLM es
  inviscido y no ve el fuselaje. También se guardan en `lineas_flujo/<familia>.html` de cada corrida
  (`guardar_resultados(..., flujo=False)` para saltearlas: ~20 s y ~3 MB por familia).
- **Resultados fuera del repositorio:** `CARPETA_RESULTADOS` pasa a ser `Proyecto final/
  resultados_optimizador/` (al lado de `genetic_wing`), o la variable de entorno `UAV_RESULTADOS`,
  o `CARPETA_RESULTADOS` en la sección 0 del notebook. El `LEEME.md` con la nomenclatura se escribe
  solo en esa carpeta. La carpeta `genetic_wing/resultados/` se eliminó (la corrida que había se
  movió a la carpeta nueva).

## V52.3 (2026-10-19) — marca de mejora del notebook

- La marca `<-- mejoro` de la sección 4 se lee del historial (`mejoro`) y no de la racha: mientras no
  hay ningún padre factible la racha queda en 0 (la paciencia no corre) y la marca aparecía en todas
  las generaciones aunque la violación no bajara.

## V52.4 (2026-10-19) — envergadura máxima de 3.0 m (SORA)

- **Requisito nuevo** (modo "mision"): envergadura TOTAL ≤ `mision_avion.ENVERGADURA_MAX_M = 3.0` m,
  medida sobre el avión completo (máximo |y| de todas las superficies, winglets incluidos;
  `analisis["envergadura_total"]`). Motivo: ANAC (Res. 550/2025) no limita la envergadura, pero la
  misión es BVLOS → categoría Específica → evaluación de riesgo documentada (SORA u otra). En la tabla
  de riesgo en tierra de SORA 2.0, BVLOS en zona poco poblada da GRC 4 hasta 3 m y 5 por encima.
  "Por ahora": a confirmar con la Parte 102 de las RAAC.
- `BOUNDS_ALA["envergadura"]` pasa de (2.0, 3.5) a (2.0, 3.0). Las semillas y checkpoints con más
  envergadura se recortan al cargarlos (pueden quedar infactibles en vuelo lento: el ranking por
  violación se encarga).
- El término de envergadura por fabricación (> 2 m) sale del modo "mision" (sigue en "legado").
- Semilla pod_boom[0] de `semillas_bateria.json` / `semillas/bateria_350km.json` reemplazada por un
  fuselaje continuo de 2.0 × 0.165 m con cuerdas ×1.15, factible con viento y batería (1498 Wh).

## V52.5 (2026-10-19) — el ranking suma TODAS las violaciones

- Problema (corrida de v_tail del 19/10): con el ranking por etapas, un avión que pasaba el vuelo
  lento pero era inestable (SM < 0) quedaba MEJOR que uno casi factible al que le faltaba 0.01 de
  vuelo lento. El GA pasó de "vuelo lento 0.00" a "inestable 2.35" y a la generación 15 seguía
  en 1.47.
- Ahora el análisis NO corta en la primera restricción que falla: la anota y sigue
  (`analisis["violaciones_analisis"]`), y el puntaje del infactible usa la SUMA de todas las
  violaciones (volumen, vuelo lento, sustentación en crucero y a V_MAX, trim, ráfaga, banda de SM,
  margen de pérdida, Cn_beta / Cl_beta, envergadura). Solo cortan antes los casos en que el análisis
  no puede seguir (la masa o la batería divergen, un CL_max no calculable...). Con las mismas
  semillas, el GA llega a un avión factible en 4 generaciones.
- Si el trim pide más incidencia que la permitida, se usa la del borde y se anota la violación.
- `analizar_mision_avion` sigue devolviendo None para todo lo que antes invalidaba
  (`_restricciones_duras`), así que el modo "legado", los scripts y los exportadores no cambian.
- Costo: un infactible ahora se analiza completo (~10 s en vez de ~2–5 s).
- `bateria.cerrar_masa_bateria` devuelve inf si el lazo diverge (más de `MASA_BATERIA_MAX_KG` = 50 kg);
  antes un avión muy malo podía tirar OverflowError y cortar la corrida.

## V52.6 (2026-10-20) — tabla de semillas legible

- La tabla de la sección 2 del notebook agrega `estado` (factible, o "infactible: ... (violación v)")
  y `falla` (qué restricción no cumple cada semilla). Un score por debajo de −1000 es un infactible:
  −1000 menos lo que viola; los factibles valen más de 0.

## V53 (2026-10-20) — exportación a XFLR5

Módulo nuevo `optimizacion_avion/xflr5.py` (por eso sube el número).

- `av.exportar_xflr5(params, familia, carpeta)` escribe `<familia>_avion.xml` en el formato XML de
  XFLR5 v6 ("explane", etiquetas verificadas contra el ejecutable de la v6.62), `perfiles/*.dat`
  (Selig) y `condiciones.txt` (velocidad, densidad, viscosidad, masa, CG, alpha de crucero y los pasos
  para importarlo). El avión es el TRIMADO; el ala con sus 11 secciones y los winglets como tramos con
  diedro; colas y derivas (el doble boom como una deriva doble, porque XFLR5 admite una sola). Sin
  fuselaje; la masa total va como masa puntual en el CG.
- Cada corrida guardada trae `xflr5/<familia>/`; para un ganador suelto,
  `python exportar_xflr5_avion.py --params <ganadores.json> --topologia <familia>`.
- Falta probar la importación dentro de XFLR5.
- `CLAUDE.md` nuevo en la raíz: el contexto actual del proyecto para Claude Code (lo carga solo al
  abrir el repo) y para quien llegue nuevo. Hay que mantenerlo al día con cada versión.

## V53.1 (2026-10-20) — la envergadura es la TOTAL (con winglets)

- Problema (corrida de v_tail del 20/10, sin winglets): las dos semillas traían el mismo winglet
  (0.007 m, por debajo del mínimo) y el ala en el máximo de 3.0 m. BLX entre dos valores iguales no
  explora, la mutación es de ~2 cm, y cualquier winglet inclinado sumaba envergadura y pasaba los
  3.0 m. El GA prácticamente no podía probarlos, aunque convienen: con winglets verticales de 0.20 m
  el mismo avión pide 1139 Wh en vez de 1173 (−3 %).
- Ahora el parámetro `envergadura` es la envergadura TOTAL del avión, puntas de winglet incluidas;
  el ala se achica sola lo que ocupen los winglets (`geometria_avion.semi_envergadura`,
  `extension_winglet`). Agregar o inclinar un winglet ya no rompe el límite de 3.0 m.
  Los params viejos con winglets inclinados cambian de geometría (el ala queda algo más corta).
- `semillas_bateria.json` / `semillas/bateria_350km.json`: v_tail[1] ahora tiene winglets verticales
  de 0.18 m (violación 0.02, casi factible), así las dos semillas difieren en el winglet.
- `tabla_resumen.csv` de cada corrida agrega `winglet_m` y la envergadura es la total.

## V54 (2026-10-21) — vuelve el pod boom y el fuselaje continuo es una familia aparte

- **`pod_boom` vuelve a ser el motovelero:** góndola corta + viga fina de cola + cola convencional,
  como estaba hasta el 13/10 (constructor `_fuselaje_pod_boom` recuperado de la historia de git, con
  la nariz roma de V51; masa de la viga en `estructura_avion`; `BOUNDS_POD_BOOM` originales).
- **`fuselaje_continuo` es una familia nueva:** el fuselaje tubular de diámetro casi constante que
  desde el 13/10 se llamaba `pod_boom` (`BOUNDS_FUSELAJE_CONTINUO`). Ahora son 6 familias.
- **OJO con archivos de entre el 13/10 y el 21/10:** lo guardado como "pod_boom" en esas fechas
  (checkpoints, carpetas de `resultados_optimizador/`, `avion_design_params_pod_boom.json`) es en
  realidad un fuselaje continuo. Cargado ahora como pod_boom se convierte en otro avión.
- Semillas: `semillas_bateria.json` y `semillas/bateria_350km.json` tienen `pod_boom` (pod boom real
  reparado para batería + el ganador con viento del 02/10) y `fuselaje_continuo` (el de 2.0 × 0.165 m
  y una variante de 1.6 × 0.18 m); `semillas.json`, `felipe_originales` y
  `ganadores_sin_y_con_viento` suman `fuselaje_continuo`. `semillas_para_escenario` completa las
  familias que le falten a un set con el de batería o con semillas.json. `gen_semillas.py` tiene las
  dos familias.

## V54.1 (2026-10-21) — resultados reproducibles (cachés de perfiles)

- Problema: la misma corrida de v_tail (mismo azar, mismas semillas) dio 1.659 con V53.1 y 1.630
  con V54, que no cambió nada del v_tail. Causa: `perfiles_avion.perfil_con_flap` guardaba el perfil
  con flap bajo la deflexión REDONDEADA a 0.1° pero lo calculaba con la deflexión EXACTA del primero
  que llegaba; los siguientes con la misma clave recibían ese perfil. El resultado dependía del orden
  en que se evaluaron los aviones en el kernel (otra familia antes, la tabla de semillas, una corrida
  anterior). Verificado: el mismo avión daba 1.47988 o 1.48026 según el orden.
- Ahora se calcula con los valores ya redondeados (también en `manufactura.perfil_con_te`): el
  resultado no depende del orden. Cambia muy poco cada avión (deflexión de flap cuantizada a 0.1°),
  pero las corridas de V54.1 no van a coincidir exactamente con las anteriores.
- Regla: un caché con clave redondeada tiene que CALCULAR con el valor redondeado.

## V54.2 (2026-10-29) — borde de fuga abierto hacia el lado correcto

- Problema: `manufactura.perfil_con_te` abría el borde de fuga de 2 mm con
  `asb.Airfoil.set_TE_thickness`, que lo abre en la dirección del hueco que el perfil ya tiene. En
  un perfil cerrado ese hueco es ruido numérico (~1e-20) y la dirección sale al azar:
  - sd7062, fx63137, mh60 y sus mezclas: el extradós quedaba 2 mm POR DEBAJO del intradós (borde de
    fuga cruzado, espesor negativo cerca del borde de fuga). En v_tail, 9 de las 12 secciones del ala.
  - mezclas mh80/fx63137: el hueco se abría en x (filo de ~0.5 mm o menos, no 2 mm).
  - naca0010, naca4412 y sus mezclas salían bien.
  Efectos: XFoil no converge con un borde de fuga cruzado (en XFLR5 las polares de esos perfiles
  terminan "Finished" pero vacías, y el análisis del avión falla con "could not be interpolated
  (Clmax = 0.00)"); en Fusion el loft de esas secciones se corta a sí mismo; NeuralFoil analizaba
  esa forma. `verificar_avion` del CAD no lo detectaba porque mide el hueco sin signo.
- Arreglo: `manufactura.abrir_borde_de_fuga` reemplaza a `set_TE_thickness`. Abre siempre en
  vertical (extradós arriba, intradós abajo), lineal desde el borde de ataque, y corrige la
  diferencia CON SIGNO, así que también endereza un perfil que llegue cruzado. Verificado en los
  ganadores v_tail y pod_boom: las 29 secciones con 2.00 mm y espesor positivo en toda la cuerda.
- `exportar_cad_avion.verificar_avion` suma `borde_fuga_orientado_ok` (aplicado al
  `avion_geometry_cad.json` anterior marca las 6 secciones sd7062 de la raíz).
- `xflr5.py`: un perfil que aparece en dos cuerdas distintas sale como dos `.dat` (el segundo con
  la cuerda en mm en el nombre, p. ej. `fx63137_c92`). Antes salía uno solo, el de la cuerda mayor,
  y en la menor el borde de fuga quedaba más fino que 2 mm (1.3 mm en la punta del v_tail).
- Cambio en los resultados (mismos parámetros, AeroBuildup): v_tail CD crucero +2.7 %, L/D 19.39 →
  19.06, masa +0.9 %, SM 13.8 % → 13.8 %; pod_boom CD +1.2 %, L/D 20.52 → 20.35. Las corridas
  anteriores a V54.2 se hicieron con la forma cruzada: no son comparables uno a uno con las nuevas.
- Notebook regenerado (`Optimizador_V54.2.ipynb`). Pendiente: volver a exportar CAD/XFLR5 de los
  ganadores que se vayan a usar.

