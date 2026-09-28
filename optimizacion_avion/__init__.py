"""
optimizacion_avion -- competencia entre topologías de avión de ala fija,
bajo una misma misión, por algoritmo genético.

Es la evolución de `optimizacion_ala` (que optimiza UNA topología, el ala
volante) hacia varias configuraciones de avión completo que compiten entre
sí. Comparte con aquel paquete el método y las constantes de material y de
misión, pero no la geometría.

==========================================================================
ESTADO AL 2026-09-17
==========================================================================
MISIÓN (dos puntos de vuelo): crucero a 120 km/h con 3 kg de carga útil, Y
poder volar a 10 m/s para reconocimiento, despegue y aterrizaje. Los dos
puntos entran juntos a la función objetivo porque piden alas opuestas -- ver
el encabezado de `mision_avion.py`.

TOPOLOGÍAS: convencional, cola en T, cola en V, doble boom, y motovelero
(góndola + viga de cola). Ver `geometria_avion.TOPOLOGIAS`.

ESPACIO DE DISEÑO: 46 a 51 parámetros según la topología -- ala de 5
estaciones con winglets, envergadura variable, flaps, fuselaje con morro y
boat-tail de forma libre, y cola con incidencia.

Estructura del paquete:
- perfiles_avion.py    : catálogo de 19 perfiles (los 12 del ala volante con
                         los MISMOS índices, más 7 de alta sustentación), y
                         el modelo de flap por deflexión de contorno
- geometria_avion.py   : TOPOLOGIAS, BOUNDS por topología, CandidateAvion,
                         construir_avion(params, topologia), diagnósticos
                         (volúmenes de cola, geometría de flap)
- estructura_avion.py  : masa de ala + winglets + flap + cola + fuselaje +
                         vigas, con la circularidad masa<->carga resuelta
- mision_avion.py      : función objetivo de los dos puntos de vuelo, las
                         tres reglas de oro de estabilidad y las derivadas
                         de amortiguamiento
- ga_numerico_avion.py : generación de hijos (BLX-alfa + mutación + wildcards)
- evolucion_avion.py   : loop evolutivo de UNA topología
- competencia.py       : semillas y orquestador de la competencia
- semillas.json        : las semillas, generadas por gen_semillas.py
- gen_semillas.py      : script que regenera las semillas (reproducibilidad)

Ver el notebook 02_Optimizacion_Avion.ipynb para el flujo de trabajo.
"""

from .perfiles_avion import (
    ALTA_SUSTENTACION,
    CATALOGO_AVION,
    N_CATALOGO_AVION,
    cargar_perfil_avion,
    indice_a_nombre_avion,
    perfil_con_flap,
    perfil_en_fraccion_avion,
    resumen_catalogo_avion,
)
from .geometria_avion import (
    BOUNDS_ALA,
    BOUNDS_FLAP,
    BOUNDS_FUSELAJE,
    BOUNDS_POR_TOPOLOGIA,
    N_ESTACIONES,
    SM_BANDS,
    TOPOLOGIAS,
    CandidateAvion,
    clamp_to_bounds_avion,
    construir_ala,
    construir_avion,
    geometria_flap,
    referencias_ala,
    semi_envergadura,
    volumenes_de_cola,
)
from .estructura_avion import converger_masa_avion, masa_estructura_avion
from .mision_avion import (
    FACTOR_UTILIZACION_VOLUMEN,
    MARGEN_SOBRE_PERDIDA,
    VOLUMEN_UTIL_MIN_L,
    V_CRUCERO,
    V_LENTO,
    V_MAX,
    analizar_mision_avion,
    desglose_mision_avion,
    evaluar_mision_avion,
)
from .ga_numerico_avion import generar_hijos_avion
from .evolucion_avion import (
    EstadoEvolucionAvion,
    cargar_checkpoint,
    correr_evolucion_completa_avion,
    correr_generacion_avion,
    guardar_checkpoint,
    iniciar_evolucion_avion,
)
from .competencia import (
    SEEDS_POR_TOPOLOGIA,
    correr_competencia,
    optimizar_topologia,
    tabla_resultados,
)

# Se reutiliza tal cual del ala volante (ver evolucion_avion.py): se
# re-exporta para que el notebook importe de un solo paquete.
from optimizacion_ala.evolucion import deberia_parar

__all__ = [
    # perfiles
    "CATALOGO_AVION", "N_CATALOGO_AVION", "ALTA_SUSTENTACION",
    "indice_a_nombre_avion", "cargar_perfil_avion", "perfil_en_fraccion_avion",
    "perfil_con_flap", "resumen_catalogo_avion",
    # geometría
    "TOPOLOGIAS", "SM_BANDS", "N_ESTACIONES",
    "BOUNDS_ALA", "BOUNDS_FLAP", "BOUNDS_FUSELAJE", "BOUNDS_POR_TOPOLOGIA",
    "CandidateAvion", "clamp_to_bounds_avion", "construir_avion", "construir_ala",
    "referencias_ala", "semi_envergadura", "volumenes_de_cola", "geometria_flap",
    # estructura
    "masa_estructura_avion", "converger_masa_avion",
    # misión
    "V_CRUCERO", "V_LENTO", "V_MAX", "MARGEN_SOBRE_PERDIDA",
    "VOLUMEN_UTIL_MIN_L", "FACTOR_UTILIZACION_VOLUMEN",
    "analizar_mision_avion", "evaluar_mision_avion", "desglose_mision_avion",
    # GA / evolución
    "generar_hijos_avion", "EstadoEvolucionAvion", "iniciar_evolucion_avion",
    "correr_generacion_avion", "correr_evolucion_completa_avion",
    "guardar_checkpoint", "cargar_checkpoint", "deberia_parar",
    # competencia
    "SEEDS_POR_TOPOLOGIA", "optimizar_topologia", "correr_competencia", "tabla_resultados",
]
