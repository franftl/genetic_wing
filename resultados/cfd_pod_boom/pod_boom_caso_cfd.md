# Caso CFD - pod_boom
_Fuselaje continuo (diámetro casi constante, afinado en la cola) + cola convencional_  |  escenario del modelo: viento ON, bateria ON

STL en **n/a**. Ejes: x hacia atras (del morro a la cola), y a la derecha, z hacia arriba.

## Condiciones de entrada
- Velocidad: 22.22 m/s (80 km/h), Mach 0.066
- rho = 1.0560 kg/m3, mu = 1.7433e-05 Pa.s, T = 278.7 K, p = 84476 Pa
- Re (MAC) = 5.822e+05   q = 260.74 Pa

## Referencias para los coeficientes
- S_ref = 1.2896 m2, c_ref (MAC) = 0.4325 m, b = 3.242 m (AR 8.15)
- Momentos respecto de xyz = [0.3975, 0.0, 0.0] m
- Masa 12.14 kg, peso 119.1 N

## Punto de calculo (crucero)
- alpha del modelo = 1.158 deg  ->  CL objetivo = 0.3543
- Ajustar alpha en el CFD hasta que CL coincida, y comparar CD a igual CL.

## Lo que predice el modelo (AeroBuildup) en ese punto
- CL = 0.3535   CD = 0.01764   L/D = 20.05
- D = 5.930 N  (perfil 4.061 N + inducido 1.869 N)

## Geometria exportada
| Cuerpo | Triangulos | Area mojada [m2] | Volumen [L] | Cerrado |
|---|---|---|---|---|
| Ala principal | 4600 | 2.7422 | 45.95 | si |
| Estabilizador horizontal | 768 | 0.1845 | 0.75 | si |
| Deriva | 384 | 0.1071 | 0.47 | si |
| Fuselaje | 1536 | 0.6308 | 24.15 | si |

Volumen de fuselaje segun el modelo: 24.22 L (debe coincidir con el volumen del cuerpo 'Fuselaje').

## Recordatorios
- Los cuerpos se superponen: unir en el CAD o con el wrapper de Fluent Meshing.
- No incluye helice ni spinner ni superficies deflectadas.
- Re ~ 5-7e5: usar un modelo con transicion (k-omega SST gamma-Re_theta) si se quiere comparar con AeroBuildup/NeuralFoil; un modelo totalmente turbulento da mas drag de perfil.
- Se puede correr medio modelo (y >= 0) con plano de simetria.
