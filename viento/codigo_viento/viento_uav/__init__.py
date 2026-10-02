"""
viento_uav -- implementación de la caracterización de viento del proyecto.

Paquete INDEPENDIENTE del optimizador (optimizacion_avion / optimizacion_ala):
no modifica nada de ese código. Lo puede usar desde afuera (importando
construir_avion o leyendo ganadores.json) para evaluar diseños con el viento
real de cada sitio.

Módulos:
    fichas         lectura de fichas/*.yaml y del resumen estadístico
    campos         campos de viento: ráfaga 1-coseno, cortante, Dryden
    vlm_viento     VLM de AeroSandbox con viento no uniforme (cargas de ráfaga)
    mision_viento  operabilidad, velocidad respecto del suelo, chequeo de ráfaga rápido
"""
from .fichas import FichaViento, cargar_ficha, dryden_baja_altura, SITIOS
from .campos import (Campo, CampoNulo, CampoSuma, RafagaUniforme, RafagaCoseno,
                     CortanteVertical, TurbulenciaDryden)
from .mision_viento import (velocidad_suelo, factor_ida_vuelta, factor_ida_vuelta_promedio_rumbos,
                            operabilidad, alcance_efectivo, chequeo_rafaga,
                            chequeo_rafaga_desde_analisis, CL_crucero_en_sitio)

# vlm_viento necesita AeroSandbox; se importa aparte para que lo demás funcione sin él:
#     from viento_uav import vlm_viento

__all__ = [
    "FichaViento", "cargar_ficha", "dryden_baja_altura", "SITIOS",
    "Campo", "CampoNulo", "CampoSuma", "RafagaUniforme", "RafagaCoseno", "CortanteVertical",
    "TurbulenciaDryden",
    "velocidad_suelo", "factor_ida_vuelta", "factor_ida_vuelta_promedio_rumbos", "operabilidad",
    "alcance_efectivo", "chequeo_rafaga", "chequeo_rafaga_desde_analisis", "CL_crucero_en_sitio",
]
