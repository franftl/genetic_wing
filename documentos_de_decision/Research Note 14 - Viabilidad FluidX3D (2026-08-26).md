# Research Note 14 — Viabilidad de FluidX3D (CFD por Lattice Boltzmann) en el loop de optimización

**Fecha:** 2026-08-26
**Pregunta que dispara la nota:** ¿qué tan viable es meter FluidX3D —el solver CFD open source por Lattice Boltzmann, acelerado por GPU— dentro del pipeline de optimización que estamos armando?

**Respuesta corta:** **no es viable dentro del loop de optimización**, por tres razones independientes, cualquiera de las cuales alcanzaría por sí sola. **Sí es la herramienta correcta para la validación final de la geometría ganadora**, que es exactamente el rol que ya tenía asignado en el documento de objetivos mínimos. No hay que cambiar el plan; hay que no adelantarlo.

---

## 1. Estado actual del proyecto FluidX3D

| | |
|---|---|
| Repo | github.com/ProjectPhysX/FluidX3D (autor: Dr. Moritz Lehmann) |
| Versión | v3.7 (mayo 2026) |
| Método | Lattice Boltzmann (LBM), no Navier-Stokes por volúmenes finitos |
| Lenguaje | C++17 + kernels OpenCL. **Sin bindings de Python.** |
| Corre en | GPUs y CPUs de AMD, Intel y Nvidia vía OpenCL; multi-GPU |
| Memoria | ~55 bytes/celda → ~19 millones de celdas por GB de VRAM |
| Geometría | Importa y voxeliza mallas `.stl` binarias en GPU |
| Fuerzas | Extensión `FORCE_FIELD` + `lbm.object_force()` / `lbm.object_torque()` |
| Turbulencia | LES con modelo de submalla Smagorinsky-Lilly |
| Licencia | Gratis para uso no comercial |

Es un proyecto serio y genuinamente rápido: el LBM es mucho más paralelizable que un solver Navier-Stokes clásico, y por eso rinde tan bien en GPU. La premisa de "es más rápido" es cierta. El problema es contra qué lo estamos comparando.

---

## 2. Los tres bloqueantes para meterlo en el loop

### 2.1 Velocidad — no es rápido *comparado con lo que ya usamos*

FluidX3D es rápido *para ser CFD 3D*. Nuestro loop no usa CFD: usa un método de paneles (VLM), que es entre 3 y 5 órdenes de magnitud más barato.

Medido en este entorno, sobre nuestro propio código:

| Método | Tiempo por candidato |
|---|---|
| VLM (`evaluar_candidato` actual) | **268 ms** |
| NeuralFoil (perfil, viscoso) | **4.8 ms** |
| CFD 3D de aeronáutica externa | minutos a horas |

Una corrida típica del GA hoy: 19 generaciones × 10 hijos = **190 evaluaciones**.

| Costo por evaluación | Costo de UNA corrida del GA |
|---|---|
| 268 ms (VLM) | **51 segundos** |
| 5 min (CFD optimista) | 16 horas |
| 30 min (CFD realista) | 4 días |
| 120 min (CFD con malla fina) | 16 días |

Y eso es **una** corrida. Un proyecto de optimización real implica decenas: cambiar pesos, cambiar el espacio de diseño, re-correr tras un bug. Con CFD en el loop, cada iteración del *proyecto* pasa de un café a una semana.

### 2.2 Precisión — la documentación del propio autor lo desaconseja para esto

Esto es más grave que la velocidad, porque no se arregla con más GPU. De `DOCUMENTATION.md` del repo, textual:

> "in the highly turbulent regime, computed body forces are too large by up to a factor 2, because even large resolution is not enough to fully capture the turbulent boundary layer. A wall function is still needed."

Traducido: **las fuerzas sobre el cuerpo pueden salir hasta el doble de lo que corresponde**, porque ni con resolución alta se captura la capa límite turbulenta, y todavía falta implementar una función de pared.

Un error de hasta 2× en la fuerza es fatal para lo que necesitamos. Una optimización aerodinámica compara diseños que difieren en un 2-5% de resistencia. Un modelo con hasta 100% de error sistemático no puede ordenar esos candidatos: el ruido del modelo es 20 a 50 veces más grande que la señal que buscamos. El GA no optimizaría el ala, optimizaría el error del solver.

Además, nuestro régimen es justamente el complicado. Con V = 20 m/s y ν = 1.5×10⁻⁵ m²/s:

| Cuerda | Reynolds |
|---|---|
| 0.40 m (raíz) | 533.000 |
| 0.30 m | 400.000 |
| 0.12 m (punta) | 160.000 |

Estamos en Re de 10⁵–10⁶, es decir, de lleno en el régimen donde el propio autor advierte el problema. *(La documentación también menciona inestabilidad a Re muy altos; el umbral exacto conviene verificarlo corriendo el solver, no confiar en la lectura de la doc.)*

### 2.3 Integración — C++/OpenCL, sin API de Python

No hay bindings de Python. El acople sería: exportar `.stl` desde el candidato → escribir un `setup.cpp` → recompilar o parametrizar → ejecutar el binario → parsear la salida de fuerzas → devolver el score. Cada eslabón es un punto de falla dentro de un loop que hoy es una llamada a función. Es hacible, pero es trabajo de integración real, y sería trabajo puesto al servicio de las dos objeciones anteriores.

---

## 3. Sobre "la red neuronal que estamos creando"

Vale aclarar un punto de vocabulario que afecta la respuesta, porque hay dos lecturas posibles de la pregunta.

**Lo que tenemos hoy no es una red neuronal que entrenamos nosotros.** El pipeline es un **algoritmo genético** (`ga_numerico.py`: cruzamiento BLX-alfa + mutación gaussiana) que busca sobre 17 parámetros. La única red neuronal involucrada es **NeuralFoil**, que viene **pre-entrenada** dentro de AeroSandbox: no la entrenamos, la usamos. Conviene tener esto claro para la defensa ante la junta, porque el documento de objetivos habla de "una red neuronal que optimice genéticamente la geometría" y esa frase mezcla dos cosas distintas.

**La otra lectura: ¿usar CFD para generar datos de entrenamiento de una red sustituta (surrogate)?** Ese sí es un patrón legítimo y usado en la industria: correr CFD offline sobre N cientos de diseños, entrenar una red que aprenda geometría → coeficientes, y meter *la red* (milisegundos) en el loop del GA en lugar del CFD. Resuelve el problema de velocidad de forma elegante.

Pero para nuestro caso no cierra, por dos motivos:

1. **El problema de precisión se hereda, no se cancela.** Una red entrenada sobre datos con hasta 2× de error aprende a reproducir ese error con mucha fidelidad. Basura entra, basura sale — solo que más rápido y con más apariencia de rigor.
2. **Es una tesis en sí mismo.** Generar el dataset (cientos de corridas CFD), diseñar la arquitectura, entrenar, validar, y recién ahí conectarlo al GA, es un proyecto entero. Sería reemplazar el objetivo mínimo comprometido por otro más ambicioso, a mitad de año.

Y hay un detalle de licencia a tener en cuenta si alguna vez se va por este camino: la licencia de FluidX3D **prohíbe entrenar modelos de IA sobre el código fuente**. Entrenar sobre los *resultados* de simulaciones es otra cosa y no está obviamente prohibido, pero si el plan fuera publicar un surrogate entrenado con datos de FluidX3D, conviene leer la licencia con cuidado o consultarle directamente al autor antes de invertir tiempo.

---

## 4. Dónde SÍ va FluidX3D

En el rol que ya tenía en el documento de objetivos mínimos: **validación por CFD de la geometría final**. Es decir, **una sola corrida** (o un puñado), sobre el diseño ya elegido, para verificar que lo que predijo el modelo rápido se sostiene con un modelo de mayor fidelidad.

En ese rol, todas las objeciones se caen:

- **Velocidad**: correr 30 minutos una vez no es un problema, es lo normal.
- **Precisión**: para validación cualitativa —¿se separa el flujo donde esperábamos?, ¿hay algo raro en la punta?, ¿el campo de presiones tiene sentido?— el factor 2 en la fuerza integrada importa mucho menos. Y para el número de resistencia, se lo reporta con la incertidumbre declarada, honestamente.
- **Integración**: exportar un `.stl` a mano y correr el binario una vez no necesita ninguna automatización.
- **Licencia**: tesis universitaria = "public research, education". Permitido, citando al autor y los papers que el repo pide citar.

**Advertencia de licencia aparte:** la licencia también **prohíbe el uso militar o para la industria de defensa**. Nuestra aplicación (monitoreo de pozos de petróleo y gas) no es eso, pero vale tenerlo presente dado que el proyecto es un UAV y que en las notas anteriores apareció CITEDEF como antecedente nacional. Si en algún momento el proyecto rozara ese ámbito, esta dependencia habría que sacarla.

---

## 5. Lo que sí resuelve el problema que tenemos hoy

La pregunta llega justo después de haber diagnosticado por qué el objetivo actual se rompe (ver el encabezado del notebook): **`VortexLatticeMethod` es invíscido**, su CD es solo resistencia inducida, y como la inducida es ∝ CL², el L/D tiende a infinito cuando el CL tiende a cero. El GA aprendió a no generar sustentación: llegó a L/D = 551 con CL = 0.022.

Es tentador leer "me falta física en el modelo" y saltar a CFD. Pero la física que falta —**resistencia viscosa**— la da NeuralFoil en 4.8 ms, y **ya está instalado**.

Medido sobre nuestro propio perfil custom, a Re = 4×10⁵:

| Término | Valor |
|---|---|
| CD viscoso de perfil (NeuralFoil) | **0.00899** |
| CD inducido del "ganador" (VLM) | 0.000039 |
| Razón | **el término que falta es ~230× más grande que el que teníamos** |

O sea: no estábamos calculando "la mayor parte de la resistencia con un error chico". Estábamos calculando **menos del 0.5% de la resistencia**. Sumando el CD₀, ese L/D de 551 se derrumba a un valor de un dígito. *(La cuenta exacta requiere integrar el perfil a lo largo de la envergadura, no aplicar un CD₀ plano; el punto acá es el orden de magnitud, no el número.)*

**Conclusión operativa:** el próximo paso del pipeline aerodinámico no es CFD. Es:

1. Sumar CD viscoso vía NeuralFoil al CD inducido del VLM (integrando por estación de envergadura).
2. Evaluar a **sustentación fija** en vez de alpha fijo, para que "no sustentar" deje de ser una jugada válida.

Ambos son cambios acotados dentro de `objetivo.py`, del orden de horas, no de semanas. FluidX3D entra después, sobre el ganador.

---

## Fuentes

- [ProjectPhysX/FluidX3D — repositorio principal](https://github.com/ProjectPhysX/FluidX3D)
- [FluidX3D — DOCUMENTATION.md](https://github.com/ProjectPhysX/FluidX3D/blob/master/DOCUMENTATION.md) (de acá sale la advertencia textual sobre el factor 2 en las fuerzas)
- [FluidX3D — LICENSE.md](https://github.com/ProjectPhysX/FluidX3D/blob/master/LICENSE.md)
- [fluidx3d.com — sitio del proyecto](https://fluidx3d.com/)
- Mediciones de tiempo (VLM 268 ms, NeuralFoil 4.8 ms) y de Reynolds: hechas sobre nuestro propio código, `optimizacion_ala/`, 2026-08-26.


---

## 6. Addendum (2026-08-26, mismo día): qué se implementó finalmente

La sección 5 proponía sumar a mano el CD viscoso de NeuralFoil al CD inducido del VLM, integrando por estación de envergadura. **No hizo falta escribir esa integración**: AeroSandbox ya trae `asb.AeroBuildup`, que hace exactamente eso internamente y expone los dos términos por separado (`D_induced`, `D_profile`, que suman `D`).

Se reemplazó `VortexLatticeMethod` por `AeroBuildup` en `objetivo.py`. El cambio ganó en los dos ejes a la vez:

| | VLM invíscido | AeroBuildup |
|---|---|---|
| Tiempo por candidato | 268 ms | **52 ms** (5× más rápido) |
| Resistencia viscosa | no la calcula | sí, vía NeuralFoil |
| L/D del diseño semilla | 86 (irreal) | **17.0** (creíble) |
| L/D del diseño degenerado | **551** (lo premiaba) | **0.58** (lo hunde) |

En una corrida completa del GA con el objetivo nuevo, el ganador dio **L/D = 33.3**, con la resistencia repartida 41% inducida / 59% de perfil. Números creíbles para un ala volante de esta escala.

**El VLM no se descartó**: `AeroBuildup` no produce campo de flujo, así que el notebook lo sigue usando para dibujar las líneas de corriente sobre el diseño final (sección 8). La división quedó: **AeroBuildup para evaluar, VLM para visualizar.**

Esto no cambia la conclusión sobre FluidX3D: sigue siendo la herramienta correcta para la validación final del ganador, y sigue sin ser viable dentro del loop.
