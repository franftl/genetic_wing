"""
optimizacion_ala -- pipeline de optimización del flying wing (UAV FP).

Estructura del paquete:
- geometria.py     : Candidate, BOUNDS, construir_avion()  (estable, no cambia según backend)
- objetivo.py       : evaluar_candidato() -- L/D con resistencia inducida + viscosa
                       (AeroBuildup + NeuralFoil). Faltan estabilidad y estructura, ver Nota 11
- ga_numerico.py    : backend ACTIVO de generación de hijos (BLX-alfa + mutación gaussiana,
                       sin llamadas a IA -- no consume créditos). Ver Nota sobre backends abajo.
- cruzamiento_ia.py : backend alternativo de generación de hijos vía Claude (archivado
                       desde que el equipo decidió dejar de gastar créditos de IA en esto).
                       MOVIDO a ../codigo_obsoleto/optimizacion_ala/cruzamiento_ia.py
                       (2026-08-28, orden de carpeta) -- no forma parte del paquete
                       importable; se guarda por si se quiere retomar/comparar
- evolucion.py      : loop evolutivo, corrible generación por generación desde una notebook
- estructura.py     : modelo de masa (larguero por rigidez/resistencia + piel). La masa
                       YA NO es una constante: depende de la geometría
- mision.py         : funcion objetivo de MISION (crucero 60 km/h, 3 kg de carga util,
                       terminos estructurales y de rafaga). Es la mas completa
- perfiles.py       : catalogo de perfiles REALES (UIUC) ordenado por Cm0. El
                       optimizador ELIGE de aca (raiz/medio/punta); no inventa
                       perfiles -- ver el encabezado del modulo para el porque
- exportar_cad.py   : coordenadas 3D de cada seccion para el CAD. Lo consume
                       fusion_generar_ala.py, que corre DENTRO de Fusion
- graficos.py       : vistas 2D de la geometría y curvas de performance del diseño final
                       (barrido de alpha, velocidad de pérdida, vuelo nivelado)

Ver el notebook 01_Optimizacion_Ala.ipynb para el flujo de trabajo interactivo.
"""

from .geometria import (
    BOUNDS, CG_FRAC_MAC, HALF_SPAN, MASA_TOTAL, N_SECCIONES_LOFT,
    Candidate, camino_winglet, clamp_to_bounds, construir_avion, construir_perfil,
    distribucion_envergadura, elevacion_envergadura, linea_de_curvatura,
)
from .graficos import barrido_alpha, plot_geometria_2d, plot_performance
from .objetivo import (
    OP_POINT,
    calcular_aero,
    evaluar_candidato,
    evaluar_candidato_invisido,
    evaluar_candidato_toy,
)
from .estructura import converger_masa, masa_estructura
from .mision import analizar_mision, desglose_mision, evaluar_mision
from .ga_numerico import generar_hijos
from .perfiles import (
    CATALOGO, CATALOGO_REFLEJADOS, CM0_MEDIDO, N_CATALOGO, cargar_perfil,
    generar_hijos_con_catalogo, indice_a_nombre, mezclar, perfil_en_fraccion,
    perfiles_del_diseno, poblacion_semilla, resumen_catalogo, semilla_desde_perfil,
)
from .exportar_cad import exportar_json, secciones_3d, verificar
from .evolucion import (
    EstadoEvolucion,
    correr_evolucion_completa,
    correr_generacion,
    deberia_parar,
    guardar_checkpoint,
    cargar_checkpoint,
    iniciar_evolucion,
)

__all__ = [
    "BOUNDS",
    "HALF_SPAN",
    "MASA_TOTAL",
    "CG_FRAC_MAC",
    "N_SECCIONES_LOFT",
    "construir_perfil",
    "camino_winglet",
    "distribucion_envergadura",
    "linea_de_curvatura",
    "barrido_alpha",
    "plot_geometria_2d",
    "plot_performance",
    "Candidate",
    "clamp_to_bounds",
    "construir_avion",
    "OP_POINT",
    "calcular_aero",
    "evaluar_candidato",
    "evaluar_candidato_invisido",
    "evaluar_candidato_toy",
    "generar_hijos",
    "generar_hijos_con_catalogo",
    "CATALOGO",
    "CATALOGO_REFLEJADOS",
    "CM0_MEDIDO",
    "N_CATALOGO",
    "cargar_perfil",
    "indice_a_nombre",
    "mezclar",
    "perfil_en_fraccion",
    "perfiles_del_diseno",
    "resumen_catalogo",
    "elevacion_envergadura",
    "poblacion_semilla",
    "semilla_desde_perfil",
    "converger_masa",
    "masa_estructura",
    "analizar_mision",
    "evaluar_mision",
    "desglose_mision",
    "EstadoEvolucion",
    "correr_evolucion_completa",
    "correr_generacion",
    "deberia_parar",
    "guardar_checkpoint",
    "cargar_checkpoint",
    "iniciar_evolucion",
    "exportar_json",
    "secciones_3d",
    "verificar",
]
