# UAV FP — Research Note 11: Walkthrough de `evolutionary_design.py` y cómo evolucionar la función objetivo

*Compilado 14 agosto 2026. Sigue a la Nota 9 (implementación en Python) y a la Nota 10 (parametrización en Fusion). Este documento analiza el script `evolutionary_design.py` que subiste — es un test harness de la mecánica del algoritmo, no todavía la herramienta de diseño final, y el propio archivo lo dice explícitamente en su docstring.*

## 1. Qué es y qué NO es este script

Antes de entrar al detalle: el propio código se declara a sí mismo un arnés de prueba (*test harness*) para la **mecánica** del loop evolutivo (selección, cruzamiento vía IA, criterio de parada), no para el **contenido** del diseño real. Dos cosas están explícitamente marcadas como placeholder:

- La función objetivo (`evaluate_candidate`) hoy solo maximiza L/D (planeo) en un único punto de vuelo fijo.
- El criterio de parada ("2 generaciones consecutivas sin mejora") es una interpretación razonable de lo que se había hablado, pero no una decisión cerrada.

Esto importa porque tu pregunta — cómo modificar la función objetivo — es exactamente el punto que el propio autor del script dejó señalado como pendiente. No hay que "arreglar un error"; hay que completar una pieza que se dejó intencionalmente vacía para poder probar el resto primero.

## 2. Representación del candidato

Cada diseño candidato es un `Candidate`: los mismos 7 parámetros geométricos que ya vienen apareciendo en todo el proyecto (`root_chord`, `tip_chord`, `half_span`, `le_sweep_offset`, `tip_dihedral`, `root_twist`, `tip_twist`), más un campo `score`. El perfil aerodinámico queda fijo (MH60, reflexado) — por ahora solo se está evolucionando el planform, no la sección.

`BOUNDS` define el espacio de diseño válido para cada parámetro (ej. `half_span` entre 0.50 y 2.00 m). Un detalle de implementación importante: estos límites **no** se le imponen a la IA a nivel de esquema — el schema estructurado de salida (`ChildCandidate`, ver sección 4) no soporta declarar mínimos/máximos numéricos — así que se le piden como instrucción en el texto del prompt, y después `clamp_to_bounds()` recorta a la fuerza cualquier valor propuesto que se haya ido de rango antes de evaluarlo. Es un doble resguardo razonable (pedir + forzar), pero vale notar que si la IA se sale de rango seguido, el recorte silencioso puede estar empujando muchos candidatos hacia el borde del espacio de diseño sin que se vea en los logs — es algo a vigilar si el algoritmo converge sospechosamente rápido hacia un límite.

## 3. El loop evolutivo, paso a paso

1. **Población semilla:** arranca con un puñado de diseños candidatos definidos a mano (en el `if __name__ == "__main__":` hay 2 de ejemplo).
2. **Evaluación:** cada candidato se puntúa con `objective_fn` (por defecto `evaluate_candidate`, que corre el VLM vía AeroSandbox y devuelve CL/CD).
3. **Selección de padres:** se ordenan por score y se toman los 2 mejores como "padres" de la generación actual.
4. **Cruzamiento vía IA:** se le pide a Claude que proponga N diseños "hijos" (10 por defecto: 7 combinando/mutando los padres + 3 "wildcard" completamente exploratorios) — ver sección 4, es la parte más distinta de un algoritmo genético clásico.
5. **Evaluación de hijos** con la misma `objective_fn`.
6. **Reemplazo elitista:** se junta el pool (2 padres + N hijos), se ordena por score, y los 2 mejores de ese pool combinado pasan a ser los padres de la próxima generación. Si ningún hijo superó al peor de los dos padres actuales, esa generación cuenta como "sin mejora".
7. **Corte:** después de 2 generaciones seguidas sin mejora (o al llegar a `max_generations`), el loop para y devuelve el mejor de los 2 padres finales.

Cada generación se guarda en `evolution_checkpoint.json` — así, si el proceso se corta a mitad de camino (por límite de uso de la API, falla de red, etc.), no se pierde el progreso: el mejor diseño encontrado hasta ese punto queda en disco.

## 4. Cómo se integra la IA — el punto más importante para entender el script

Esto es lo que hace que este NO sea un algoritmo genético en el sentido clásico. Un GA tradicional (como el que usa el paper de Tran et al. que venimos citando) cruza dos padres con un operador **numérico**: por ejemplo, promediar sus parámetros, o intercambiar genes al azar entre ambos vectores. Acá, en cambio, el "operador de cruzamiento" es directamente **una llamada a un modelo de lenguaje** (`ai_generate_children`):

- Se arma un prompt (`_build_crossbreed_prompt`) que le describe a Claude el significado físico de cada uno de los 7 parámetros, los límites del espacio de diseño, y los valores + score de los dos padres actuales.
- Se le pide que proponga los hijos en dos grupos distintos, con roles distintos:
  - **"crossbred"**: combinar/interpolar rasgos de ambos padres, con alguna mutación que empuje un poco más allá de ambos en una dirección prometedora — esto es lo más parecido a un crossover + mutación clásico, pero hecho por razonamiento en lugar de aritmética.
  - **"wildcard"**: propuestas independientes de los valores puntuales de los padres, usando "criterio propio" sobre qué podría funcionar para un ala volante eficiente — el objetivo explícito de este grupo es evitar que la búsqueda converja prematuramente a lo que los primeros dos padres ya representan (el problema clásico de "diversidad genética" en un GA con población chica).
- La respuesta se fuerza a una forma estructurada con `pydantic` (`ChildCandidate`/`CrossbreedResult`: los 7 parámetros + `origin` + `rationale`), para poder parsearla de manera confiable en vez de tener que interpretar texto libre. Aun así, el código tiene un `_parse_crossbreed_response` con fallback (recortar el bloque `{...}` de la respuesta) por si el modelo agrega texto o un code fence alrededor del JSON pese a la instrucción de no hacerlo.
- Los valores que vuelven se pasan por `clamp_to_bounds()` antes de evaluarse — el resguardo mencionado en la sección 2.

Hay dos backends intercambiables para hacer esta llamada, con un trade-off real entre ellos:

| Backend | Cómo se llama | Se factura contra | Consideración |
|---|---|---|---|
| `"api"` | API de Mensajes de Anthropic (`client.messages.create`) | Créditos pay-as-you-go de la API (requiere `ANTHROPIC_API_KEY`) | Más directo/programático, pero es gasto separado de una suscripción |
| `"cli"` | CLI de Claude Code en modo headless (`claude -p ... --output-format json`) | El uso incluido de tu suscripción de claude.ai/Claude Code | No gasta créditos de API aparte, pero queda sujeto a los límites de uso de esa suscripción, y el script mismo advierte que los flags de la CLI no fueron probados en este entorno — conviene verificar con `claude --help` antes de confiar en ellos |

El script por defecto corre con `BACKEND = "cli"` en el bloque de demo.

**Por qué usar IA acá y no un crossover numérico tradicional:** la ventaja conceptual es que la IA puede razonar sobre combinaciones que tengan sentido de ingeniería (por ejemplo, "si este padre tiene mucha flecha y este otro mucho washout, combinar ambos rasgos en una dirección que probablemente mejore la estabilidad") en lugar de simplemente promediar números sin ningún criterio físico de por medio. La desventaja es que cada generación ahora depende de una llamada de red no determinística, con la latencia, el costo (o consumo de cuota) y el parsing de JSON que eso implica — es una superficie de falla que un crossover aritmético simple no tiene, y por eso el código tiene tanto manejo defensivo alrededor (try/except en la llamada, checkpoint después de cada generación, fallback de parseo).

## 5. La función objetivo actual — y qué le falta

Hoy `evaluate_candidate()` hace exactamente una cosa: corre el VLM en un único punto de operación fijo (`velocity=20 m/s, alpha=4°`) y devuelve `CL/CD` (planeo). Todo lo demás es rechazo cableado a mano: si `tip_chord > root_chord` (no es un ahusamiento válido) o si el solver falla o devuelve algo no finito, el score es `-inf` para que ese candidato se hunda solo en el ranking sin romper el loop.

También existe `evaluate_candidate_toy()`, una función completamente no aerodinámica (no corre VLM en absoluto) usada solo para probar que el mecanismo del loop (llamada a IA + parseo + selección + checkpoint) funciona de punta a punta sin gastar tiempo de cómputo ni tokens en algo que todavía no importa. Es la que está activa en el bloque de demo (`objective_fn=evaluate_candidate_toy`) — el propio script indica que hay que volver a `evaluate_candidate` (o al objetivo real) una vez confirmada la plomería.

### Qué habría que agregar para que sea la función objetivo real del proyecto

Tomando la función objetivo ponderada que ya definimos como marco (Nota — documento de objetivos mínimos/máximos entregado a la junta), a `evaluate_candidate()` le faltan, como mínimo, estas piezas:

1. **Más de un criterio, no solo L/D.** Sumar el margen estático (o directamente la pendiente de `Cm` respecto a `alpha`, que ya devuelve el VLM), el `CL` máximo o margen a la entrada en pérdida, y una estimación de peso estructural — hoy ninguno de estos entra al score en absoluto.
2. **Combinar esos criterios con pesos, no in situ sino normalizados.** L/D, margen estático y peso estructural están en escalas numéricas completamente distintas (L/D puede ser ~15-30, el margen estático es una fracción de la cuerda ~0.05-0.15, el peso en kg puede ser ~1-5). Sumarlos directamente con pesos arbitrarios hace que el término de mayor magnitud numérica domine el score sin que eso sea la intención — hace falta normalizar cada término (por ejemplo, contra un rango esperado o con z-score) antes de combinarlos.
3. **Evaluar en más de un punto de operación.** Hoy todo el objetivo se calcula a `alpha=4°` fijo. Dado que Vaca Muerta tiene un régimen de viento con ráfagas (relevado en la sección 2.1 del documento de objetivos), tiene sentido evaluar cada candidato en un pequeño barrido de `alpha` (o de velocidad) y usar el peor caso (robustez) o un promedio ponderado, en lugar de un único punto — así el algoritmo no premia diseños que son excelentes a `alpha=4°` pero se comportan mal apenas cambia la condición de vuelo.
4. **Restricciones duras, no solo blandas.** El paper de Tran et al. que citamos encontró exactamente el problema que este objetivo actual va a reproducir si no se corrige: optimizar solo L/D converge a diseños inestables (margen estático negativo). Conviene agregar una penalización fuerte (no solo un descarte a `-inf`, que trata "un poco inestable" igual que "geométricamente inválido") cuando el margen estático cae por debajo de un mínimo aceptable, en vez de dejar que el término de estabilidad compita en igualdad de condiciones con el de eficiencia.
5. **Un estimador de peso estructural.** Hoy no existe ningún término de peso en absoluto. No hace falta un modelo estructural completo para arrancar — un modelo semi-empírico simple (proporcional a la superficie alar y a alguna referencia de espesor/material) ya sería suficiente para que el algoritmo empiece a penalizar geometrías innecesariamente grandes o pesadas.

Un esqueleto de cómo quedaría la firma de la función (sin implementar el detalle de cada término, que depende de decisiones de diseño que el equipo todavía tiene que fijar):

```python
def evaluate_candidate(params: dict) -> float:
    if params["tip_chord"] > params["root_chord"]:
        return -np.inf

    airplane = build_airplane(params)

    # Barrido de puntos de operación en vez de uno solo, para robustez frente a ráfagas
    resultados = []
    for alpha in ALPHA_SWEEP:  # ej. [0, 4, 8, 12] grados
        vlm = asb.VortexLatticeMethod(airplane=airplane, op_point=asb.OperatingPoint(velocity=20, alpha=alpha))
        aero = vlm.run()
        if not np.isfinite(aero["CL"]) or not np.isfinite(aero["CD"]) or aero["CD"] <= 0:
            return -np.inf
        resultados.append(aero)

    ld_peor_caso = min(r["CL"] / r["CD"] for r in resultados)
    margen_estatico = estimar_margen_estatico(airplane, resultados)   # a partir de dCm/dalpha
    peso_estructural = estimar_peso(params)                            # modelo semi-empírico, TODO

    if margen_estatico < MARGEN_ESTATICO_MINIMO:
        return -1000 + margen_estatico  # penalización fuerte pero graduada, no un -inf duro

    score = (
        PESO_LD * normalizar(ld_peor_caso, rango_ld)
        + PESO_ESTABILIDAD * normalizar(margen_estatico, rango_margen)
        - PESO_PESO * normalizar(peso_estructural, rango_peso)
    )
    return score
```

Los `PESO_*` son exactamente los mismos pesos que quedaron como "esquema abierto" en la sección 2.3 del documento de objetivos entregado a la junta — este es el lugar concreto del código donde esa decisión de ponderación termina aterrizando.

## 6. Otras dos cosas para tener en el radar (no bloqueantes, pero vale mencionarlas)

- **Población élite muy chica (2 padres):** favorece convergencia rápida, pero con solo 2 padres el riesgo de quedar atrapado en un óptimo local es mayor que con una población más amplia — algo para probar/ajustar una vez que el objetivo real esté puesto, no antes.
- **Criterio de parada sensible al ruido de la IA:** como el "cruzamiento" no es determinístico, 2 generaciones sin mejora podría ser mala suerte en el muestreo más que una señal real de convergencia. Si en la práctica el loop corta demasiado pronto, subir ese número (o exigir una mejora relativa mínima en vez de cualquier mejora) es un ajuste simple.

## Fuentes

- Código analizado: `evolutionary_design.py` (provisto por el usuario, 14 agosto 2026)
- [AeroSandbox — VortexLatticeMethod / OperatingPoint (GitHub)](https://github.com/peterdsharpe/AeroSandbox)
- Tran, D.T.; Pham, V.K.; Nguyen, A.T.; Nguyen, D.-T. *Aerodynamic Design Optimization for Flying Wing Gliders Based on the Combination of Artificial Neural Networks and Genetic Algorithms*. Aerospace 2025, 12(9), 818 — [mdpi.com/2226-4310/12/9/818](https://www.mdpi.com/2226-4310/12/9/818)
- Documento entregado a la junta: `UAV_FP_Objetivos_Minimos_Maximos.docx` (sección 2.3, función objetivo ponderada)
