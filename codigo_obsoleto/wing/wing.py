"""
UAV FP - Script para Fusion (correr DENTRO de Fusion, via Scripts and Add-Ins)
================================================================================

IMPORTANTE - por que este script vive separado del notebook de Python:
La API de Fusion solo corre adentro del proceso de Fusion, disparada desde
el panel "Scripts and Add-Ins" (o depurada con la extension de VS Code que
provee Autodesk). No hay forma soportada de llamar a esta API desde un
kernel de Jupyter externo ni desde un interprete de Python corriendo afuera
de Fusion. Por eso separamos: el notebook (AeroSandbox/NeuralFoil) corre
afuera y decide el diseno; ESTE script corre adentro de Fusion y genera la
geometria a partir de esos numeros.

COMO INSTALARLO EN FUSION:
1. Abri Fusion > pestana UTILITIES > panel "ADD-INS" > boton "Scripts and
   Add-Ins".
2. En la pestana "Scripts", boton "+" (Create), elegi Python, dale un
   nombre (ej. "generar_ala").
3. Fusion crea una carpeta con un .py de plantilla -- reemplaza el
   contenido entero por este archivo (o copia este archivo a esa carpeta).
4. Corre el script con el boton "Run" del mismo panel.

QUE HACE:
1. La primera vez que corre, crea los User Parameters de Fusion listados
   en DEFAULT_PARAMS (los vas a ver en Modificar > Cambiar Parametros).
2. Lee el VALOR ACTUAL de esos parametros (por si ya los editaste a mano
   en Fusion despues de la primera corrida).
3. Lee el perfil del ala desde un archivo .dat (formato Selig, el mismo
   que usa AeroSandbox/XFLR5/airfoiltools.com).
4. Calcula la geometria 3D de la seccion de raiz y de punta (aplicando
   escala por cuerda, rotacion por torsion/washout, desplazamiento por
   flecha y diedro) y arma el solido con un Loft entre ambas.

PARA REGENERAR LA GEOMETRIA DESPUES DE CAMBIAR UN PARAMETRO:
Cambia el valor en el dialogo de Fusion (Modificar > Cambiar Parametros) y
volve a correr este script. No se actualiza solo/en vivo -- correrlo de
nuevo tarda pocos segundos y es mas simple/confiable que encadenar
expresiones nativas de Fusion para todo (torsion, flecha y diedro a la vez).
"""

import adsk.core
import adsk.fusion
import traceback
import math
import os

# =============================================================================
# CONFIGURACION -- editar estas dos cosas segun tu caso
# =============================================================================

# Ruta al archivo de coordenadas del perfil (.dat, formato Selig: primera
# linea = nombre del perfil, despues pares "x y" normalizados a cuerda 1,
# empezando y terminando cerca del borde de fuga, dando la vuelta por el
# extrados y despues el intrados).
AIRFOIL_DAT_PATH = r"C:\Users\felip\Documents\Claude\Projects\ITBA 2026 1C\Proyecto Final\UAV FP\rg15.dat"

# Nombres, valor/expresion por defecto, unidades y comentario de los User
# Parameters que este script crea en Fusion la primera vez. Si ya existen
# (porque los creaste vos o corriste el script antes), NO se pisan --  se
# usa el valor que ya tengan en el documento.
DEFAULT_PARAMS = {
    "envergadura":   ("1200 mm", "mm", "Semi-envergadura, de la raiz a la punta"),
    "cuerda_raiz":   ("400 mm", "mm", "Cuerda en la seccion de raiz"),
    "cuerda_punta":  ("180 mm", "mm", "Cuerda en la seccion de punta"),
    "flecha":        ("300 mm", "mm", "Desplazamiento del borde de ataque en la punta (sweep)"),
    "torsion_punta": ("-4 deg", "deg", "Washout: torsion de la punta respecto a la raiz"),
    "diedro":        ("0 deg", "deg", "Angulo de diedro"),
}

PIVOTE_TORSION_FRAC = 0.25  # rotar la torsion alrededor del 25% de la cuerda (convencion habitual)


# =============================================================================
# Funciones auxiliares
# =============================================================================

def leer_perfil_dat(path):
    """Lee un archivo .dat formato Selig y devuelve una lista de tuplas
    (x, y) normalizadas a cuerda unitaria (0 a 1)."""
    puntos = []
    with open(path, "r") as f:
        lineas = f.readlines()
    for linea in lineas[1:]:  # la primera linea suele ser el nombre del perfil
        partes = linea.split()
        if len(partes) == 2:
            try:
                x, y = float(partes[0]), float(partes[1])
                puntos.append((x, y))
            except ValueError:
                continue
    return puntos


def crear_o_leer_parametro(userParams, nombre, expresion_default, unidades, comentario):
    existente = userParams.itemByName(nombre)
    if existente:
        return existente
    valueInput = adsk.core.ValueInput.createByString(expresion_default)
    return userParams.add(nombre, valueInput, unidades, comentario)


def seccion_a_puntos_2d(perfil_normalizado, cuerda_cm, torsion_deg, offset_u_cm, offset_v_cm):
    """Escala el perfil por la cuerda, lo rota por la torsion (alrededor de
    PIVOTE_TORSION_FRAC de la cuerda) y lo desplaza por (offset_u, offset_v)
    -- offset_u es la direccion de la cuerda (para la flecha), offset_v es
    la direccion "vertical" dentro del plano de esa seccion (para el
    diedro). Devuelve puntos 2D locales (u, v) en cm, todavia sin el
    componente de envergadura (eso lo pone la posicion del plano)."""
    torsion_rad = math.radians(torsion_deg)
    cos_t, sin_t = math.cos(torsion_rad), math.sin(torsion_rad)
    pivote_u = PIVOTE_TORSION_FRAC * cuerda_cm

    puntos_uv = []
    for x_norm, y_norm in perfil_normalizado:
        u = x_norm * cuerda_cm
        v = y_norm * cuerda_cm  # espesor del perfil

        # rotar alrededor del punto de pivote
        du, dv = u - pivote_u, v
        u_rot = pivote_u + du * cos_t - dv * sin_t
        v_rot = du * sin_t + dv * cos_t

        puntos_uv.append((u_rot + offset_u_cm, v_rot + offset_v_cm))
    return puntos_uv


def crear_sketch_perfil(rootComp, plano, nombre, puntos_uv, y_cm):
    """Crea un sketch en el plano dado con una spline pasando por los
    puntos (u, v) ya transformados, ubicados en la posicion Y = y_cm
    (la envergadura de esa seccion)."""
    sketch = rootComp.sketches.add(plano)
    sketch.name = nombre

    coleccion = adsk.core.ObjectCollection.create()
    for u, v in puntos_uv:
        coleccion.add(adsk.core.Point3D.create(u, y_cm, v))
    sketch.sketchCurves.sketchFittedSplines.add(coleccion)

    return sketch


# =============================================================================
# Script principal
# =============================================================================

def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            ui.messageBox("Abri o crea un diseno de Fusion antes de correr este script.")
            return

        rootComp = design.rootComponent
        userParams = design.userParameters

        # 1. Crear los parametros si no existen todavia
        for nombre, (expr, unidades, comentario) in DEFAULT_PARAMS.items():
            crear_o_leer_parametro(userParams, nombre, expr, unidades, comentario)

        # 2. Leer los valores actuales (la API interna siempre da longitudes
        # en cm y angulos en radianes, sin importar las unidades mostradas
        # en el dialogo de Fusion)
        envergadura_cm   = userParams.itemByName("envergadura").value
        cuerda_raiz_cm   = userParams.itemByName("cuerda_raiz").value
        cuerda_punta_cm  = userParams.itemByName("cuerda_punta").value
        flecha_cm        = userParams.itemByName("flecha").value
        torsion_punta_deg = math.degrees(userParams.itemByName("torsion_punta").value)
        diedro_deg        = math.degrees(userParams.itemByName("diedro").value)

        # 3. Leer el perfil
        if not os.path.exists(AIRFOIL_DAT_PATH):
            ui.messageBox("No encontre el archivo de perfil en:\n{}".format(AIRFOIL_DAT_PATH))
            return
        perfil = leer_perfil_dat(AIRFOIL_DAT_PATH)
        if len(perfil) < 10:
            ui.messageBox("El archivo de perfil parece invalido (muy pocos puntos).")
            return

        # 4. Seccion de RAIZ: sin torsion, sin flecha, sin diedro, Y = 0
        puntos_raiz = seccion_a_puntos_2d(perfil, cuerda_raiz_cm, torsion_deg=0, offset_u_cm=0, offset_v_cm=0)

        # 5. Seccion de PUNTA: con torsion, flecha (offset_u) y diedro (offset_v)
        offset_v_diedro = envergadura_cm * math.tan(math.radians(diedro_deg))
        puntos_punta = seccion_a_puntos_2d(
            perfil,
            cuerda_punta_cm,
            torsion_deg=torsion_punta_deg,
            offset_u_cm=flecha_cm,
            offset_v_cm=offset_v_diedro,
        )

        # 6. Crear los sketches. El de raiz va en el plano base (Y=0); para
        # la punta creamos un plano paralelo, desplazado en Y por la
        # envergadura -- asi los puntos (u, y_fijo, v) quedan realmente
        # coplanares con el plano donde vive cada sketch.
        planoRaiz = rootComp.xZConstructionPlane

        planos = rootComp.constructionPlanes
        planeInput = planos.createInput()
        planeInput.setByOffset(planoRaiz, adsk.core.ValueInput.createByReal(envergadura_cm))
        planoPunta = planos.add(planeInput)
        planoPunta.name = "Plano punta (envergadura)"

        sketchRaiz = crear_sketch_perfil(rootComp, planoRaiz, "Perfil raiz", puntos_raiz, y_cm=0)
        sketchPunta = crear_sketch_perfil(rootComp, planoPunta, "Perfil punta", puntos_punta, y_cm=envergadura_cm)

        # 7. Loft entre las dos secciones
        loftFeats = rootComp.features.loftFeatures
        loftInput = loftFeats.createInput(adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        loftInput.loftSections.add(sketchRaiz.profiles.item(0))
        loftInput.loftSections.add(sketchPunta.profiles.item(0))
        loftInput.isSolid = True
        loftFeats.add(loftInput)

        ui.messageBox(
            "Ala generada.\n\n"
            "envergadura = {:.1f} mm\ncuerda_raiz = {:.1f} mm\ncuerda_punta = {:.1f} mm\n"
            "flecha = {:.1f} mm\ntorsion_punta = {:.1f} deg\ndiedro = {:.1f} deg\n\n"
            "Para cambiar el diseno: edita estos valores en Modificar > Cambiar Parametros "
            "y volve a correr este script.".format(
                envergadura_cm * 10, cuerda_raiz_cm * 10, cuerda_punta_cm * 10,
                flecha_cm * 10, torsion_punta_deg, diedro_deg,
            )
        )

    except:
        if ui:
            ui.messageBox("Fallo:\n{}".format(traceback.format_exc()))
