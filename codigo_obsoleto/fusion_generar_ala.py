"""
UAV FP -- generar el ala en Fusion desde el diseno optimizado.
================================================================================
Correr DENTRO de Fusion (UTILITIES > ADD-INS > "Scripts and Add-Ins").

REESCRITO 2026-08-28. La version anterior estaba obsoleta: seguia el esquema
viejo de 7 parametros (dos secciones, perfil leido de un .dat fijo) y no podia
consumir las salidas del notebook actual. Esta version no tiene ese problema
por construccion, y vale la pena entender por que.

================================================================================
LA IDEA: ESTE SCRIPT NO HACE GEOMETRIA
================================================================================
La tentacion natural es pasarle a Fusion los PARAMETROS (cuerda, flecha,
torsion, diedro) y rearmar el ala aca con trigonometria. Eso esta mal, y el
error es silencioso: alcanza con aplicar la torsion respecto de otro eje, o con
no reproducir el bisel que AeroSandbox mete en los quiebres, para que el solido
que se fabrica NO sea el que se analizo. La diferencia no se ve en la pantalla;
se descubre cuando el avion no vuela como decia el informe.

Asi que la division es tajante:

  optimizacion_ala/exportar_cad.py  (afuera, con AeroSandbox)
      calcula las coordenadas 3D de cada punto de cada seccion, usando el
      MISMO marco de referencia que usa el solver, y las escribe en un JSON.

  este script  (adentro de Fusion)
      lee esos puntos y los dibuja. No calcula nada.

Si el ala del CAD no coincide con la analizada, es un bug de una linea en un
solo lugar, no una discrepancia difusa entre dos implementaciones.

================================================================================
COMO USARLO
================================================================================
1. En el notebook, despues de optimizar (seccion 13):

       from optimizacion_ala.exportar_cad import exportar_json, verificar
       print(verificar(mejor.params()))          # todos los *_ok deben dar True
       exportar_json(mejor.params(), "wing_geometry_cad.json")

2. En Fusion: UTILITIES > ADD-INS > "Scripts and Add-Ins" > pestana "Scripts"
   > boton "+" > Python > ponerle un nombre. Fusion crea una carpeta con un
   .py de plantilla: reemplazar el CONTENIDO ENTERO de ese archivo por el de
   este. El archivo tiene que seguir llamandose igual que su carpeta.

3. Boton "Run", con un documento de Diseno abierto.

NO HACE FALTA EDITAR NADA. El script busca el JSON en la ruta fija de
RUTA_JSON y despues al lado de si mismo; si no lo encuentra, abre un dialogo
para que lo elijas a mano. Si igual queres cambiar la ruta fija, edita SOLO el
texto entre comillas de RUTA_JSON -- es una linea suelta a nivel del modulo, no
va adentro de ninguna funcion.

QUE DEJA EN EL DOCUMENTO
  - Un sketch por seccion (spline cerrado del perfil, ya ubicado en el espacio).
  - Un loft solido para el ala y otro para el winglet, unidos.
  - La semiala espejada respecto del plano XZ.
  - Un punto de construccion en el CG de diseno.
  - Todo dentro de un componente "Ala optimizada".

Volver a correrlo con otro JSON crea un componente NUEVO; no pisa el anterior.
Es a proposito: permite comparar dos disenos en el mismo documento.
"""

import json
import os
import traceback

import adsk.core
import adsk.fusion

# =============================================================================
# DONDE BUSCAR EL JSON DE GEOMETRIA
# =============================================================================
# No hace falta tocar nada de esto: si el archivo no aparece en ninguna de las
# rutas de abajo, el script abre un dialogo para que lo elijas a mano.
#
# Si igual queres fijar la ruta, editá SOLO el texto entre comillas de
# RUTA_JSON aca abajo. Es una linea suelta, a nivel del modulo: no la muevas
# adentro de ninguna funcion.
RUTA_JSON = r"C:\Users\felip\Documents\Claude\Projects\ITBA 2026 1C\Proyecto Final\UAV FP\wing_geometry_cad.json"

# Nombre del archivo, para buscarlo al lado de este script si RUTA_JSON falla.
NOMBRE_JSON = "wing_geometry_cad.json"

# La API de Fusion trabaja SIEMPRE en CENTIMETROS, sin importar las unidades
# que muestre la interfaz. Es la fuente clasica de modelos 10 veces mas grandes
# o mas chicos. El JSON viene en milimetros y la conversion pasa por aca, una
# sola vez, a proposito.
MM_A_UNIDADES_API = 0.1

# Cerrar el borde de fuga con un segmento recto cuando el perfil viene abierto.
# Por debajo de esta separacion se considera que el perfil ya cierra solo.
TOL_CIERRE_MM = 1e-4


def _carpeta_de_este_script():
    try:
        return os.path.dirname(os.path.realpath(__file__))
    except NameError:
        return os.getcwd()


def _ruta_json(ui):
    """Ubica el JSON de geometria.

    Busca en orden: la ruta fija de RUTA_JSON, y despues al lado de este mismo
    script. Si no lo encuentra en ninguna, abre un dialogo de archivo -- asi el
    script funciona sin tener que editar codigo, que es donde se rompe todo el
    mundo (incluido yo cuando escribi las instrucciones)."""
    candidatos = []
    if RUTA_JSON:
        candidatos.append(RUTA_JSON if os.path.isabs(RUTA_JSON)
                          else os.path.join(_carpeta_de_este_script(), RUTA_JSON))
    candidatos.append(os.path.join(_carpeta_de_este_script(), NOMBRE_JSON))

    for c in candidatos:
        if os.path.exists(c):
            return c

    dialogo = ui.createFileDialog()
    dialogo.title = "Elegi el JSON de geometria (wing_geometry_cad.json)"
    dialogo.filter = "JSON de geometria (*.json)"
    dialogo.isMultiSelectEnabled = False
    if dialogo.showOpen() != adsk.core.DialogResults.DialogOK:
        return None
    return dialogo.filename


def _nombre_seguro(texto):
    """Fusion rechaza algunos caracteres en los nombres de entidades. Los
    perfiles mezclados vienen con nombres como "80% mh80, 20% s5010", asi que
    hay que limpiarlos antes de usarlos."""
    ok = "".join(c if (c.isalnum() or c in "_-") else "_" for c in texto)
    return ok[:24].strip("_") or "perfil"


def _punto(p_mm):
    """[x, y, z] en mm  ->  Point3D en unidades de la API (cm)."""
    return adsk.core.Point3D.create(p_mm[0] * MM_A_UNIDADES_API,
                                    p_mm[1] * MM_A_UNIDADES_API,
                                    p_mm[2] * MM_A_UNIDADES_API)


def _punto_construccion(comp, p_mm, nombre):
    """Un ConstructionPoint real del documento, en las coordenadas dadas.

    Existe porque `ConstructionPlaneInput.setByThreePoints` exige que sus tres
    argumentos sean ENTIDADES del documento (un SketchPoint, un
    ConstructionPoint, un vertice) -- no acepta coordenadas sueltas. Pasarle un
    `Point3D` crudo es sintacticamente valido pero Fusion lo rechaza adentro.
    `ConstructionPointInput.setByPoint`, en cambio, SI acepta un Point3D crudo
    para crear el punto -- ese es el unico lugar donde conviene cruzar de
    coordenadas sueltas a entidad."""
    entrada = comp.constructionPoints.createInput()
    entrada.setByPoint(_punto(p_mm))
    punto = comp.constructionPoints.add(entrada)
    punto.name = nombre
    punto.isLightBulbOn = False
    return punto


def _crear_sketch_seccion(comp, seccion):
    """Un sketch con el perfil de una seccion, en su plano real del espacio.

    COMO SE UBICA EL PLANO, que es la parte delicada y tuvo dos intentos
    previos fallidos, vale la pena dejar registrado por que:

    1. `setByThreePoints(Point3D, Point3D, Point3D)` -- rechazado adentro con
       "InternalValidationError": los tres puntos tienen que ser ENTIDADES del
       documento, no coordenadas sueltas.
    2. `setByPlane(adsk.core.Plane.create(punto, normal))` -- geometria
       matematica pura, sin entidades. Debería haber funcionado, pero Fusion
       devuelve "RuntimeError 3: Environment is not supported": es una
       limitacion conocida de esa variante de la API en varias instalaciones,
       no algo que dependa de la geometria del ala.

    LA QUE FUNCIONA: crear tres `ConstructionPoint` reales (que SI son
    entidades) a partir de las mismas coordenadas, y pasarselos a
    `setByThreePoints`. Es un paso mas, pero es el camino documentado y
    portable -- no depende de variantes de API que algunas instalaciones no
    soportan. Los puntos se dejan ocultos en el arbol, no se borran: si se
    borraran, el plano (que depende parametricamente de ellos) quedaria con
    una referencia colgante.

    Una vez que el plano existe, un sketch de Fusion es plano: si uno le tira
    puntos 3D, los proyecta contra su plano y deforma la seccion sin avisar.
    Por eso los puntos 3D se convierten a coordenadas 2D de este sketch con
    `modelToSketchSpace` recien despues de que el plano ya pasa exactamente
    por ellos (el exportador verifica que son coplanares), asi la conversion
    es exacta y no hay proyeccion real."""
    pts = seccion["puntos_mm"]
    n = len(pts)
    nombre_base = "%02d_%s" % (seccion["indice"], _nombre_seguro(seccion["perfil"]))
    # Bien separados entre si (inicio, un tercio, dos tercios del contorno):
    # tres puntos casi alineados dan un plano mal condicionado.
    p1 = _punto_construccion(comp, pts[0], "pt_%s_a" % nombre_base)
    p2 = _punto_construccion(comp, pts[n // 3], "pt_%s_b" % nombre_base)
    p3 = _punto_construccion(comp, pts[2 * n // 3], "pt_%s_c" % nombre_base)

    planos = comp.constructionPlanes
    entrada = planos.createInput()
    entrada.setByThreePoints(p1, p2, p3)
    plano = planos.add(entrada)
    plano.name = "plano_%s" % nombre_base
    plano.isLightBulbOn = False

    sketch = comp.sketches.add(plano)
    sketch.name = "perfil_%s" % nombre_base
    # Diferir el calculo mientras se agregan cientos de puntos: sin esto Fusion
    # resuelve las restricciones del sketch en cada punto y tarda muchisimo.
    sketch.isComputeDeferred = True

    coleccion = adsk.core.ObjectCollection.create()
    for p in pts:
        coleccion.add(sketch.modelToSketchSpace(_punto(p)))

    sketch.sketchCurves.sketchFittedSplines.add(coleccion)

    # Cerrar el borde de fuga si el perfil viene abierto (los perfiles reales
    # de la base UIUC casi siempre tienen espesor finito en el borde de fuga).
    d = sum((a - b) ** 2 for a, b in zip(pts[0], pts[-1])) ** 0.5
    if d > TOL_CIERRE_MM:
        sketch.sketchCurves.sketchLines.addByTwoPoints(
            sketch.modelToSketchSpace(_punto(pts[-1])),
            sketch.modelToSketchSpace(_punto(pts[0])),
        )

    sketch.isComputeDeferred = False
    sketch.isLightBulbOn = False
    return sketch


def _perfil_del_sketch(sketch):
    """El perfil cerrado de un sketch. Si hay mas de uno, se toma el de mayor
    area: significa que el spline se auto-intersecto en algun lado y dejo un
    lazo parasito chico, y el bueno es el grande."""
    if sketch.profiles.count == 0:
        raise RuntimeError(
            "El sketch '%s' no cerro ningun perfil. Suele pasar cuando el borde "
            "de fuga quedo abierto o el spline se cruzo a si mismo." % sketch.name
        )
    mejor, area_mejor = None, -1.0
    for i in range(sketch.profiles.count):
        pr = sketch.profiles.item(i)
        a = pr.areaProperties(adsk.fusion.CalculationAccuracy.LowCalculationAccuracy).area
        if a > area_mejor:
            mejor, area_mejor = pr, a
    return mejor


def _loft(comp, sketches, nombre, operacion):
    """Loft solido a traves de una lista de sketches consecutivos."""
    entrada = comp.features.loftFeatures.createInput(operacion)
    for sk in sketches:
        entrada.loftSections.add(_perfil_del_sketch(sk))
    entrada.isSolid = True
    # isClosed = False: la superficie no vuelve sobre si misma (no es un toro).
    entrada.isClosed = False
    feature = comp.features.loftFeatures.add(entrada)
    if feature.bodies.count:
        feature.bodies.item(0).name = nombre
    return feature


def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface

        ruta = _ruta_json(ui)
        if not ruta:
            ui.messageBox(
                "No elegiste ningun archivo, asi que no genero nada.\n\n"
                "El JSON se genera desde el notebook con:\n"
                "    from optimizacion_ala.exportar_cad import exportar_json\n"
                "    exportar_json(mejor.params(), 'wing_geometry_cad.json')"
            )
            return

        with open(ruta, "r") as f:
            datos = json.load(f)

        meta = datos.get("meta", {})
        if meta.get("unidades") != "mm":
            ui.messageBox("El JSON dice unidades '%s' y este script espera 'mm'. "
                          "Aborto antes de generar un ala de la escala equivocada."
                          % meta.get("unidades"))
            return

        secciones_ala = datos["secciones_ala"]
        secciones_wl = datos.get("secciones_winglet", [])
        if len(secciones_ala) < 2:
            ui.messageBox("El JSON trae menos de 2 secciones de ala. No hay nada que loftear.")
            return

        diseno = app.activeProduct
        if not isinstance(diseno, adsk.fusion.Design):
            ui.messageBox("Abri un documento de Diseno antes de correr el script.")
            return

        raiz = diseno.rootComponent
        ocurrencia = raiz.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        comp = ocurrencia.component
        comp.name = "Ala optimizada"

        # ACTIVAR la ocurrencia recien creada. Sin esto, crear geometria de
        # construccion (puntos, planos) DENTRO de un componente nuevo falla
        # con "RuntimeError 3: Environment is not supported" -- el error que
        # tiraron los dos intentos anteriores, con metodos de API distintos.
        # El comun denominador de los dos fallos no era el metodo elegido: era
        # que el componente nunca quedaba activado como destino de edicion.
        # `addNewComponent` crea el componente pero no lo activa solo; hace
        # falta pedirselo de forma explicita.
        if not ocurrencia.activate():
            ui.messageBox(
                "No pude activar el componente nuevo ('Ala optimizada'). "
                "Probá cerrar y reabrir el documento, o correr el script con "
                "el navegador del modelo (arbol de la izquierda) sin nada "
                "seleccionado."
            )
            return

        # --- Perfiles ----------------------------------------------------
        sk_ala = [_crear_sketch_seccion(comp, s) for s in secciones_ala]
        sk_wl = [_crear_sketch_seccion(comp, s) for s in secciones_wl]

        # --- Solidos -----------------------------------------------------
        # Dos lofts y no uno solo: cuando `winglet_radio` vale 0, la union
        # ala-winglet es un quiebre vivo, y un loft unico que atraviesa un
        # quiebre asi sale retorcido. Los dos lofts comparten la seccion de la
        # punta del ala, asi que la cara es coincidente y la union es limpia.
        nuevo = adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        _loft(comp, sk_ala, "semiala", nuevo)
        if len(sk_wl) >= 2:
            _loft(comp, sk_wl, "winglet", adsk.fusion.FeatureOperations.JoinFeatureOperation)

        # --- Espejar la semiala ------------------------------------------
        # El plano XZ es el plano y = 0, que es el de simetria del avion.
        cuerpos = adsk.core.ObjectCollection.create()
        for i in range(comp.bRepBodies.count):
            cuerpos.add(comp.bRepBodies.item(i))
        entrada_esp = comp.features.mirrorFeatures.createInput(cuerpos, comp.xZConstructionPlane)
        entrada_esp.isCombine = True
        comp.features.mirrorFeatures.add(entrada_esp)

        # --- CG de diseno ------------------------------------------------
        # Se deja marcado porque es el dato que hay que respetar al ubicar la
        # bateria y la carga util: todo el analisis de estabilidad supone el CG
        # exactamente aca. Un ala volante con el CG corrido unos milimetros es
        # otro avion.
        if "cg_x_mm" in meta:
            sk_cg = comp.sketches.add(comp.xYConstructionPlane)
            sk_cg.name = "CG_diseno"
            sk_cg.sketchPoints.add(
                sk_cg.modelToSketchSpace(_punto([meta["cg_x_mm"], 0.0, 0.0]))
            )

        ui.messageBox(
            "Ala generada.\n\n"
            "Envergadura del ala: %.0f mm\n"
            "Envergadura con winglets: %.0f mm\n"
            "MAC: %.1f mm    Superficie: %.4f m2\n"
            "CG de diseno: x = %.1f mm (%.0f%% de la MAC)\n"
            "Secciones: %d de ala + %d de winglet\n"
            "Score del diseno: %s"
            % (meta.get("envergadura_ala_mm", 0.0),
               meta.get("envergadura_total_con_winglets_mm", 0.0),
               meta.get("mac_mm", 0.0), meta.get("superficie_m2", 0.0),
               meta.get("cg_x_mm", 0.0), 100 * meta.get("cg_frac_mac", 0.0),
               len(secciones_ala), len(secciones_wl),
               meta.get("score"))
        )

    except:  # noqa: E722 -- Fusion necesita el traceback completo en el dialogo
        if ui:
            ui.messageBox("Fallo:\n%s" % traceback.format_exc())
