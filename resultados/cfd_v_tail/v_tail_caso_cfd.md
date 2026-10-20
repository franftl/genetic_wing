# Caso CFD - v_tail
_Ala + fuselaje + cola en V_  |  escenario del modelo: viento ON, bateria ON

STL en **n/a**. Ejes: x hacia atras (del morro a la cola), y a la derecha, z hacia arriba.

## Condiciones de entrada
- Velocidad: 22.22 m/s (80 km/h), Mach 0.066
- rho = 1.0560 kg/m3, mu = 1.7433e-05 Pa.s, T = 278.7 K, p = 84476 Pa
- Re (MAC) = 5.569e+05   q = 260.74 Pa

## Referencias para los coeficientes
- S_ref = 1.3316 m2, c_ref (MAC) = 0.4137 m, b = 3.515 m (AR 9.28)
- Momentos respecto de xyz = [0.6389, 0.0, 0.0] m
- Masa 12.15 kg, peso 119.2 N

## Punto de calculo (crucero)
- alpha del modelo = 0.404 deg  ->  CL objetivo = 0.3432
- Ajustar alpha en el CFD hasta que CL coincida, y comparar CD a igual CL.

## Lo que predice el modelo (AeroBuildup) en ese punto
- CL = 0.3429   CD = 0.01688   L/D = 20.31
- D = 5.861 N  (perfil 4.134 N + inducido 1.727 N)

## Sustentacion y resistencia del modelo en funcion del angulo de ataque
AeroBuildup a 22.22 m/s, mismas condiciones. Fuerzas del avion COMPLETO (si el CFD es medio modelo, comparar contra la mitad).

| alpha [deg] | CL | CD | L [N] | D [N] | L/D | Cm |
|---|---|---|---|---|---|---|
| -4.00 | -0.0875 | 0.01627 | -30.4 | 5.65 | -5.4 | 0.0263 |
| -2.00 | 0.1055 | 0.01329 | 36.6 | 4.61 | 7.9 | 0.0152 |
| 0.00 | 0.3033 | 0.01583 | 105.3 | 5.50 | 19.2 | 0.0004 |
| 0.40 | 0.3429 | 0.01688 | 119.0 | 5.86 | 20.3 | -0.0029 |  <- crucero
| 2.00 | 0.4977 | 0.02252 | 172.8 | 7.82 | 22.1 | -0.0168 |
| 4.00 | 0.6910 | 0.03276 | 239.9 | 11.37 | 21.1 | -0.0362 |
| 6.00 | 0.8827 | 0.04662 | 306.5 | 16.19 | 18.9 | -0.0546 |
| 8.00 | 1.0677 | 0.06355 | 370.7 | 22.06 | 16.8 | -0.0698 |
| 10.00 | 1.2463 | 0.08341 | 432.7 | 28.96 | 14.9 | -0.0836 |
| 12.00 | 1.4131 | 0.10542 | 490.6 | 36.60 | 13.4 | -0.0969 |

## Geometria exportada
| Cuerpo | Triangulos | Area mojada [m2] | Volumen [L] | Cerrado |
|---|---|---|---|---|
| Ala principal | 4648 | 2.7956 | 44.61 | si |
| Cola en V | 768 | 0.3275 | 1.96 | si |
| Fuselaje | 1824 | 0.6200 | 18.50 | si |

Volumen de fuselaje segun el modelo: 18.55 L (debe coincidir con el volumen del cuerpo 'Fuselaje').

## Recordatorios
- Los cuerpos se superponen: unir en el CAD o con el wrapper de Fluent Meshing.
- No incluye helice ni spinner ni superficies deflectadas.
- Re ~ 5-7e5: usar un modelo con transicion (k-omega SST gamma-Re_theta) si se quiere comparar con AeroBuildup/NeuralFoil; un modelo totalmente turbulento da mas drag de perfil.
- Se puede correr medio modelo (y >= 0) con plano de simetria.
