# Resultados de la optimización con viento

Todo lo de esta carpeta lo genera `viento/optimizar_con_viento.py`. No se edita a mano:
para rehacerlo, correr el script (ver abajo).

La comparación es siempre la misma: para cada topología, el **diseño sin viento** de
Felipe (`optimizacion_avion/ganadores.json`, corrida del 18/09) contra el **diseño con
viento**, **los dos evaluados con el viento del sitio**. En los gráficos, gris = sin
viento y azul = con viento.

```
resultados/
├── ganadores/                    un JSON por topología: parámetros, análisis e historial del ganador con viento
├── tablas/
│   ├── comparacion_sin_vs_con_viento.csv   todas las magnitudes, una fila por avión
│   └── comparacion_sin_vs_con_viento.md    la misma tabla resumida, con el ranking
├── graficos/
│   ├── comparacion/
│   │   ├── comparacion_sin_vs_con_viento.png   score, superficie alar, velocidad de pérdida, L/D
│   │   └── comparacion_performance.png         resistencia y potencia (crucero y 120 km/h), masa,
│   │                                           carga alar, factor de carga con ráfaga, turbulencia
│   ├── curvas_vuelo_nivelado/
│   │   └── curvas_empuje_potencia.png          empuje requerido, potencia requerida y L/D contra velocidad
│   └── convergencia/
│       └── convergencia_con_viento.png         mejor score por generación, cada topología
└── vistas_3d/                    un HTML interactivo por avión: <topologia>_sin_viento_18-09.html y <topologia>_con_viento.html
```

**Vistas 3D:** doble clic en el `.html` y se abre en el navegador. Arrastrar para rotar,
rueda para el zoom. Necesitan internet (cargan la librería plotly).

**Para regenerar** (desde la carpeta `genetic_wing`):

- `python viento/optimizar_con_viento.py`: vuelve a optimizar las 5 topologías y rehace todo (~1 h).
- `python viento/optimizar_con_viento.py --solo-comparar`: usa los ganadores ya guardados y rehace
  tablas, gráficos y vistas 3D (unos minutos).

Los ganadores con viento también se copian a `optimizacion_avion/ganadores_viento.json`.
