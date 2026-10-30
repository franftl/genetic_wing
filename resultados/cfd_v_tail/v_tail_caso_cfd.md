# Caso CFD - v_tail
_Ala + fuselaje + cola en V_  |  escenario del modelo: viento ON, bateria ON

STL en **n/a**. Ejes: x hacia atras (del morro a la cola), y a la derecha, z hacia arriba.

## Condiciones de entrada
- Velocidad: 22.22 m/s (80 km/h), Mach 0.066
- rho = 1.0560 kg/m3, mu = 1.7433e-05 Pa.s, T = 278.7 K, p = 84476 Pa
- Re (MAC) = 6.356e+05   q = 260.74 Pa

## Referencias para los coeficientes
- S_ref = 1.2876 m2, c_ref (MAC) = 0.4722 m, b = 2.979 m (AR 6.89)
- Momentos respecto de xyz = [0.4768, 0.0, 0.0] m
- Masa 11.90 kg, peso 116.8 N

## Punto de calculo (crucero)
- alpha del modelo = 1.307 deg  ->  CL objetivo = 0.3478
- Ajustar alpha en el CFD hasta que CL coincida, y comparar CD a igual CL.

## Lo que predice el modelo (AeroBuildup) en ese punto
- CL = 0.3479   CD = 0.01745   L/D = 19.94
- D = 5.858 N  (perfil 3.840 N + inducido 2.019 N)

## Sustentacion y resistencia del modelo en funcion del angulo de ataque
AeroBuildup a 22.22 m/s, mismas condiciones. Fuerzas del avion COMPLETO (si el CFD es medio modelo, comparar contra la mitad).

| alpha [deg] | CL | CD | L [N] | D [N] | L/D | Cm |
|---|---|---|---|---|---|---|
| -4.00 | -0.1292 | 0.01535 | -43.4 | 5.15 | -8.4 | 0.0400 |
| -2.00 | 0.0478 | 0.01283 | 16.1 | 4.31 | 3.7 | 0.0265 |
| 0.00 | 0.2286 | 0.01419 | 76.7 | 4.76 | 16.1 | 0.0112 |
| 1.31 | 0.3479 | 0.01745 | 116.8 | 5.86 | 19.9 | 0.0005 |  <- crucero
| 2.00 | 0.4112 | 0.01993 | 138.1 | 6.69 | 20.6 | -0.0056 |
| 4.00 | 0.5936 | 0.02968 | 199.3 | 9.97 | 20.0 | -0.0262 |
| 6.00 | 0.7753 | 0.04302 | 260.3 | 14.44 | 18.0 | -0.0501 |
| 8.00 | 0.9547 | 0.05981 | 320.5 | 20.08 | 16.0 | -0.0749 |
| 10.00 | 1.1306 | 0.07988 | 379.6 | 26.82 | 14.2 | -0.0996 |
| 12.00 | 1.2990 | 0.10271 | 436.1 | 34.48 | 12.6 | -0.1224 |

## Geometria exportada
| Cuerpo | Triangulos | Area mojada [m2] | Volumen [L] | Cerrado |
|---|---|---|---|---|
| Ala principal | 4648 | 2.7592 | 50.99 | si |
| Cola en V | 768 | 0.2214 | 1.12 | si |
| Fuselaje | 1824 | 0.5712 | 18.17 | si |

Volumen de fuselaje segun el modelo: 18.22 L (debe coincidir con el volumen del cuerpo 'Fuselaje').

## Recordatorios
- Los cuerpos se superponen: unir en el CAD o con el wrapper de Fluent Meshing.
- No incluye helice ni spinner ni superficies deflectadas.
- Re ~ 5-7e5: usar un modelo con transicion (k-omega SST gamma-Re_theta) si se quiere comparar con AeroBuildup/NeuralFoil; un modelo totalmente turbulento da mas drag de perfil.
- Se puede correr medio modelo (y >= 0) con plano de simetria.
