# codigo_viento: implementación de la investigación de viento

Paquete de Python que convierte las fichas de viento (`../fichas/*.yaml`) en algo que se puede usar en el diseño:
- campos de viento para el VLM,
- operabilidad de la misión,
- cargas de ráfaga.

**Es independiente del código del optimizador** (`optimizacion_avion`): para evaluar los diseños, solamente **lee** `optimizacion_avion/ganadores.json` y llama a `construir_avion()` para armar la geometría. Para que el viento entre en la *optimización* (no solo en la evaluación) ver `optimizacion_avion/viento.py` y la Research Note 16; sus pruebas están en `tests/test_optimizador_viento.py`.

## Estructura

```
codigo_viento/
├── viento_uav/
│   ├── fichas.py          lee fichas/*.yaml y el resumen estadístico (histogramas, rosa)
│   ├── campos.py          campos de viento: ráfaga 1−coseno, cortante vertical, turbulencia de Dryden
│   ├── vlm_viento.py      VLM de AeroSandbox con viento no uniforme + respuesta dinámica a ráfagas
│   └── mision_viento.py   velocidad respecto del suelo, ida y vuelta, operabilidad, chequeo de ráfaga (FAR 23.341)
├── ejemplos/
│   └── evaluar_ganadores_con_viento.py   evalúa los 5 ganadores del optimizador en los dos sitios
├── tests/test_viento.py   12 pruebas de verificación
├── tests/test_optimizador_viento.py   6 pruebas del viento dentro del optimizador
└── resultados/            salida del ejemplo (CSV + figuras)
```

## Instalación y uso

Usa las mismas dependencias que el optimizador, más `pyyaml` y `pytest`:

```
pip install aerosandbox numpy matplotlib pyyaml pytest
```

Desde la carpeta `codigo_viento`:

```
python -m pytest tests -q                                   # verificar que todo anda
python ejemplos/evaluar_ganadores_con_viento.py --repo "C:\...\genetic_wing"
python ejemplos/evaluar_ganadores_con_viento.py --repo "..." --sin-vlm      # versión rápida, sin VLM
```

### Ejemplos sueltos

```python
import viento_uav as vu
f = vu.cargar_ficha("canadon_leon")

# Misión
vu.operabilidad(f, V=80/3.6, corregido=True)          # % de horas operables
vu.factor_ida_vuelta(V=22.2, W=12.0)                  # cuánto se alarga el viaje con 12 m/s de frente

# Ráfaga rápida con los números del optimizador (dict 'analisis' de ganadores.json)
vu.chequeo_rafaga_desde_analisis(analisis, f, criterio="diseno")   # n, Kg, margen de pérdida

# Campos de viento (componibles con +)
campo = vu.RafagaCoseno(U_ds=f.U_ds("diseno"), H=10.0) + vu.TurbulenciaDryden.desde_ficha(f, 120)

# VLM con viento sobre cualquier asb.Airplane
from viento_uav import vlm_viento as vv
r = vv.correr_vlm(avion, V=22.2, alpha=2.0, rho=f.rho_diseno, campo=campo, X_avion=5.0)
filas = vv.barrido_H(avion, 22.2, f.rho_diseno, W, f.U_ds("diseno"), [4, 10, 20, 40])
```

## Convención de ejes de los campos

Los campos usan ejes tierra solidarios a la ruta:
- **X** hacia adelante, **Y** a la derecha, **Z** hacia arriba.
- **u > 0** es viento de cola y **w > 0** es una ráfaga ascendente.

Los campos representan **perturbaciones**. El viento medio no va en el campo, porque un viento uniforme no cambia la aerodinámica; se trata en `mision_viento`.

## Cómo entra el viento al VLM

El VLM de AeroSandbox calcula la velocidad en cada panel como `V_inf + rotación`. `OperatingPointConViento` le suma, en ese mismo lugar, la velocidad del campo evaluada en cada punto. Así el viento entra en dos lugares: en el lado derecho del sistema y en el cálculo de fuerzas. La matriz de influencia, que depende solo de la geometría, no cambia.

Hay dos modos para ráfagas:

| Modo | Qué supone | Para qué sirve |
|---|---|---|
| `simular_paso` (cuasi-estático) | El avión queda fijo y el ala responde al instante | Da una cota superior conservadora. El pico casi no depende de H |
| `simular_rafaga_dinamica` (recomendado) | El avión puede subir con la ráfaga (1 grado de libertad vertical) y la sustentación tarda en crecer (funciones de Küssner y Wagner) | Es lo que hay detrás del factor Kg de FAR 23.341, pero con la geometría real. Permite barrer H y encontrar la ráfaga crítica |

El modo dinámico reproduce la fórmula con Kg con un error de alrededor del 3 % (está verificado en los tests). No incluye cabeceo, alivio inercial del peso del ala ni flexibilidad.

## Verificaciones (tests)

- Las fichas devuelven los mismos números que el informe.
- La operabilidad reproduce la tabla del informe.
- El chequeo de ráfaga reproduce la cuenta de `mision_avion.py`: Kg = 0.487 y Δn = 1.46 para el ganador convencional con 3 m/s.
- Una ráfaga vertical uniforme en el VLM da lo mismo que girar el viento relativo.
- Sin viento, el VLM da exactamente lo mismo que el VLM original de AeroSandbox.
- La turbulencia de Dryden sintetizada tiene la σ pedida.
- La respuesta dinámica a la ráfaga CS-23 coincide con la fórmula de Kg.

## Resultados del ejemplo (ganadores del 18/09, `resultados/`)

| | Cañadón León | Puesto Hernández |
|---|---|---|
| Horas de día operables a 80 km/h (ERA5 / corregido) | 80 % / 63 % | 97 % / 96 % |
| Horas de día operables a 120 km/h (corregido) | 92 % | 100 % |
| n con ráfaga de 4.6 m/s a 80 km/h | 3.1 – 3.4 | 3.1 – 3.3 |
| n con ráfaga de 3.1 m/s a 120 km/h | 3.2 – 3.4 | 3.1 – 3.3 |
| Entrada en pérdida por ráfaga | no (margen 18–41 %) | no |

**Punto para discutir con el grupo:** la estructura del optimizador se dimensiona con `N_LIMITE = 3.0` (con `N_ULTIMO = 4.5`). La ráfaga de diseño a 80 km/h (n ≈ 3.1–3.4) y la ráfaga de operación a 120 km/h (n ≈ 3.2–3.4) superan levemente ese límite. Una ráfaga de 4.6 m/s a 120 km/h llega a n ≈ 4.2–4.6, en el borde del último. Hay dos maneras de resolverlo, y es una decisión de diseño, no algo que este código cambie:
- subir `N_LIMITE`;
- limitar la velocidad en aire turbulento, como hace CS-23, que exige la mitad de ráfaga a V_D.

## Pendiente

- ~~Integrar el análisis al puntaje del optimizador.~~ Hecho el 2026-10-02 (Research Note 16).
- Agregar cabeceo a la respuesta dinámica (2 grados de libertad) y alivio inercial.
- Cortante vertical en despegue y aterrizaje: el campo `CortanteVertical` ya está hecho, falta el análisis de trayectoria.
