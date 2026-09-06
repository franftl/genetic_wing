# UAV FP — Estado del Proyecto y Próximos Pasos

*Compilado 14 agosto 2026. Síntesis de todo lo relevado hasta ahora (Notas 1-13 + documento de objetivos entregado a la junta), para ordenar qué sigue y qué falta saber antes de cerrar el scope definitivo.*

## 1. Dónde estamos parados

El proyecto pasó por dos pivotes grandes: de "UAV autónomo de monitoreo O&G con cámara de gas" (descartado por costo de la cámara OGI) a "UAV de RGB + térmica opcional", y de ahí al pivot mayor actual: **el desarrollo se centra en un pipeline de IA que optimiza genéticamente la geometría de un ala volante, y después la construye**. Eso quedó formalizado en el documento entregado a la junta (`UAV_FP_Objetivos_Minimos_Maximos.docx`):

- **Objetivo mínimo:** relevar los requisitos operativos de Vaca Muerta (viento, autonomía, terreno) → optimizar la geometría con red neuronal (NeuralFoil) + algoritmo genético, evaluando con VLM (AeroSandbox) → validar por CFD → construir un MVP → dimensionar/fabricar liviano.
- **Objetivos máximos:** vuelo autónomo GPS, visión computacional + seguimiento en tiempo real, telemetría BVLOS, baterías de mayor densidad, y — como extensión sujeta a presupuesto — sensor térmico/gas.

**Estado del código:** existe un notebook de análisis VLM (`UAV_FP_flying_wing_optimization.ipynb`), un script de generación CAD que corre dentro de Fusion (`fusion_generar_ala.py`, ya con el perfil `rg15.dat` resuelto), y un test harness del loop evolutivo (`evolutionary_design.py`) que usa a Claude como operador de cruzamiento. La función objetivo de este último sigue siendo un placeholder (solo L/D en un punto de vuelo fijo) — eso quedó documentado en detalle en la Nota 11, con un esqueleto concreto de los cinco cambios que le faltan.

**Un dato a tener en cuenta antes de seguir:** de las últimas ~6 consultas, la gran mayoría (Notas 9, 12, 13) fueron sobre tecnología de detección de gas/metano — que en el documento oficial de objetivos es un **objetivo máximo**, no el mínimo. Nada de eso está mal — es información valiosa y probablemente entra en el marco teórico de la tesis — pero vale la pena decirlo explícitamente: el esfuerzo de investigación reciente estuvo desacoplado del objetivo mínimo comprometido con la junta (la optimización aerodinámica), que es donde todavía hay definiciones pendientes concretas (ver sección 3). No hace falta resolver esto ahora mismo, pero sí conviene que el equipo lo tenga presente al repartir el tiempo que queda del año.

## 2. Próximos pasos, por frente de trabajo

### A. Pipeline de optimización aerodinámica (el objetivo mínimo — el frente más urgente)

1. **Cerrar la función objetivo real**, siguiendo el esqueleto de la Nota 11: sumar margen estático, margen de entrada en pérdida, estimador de peso estructural, normalización de términos, evaluación en barrido de ángulos de ataque.
2. **Decidir el backend del algoritmo genético** — esto sigue abierto desde la Nota 9: ¿se sigue con el cruzamiento vía IA de `evolutionary_design.py` (más caro, más lento, pero razona semánticamente), se pasa a un GA numérico clásico (PyGAD/DEAP, más fiel al paper de Tran et al.), o al optimizador por gradiente nativo de AeroSandbox (`asb.Opti`, más rápido si la función es diferenciable)? Es una decisión de diseño, no algo que dependa de más investigación.
3. **Correr la optimización con el objetivo real** y obtener un primer diseño candidato serio (no el placeholder de L/D solo).
4. **Validar ese diseño por CFD** — FluidX3D es el candidato que evaluamos; falta efectivamente instalarlo/correrlo con una geometría real exportada como STL.
5. **Iterar la geometría en Fusion** con `fusion_generar_ala.py` usando los parámetros del diseño ganador.
6. **Arrancar la definición de fabricación** (ver frente D).

### B. Encuadre operativo/regulatorio

1. Revisar en detalle la Resolución ANAC 550/2025 para confirmar bajo qué categoría (Open/Specific/Certified) va a operar la misión real, y si BVLOS es efectivamente necesario dado el radio de operación real (esto todavía no se relevó con un número concreto — ver vacío en sección 3).
2. Definir dónde se van a hacer los vuelos de validación/prueba del MVP — Vaca Muerta específicamente, o un sitio de prueba más accesible cerca de Buenos Aires que simule las condiciones relevantes.

### C. Payload de monitoreo (el objetivo máximo — decisión de alcance, no de investigación)

Dado el volumen de opciones ya relevadas (OGI, TDLAS standoff/punto, electroquímicos, el enfoque de visión por computadora de SkySniff, magnetometría para pozos huérfanos), el paso que falta acá no es investigar más tecnología — es **decidir si alguna de estas entra al desarrollo real de este año o si todo queda documentado como trabajo futuro en la tesis**. Esa decisión determina si vale la pena, por ejemplo, cotizar el TDLAS standoff (Bridger/SeekOps) en serio o no.

### D. Fabricación y MVP

1. Decidir entre corte de espuma por hilo caliente (CNC) o impresión 3D con optimización topológica para las piezas estructurales — ninguna de las dos rutas tiene todavía una decisión de "cuál, con qué máquina, dónde" (¿tiene ITBA una cortadora de hilo caliente, o hay que construir una?).
2. Una vez que haya una geometría validada, definir la lista de materiales real (espuma, fibra de carbono para el larguero, servos, motor, ESC, batería) y empezar a cotizar.

## 3. Vacíos de conocimiento concretos

Esto es lo que hace falta saber —por investigación, por dato de campo, o por decisión de equipo— para poder cerrar el scope definitivo. Los separo por tipo, porque no todos se resuelven de la misma manera:

| Vacío | Por qué importa | Cómo se resuelve |
|---|---|---|
| Datos reales de viento en Vaca Muerta (velocidad media, ráfagas) | Es el insumo directo para el margen de estabilidad/entrada en pérdida de la función objetivo (sección 2.1 del doc de objetivos) — sin esto, los pesos de la función objetivo son una suposición | Dato de campo/investigación — hay estaciones meteorológicas públicas en la zona (SMN, o datos abiertos de Neuquén) que probablemente ya tienen esto relevado |
| Distancia típica entre pozos y base de operación | Define la autonomía/alcance objetivo, que a su vez define si hace falta BVLOS y qué tanto pesa la batería en la función objetivo | Investigación — densidad de pozos por bloque en Vaca Muerta es información pública (mapas de YPF/Neuquén) |
| Peso objetivo del payload de misión | Es un input que la optimización de ala necesita para dimensionar correctamente, y hoy no está definido porque el sensor de monitoreo quedó como "objetivo máximo" — es un problema del huevo y la gallina | Decisión de equipo — conviene fijar un peso de payload de trabajo (aunque sea provisorio, ej. "500 g reservados para cámara + electrónica") para poder cerrar la optimización, en vez de esperar a decidir el sensor final |
| Margen estático mínimo aceptable | Es la restricción dura que la Nota 11 dejó como placeholder (`MARGEN_ESTATICO_MINIMO`) | Investigación puntual — hay valores de referencia típicos en literatura de ala volante (el propio paper de Tran et al. da un punto de partida) |
| Modelo de peso estructural | La función objetivo no tiene hoy ningún término de peso | Puede ser una fórmula semi-empírica simple para arrancar (superficie alar × densidad areal de referencia), sin necesidad de un modelo estructural completo todavía |
| Acceso a fabricación (cortadora CNC de hilo caliente o impresora 3D adecuada) | Sin esto, "construir el MVP" queda abstracto | Relevamiento interno — qué tiene disponible ITBA, qué hay que conseguir o construir |
| Licencia de FluidX3D para uso de tesis | "Gratis para uso no comercial" es ambiguo si el proyecto termina asociado a un sponsor | Consulta directa al desarrollador (ProjectPhysX) antes de comprometerse a usarlo para la validación final |
| Alcance real del payload de monitoreo este año | Determina si vale la pena seguir cotizando TDLAS/OGI o cerrar ese capítulo como trabajo futuro | Decisión de equipo, no investigación |

## 4. Sobre reiniciar el codebase: Jupyter o Python

Ver la respuesta en el chat — la recomendación es un esquema híbrido: lógica reutilizable en módulos `.py` planos, y un notebook como "panel de control" para correr y ver la optimización paso a paso.
