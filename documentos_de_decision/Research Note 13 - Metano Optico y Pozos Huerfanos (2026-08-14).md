# UAV FP — Research Note 13: Métodos Ópticos de Detección de Metano (revisión completa) + Localización de Pozos Huérfanos por Magnetometría UAV

*Compilado 14 agosto 2026. Condensa los dos papers subidos (Kwaśny & Bombalska 2023; Nikulin & de Smet 2023) y suma al acervo de fuentes los links relevantes del documento interno "Punteo de ideas" del equipo. Sigue a la Nota 12 (papers de hardware de detección de metano).*

## 1. Kwaśny & Bombalska (2023) — revisión completa de métodos ópticos de detección de metano

Este paper (*Sensors* 23, 2834) es el mapa más completo que encontramos hasta ahora de **todas** las técnicas ópticas de detección de metano, no solo TDLAS — vale la pena tenerlo como referencia central de la sección de detección de gas de la tesis. Resumen por técnica:

| Técnica | Principio | Sensibilidad típica | Nota práctica |
|---|---|---|---|
| **NDIR / opto-par no dispersivo** | Absorción diferencial en dos bandas (de trabajo y de referencia) con LED/fotodiodo, sin partes móviles | ~10 ppm | La más simple y barata de construir; ejemplo comercial: analizador RMt Ltd., 300 g, USD gama baja |
| **CIPS (filtro de interferencia-polarización)** | Correlación óptica entre un filtro electrónicamente controlado y las líneas de absorción del gas | 0.1 ppm, selectividad metano:butano 4000:1 | 4 kg, más selectivo que NDIR simple |
| **TDLAS (láser diodo sintonizable)** | Barre la longitud de onda de un láser angosto sobre una línea de absorción específica del metano | ppb–ppt según la variante | La técnica más madura y comercial; es la misma familia que ya veníamos investigando (Notas 11 y 12) |
| **CRDS / CEAS / OF-CEAS** (ring-down / cavidad realzada) | Mide el tiempo de decaimiento de un pulso láser atrapado en una cavidad óptica de espejos de alta reflectancia (R&gt;99.995%) | hasta 3 ppt (OF-CEAS con láser cascada cuántica) | Mucho más sensible que TDLAS simple, pero de mayor complejidad óptica/costo |
| **DIAL (LIDAR de absorción diferencial)** | Emite dos longitudes de onda (una absorbida por metano, una de referencia) y mide el retrodispersado desde una distancia | detectabilidad de miles de ppm·m a 100-500 m de distancia | Es la técnica de **medición remota** por excelencia — no necesita que el sensor esté cerca del gas; existe incluso una variante satelital (proyecto MERLIN, misión franco-alemana) |
| **Fotoacústica (PAS/QEPAS)** | La absorción de luz modulada calienta el gas cíclicamente, generando una onda de presión/sonido que un micrófono (o un diapasón de cuarzo en la variante QEPAS) detecta | 10⁻⁸–10⁻⁹ cm⁻¹·W·Hz⁻¹/² | Diseño compacto y económico, pero sensible a vibraciones mecánicas/acústicas — algo a tener en cuenta si se monta sobre un dron con motores |

**Dos referencias que el propio paper cita y que conectan directamente con lo que ya veníamos investigando:**

- Confirma como referencia el mismo paper de revisión que ya habíamos encontrado nosotros — Hollenbeck, Zulevic & Chen (2021), *"Advanced leak detection and quantification of methane emissions using sUAS"* (Drones) — dándole más peso como fuente consolidada del estado del arte en detección por UAV.
- Suma una referencia nueva y muy directa que no teníamos: **Iwaszenko, Kalisz, Słota & Rudzki (2021), *"Detection of natural gas leakages using a laser-based methane sensor and UAV"* (Remote Sensing, 13, 510)** — un caso de implementación específico de sensor láser de metano montado en UAV, vale la pena leerlo en detalle en la próxima iteración de investigación.

**Nota práctica que aporta el paper para la sección de detección de gas de la tesis:** el DIAL es, entre todas las técnicas, la única diseñada explícitamente para **detección remota real** (decenas a cientos de metros), que es justamente el escenario de un UAV sobrevolando instalaciones sin necesidad de acercarse a cada válvula — mientras que NDIR, CIPS, CRDS y PAS clásicos son técnicas de "punto" (el gas tiene que pasar físicamente por la celda de medición del instrumento).

## 2. Nikulin & de Smet (2023) — localización de pozos huérfanos por magnetometría aérea con UAV

Este paper (*The Leading Edge*, diciembre 2023) es sobre un problema y una tecnología **distintos** a todo lo investigado hasta ahora: no mide fugas de gas, sino que **localiza pozos abandonados/huérfanos** cuya ubicación se perdió (mapas históricos poco confiables, sin registro), usando el hecho de que el revestimiento metálico vertical de un pozo convencional genera una anomalía magnética detectable en superficie.

**Cómo funciona:**
- Un magnetómetro miniaturizado (ej. Geometrics MFAM, un magnetómetro atómico microfabricado) se monta colgado debajo de un UAV, típicamente en configuración remolcada para reducir el ruido electromagnético del motor del dron.
- El UAV vuela a una altitud constante dentro de una "ventana de detección" — en el caso de estudio (Olean, NY, con dosel forestal de ~33 m), esa ventana quedó definida entre 34 y 50 m sobre el nivel del suelo: por debajo, colisión con el follaje; por encima, la anomalía se atenúa demasiado para distinguirse del ruido de fondo.
- Los datos crudos se corrigen por variación diurnal, errores de rumbo y ruido de alta frecuencia, y se generan mapas georeferenciados (raster o de contornos) donde los pozos aparecen como anomalías puntuales de alta amplitud tipo "ojo de buey".

**Resultado del caso de estudio real (Olean, NY):** en un área boscosa donde los mapas históricos indicaban 278 pozos de principios del siglo XX pero solo 11 estaban registrados con precisión, un survey de UAV de menos de 4 horas (3 vuelos, 1.08 km²) reveló 72 anomalías magnéticas nuevas. De 9 verificadas en terreno, 8 correspondían efectivamente a pozos (1 falso positivo, un puesto de caza metálico) — 97% de tasa de detección.

**Dato clave para el objetivo mínimo del proyecto:** el paper documenta que la **intensidad** de la anomalía magnética se correlaciona con el estado físico del pozo — anomalías de alta amplitud corresponden a bombas mecánicas (pumpjacks) intactas, anomalías más moderadas a pozos con revestimiento metálico intacto, y las más débiles a pozos sin revestimiento (removido durante la Segunda Guerra Mundial). Más interesante todavía: los propios autores señalan evidencia preliminar (de Smet et al. 2023) de que la integridad del revestimiento cercano a la superficie —correlacionada con la anomalía magnética— también se relaciona con el potencial del pozo de emitir gases/fluidos, aunque marcan que hace falta más trabajo de campo para confirmarlo con solidez.

**Por qué esto es relevante más allá de "otra tecnología más":** el propio paper cita un trabajo de seguimiento — **de Smet, Nikulin, Balrup & Graber (2023), *"Successful integration of UAV aeromagnetic mapping with terrestrial methane emissions surveys in orphaned well remediation"* (Remote Sensing, 15, 5004)** — donde el mismo grupo combina explícitamente el survey magnético (para *encontrar* el pozo) con relevamientos de emisiones de metano (para *caracterizarlo* una vez encontrado). Esto conecta directamente los dos papers que subiste en un único flujo de trabajo con precedente académico: localizar primero, medir después — y calza con la mención de "Auditoría de Pozos Abandonados" que ya aparecía como aplicación crítica en los apuntes del equipo (ver sección 3).

## 3. Links del "Punteo de ideas" del equipo — lo nuevo que no estaba ya en las notas anteriores

El documento interno tenía varios artículos que ya habíamos incorporado a notas previas (YPF RTIC, la normativa de reporte de metano de Neuquén). Lo que sí es nuevo y vale la pena dejar registrado:

- **Marco Internacional MMRV** (Measurement, Monitoring, Reporting, Verification) — iniciativa voluntaria liderada por el Departamento de Energía de EE.UU. junto a gobiernos y empresas (incluida Argentina entre los participantes indirectos vía YPF) para unificar cómo se mide y verifica la emisión de metano/CO₂ en toda la cadena de petróleo y gas. Es el marco internacional "paraguas" que le da contexto a la normativa provincial de Neuquén que ya veníamos citando.
- **Marco provincial de Neuquén para pozos inactivos/abandonados** — Neuquén ya tiene un programa específico de monitoreo de emisiones en pozos inactivos y abandonados (no solo activos), lo cual conecta directamente con el ángulo de "pozos huérfanos" del paper de Nikulin & de Smet.
- **YPF y sus marcos ESG** (GRI, SASB, TCFD, Dow Jones Sustainability Index, Pacto Global de la ONU, EITI) — útil como contexto de por qué YPF necesita datos de emisiones medidos y no estimados: estos marcos exigen reportes auditables.
- **Make Energy Sustainable (MES)** — la startup neuquina que ya habíamos identificado como competidor/referencia local; el documento aporta que trabaja en **alianza estratégica con Sensia Solutions** (sensia-solutions.com / sensiaglobal.com), y que su diferencial declarado es la *cuantificación y mitigación*, no solo la detección.
- **CITEDEF (Instituto de Investigaciones Científicas y Técnicas para la Defensa)** — un desarrollo de UAV hecho en Argentina, documentado en un trabajo académico (Serruya, CEFADIGITAL/UNDEF): vale la pena revisarlo como antecedente nacional de ingeniería de UAV, más allá de la aplicación específica a Vaca Muerta.
- **Servicios comerciales de detección de pozos abandonados con drones** (sphengineering.com/applications/drone-orphaned-abandoned-well-detection) — confirma que lo que describe el paper de Nikulin & de Smet ya se ofrece como servicio comercial, no solo como resultado académico.
- Un conjunto de artículos/páginas de proveedores ya cubiertos conceptualmente en notas anteriores (Pergam, Acecore, Flyability, LI-COR, COPTRZ, The Drone Centre) — quedan documentados en la bibliografía por completitud, sin agregar información nueva a lo ya condensado.

## Bibliografía (fuentes nuevas agregadas en esta nota)

- Kwaśny, M.; Bombalska, A. *Optical Methods of Methane Detection*. Sensors 2023, 23, 2834. [https://doi.org/10.3390/s23052834](https://doi.org/10.3390/s23052834)
- Nikulin, A.; de Smet, T. S. *UAV-based aeromagnetic surveys for orphaned well location: Emerging best practices*. The Leading Edge, December 2023. [https://doi.org/10.1190/tle42120817.1](https://doi.org/10.1190/tle42120817.1)
- de Smet, T. S.; Nikulin, A.; Balrup, N.; Graber, N. (2023). *Successful integration of UAV aeromagnetic mapping with terrestrial methane emissions surveys in orphaned well remediation*. Remote Sensing, 15(20), 5004. [https://doi.org/10.3390/rs15205004](https://doi.org/10.3390/rs15205004)
- de Smet, T. S.; Nikulin, A.; Romanzo, N.; Graber, N.; Dietrich, C.; Puliaiev, A. (2021). *Successful application of drone-based aeromagnetic surveys to locate legacy oil and gas wells in Cattaraugus County, New York*. Journal of Applied Geophysics, 186, 104250. [https://doi.org/10.1016/j.jappgeo.2020.104250](https://doi.org/10.1016/j.jappgeo.2020.104250)
- Hollenbeck, D.; Zulevic, D.; Chen, Y. (2021). *Advanced leak detection and quantification of methane emissions using sUAS*. Drones, 5, 117. [https://doi.org/10.3390/drones5040117](https://doi.org/10.3390/drones5040117)
- Iwaszenko, S.; Kalisz, P.; Słota, M.; Rudzki, A. (2021). *Detection of natural gas leakages using a laser-based methane sensor and UAV*. Remote Sensing, 13, 510. [https://doi.org/10.3390/rs13030510](https://doi.org/10.3390/rs13030510)
- Marco Internacional MMRV — Departamento de Energía de EE.UU. [energy.gov/hgeo/greenhouse-gas-supply-chain-emissions-measurement-monitoring-reporting-verification-framework](https://www.energy.gov/hgeo/greenhouse-gas-supply-chain-emissions-measurement-monitoring-reporting-verification-framework)
- Neuquén monitorea emisiones de metano en pozos inactivos y abandonados. [neuqueninforma.gob.ar](https://www.neuqueninforma.gob.ar/noticias/2026/05/24/258162-neuquen-monitorea-las-emisiones-de-metano-en-pozos-inactivos-y-abandonados)
- Tecnología neuquina para reducir emisiones y ganar eficiencia en Vaca Muerta (MES). [mejorenergia.com.ar](https://www.mejorenergia.com.ar/noticias/2025/08/06/4464-tecnologia-neuquina-para-reducir-emisiones-y-ganar-eficiencia-en-vaca-muerta)
- Make Energy Sustainable (MES) — perfil de la empresa. [LinkedIn](https://ar.linkedin.com/company/mesust)
- Sensia Solutions (alianza estratégica con MES). [sensia-solutions.com](https://sensia-solutions.com/) / [sensiaglobal.com](https://www.sensiaglobal.com/)
- YPF — Reporte de Sustentabilidad y marcos ESG. [sustentabilidad.ypf.com](https://sustentabilidad.ypf.com/Resumen-Ejecutivo-2023.html)
- Desarrollos de UAV en Argentina — CITEDEF (Serruya). [cefadigital.edu.ar](https://cefadigital.edu.ar/bitstream/1847939/321/1/Desarrollos%20de%20UAV%20en%20Argentina_Serruya.pdf)
- Drone-based orphaned/abandoned well detection (servicio comercial). [sphengineering.com](https://www.sphengineering.com/applications/drone-orphaned-abandoned-well-detection)
