# Versiones del optimizador de avión

El nombre del notebook lleva la versión: `Optimizador_V51.ipynb`. La versión se define
en un solo lugar, `VERSION` en `optimizacion_avion/__init__.py`; el notebook y su nombre
de archivo salen de ahí (`construir_notebook_avion.py` lo lee al regenerar).

## Regla

| Qué cambia | Cómo se numera | Ejemplo |
|---|---|---|
| Una modificación sobre la versión existente (parámetros, supuestos, ajustes, correcciones) | sube el decimal | V50 → V50.1 → V50.2 |
| Se agrega o se modifica un **módulo** | sube el número | V50 → V51 |

Al subir de versión: cambiar `VERSION`, regenerar el notebook (`python construir_notebook_avion.py`),
y agregar una entrada abajo con qué cambió. El notebook de la versión anterior se conserva
solo si hace falta comparar; si no, se reemplaza.

## V50 (2026-10-13) — versión base

Rama `bateria-350km`. Lo que incluye:

- Batería dimensionada por alcance (350 km a velocidad de crucero constante), con
  eficiencia propulsiva modificable (`optimizacion_avion/bateria.py`, `mision_avion.BATERIA_ACTIVA`).
- Viento de los sitios (`mision_avion.VIENTO_ACTIVO`, de `viento`).
- Penalización de envergadura > 2 m (fabricación), sweep monótono y 11 estaciones en el ala.
- `pod_boom` es un fuselaje continuo (diámetro casi constante, afinado en la cola),
  sin góndola ni viga fina.
- Exportación a CAD y CFD: `exportar_cad_avion.py` + `fusion_generar_avion.py` (Fusion) y
  `exportar_cfd_avion.py` (STL, caso de cálculo y comparación de drag).
- Evaluación y resultados en `evaluacion_bateria_350km/`.

Pendientes conocidos: el script de Fusion no se probó dentro de Fusion; la forma cóncava del
ala (anedro en la raíz, diedro en la punta) sigue permitida por el hueco de la proyección de
elevación; el modelo no incluye hélice ni superficies de control.

## V50.1 (2026-10-15) — script de Fusion mallable en Ansys

Modificación sobre V50 (no toca el optimizador ni el modelo): `fusion_generar_avion.py` v2.

- Un loft por tramo entre secciones vecinas (igual que la interpolación lineal del solver) en vez de
  un solo loft por todas: el loft único hacía sobreimpulso en el ala exterior (tramos de 175 mm y de
  26 mm con ~30° de giro) y Fluent rechazaba el modelo por autointersecciones.
- Borde de fuga a espesor uniforme (`ESPESOR_TE_MM`, 1.0 mm por defecto; `None` lo deja como viene).
- Chequeo de secciones vecinas que se cruzan, limpieza de puntos repetidos, espejo sin fusionar y
  unión final con diagnóstico por cuerpo.
- Versión anterior en `codigo_obsoleto/fusion_generar_avion_v1_un_loft.py`.

Pendiente: probar v2 dentro de Fusion y mallar en Fluent.


## V51 (2026-10-16) — restricciones de manufacturabilidad

Módulo nuevo `optimizacion_avion/manufactura.py`, aplicado en `construir_avion`, así que lo ven
el optimizador, el export CAD/CFD y Fusion con la misma geometría.

- **Borde de fuga de 2 mm absolutos** en todas las superficies (ala, winglets, colas, derivas):
  cada sección usa 2 mm / su cuerda como fracción. Las puntas quedan cerradas por la sección
  terminal, que también tiene 2 mm. NeuralFoil ve el espesor, así que la resistencia de base ya
  entra en el CD.
- **Nariz sin punta**: cara plana de radio 5 mm y ley de potencia `morro_exp` (0.45–1.0) hasta el
  radio del fuselaje, con más secciones cerca de la punta. La ojiva de Von Kármán pura es
  puntiaguda y es para régimen supersónico; a 22 m/s se usa una forma roma truncada.
- `exportar_cad_avion.py` completa solo la diferencia hasta 2 mm (no suma el borde de fuga dos
  veces); `fusion_generar_avion.py` con `ESPESOR_TE_MM = 2.0`.
- Efecto medido en el ganador v_tail (sin re-optimizar): CD crucero 0.0173 → 0.0175, puntaje
  4.91 → 4.85 (~1 %).
- **Hay que volver a correr el GA**: los ganadores anteriores se optimizaron con filo exacto y
  nariz en punta.
