# Contexto para Claude — optimizador de UAV de ala fija (Proyecto Final, ITBA)

Este archivo lo lee Claude Code automáticamente al abrir el repositorio. Resume el estado ACTUAL
del proyecto para que cualquiera del equipo (Felipe, Ivna, Santi) arranque con el mismo contexto.
El historial de cambios está en `VERSIONES.md`; el informe largo, en `README.md` (su §7 es
histórico, del 18/09). Mantener este archivo al día cuando cambie algo de lo que dice.

## Qué es

Un algoritmo genético (GA) que diseña un UAV eléctrico de ala fija para **Quintana Energy**:
monitorear pozos petroleros remotos (Cañadón León, Santa Cruz; Puesto Hernández, Mendoza) a
60–70 km de la base. Compiten 6 **familias** (topologías): `convencional`, `t_tail`, `v_tail`,
`doble_boom`, `pod_boom` (motovelero: góndola + viga fina) y `fuselaje_continuo` (fuselaje tubular
de diámetro casi constante). Ojo: entre el 13/10 y el 21/10, "pod_boom" era el fuselaje continuo.
Cada familia evoluciona por separado y al final se
comparan. Aerodinámica: AeroSandbox (AeroBuildup + NeuralFoil). Todo en Python, en español.

**Versión actual: ver `VERSION` en `optimizacion_avion/__init__.py`** (el notebook se llama
`Optimizador_<VERSION>.ipynb`).

## Misión (en `optimizacion_avion/mision_avion.py` y `bateria.py`)

- Crucero de diseño **80 km/h**, velocidad máxima **120 km/h**, vuelo lento **10 m/s**, 3 kg de carga útil.
- **Alcance 350 km** a velocidad de crucero, con la batería dimensionada por ese alcance
  (`BATERIA_ACTIVA`, lazo cerrado masa de batería ↔ resistencia; celda Molicel M65A, eta propulsiva 0.65 supuesta).
- **Viento de los sitios** (`VIENTO_ACTIVO`): densidad 1.056 kg/m³, ráfaga 4.63 m/s, turbulencia de Dryden.

## Cómo se puntúa (modo `PUNTAJE_MODO = "mision"`, el de trabajo)

- **Objetivo único:** energía de batería para volar el alcance, `1.0 · 1200 Wh / E`.
- **Pendientes de decisión** (con su forma y peso de antes): margen de vuelo lento (1.0) y
  resistencia a 120 km/h (0.5).
- **Requisitos pasa / no pasa:** volumen de fuselaje, volar a 10 m/s con flap, sostenerse a
  120 km/h, margen estático dentro de la banda 10–20 %, margen de pérdida con ráfaga ≥ 20 %,
  Cn_beta ≥ 0.0005 y Cl_beta ≤ −0.0005 /grado (supuestos), ráfaga del sitio ≤ carga límite 3.0 g,
  trim posible dentro del rango de incidencia, **envergadura total (con winglets) ≤ 3.0 m**.
  El parámetro `envergadura` ES la total: el ala se achica sola lo que ocupen los winglets
  (`semi_envergadura`), así agregar un winglet nunca rompe el límite.
- **Trim resuelto** (`TRIM_RESUELTO`): la incidencia de cola se calcula para Cm = 0 en crucero.
  El avión "real" es `av.params_trimados(params, familia)`; eso es lo que se exporta.
- **Infactibles rankeados por violación (reglas de Deb):** un avión que no cumple NO vale −inf:
  vale `−1000 − (suma de violaciones)`. **Un puntaje < −1000 es infactible**; uno > 0 es factible.
  Para leerlo: `av.describir_puntaje(s)`, `av.es_factible(s)`; para saber qué falla:
  `av.analizar_con_motivo(...)` o `av.desglose_mision_avion(...)`.
- `PUNTAJE_MODO = "legado"` reproduce la suma de 11–12 términos anterior (para comparar con
  corridas viejas). Los puntajes de distintos modos/versiones NO son comparables: comparar
  energía (Wh) y masa.

## Mapa del código

| Dónde | Qué |
|---|---|
| `optimizacion_avion/geometria_avion.py` | Familias, `BOUNDS_*`, `construir_avion` (asb.Airplane), proyecciones de fabricación |
| `optimizacion_avion/mision_avion.py` | Análisis de misión, requisitos, puntaje, trim, ranking de infactibles |
| `optimizacion_avion/estructura_avion.py` | Masa (larguero por flexión + rigidez, piel, cola, fuselaje) |
| `optimizacion_avion/bateria.py`, `viento.py`, `manufactura.py` | Batería por alcance, viento de los sitios, borde de fuga 2 mm y nariz roma |
| `optimizacion_avion/ga_numerico_avion.py`, `evolucion_avion.py` | Operadores (BLX-α, mutación, wildcards) y el loop (μ+λ, μ=2) |
| `optimizacion_avion/competencia.py` | Semillas por escenario (`semillas_para_escenario`) y orquestador |
| `optimizacion_avion/resultados.py` | Carpeta de resultados de cada corrida, vista 3D, líneas de flujo (VLM) |
| `optimizacion_avion/xflr5.py` | Exportación a XFLR5 (XML + perfiles .dat + condiciones) |
| `optimizacion_ala/` | El paquete viejo del ala volante; el avión reutiliza de ahí materiales, proyecciones y perfiles |
| `construir_notebook_avion.py` | **Genera** `Optimizador_<VERSION>.ipynb` |
| `viento/` | Caracterización de viento (ERA5), paquete `viento_uav`, tests |
| `semillas/` | Biblioteca de sets de semillas (`semillas.listar()`, `semillas.cargar(nombre)`) |
| `evaluacion_bateria_350km/` | `correr_escenarios.py` (corridas por línea de comandos), `reparar_semillas.py` |
| `exportar_cad_avion.py`, `exportar_cfd_avion.py`, `exportar_xflr5_avion.py`, `fusion_generar_avion.py` | Llevar un ganador a Fusion, CFD o XFLR5 |
| `documentos_de_decision/` | Research Notes (15: misión; 16: viento; 17: baterías) |

## Cómo se usa

- **Notebook** `Optimizador_<VERSION>.ipynb`, sección 0 (interruptores): `VIENTO`, `BATERIA`,
  **`FAMILIAS`** (lista o `"todas"`), `CORRIDA_RAPIDA` (paciencia/generaciones 8/20 o 10/60),
  `SET_SEMILLAS`, `SEMILLA_AZAR`, `GUARDAR_RESULTADOS`, `CARPETA_RESULTADOS`. Correr en orden.
- **Línea de comandos:** `python evaluacion_bateria_350km/correr_escenarios.py --viento on --bateria on --topologias v_tail pod_boom`
- **Resultados:** cada corrida se guarda FUERA del repo, en `../resultados_optimizador/<fecha>_<hora>_<escenario>_<familias>/`
  (o la variable de entorno `UAV_RESULTADOS`): LEEME, tabla, `ganadores.json` (params trimados),
  gráficos, vistas 3D, líneas de flujo, desgloses y `xflr5/<familia>/`. Nunca se pisa una corrida.
- **Tests:** `python -m pytest viento/codigo_viento/tests -q` (29 tests, ~6 min; los de ranking son rápidos).
- Los `checkpoint_avion_*.json` de la raíz son los 2 mejores aviones de la última corrida de cada
  familia (se pisan en cada corrida). Están en `.gitignore` pero quedaron versionados de antes.

## Reglas del proyecto (respetarlas)

- **Versionado** (`VERSIONES.md`): un cambio sobre lo existente sube el decimal (V53 → V53.1);
  agregar o modificar un MÓDULO sube el número (V53 → V54). Al subir: cambiar `VERSION` en
  `optimizacion_avion/__init__.py`, correr `python construir_notebook_avion.py`, mover el notebook
  anterior a `codigo_obsoleto/` y anotar el cambio en `VERSIONES.md`.
- **No editar el `.ipynb` a mano:** se regenera desde `construir_notebook_avion.py`.
- **Cambiar `BOUNDS_*` o la misión** puede dejar inválidas semillas y checkpoints viejos (el GA
  igual arranca, ordenando por violación). Avisar en `VERSIONES.md`.
- **Catálogo de perfiles** (`perfiles_avion.py`): agregar solo al final, nunca reordenar (los
  índices son variables de diseño).
- `analizar_mision_avion` devuelve `None` para cualquier avión que no cumple; para el motivo usar
  `analizar_con_motivo`. No sumar `_terminos` a mano: usar `puntaje_de_analisis` (respeta los requisitos).
- Errores de programación (KeyError, TypeError, ...) dentro del análisis SUBEN a propósito; los
  numéricos descartan el candidato y se cuentan en `mision_avion.FALLAS_ANALISIS`.
- Archivos con CRLF y UTF-8; escribir siempre con `encoding="utf-8"` (Windows usa cp1252 por defecto).
- Cachés (perfiles, flap, borde de fuga): si la clave se redondea, el valor se CALCULA con lo
  redondeado; si no, el resultado depende del orden de evaluación y las corridas no se reproducen.
- Autoría: el código general es de Felipe; el viento (`viento/`, `optimizacion_avion/viento.py`,
  partes `VIENTO_ACTIVO`) es de Ivna. Si un cambio toca código del otro, decirlo.

## Decisiones pendientes (no "arreglarlas" sin hablar con el equipo)

- **Velocidad lenta:** Quintana pidió ~7 m/s para sensores de metano/IR; el modelo usa 10 m/s.
- **Viento / velocidad máxima:** cómo pesar la operación con viento fuerte (45 km/h recomendado, 20 m/s extremo).
- **Envergadura 3.0 m:** sale de SORA (ANAC Res. 550/2025: el vuelo BVLOS es categoría Específica y
  pide una evaluación de riesgo tipo SORA; > 3 m sube un escalón el riesgo en tierra). A confirmar
  con la Parte 102 de las RAAC.
- **Supuestos sin medir:** eta propulsiva 0.65, CN_BETA_MIN / CL_BETA_MIN, factor de volumen útil 0.55,
  masa de sistemas sin batería 1.0 kg.
- **Fuera del modelo:** torsión/flutter del ala, hélice, superficies de control, fuselaje en el VLM.
