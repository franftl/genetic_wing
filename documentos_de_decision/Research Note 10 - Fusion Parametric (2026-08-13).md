# UAV FP — Research Note 10: Parametrizando el Ala en Fusion (conectado al pipeline de Python)

*Compilado 13 agosto 2026. Sigue a la Nota 9 (implementación en Python con AeroSandbox/NeuralFoil).*

## Por qué esto es distinto a parametrizar un sketch "normal"

En Fusion, parametrizar un sketch normalmente significa: crear **User Parameters** (Modificar > Cambiar Parámetros), darles un nombre corto (ej. "envergadura", "cuerda_raiz"), y después, en vez de tipear un número fijo en una cota del sketch, tipear el nombre del parámetro — así, cambiar el parámetro actualiza todo el modelo automáticamente. Eso funciona perfecto para formas simples (rectángulos, círculos, extrusiones).

El problema es que un perfil de ala **no es una forma simple con cotas** — es una curva definida por 50-200 puntos (x,y) que vienen de un archivo de coordenadas (el mismo tipo de archivo `.dat` formato Selig que usa AeroSandbox/NeuralFoil/XFLR5). Fusion no tiene una manera nativa de "cotar" esa curva con unos pocos parámetros — hay que traerla como una spline a través de puntos.

## El workflow real, en dos niveles

**Nivel 1 — traer el perfil como spline (geometría, no todavía paramétrico):** Fusion permite crear una spline a partir de una nube de puntos (Sketch > Insertar Punto, o Sketch > Spline > "Fit Point Spline"). Existen además add-ins ya hechos específicamente para esto — [`airfoil_toolkit_fusion360`](https://github.com/finlaywallace/airfoil_toolkit_fusion360) importa directamente archivos `.dat` en formato Selig (los mismos que bajás de airfoiltools.com o que ya estás generando/usando en tu script de Python) y arma la spline del perfil en un sketch nuevo. Ojo: este add-in específico **no** parametriza automáticamente cuerda/torsión/posición en la envergadura — solo importa la forma cruda; escalar, rotar y ubicar cada sección en su lugar todavía se hace a mano con las herramientas nativas de Fusion (Escalar, Mover/Copiar), o mediante los User Parameters aplicados sobre esas operaciones (por ejemplo, el factor de escala de cada sección sí puede estar atado a un parámetro "cuerda_raiz" o "cuerda_punta").

**Nivel 2 — parametrización real, conectada a tu pipeline de Python:** esta es la parte más relevante para el proyecto. Fusion tiene una **API de Python** completa y documentada oficialmente por Autodesk, incluyendo funciones específicas para crear splines a través de puntos por código ("Sketch spline through points creation" — ver [documentación oficial](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/SketchSplineThroughPoints_Sample.htm)). Esto permite escribir un script que agarre los valores exactos que salieron de tu optimización en AeroSandbox (cuerda de raíz, cuerda de punta, flecha, torsión, coordenadas del perfil) y genere el sketch/loft en Fusion automáticamente — sin tener que re-tipear a mano los mismos números que ya calculó Python. Esto cierra el círculo: la geometría que valida el VLM es matemáticamente la misma que termina como sólido en Fusion, sin margen para errores de transcripción entre ambos programas.

## Armando el ala 3D completa (no solo un perfil)

Para pasar de "un perfil 2D" a "un ala sólida", el flujo estándar en Fusion es: crear un plano de sketch en cada estación de envergadura que definiste en tu script de Python (por ejemplo, raíz y punta, igual que tus `asb.WingXSec`), importar/escalar el perfil en cada plano usando exactamente la cuerda y torsión de esa sección, y después usar **Loft** (Crear > Loft) entre esos perfiles para generar el sólido 3D que conecta la raíz con la punta respetando la flecha y el taper. Ese sólido es el que después usás para diseñar estructura interna (costillas, larguero) o para preparar archivos de fabricación.

## Recomendación práctica

Dado que tu equipo ya está trabajando en Python (Nota 9), el camino más prolijo es: definir las variables de diseño una sola vez (en tu script de optimización), y usarlas tanto para correr el VLM como, mediante la API de Fusion, para generar el modelo CAD — en vez de mantener dos fuentes de verdad (un Excel/números a mano en Fusion, y otro set de números en tu script de Python) que se pueden desincronizar entre iteraciones del diseño.

## Caso simplificado: perfil ya definido, solo falta la geometría externa

Si ya tenés el perfil (la sección 2D) resuelto y lo único que falta parametrizar es la geometría externa — envergadura, cuerda de raíz/punta, flecha, torsión, diedro — el flujo en Fusion es más simple de lo que parece, y se apoya en tres herramientas nativas: **planos de construcción**, **escala de sketch**, y **Loft**. Paso a paso:

1. **Definí los User Parameters primero** (Modificar > Cambiar Parámetros): `envergadura`, `cuerda_raiz`, `cuerda_punta`, `flecha`, `torsion_punta`, `diedro` — idealmente con los mismos nombres/valores que las variables de tu función `evaluar_diseño()` en Python, para que no haya ambigüedad sobre qué representa cada uno.

2. **Sketch de raíz:** poné tu perfil ya importado en el plano XZ (o el que uses como referencia), y escalalo (Sketch > Escalar) usando `cuerda_raiz` como factor de escala. Si tu archivo `.dat` está normalizado a cuerda unitaria (0 a 1, que es el estándar), escalar por la cuerda real te da directamente el tamaño correcto — y de paso escala el espesor proporcionalmente, que es exactamente el comportamiento físico correcto (el espesor de un perfil se expresa como %cuerda).

3. **Plano de punta:** creá un plano de construcción "Offset Plane" a distancia `envergadura` (o `envergadura/2` si es una semi-ala que después vas a espejar) desde el plano de raíz, a lo largo del eje de envergadura. Si además querés diedro, usá "Plane at Angle" en vez de un offset simple, con `diedro` como el ángulo — así el plano de punta queda inclinado hacia arriba, y el sketch que pongas ahí hereda esa inclinación automáticamente.

4. **Sketch de punta:** en ese plano, poné una copia del mismo perfil, escalada por `cuerda_punta` (más chica que la raíz, para el taper). Para la flecha, desplazá el origen del sketch (o el punto de borde de ataque) una distancia `flecha` en la dirección de la cuerda, dentro de ese mismo plano.

5. **Torsión (washout) — el punto donde la gente se traba:** un hilo del foro de Autodesk sobre exactamente este problema (lofts de ala con washout) confirma algo importante: **no se puede "torcer" un sólido después de hacer el loft** — el twist tiene que estar ya construido en la orientación del sketch de punta *antes* de lofter. La forma correcta es rotar el sketch de punta (o el plano donde vive) por el ángulo `torsion_punta` alrededor de un punto de referencia fijo (normalmente el punto a 1/4 de la cuerda, para que coincida con la convención que ya usaste en el modelo aerodinámico de Python) — no ajustar nada después de crear el loft.

6. **Loft:** Crear > Loft, seleccioná el perfil de raíz y el de punta (en ese orden), y Fusion genera el sólido que conecta ambos respetando la flecha, el taper y la torsión que ya quedaron definidos en la posición/orientación de cada sketch. Si es un flying wing simétrico, con Espejo (Mirror) replicás la semi-ala para tener el ala completa.

Con este esquema, cambiar un solo parámetro (por ejemplo, subir `torsion_punta` de -4 a -6) recalcula automáticamente la posición del sketch de punta y el loft entero — que es exactamente el comportamiento paramétrico que buscás, sin tener que rehacer el sólido a mano cada vez que cambie el resultado de la optimización en Python.

## Fuentes

- [airfoil_toolkit_fusion360 — add-in para importar perfiles .dat en Fusion (GitHub)](https://github.com/finlaywallace/airfoil_toolkit_fusion360)
- [Fusion360ImportCSVPoints — add-in genérico para importar nubes de puntos (GitHub)](https://github.com/hanskellner/Fusion360ImportCSVPoints/blob/master/README.md)
- [User Parameters for Parametric Modeling in Fusion 360 (Noble Desktop)](https://blog.nobledesktop.com/learn/cad/building-user-parameters-for-parametric-modeling-in-fusion-360)
- [Sketch spline through points creation — Fusion API (Autodesk, documentación oficial)](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/SketchSplineThroughPoints_Sample.htm)
- [Create an offset plane — Fusion Help (Autodesk)](https://help.autodesk.com/view/fusion360/ENU/?guid=SLD-CONSTRUCT-OFFSET-PLANE)
- [Create a plane at an angle — Fusion Help (Autodesk)](https://help.autodesk.com/view/fusion360/ENU/?guid=SLD-CONSTRUCT-PLANE-AT-ANGLE)
- [Struggling to loft a wing with washout (twist) at the tip — Autodesk Community forum](https://forums.autodesk.com/t5/fusion-design-validate-document/struggling-to-loft-a-wing-with-washout-twist-at-the-tip/td-p/11880143)
