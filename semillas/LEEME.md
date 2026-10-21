# Semillas

Biblioteca de puntos de partida para el optimizador de avión. Cada `.json` es un **set**
con el mismo formato que `optimizacion_avion/semillas.json`:

```
{"convencional": [avion, avion], "t_tail": [...], "v_tail": [...], "doble_boom": [...], "pod_boom": [...]}
```

donde cada `avion` es un diccionario de parámetros. Hacen falta **al menos dos aviones
por topología**: el GA arranca con los dos mejores, y cruzar dos padres iguales no explora.

Un set puede ser un diseño hecho a mano (como las semillas originales de Felipe) o los
**aviones que salieron de una corrida**, para seguir optimizando desde ahí.

## Cómo se usa

**En el notebook** (celda propia, después de importar `optimizacion_avion as av`):

```python
import semillas
semillas.listar()                                              # qué sets hay
av.SEEDS_POR_TOPOLOGIA.update(semillas.cargar("bateria_350km"))
```

`cargar()` pasa cada avión por `clamp_to_bounds_avion`, igual que hace `competencia.py`.

**Guardar una corrida como set nuevo** (desde `genetic_wing`):

```bash
python semillas/guardar_semillas.py checkpoint_avion_*.json --nombre v51_bateria_viento --descripcion "corrida V51 con viento y batería"
```

Acepta checkpoints del notebook (aporta los dos padres finales de cada topología),
archivos `ganadores*.json` y `ganador_viento_<topologia>.json`. Se queda con los dos
mejores por topología y agrega una fila a la tabla de abajo.

**Ver con qué modelo es válido un set:**

```bash
python semillas/validar_semillas.py                # todos
python semillas/validar_semillas.py bateria_350km  # uno
```

Un set inválido con el modelo actual igual sirve de punto de partida (el GA reemplaza a
los padres por el primer hijo válido), pero arranca más lento.

## Sets

Los tres primeros son **copias**: el código de Felipe sigue leyendo los originales en su
lugar (`optimizacion_avion/semillas.json`, `evaluacion_bateria_350km/semillas_bateria.json`),
así que si se regeneran allá hay que volver a copiarlos acá.

Aviones válidos = los que pasan `analizar_mision_avion`, sobre 10 (2 por topología), para cada
combinación de `VIENTO_ACTIVO` / `BATERIA_ACTIVA`. Medido el 2026-10-19 con V51.2: válido = puntaje finito, o sea que además cumple los requisitos pasa/no pasa (banda de SM, Cn_beta/Cl_beta mínimos, margen de pérdida, trim dentro del rango de incidencia). Entre corchetes, V51.1 (solo pasar el análisis).

| Set | Fecha | Qué es | Origen | Aviones válidos (de 10) |
|---|---|---|---|---|
| `felipe_originales` | 2026-09-18 | Semillas a mano de Felipe: A (ala grande, alta sustentación) y B (ala chica) | copia de `optimizacion_avion/semillas.json` (las genera `gen_semillas.py`) | sin batería: 1 sin viento [8], 0 con viento · con batería: 0 y 0 |
| `bateria_350km` | 2026-10-12 (pod_boom[0] reemplazada el 2026-10-19; v_tail[1] el 2026-10-20, ahora con winglets verticales de 0.18 m para que el GA los explore) | Semillas reparadas para el modelo de batería. pod_boom[0] es ahora un fuselaje continuo de 2.0 m × 0.165 m con cuerdas ×1.15, factible con viento y batería (1498 Wh) | copia de `evaluacion_bateria_350km/semillas_bateria.json` (`reparar_semillas.py`) | sin batería: 4 sin viento [10], 3 con viento [5] · con batería: 4 sin viento [10], **4 con viento** [9] |
| `ganadores_sin_y_con_viento` | 2026-10-17 | Por topología: el ganador con viento y el ganador sin viento del 18/09 (lo mismo que arma `competencia.semillas_para_escenario` con viento y sin batería) | `optimizacion_avion/ganadores_viento.json` + `ganadores.json` | sin batería: 7 sin viento [8], 0 con viento · con batería: 2 sin viento, 0 con viento |
