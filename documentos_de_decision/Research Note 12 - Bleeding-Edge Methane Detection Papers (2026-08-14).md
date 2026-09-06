# UAV FP — Research Note 12: Papers on Bleeding-Edge Methane Detection Hardware (con detalle de implementación)

*Compilado 14 agosto 2026. Sigue a la conversación sobre cámaras OGI, detección digital de metano y FluidX3D. Estos son papers que no solo describen el estado del arte, sino que dan suficiente detalle técnico (componentes, esquemas, especificaciones) como para entender cómo se construyen estos sistemas — no solo qué hacen.*

## 1. La más relevante para ustedes: plataforma UAV de bajo costo (SkySniff, UCSD)

**["Remote Gas Leak Detection on a Low-Cost UAV Platform" (UC San Diego)](https://kastner.ucsd.edu/wp-content/uploads/2025/06/admin/gasleakdrone.pdf)**

Esta es probablemente la más accionable de todas para un proyecto de tesis con presupuesto acotado, porque **no usa una cámara OGI en absoluto** — y por eso vale la pena revisar la conclusión de costo que habían cerrado antes con cuidado, sin sobre-interpretarla.

- **Hardware:** un microbolómetro térmico no enfriado (VOx, el mismo tipo de sensor "genérico" que ya habíamos descartado para detección de gas por motivos físicos) combinado con una cámara RGB FPV normal. Costo total declarado: **menos de USD 1.000**, peso máximo de despegue de **250 g**.
- **Método:** en vez de depender de que el sensor "vea" el gas ópticamente (que es justamente lo que un microbolómetro genérico no puede hacer sin filtrado espectral, como ya habíamos establecido), el sistema fusiona la imagen térmica con la imagen RGB y usa un modelo de segmentación semántica (U-Net, preentrenado sobre ImageNet, con 3 clases: fondo / fuga diurna / fuga nocturna) entrenado sobre un dataset propio de fugas etiquetadas, corriendo la inferencia en tierra (no a bordo, por restricción de peso) a ≥10 Hz.
- **Resultados:** 85% de accuracy en su dataset propio, con demostración exitosa de detección de plumas de escape en condiciones nocturnas reales; los propios autores marcan esto como prueba de concepto, con problemas de calibración/alineación óptica pendientes de resolver.

**Por qué importa sin contradecir lo que ya sabían:** el hallazgo anterior (que un microbolómetro genérico no puede reemplazar físicamente a una cámara OGI espectralmente filtrada) sigue siendo correcto — este paper no hace imaging espectral del gas. Lo que hace es una cosa distinta: usar visión por computadora para reconocer el patrón térmico/visual indirecto de una fuga (diferencial de temperatura por expansión adiabática, distorsión visual del aire, plumas visibles de noche) en vez de "ver" el gas directamente. Es una ruta alternativa genuina, no una versión barata de OGI — con su propio techo de precisión (85%, en fase de prueba de concepto) y limitaciones (probablemente mucho más difícil en condiciones diurnas que en las nocturnas que mostraron). Vale la pena tenerlo en el radar como el camino de "detección aproximada muy barata" en paralelo al camino de "TDLAS de estándar más alto pero más caro" de los papers siguientes.

## 2. Diseños de sensores TDLAS miniaturizados — con nivel de detalle de componentes

Estos dos papers documentan sensores TDLAS lo suficientemente livianos como para pensar en integrarlos a un ala volante, con listas de componentes reales (no solo principios de funcionamiento):

**["Ultra-Lightweight Mid-IR Methane Sensor for UAV-based Measurements" (EGUsphere/Copernicus, preprint 2026)](https://egusphere.copernicus.org/preprints/2026/egusphere-2026-137/egusphere-2026-137.pdf)**

El más completo en detalle de implementación de todos los que encontramos:

- **Láser:** diodo DFB sintonizable basado en GaSb, a 3270.4 nm (banda de absorción ν3 del metano).
- **Detector:** fotodiodo HgCdTe ópticamente inmerso, enfriado a ~-42.7°C con un Peltier.
- **Método:** espectroscopía de modulación de longitud de onda (WMS) con demodulación de segundo armónico (2f) para mejorar la relación señal/ruido.
- **Celda óptica:** dos espejos esféricos cóncavos dorados de 25.4 mm con distancia focal de 100 mm, configuración Herriott multi-paso (35 pasadas, 4.6 m de longitud de camino efectiva, separación de espejos de 131.4 mm) — con dimensiones específicas dadas.
- **Electrónica:** computadora de placa única BeagleBone Black con PCB a medida, DAC de 12 bits (AD5621), ADC de 16 bits (MCP33131D-10), controladores de temperatura y driver de láser detallados.
- **Performance:** **1.2 kg de peso total con batería incluida**, hasta 11 W de consumo, resolución de 3.7 ppb (laboratorio) / 26 ppb en vuelo, capaz de detectar tasas de fuga de metano tan bajas como **0.2 kg/h**.
- **Reproducibilidad:** buena — da part numbers específicos y arquitectura completa del sistema, aunque le faltan planos mecánicos completos y esquemas de PCB detallados para una réplica 100% independiente. Prioriza componentes off-the-shelf, lo cual ayuda a la accesibilidad.

**["Highly Responsive, Miniaturized Methane Telemetry Sensor Based on Open-Path TDLAS" (Photonics, MDPI, 2023)](https://www.mdpi.com/2304-6732/10/11/1281)**

Más chico y más rápido, con menos detalle de circuitos pero con dimensiones exactas:

- **Óptica:** láser DFB a 1653.7 nm, colimador, fotodiodo InGaAs, filtro pasabanda, indicador láser verde para apuntado.
- **Electrónica:** FPGA (GW1N-LV9QN48C6I5) + microcontrolador ARM (STM32G431CBU6), DAC de alta velocidad (AD9760), ADC (AD9214-65), driver de láser de corriente constante controlada por voltaje (95-135 mA).
- **Tamaño:** sistema óptico de 68.8 × 52 × 62.7 mm, sistema electrónico de 70 × 50 mm (no se especifica peso).
- **Performance:** tiempo de respuesta de 1.8 ms (10-90%), límite de detección mínimo de 43.14 ppm·m, linealidad R²=0.998.
- **Reproducibilidad:** moderada — da part numbers y diagramas de bloque de la señal, pero le faltan los esquemas del driver de láser, control de temperatura y diseño del filtro para una reproducción a nivel de circuito.

## 3. Imaging TDLAS con escaneo (pan-tilt) — el puente entre "punto" e "imagen"

**["Active methane gas imaging and leakage quantification based on standoff TDLAS and pan-tilt units" (ScienceDirect)](https://www.sciencedirect.com/science/article/abs/pii/S0925400525004733)**

Interesante porque resuelve la limitación de que un TDLAS típico solo mide a lo largo de un único rayo láser (un punto o una línea): monta el sensor TDLAS sobre una unidad pan-tilt motorizada que escanea el rayo en una grilla, reconstruyendo algo parecido a una "imagen" de concentración de gas a partir de muchas mediciones puntuales — efectivamente un punto intermedio conceptual entre un sensor de punto barato y una cámara OGI de imagen completa instantánea.

## 4. Revisión académica de métodos de cuantificación por UAV — el marco metodológico completo

**["Advanced Leak Detection and Quantification of Methane Emissions Using sUAS" (Drones, MDPI, revisión)](https://www.mdpi.com/2504-446X/5/4/117)**

Este no es un paper de hardware sino una revisión que mapea todo el campo — el mejor punto de partida si quieren anclar la sección de "objetivos máximos" del proyecto en la literatura académica real en vez de solo especificaciones de producto comercial. Cubre:

- **Tecnologías de sensado revisadas:** TDLAS (incluida la variante backscatter), espectroscopía de cavidad ring-down (CRDS), espectrómetro de cavidad óptica off-axis (OA-ICOS), láseres de cascada cuántica (QCL), cámaras OGI, imaging térmico MWIR/LWIR, sensores electroquímicos (AlphaSense), NDIR, LiDAR de absorción diferencial (DiAL) y Gas Mapping LiDAR.
- **Métodos de cuantificación cubiertos:** inversión de pluma gaussiana de campo cercano (NGI), balance de masa (estacionario y móvil), plano de flujo vertical (VFP, muestreo en trayectoria circular con integración de flujo), correlación con trazador (TCM), modelado de dispersión inversa (incluyendo enfoques bayesianos), covarianza de vórtices (eddy covariance, con torres) y métodos de cámara estática/dinámica.
- **Conclusión de los autores:** los métodos más prometedores específicamente para sUAS son la inversión de pluma gaussiana de campo cercano (NGI) y el plano de flujo vertical (VFP), con precisión comparable a los métodos convencionales de referencia.
- **Desafíos abiertos que señalan:** qué constituye "suficientemente preciso" para cuantificación, la fuerte incertidumbre inducida por el viento en los cálculos de flujo, y la falta de protocolos estandarizados de clasificación/graduación de fugas — todo esto conecta directamente con el relevamiento de condiciones de viento de Vaca Muerta que ya está en el objetivo mínimo del proyecto (sección 2.1 del documento de objetivos).

## Cómo se relacionan entre sí, en una frase cada uno

- **SkySniff (UCSD):** el camino más barato (<USD 1.000) — visión por computadora sobre hardware térmico genérico, no imaging espectral real, precisión moderada (85%), prueba de concepto.
- **Sensor mid-IR ultraliviano (2026):** el camino de mayor rigor físico — TDLAS real con celda multipaso, 1.2 kg, detecta tasas de hasta 0.2 kg/h, con buen nivel de detalle de componentes para replicar.
- **Sensor TDLAS miniaturizado (Photonics 2023):** el más chico y rápido de los dos TDLAS, con menos peso mostrado pero también menos detalle circuital.
- **TDLAS + pan-tilt:** la manera de convertir una medición puntual TDLAS en algo parecido a una imagen escaneada.
- **Revisión de sUAS (Drones journal):** el mapa completo del campo — qué método de cuantificación usar según el caso, no cómo construir el sensor en sí.

## Fuentes

- [Remote Gas Leak Detection on a Low-Cost UAV Platform (UC San Diego, SkySniff)](https://kastner.ucsd.edu/wp-content/uploads/2025/06/admin/gasleakdrone.pdf)
- [Ultra-Lightweight Mid-IR Methane Sensor for UAV-based Measurements (EGUsphere preprint, 2026)](https://egusphere.copernicus.org/preprints/2026/egusphere-2026-137/egusphere-2026-137.pdf)
- [Highly Responsive, Miniaturized Methane Telemetry Sensor Based on Open-Path TDLAS (Photonics, MDPI, 2023)](https://www.mdpi.com/2304-6732/10/11/1281)
- [Active methane gas imaging and leakage quantification based on standoff TDLAS and pan-tilt units (ScienceDirect)](https://www.sciencedirect.com/science/article/abs/pii/S0925400525004733)
- [Advanced Leak Detection and Quantification of Methane Emissions Using sUAS (Drones, MDPI, revisión)](https://www.mdpi.com/2504-446X/5/4/117)
- [High-Precision Methane Emission Quantification Using UAVs and Open-Path Technology (Methane journal, MDPI)](https://doi.org/10.3390/methane4030015)
- [Natural Gas Fugitive Leak Detection Using an Unmanned Aerial Vehicle: Measurement System Description and Mass Balance Approach (Atmosphere, MDPI, 2018)](https://doi.org/10.3390/atmos9100383)
