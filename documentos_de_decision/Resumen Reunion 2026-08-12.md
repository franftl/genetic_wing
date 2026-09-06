# UAV FP — Resumen para reunión (12/08/2026)

*Documento de referencia rápida para no olvidar temas en la reunión con el profesor. Incluye el "por qué" de cada decisión tomada hasta ahora.*

## 1. El proyecto en una línea

- Trabajo final de carrera de Ingeniería Mecánica (Argentina), equipo de 3 ingenieros.
- Etapa actual: brainstorming y análisis de viabilidad.
- Dirección elegida: un UAV autónomo no tripulado que realiza tareas para empresas de petróleo y gas, enfocado en pozos onshore, posiblemente en Vaca Muerta.
- Estrategia: conseguir un sponsor de la industria; se buscó primero validar que existe una necesidad real de monitoreo rutinario de pozos que un UAV pueda cubrir.

## 2. Por qué este rumbo es viable (validación de mercado)

- Existe un mercado global activo y en crecimiento: empresas como Percepto, Skydio, FlytBase y Cyberhawk ya venden sistemas de drones autónomos ("drone-in-a-box") para monitoreo de sitios de petróleo y gas. Crecimiento estimado del mercado: ~24-31% CAGR según distintas consultoras.
- YPF ya usa drones en Vaca Muerta desde su nuevo centro RTIC Upstream en Neuquén, monitoreando más de 2.000 pozos, para detectar "situaciones de seguridad o de producción" — evidencia directa de que la necesidad es real en el mismo campo donde apuntamos.
- Hay un driver regulatorio concreto: la Provincia de Neuquén exige a las operadoras reportar emisiones (CO2, metano, N2O), con **primer vencimiento en septiembre de 2026** (el mes que viene).
- Ya existe un competidor/validador local: la startup neuquina MES (Make Energy Sustainable) vende detección de metano con drones a operadoras de Vaca Muerta — confirma que el mercado paga por esto, pero también que "detección de gas" ya no es un espacio vacío.

## 3. Decisión: se descartó la cámara de imagen óptica de gas (OGI) por costo

- **Qué es:** cámara térmica especializada (banda espectral angosta, sintonizada a la absorción del metano) que permite *ver* fugas de gas directamente en el video.
- **Proveedores identificados:** Sierra Olympia (modelo Ventus OGI) y FLIR (línea G-series, ej. GF320).
- **Precio:** ninguno de los fabricantes publica precio de lista (se cotiza a pedido) — esto mismo es una señal: es equipo industrial especializado, históricamente en el orden de decenas de miles de USD (se estima $30.000–$80.000+ para las cámaras enfriadas de gama alta).
- **Por qué se descartó:** ese rango de precio está fuera del alcance de un proyecto estudiantil sin sponsor confirmado que preste o financie el equipo específicamente.
- **Alternativa más económica evaluada:** existen cámaras OGI *no enfriadas* (ej. FLIR GF77a) a mitad de precio de las enfriadas, pero igual quedan en un rango elevado (probablemente $15.000-$40.000) y con ~5x menos sensibilidad para fugas chicas — se decidió no depender de esto tampoco.

## 4. Nuevo alcance definido: monitoreo RGB + documentación, térmico como opcional

- **Alcance actual:** seguimiento/detección de personas, vehículos y cuadrillas de servicio, más fotografía/documentación de pozos en operación.
- **Por qué este cambio tiene sentido:**
  - Ya existe un mercado probado para esto específicamente: Asylon Robotics vende drones autónomos de seguridad para petróleo y gas (detección de intrusos, robo de equipos, accesos no autorizados en pozos, plantas de bombeo, tanques).
  - Encaja mejor con lo que YPF dijo que ya hace con sus propios drones ("situaciones de seguridad").
  - La tarea de IA es mucho más simple y de menor riesgo que la detección de gas: existe un dataset público hecho específicamente para esto (VisDrone: +8.600 imágenes aéreas, 10 clases incluyendo persona, auto, camioneta, camión, moto), compatible directamente con herramientas de entrenamiento estándar (YOLO/Ultralytics). Para gas, en cambio, el problema principal era la escasez de datos reales de fugas.
  - La fotografía/documentación de pozos ya es un producto establecido en la industria (Percepto, Skydio, Cyberhawk lo ofrecen como base de su servicio).
- **Contrapartida a tener en cuenta:** se pierde el driver regulatorio más fuerte (plazo de metano de septiembre 2026). Lo que se gana es una necesidad más permanente: robo/vandalismo en pozos poco vigilados, seguridad del personal, costo logístico de recorrer miles de pozos dispersos.

## 5. Cámara térmica: ahora sí es una opción económicamente razonable (como segundo sensor)

- **Por qué ahora es viable (a diferencia del punto 3):** al no necesitar detectar gas, no se requiere el filtro espectral angosto y carísimo — alcanza con una cámara térmica genérica no enfriada (banda larga, LWIR).
- **Para qué serviría:** detección de personas/vehículos de noche o baja visibilidad (el térmico es mejor que el RGB en oscuridad), y detección básica de sobrecalentamiento de equipos (riesgo de incendio).
- **Opciones de precio relevadas:**
  - Núcleo de cámara térmica cruda para integración propia (FLIR Boson 640): ≈ USD 3.500.
  - Drone integrado con RGB+térmico de fábrica (DJI Mavic 3T): ≈ USD 6.800.
  - Payload profesional RGB+térmico+zoom (DJI Zenmuse H30T): ≈ USD 11.800.
- **Importante:** una cámara térmica genérica (no especializada) **no puede** detectar gas — es una limitación física (banda espectral), no un problema de software/IA. Esto separa claramente el uso del térmico (personas/calor) del uso descartado (gas).

## 6. Factibilidad del proyecto en un año

- **Es realista si se acota bien el alcance:** vuelo autónomo por waypoints + cámara + IA de detección es alcanzable en un año usando componentes ya existentes (no hay que inventar nada desde cero).
- **Lo que NO es realista para el año 1:** un sistema "drone-in-a-box" completo, 24/7, con estación de carga/despegue automática — eso es ingeniería mecatrónica especializada por sí sola (varias empresas la venden como producto aparte). Se recomienda dejarlo como "trabajo futuro" en la tesis.
- El stack de autonomía de vuelo (ArduPilot + computadora companion) es tecnología madura y bien documentada — no es la parte de mayor riesgo.
- El mayor riesgo real detectado: conseguir acceso a cámaras y datos reales de prueba a través de un sponsor.
- Regulatoriamente (ANAC, Argentina), volar en modo BVLOS (más allá de la línea de vista) requiere autorización de la categoría "Específica" — se puede tramitar en paralelo al desarrollo, no bloquea el trabajo técnico.

## 7. Cómo se entrenaría la IA (para detección de personas/vehículos)

- No se entrena un modelo desde cero: se parte de un detector ya entrenado (YOLO, familia estándar de la industria) y se hace *transfer learning* / *fine-tuning* con el dataset VisDrone + imágenes propias de vuelos de prueba.
- Herramientas de etiquetado estándar y gratuitas: CVAT o Roboflow.
- No requiere supercomputadoras: una sola GPU de gama media (o Google Colab gratuito) alcanza para entrenar en horas, no días.
- El desafío real no es el modelo en sí, sino reducir falsos positivos (viento, polvo, sombras) con datos de prueba realistas del propio campo.

## 8. Telemetría de largo alcance con ArduPilot

- **Opciones de enlace, de menor a mayor alcance:**
  - Radio de telemetría (RFD900/RFD900x): hasta ~15-40+ km según antena y línea de vista. La estepa patagónica (terreno plano) favorece esto.
  - Celular 4G/LTE (UAVCast, soportado oficialmente por ArduPilot): alcance prácticamente ilimitado donde haya cobertura, pero ojo: las antenas de celda apuntan hacia el suelo, no hacia arriba, por lo que la cobertura puede empeorar en altura.
  - Satelital (tipo Iridium): cobertura verdaderamente global pero de bajo ancho de banda — sirve como respaldo/seguridad, no como enlace principal de video.
  - Dato relevante: YPF usa Starlink (no celular) para su centro RTIC en Vaca Muerta — señal de que la cobertura celular en el campo no es confiable.
- **¿La misión se completa si se pierde la telemetría?** Sí, pero no es el comportamiento por defecto. Por defecto, ArduPilot aborta la misión y vuelve a home (RTL) si pierde el enlace con la estación de tierra. Hay que configurar explícitamente el parámetro `FS_OPTIONS` (bit 1) para que la misión continúe pese a la pérdida de telemetría, dejando activos los demás sistemas de seguridad (batería, GPS, geocerca).

## 9. Seguimiento en tiempo real de personas/vehículos

- **Camino simple (cooperativo):** si la persona/vehículo lleva algo que transmite su GPS (una app en el celular, por ejemplo), ArduPilot tiene un modo "Follow" ya integrado que lo sigue automáticamente — sin cámara ni IA de por medio.
- **Camino difícil (no cooperativo, detección visual):** se detecta el objetivo con cámara (YOLO), se calcula su posición en el suelo usando el ángulo del gimbal + posición/actitud del avión + modelo de cámara (no es "triangulación" clásica, es geolocalización de un solo rayo cámara-suelo), se suaviza con un filtro de Kalman, y se envía la posición calculada a ArduPilot en tiempo real en modo GUIDED vía MAVLink (mensajes `SET_POSITION_TARGET_GLOBAL_INT`/`_LOCAL_NED`). Hay que reenviar el comando cada ~1 segundo o el dron se detiene — perfectamente alcanzable con el hardware disponible.
- Existe literatura académica que ya implementó y voló exactamente este pipeline con resultados reales, y ArduPilot ya tiene una funcionalidad análoga más simple (aterrizaje de precisión con cámara) que sirve de referencia de implementación.

## 10. Software existente que se usaría y modificaría (para explicarle el alcance al profesor)

- **ArduPilot** — piloto automático open source; se usaría el modo GUIDED, el modo Follow, y se configurarían los failsafes (`FS_OPTIONS`, `FS_GCS_ENABLE`) según las necesidades del proyecto.
- **MAVLink** (protocolo) — estándar de comunicación entre la computadora de a bordo y ArduPilot; se usarían librerías como `pymavlink` o `MAVSDK` para programar el envío de comandos en tiempo real.
- **mavlink-router / UAVCast** — para enrutar telemetría MAVLink sobre celular (4G/LTE) además del radio tradicional.
- **QGroundControl o Mission Planner** — estación de control terrestre estándar, para planificar misiones y monitorear el vuelo.
- **Ultralytics YOLO** — framework de detección de objetos; se tomaría un modelo pre-entrenado y se haría fine-tuning propio (no se entrena desde cero).
- **Dataset VisDrone** — dataset público de imágenes aéreas ya etiquetado (personas, autos, camiones, etc.), usado como base de entrenamiento.
- **CVAT o Roboflow** — herramientas de etiquetado de imágenes/video para generar datos de entrenamiento propios.
- **OpenCV** — procesamiento de imagen y seguimiento visual (ej. tracker CSRT) para mantener el objetivo centrado entre detecciones.
- **JetPack (NVIDIA Jetson) o equivalente** — sistema operativo/SDK de la computadora companion que correría la IA a bordo.

## 11. Preguntas abiertas / próximos pasos

- ¿Quién provee actualmente los drones y el software del RTIC de YPF (desarrollo propio vs. contratado)?
- ¿Qué usan hoy operadoras independientes más chicas (no YPF) para monitorear pozos? ¿Podrían ser un sponsor más accesible que YPF?
- ¿Se puede conseguir acceso a una cámara térmica (o a MES como socio tecnológico) a través de un sponsor?
- Definir si se apunta primero a seguimiento cooperativo (GPS/beacon, más simple) o directamente a detección visual no cooperativa.
- Avanzar en paralelo con el trámite de autorización ANAC (categoría Específica / BVLOS) ya que no bloquea el desarrollo técnico.
