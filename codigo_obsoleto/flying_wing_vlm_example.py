"""
UAV FP - Ejemplo minimo: evaluar la performance aerodinamica de un flying wing
usando AeroSandbox (VLM 3D) + NeuralFoil (polares 2D del perfil).

PUNTO CLAVE A ENTENDER:
- NeuralFoil por si solo SOLO evalua un perfil 2D (seccion de ala de
  envergadura infinita). Te da Cl/Cd/Cm de ESE PERFIL, no del avion.
- Para saber la performance del flying wing completo (con su envergadura,
  flecha, torsion/washout finitos) hace falta el metodo VLM (3D), que
  internamente usa NeuralFoil para conseguir las polares viscosas de cada
  seccion del ala y las combina en una geometria de envergadura finita.
- Por eso el flujo correcto es: 1) definir el perfil (Airfoil), que ya usa
  NeuralFoil por dentro cuando hace falta, 2) armar el ala/avion 3D con ese
  perfil (Wing, WingXSec, Airplane), 3) correr el VLM sobre esa geometria
  3D para obtener el CL/CD/Cm REAL del flying wing completo.

Instalar (una sola vez):
    pip install aerosandbox

Docs / tutorial VLM real de AeroSandbox:
https://github.com/peterdsharpe/AeroSandbox/blob/master/tutorial/06%20-%20Aerodynamics/01%20-%20AeroSandbox%203D%20Aerodynamics%20Tools/01%20-%20Vortex%20Lattice%20Method/01%20-%20Vortex%20Lattice%20Method.ipynb
"""

import aerosandbox as asb
import aerosandbox.numpy as np

# ---------------------------------------------------------------------------
# PASO 0 (opcional, solo para entender NeuralFoil): evaluar el perfil 2D
# solo, SIN armar ningun ala 3D todavia. Esto es util para comparar perfiles
# candidatos (ej. reflex airfoils tipo RG15, MH60, Eppler) antes de decidir
# cual usar en el flying wing.
# ---------------------------------------------------------------------------

wing_airfoil = asb.Airfoil("rg15")  # perfil reflex, tipico de flying wings

aero_2d = wing_airfoil.get_aero_from_neuralfoil(
    alpha=np.linspace(-5, 15, 50),  # barrido de angulo de ataque
    Re=3e5,                          # numero de Reynolds tipico de este UAV
)
# aero_2d["CL"], aero_2d["CD"], aero_2d["CM"] -> datos de UNA seccion 2D,
# NO son todavia la performance de tu flying wing real.

# ---------------------------------------------------------------------------
# PASO 1: armar la geometria 3D del flying wing (esto SI es tu avion real).
# symmetric=True significa que vos definis una sola mitad del ala (del
# centro a la punta) y AeroSandbox espeja automaticamente la otra mitad.
# ---------------------------------------------------------------------------

wing = asb.Wing(
    name="Flying Wing",
    symmetric=True,
    xsecs=[
        asb.WingXSec(  # seccion de RAIZ (centro del ala)
            xyz_le=[0, 0, 0],   # borde de ataque en el origen
            chord=0.40,          # cuerda en la raiz [m]
            twist=0,             # torsion de referencia (0 grados)
            airfoil=wing_airfoil,
        ),
        asb.WingXSec(  # seccion de PUNTA
            xyz_le=[0.30, 1.20, 0],  # el offset en x acá es lo que define la FLECHA (sweep)
            chord=0.18,               # cuerda en la punta [m] -> junto con la
                                       # de raiz define el TAPER RATIO
            twist=-4,                 # WASHOUT: torsion negativa en la punta.
                                       # Esto es lo que le da estabilidad
                                       # longitudinal a un flying wing (sin
                                       # cola). Es una de las variables que
                                       # despues va a optimizar el algoritmo.
            airfoil=wing_airfoil,
        ),
    ],
)

airplane = asb.Airplane(
    name="UAV FP Flying Wing",
    xyz_ref=[0.15, 0, 0],  # ubicacion aproximada del centro de gravedad
    wings=[wing],
)

# ---------------------------------------------------------------------------
# PASO 2: correr el analisis VLM sobre la geometria 3D completa. ESTO es
# la performance real del flying wing (ya incluye resistencia inducida por
# la envergadura finita, efecto de la flecha, etc).
# ---------------------------------------------------------------------------

vlm = asb.VortexLatticeMethod(
    airplane=airplane,
    op_point=asb.OperatingPoint(
        velocity=15,  # velocidad de crucero [m/s], ajustar a tu mision
        alpha=3,      # angulo de ataque [grados]
    ),
)

aero_3d = vlm.run()

print("Performance del flying wing completo (3D):")
print(f"  CL  = {aero_3d['CL']:.4f}")
print(f"  CD  = {aero_3d['CD']:.4f}")
print(f"  Cm  = {aero_3d['Cm']:.4f}")   # si es != 0, no esta en equilibrio de momentos
print(f"  L/D = {aero_3d['CL'] / aero_3d['CD']:.2f}")  # eficiencia aerodinamica / planeo

# ---------------------------------------------------------------------------
# PASO 3 (para la optimizacion): envolver todo esto en una funcion que
# reciba las variables de diseño (envergadura, taper, flecha, torsion,
# perfil) y devuelva una metrica de performance (ej. L/D). Esa funcion es
# la que despues le pasas a un algoritmo genetico (PyGAD/DEAP) o al
# optimizador por gradientes propio de AeroSandbox (asb.Opti).
# ---------------------------------------------------------------------------


def evaluar_diseño(envergadura, cuerda_raiz, cuerda_punta, flecha, torsion_punta):
    """Devuelve el L/D (glide ratio) de un flying wing dado un set de
    variables de diseño. Esto es lo que el optimizador va a llamar
    repetidamente con distintos valores."""
    ala = asb.Wing(
        symmetric=True,
        xsecs=[
            asb.WingXSec(xyz_le=[0, 0, 0], chord=cuerda_raiz, twist=0, airfoil=wing_airfoil),
            asb.WingXSec(
                xyz_le=[flecha, envergadura / 2, 0],
                chord=cuerda_punta,
                twist=torsion_punta,
                airfoil=wing_airfoil,
            ),
        ],
    )
    avion = asb.Airplane(wings=[ala])
    resultado = asb.VortexLatticeMethod(
        airplane=avion,
        op_point=asb.OperatingPoint(velocity=15, alpha=3),
    ).run()
    return resultado["CL"] / resultado["CD"]


if __name__ == "__main__":
    ld = evaluar_diseño(
        envergadura=2.4, cuerda_raiz=0.40, cuerda_punta=0.18, flecha=0.30, torsion_punta=-4
    )
    print(f"\nL/D de este diseño de ejemplo: {ld:.2f}")
