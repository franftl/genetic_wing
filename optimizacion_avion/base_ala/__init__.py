"""
base_ala -- lo que el optimizador de avión heredó del optimizador del ala volante (V50 y anteriores).

Antes vivía en el paquete `optimizacion_ala/`; desde V55 está acá para que `optimizacion_avion` sea autocontenido.
El resto del ala volante (misión, objetivo, GA, gráficos, exportador CAD, notebook) quedó en `codigo_obsoleto/`.

- geometria.py  : Candidate, BOUNDS, proyecciones (flecha/diedro monótonos), construcción del ala volante
- estructura.py : constantes de carga y masa (G, N_LIMITE, N_ULTIMO, MASA_PAYLOAD, MASA_SISTEMAS) y modelo del larguero
- evolucion.py  : criterio de parada del GA (`deberia_parar`) y el estado de la evolución
- perfiles.py   : catálogo base de perfiles UIUC ordenado por Cm0 (N_PUNTOS_LADO, PASO_MEZCLA)

Agregar perfiles solo al final del catálogo: los índices son variables de diseño.
"""
