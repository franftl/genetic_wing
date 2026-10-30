# Caso CFD - v_tail
_Ala + fuselaje + cola en V_  |  escenario del modelo: viento ON, bateria ON

STL en **mm**. Ejes: x hacia atras (del morro a la cola), y a la derecha, z hacia arriba.

## Condiciones de entrada
- Velocidad: 22.22 m/s (80 km/h), Mach 0.066
- rho = 1.0560 kg/m3, mu = 1.7433e-05 Pa.s, T = 278.7 K, p = 84476 Pa
- Re (MAC) = 5.195e+05   q = 260.74 Pa

## Referencias para los coeficientes
- S_ref = 1.2134 m2, c_ref (MAC) = 0.3859 m, b = 3.361 m (AR 9.31)
- Momentos respecto de xyz = [0.6343, 0.0, 0.0] m
- Masa 11.64 kg, peso 114.2 N

## Punto de calculo (crucero)
- alpha del modelo = 1.213 deg  ->  CL objetivo = 0.3608
- Ajustar alpha en el CFD hasta que CL coincida, y comparar CD a igual CL.

## Lo que predice el modelo (AeroBuildup) en ese punto
- CL = 0.3610   CD = 0.01766   L/D = 20.44
- D = 5.587 N  (perfil 3.852 N + inducido 1.735 N)

## Sustentacion y resistencia del modelo en funcion del angulo de ataque
AeroBuildup a 22.22 m/s, mismas condiciones. Fuerzas del avion COMPLETO (si el CFD es medio modelo, comparar contra la mitad).

| alpha [deg] | CL | CD | L [N] | D [N] | L/D | Cm |
|---|---|---|---|---|---|---|
| -4.00 | -0.1461 | 0.01754 | -46.2 | 5.55 | -8.3 | 0.0366 |
| -2.00 | 0.0475 | 0.01390 | 15.0 | 4.40 | 3.4 | 0.0233 |
| 0.00 | 0.2399 | 0.01475 | 75.9 | 4.67 | 16.3 | 0.0060 |
| 1.21 | 0.3610 | 0.01766 | 114.2 | 5.59 | 20.4 | -0.0063 |  <- crucero
| 2.00 | 0.4399 | 0.02041 | 139.2 | 6.46 | 21.6 | -0.0148 |
| 4.00 | 0.6391 | 0.03004 | 202.2 | 9.51 | 21.3 | -0.0385 |
| 6.00 | 0.8336 | 0.04316 | 263.8 | 13.65 | 19.3 | -0.0612 |
| 8.00 | 1.0221 | 0.05948 | 323.4 | 18.82 | 17.2 | -0.0795 |
| 10.00 | 1.2041 | 0.07887 | 381.0 | 24.95 | 15.3 | -0.0951 |
| 12.00 | 1.3754 | 0.10073 | 435.2 | 31.87 | 13.7 | -0.1107 |

## Geometria exportada
| Cuerpo | Triangulos | Area mojada [m2] | Volumen [L] | Cerrado |
|---|---|---|---|---|
| Ala principal | 4260 | 2.5504 | 39.63 | si |
| Cola en V | 768 | 0.2743 | 1.41 | si |
| Fuselaje | 1824 | 0.6390 | 19.97 | si |

Volumen de fuselaje segun el modelo: 20.03 L (debe coincidir con el volumen del cuerpo 'Fuselaje').

## Recordatorios
- Los cuerpos se superponen: unir en el CAD o con el wrapper de Fluent Meshing.
- No incluye helice ni spinner ni superficies deflectadas.
- Re ~ 5-7e5: usar un modelo con transicion (k-omega SST gamma-Re_theta) si se quiere comparar con AeroBuildup/NeuralFoil; un modelo totalmente turbulento da mas drag de perfil.
- Se puede correr medio modelo (y >= 0) con plano de simetria.
