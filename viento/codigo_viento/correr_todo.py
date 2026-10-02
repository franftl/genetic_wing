"""
Corre todo el análisis de viento de una vez (para usar con el botón "Run" de VS Code).

1. Verifica el paquete viento_uav (tests).
2. Evalúa los ganadores del optimizador (genetic_wing) con el viento de los dos sitios.

Usa el repositorio genetic_wing que contiene esta carpeta.
Los resultados quedan en  codigo_viento/resultados/.
"""
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
# El código vive dentro del repo: genetic_wing/viento/codigo_viento
REPO = AQUI.parents[1]
if not (REPO / "optimizacion_avion").exists():   # ubicación vieja: Proyecto final/Datos de viento/codigo_viento
    REPO = AQUI.parents[1] / "genetic_wing"

print("=== 1/2  Tests del paquete viento_uav ===")
r = subprocess.run([sys.executable, "-m", "pytest", str(AQUI / "tests"), "-q"], cwd=AQUI)
if r.returncode != 0:
    sys.exit("Fallaron los tests: revisar antes de seguir.")

print("\n=== 2/2  Evaluación de los ganadores con viento (tarda unos minutos por el VLM) ===")
subprocess.run([sys.executable, str(AQUI / "ejemplos" / "evaluar_ganadores_con_viento.py"),
                "--repo", str(REPO)], cwd=AQUI, check=True)
print(f"\nListo. Resultados en {AQUI / 'resultados'}")
