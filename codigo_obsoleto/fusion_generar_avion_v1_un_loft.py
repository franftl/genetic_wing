"""
UAV FP -- generar el AVION completo en Fusion desde el diseno optimizado.
================================================================================
Correr DENTRO de Fusion (UTILITIES > ADD-INS > "Scripts and Add-Ins").

Es el equivalente de `fusion_generar_ala.py` para el avion (ala + fuselaje +
cola). Misma idea, misma division de trabajo:

  exportar_cad_avion.py  (afuera, con AeroSandbox)
      calcula las coordenadas 3D de cada seccion de cada superficie y el perfil
      de revolucion de cada fuselaje, con el MISMO marco que usa el solver, y
      lo escribe en `avion_geometry_cad.json`.

  este script  (adentro de Fusion)
      lee ese JSON y lo dibuja. No calcula geometria propia.

Si el CAD no coincide con lo analizado, es un bug en un solo lugar, no una
diferencia difusa entre dos implementaciones.

================================================================================
COMO USARLO
================================================================================
1. Afuera de Fusion, en la raiz del repo (con el kernel que tiene aerosandbox):

       python exportar_cad_avion.py --params <ganador.json> --topologia pod_boom

   Tiene que imprimir "Verificacion global: OK". Escribe avion_geometry_cad.json.

2. En Fusion: UTILITIES > ADD-INS > "Scripts and Add-Ins" > pestana "Scripts" >
   "+" > Python > un nombre (por ej. fusion_generar_avion). Fusion crea una
   carpeta con un .py de plantilla: reemplazar el CONTENIDO ENTERO de ese
   archivo por el de este. El archivo tiene que seguir llamandose igual que su
   carpeta.

3. "Run", con un documento de Diseno abierto.

El script busca el JSON en RUTA_JSON, despues al lado de si mismo; si no lo
encuentra abre un dialogo para elegirlo.

QUE DEJA EN EL DOCUMENTO (dentro de un componente "Avion optimizado")
  - Un sketch por seccion de cada superficie (spline cerrado del perfil, ya
    ubicado en el espacio) y un loft solido por superficie.
  - Las superficies simetricas se construyen del lado derecho y se espejan
    respecto del plano XZ (y = 0).
  - Cada fuselaje (fuselaje, gondola, viga) como solido de REVOLUCION de su
    perfil (x, radio): nariz y cola afinadas son splines, los tramos de radio
    constante son rectas.
  - Un punto en el CG de diseno.
  - Si UNIR_CUERPOS es True, todo unido en UN solo cuerpo (lo que hace falta
    para mallar en Ansys). Si la union falla, quedan los cuerpos separados y el
    script lo avisa: se pueden unir a mano con Modify > Combine.
  - Un mensaje final con el volumen y el area de cada cuerpo en el CAD contra
    lo esperado segun el modelo: si no coinciden (~1 %), algo salio mal.

Volver a correrlo con otro JSON crea un componente NUEVO; no pisa el anterior.
"""

import json
import math
import os
import traceback

import adsk.core
import adsk.fusion

# =============================================================================
# DONDE BUSCAR EL JSON DE GEOMETRIA
# =============================================================================
RUTA_JSON = r"C:\Users\felip\Desktop\UAV FP bateria\avion_geometry_cad.json"
NOMBRE_JSON = "avion_geometry_cad.json"

# La API de Fusion trabaja SIEMPRE en CENTIMETROS, sin importar las unidades que
# muestre la interfaz. El JSON viene en milimetros y la conversion pasa por
# aca, una sola vez.
MM_A_UNIDADES_API = 0.1

# Unir todo en un solo cuerpo al final (para mallar en Ansys).
UNIR_CUERPOS = True

# Cerrar el borde de fuga con un segmento recto si el perfil viene abierto.
TOL_CIERRE_MM = 1e-4

# Dos radios que difieren menos que esto se consideran iguales (tramo recto).
TOL_RADIO_MM = 1e-4


def _carpeta_de_este_script():
    try:
        return os.path.dirname(os.path.realpath(__file__))
    except NameError:
        return os.getcwd()


def _ruta_json(ui):
    candidatos = []
    if RUTA_JSON:
        candidatos.append(RUTA_JSON if os.path.isabs(RUTA_JSON)
                          else os.path.join(_carpeta_de_este_script(), RUTA_JSON))
    candidatos.append(os.path.join(_carpeta_de_este_script(), NOMBRE_JSON))
    for c in candidatos:
        if os.path.exists(c):
            return c

    dialogo = ui.createFileDialog()
    dialogo.title = "Elegi el JSON de geometria (avion_geometry_cad.json)"
    dialogo.filter = "JSON de geometria (*.json)"
    dialogo.isMultiSelectEnabled = False
    if dialogo.showOpen() != adsk.core.DialogResults.DialogOK:
        return None
    return dialogo.filename


def _nombre_seguro(texto):
    ok = "".join(c if (c.isalnum() or c in "_-") else "_" for c in texto)
    return ok[:24].strip("_") or "x"


def _punto(p_mm):
    """[x, y, z] en mm  ->  Point3D en unidades de la API (cm)."""
    return adsk.core.Point3D.create(p_mm[0] * MM_A_UNIDADES_API,
                                    p_mm[1] * MM_A_UNIDADES_API,
                                    p_mm[2] * MM_A_UNIDADES_API)


def _plano_por_tres_puntos(comp, p1_mm, p2_mm, p3_mm, nombre):
    """Plano de construccion que pasa EXACTAMENTE por tres puntos 3D (en mm).

    POR QUE NO SE CREAN ConstructionPoint CON UNA COORDENADA SUELTA. La version
    anterior hacia `ConstructionPointInput.setByPoint(Point3D)`: Fusion lo
    rechaza en un diseno con historial ("RuntimeError 3: Environment is not
    supported"), porque eso es geometria sin padre parametrico. Tampoco sirve
    `ConstructionPlaneInput.setByPlane(Plane)`, por lo mismo.

    LO QUE SI SE PUEDE HACER EN UN DISENO PARAMETRICO: un plano desplazado
    (`setByOffset`) de un plano base, un sketch sobre el, y un SketchPoint en
    ese sketch. Un SketchPoint SI es una entidad valida para `setByThreePoints`,
    y su posicion en el espacio queda (x, y) del sketch mas la altura del plano.
    Asi se llega a cualquier punto 3D: se agrupan los tres puntos por altura z,
    se crea un plano desplazado del plano XY por cada altura distinta, y en cada
    uno se ponen los puntos que le tocan."""
    puntos = [p1_mm, p2_mm, p3_mm]
    alturas = []
    for p in puntos:
        if not any(abs(p[2] - z) < 1e-6 for z in alturas):
            alturas.append(p[2])

    sketch_de = {}
    for k, z in enumerate(alturas):
        entrada = comp.constructionPlanes.createInput()
        entrada.setByOffset(comp.xYConstructionPlane,
                            adsk.core.ValueInput.createByReal(z * MM_A_UNIDADES_API))
        plano_z = comp.constructionPlanes.add(entrada)
        plano_z.name = "z%d_%s" % (k, nombre)
        plano_z.isLightBulbOn = False
        sk = comp.sketches.add(plano_z)
        sk.name = "pts%d_%s" % (k, nombre)
        sk.isLightBulbOn = False
        sketch_de[k] = sk

    entidades = []
    for p in puntos:
        k = [i for i, z in enumerate(alturas) if abs(p[2] - z) < 1e-6][0]
        sk = sketch_de[k]
        en_sketch = sk.modelToSketchSpace(_punto(p))
        en_sketch.z = 0.0          # el punto ya esta en el plano del sketch
        entidades.append(sk.sketchPoints.add(en_sketch))

    planos = comp.constructionPlanes
    entrada = planos.createInput()
    entrada.setByThreePoints(entidades[0], entidades[1], entidades[2])
    plano = planos.add(entrada)
    plano.name = "plano_%s" % nombre
    plano.isLightBulbOn = False
    return plano


def _tres_puntos_de_la_seccion(seccion):
    """Tres puntos NO alineados del plano de una seccion, elegidos para que dos
    compartan altura z (asi hacen falta solo dos planos desplazados, no tres).

    El plano de la seccion queda definido por su normal y por el origen (el
    borde de ataque). Se toma u = direccion horizontal contenida en el plano
    (normal x z) y v = normal x u. Si la normal es vertical (seccion horizontal)
    el plano ya es z = constante y u, v son los ejes x, y."""
    n = seccion["normal_seccion"]
    o = seccion["xyz_le_mm"]
    ux, uy = n[1], -n[0]                    # n x z^
    largo = math.hypot(ux, uy)
    if largo < 1e-6:
        u, v = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
    else:
        u = (ux / largo, uy / largo, 0.0)
        v = (n[1] * u[2] - n[2] * u[1], n[2] * u[0] - n[0] * u[2], n[0] * u[1] - n[1] * u[0])
        lv = math.sqrt(sum(c * c for c in v)) or 1.0
        v = tuple(c / lv for c in v)
    L = 100.0                               # mm; solo define el plano
    pa = [o[0], o[1], o[2]]
    pb = [o[0] + L * u[0], o[1] + L * u[1], o[2] + L * u[2]]
    pc = [o[0] + L * v[0], o[1] + L * v[1], o[2] + L * v[2]]
    return pa, pb, pc


# =============================================================================
# SUPERFICIES SUSTENTADORAS (ala, estabilizadores, deriva)
# =============================================================================
def _crear_sketch_seccion(comp, seccion, prefijo):
    """Un sketch con el perfil de una seccion, en su plano real del espacio.
    El plano se arma con `_plano_por_tres_puntos` (planos desplazados +
    SketchPoint, que es lo que acepta un diseno con historial); los puntos 3D
    del perfil pasan a 2D con modelToSketchSpace."""
    pts = seccion["puntos_mm"]
    n = len(pts)
    nombre_base = "%s_%02d_%s" % (prefijo, seccion["indice"], _nombre_seguro(seccion["perfil"]))
    pa, pb, pc = _tres_puntos_de_la_seccion(seccion)
    plano = _plano_por_tres_puntos(comp, pa, pb, pc, nombre_base)

    sketch = comp.sketches.add(plano)
    sketch.name = "perfil_%s" % nombre_base
    sketch.isComputeDeferred = True

    coleccion = adsk.core.ObjectCollection.create()
    for p in pts:
        coleccion.add(sketch.modelToSketchSpace(_punto(p)))
    sketch.sketchCurves.sketchFittedSplines.add(coleccion)

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
    """El perfil cerrado de mayor area de un sketch."""
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


def _loft(comp, sketches, nombre):
    entrada = comp.features.loftFeatures.createInput(
        adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    for sk in sketches:
        entrada.loftSections.add(_perfil_del_sketch(sk))
    entrada.isSolid = True
    entrada.isClosed = False
    feature = comp.features.loftFeatures.add(entrada)
    cuerpo = feature.bodies.item(0)
    cuerpo.name = nombre
    return cuerpo


def _espejar(comp, cuerpo):
    """Espeja un cuerpo respecto del plano XZ (y = 0) y lo une con el original."""
    cuerpos = adsk.core.ObjectCollection.create()
    cuerpos.add(cuerpo)
    entrada = comp.features.mirrorFeatures.createInput(cuerpos, comp.xZConstructionPlane)
    entrada.isCombine = True
    comp.features.mirrorFeatures.add(entrada)


def _crear_ala(comp, ala):
    nombre = _nombre_seguro(ala["nombre"])
    sketches = [_crear_sketch_seccion(comp, s, nombre) for s in ala["secciones"]]
    cuerpo = _loft(comp, sketches, nombre)
    if ala.get("simetrica", False):
        _espejar(comp, cuerpo)
    return nombre


# =============================================================================
# FUSELAJES (revolucion)
# =============================================================================
def _tramos_del_perfil(xr):
    """Parte el perfil (x, r) en tramos: rectas donde el radio es constante y
    splines donde cambia. Devuelve [("linea"|"spline", i0, i1), ...] con
    indices al arreglo de puntos; los tramos se tocan en sus extremos."""
    n = len(xr)
    plano = [abs(xr[i + 1][1] - xr[i][1]) < TOL_RADIO_MM for i in range(n - 1)]
    tramos, i = [], 0
    while i < n - 1:
        j = i
        while j < n - 1 and plano[j] == plano[i]:
            j += 1
        if plano[i]:
            tramos.append(("linea", i, j))
        elif j - i == 1:
            tramos.append(("linea", i, j))     # un solo segmento: recta
        else:
            tramos.append(("spline", i, j))
        i = j
    return tramos


def _crear_fuselaje(comp, fus):
    """Solido de revolucion del perfil (x, radio) alrededor de un eje paralelo a
    x, a la altura (y, z) = (eje_y_mm, eje_z_mm)."""
    if not fus.get("eje_constante", True):
        raise RuntimeError("El fuselaje '%s' no tiene el eje recto (y, z varian a lo largo de x): "
                           "este script solo hace fuselajes de eje recto." % fus["nombre"])
    nombre = _nombre_seguro(fus["nombre"])
    xr = fus["secciones_x_r_mm"]
    yc, zc = fus["eje_y_mm"], fus["eje_z_mm"]
    x0, x1 = xr[0][0], xr[-1][0]

    # Plano del perfil: contiene al eje y es paralelo a XZ (y = yc).
    plano = _plano_por_tres_puntos(comp, [x0, yc, zc], [x1, yc, zc], [x0, yc, zc + 50.0],
                                   "fus_%s" % nombre)
    sketch = comp.sketches.add(plano)
    sketch.name = "perfil_revolucion_%s" % nombre
    sketch.isComputeDeferred = True

    def sk_pt(x, r):
        return sketch.modelToSketchSpace(_punto([x, yc, zc + r]))

    lineas = sketch.sketchCurves.sketchLines
    for tipo, i0, i1 in _tramos_del_perfil(xr):
        if tipo == "linea":
            lineas.addByTwoPoints(sk_pt(*xr[i0]), sk_pt(*xr[i1]))
        else:
            col = adsk.core.ObjectCollection.create()
            for k in range(i0, i1 + 1):
                col.add(sk_pt(*xr[k]))
            sketch.sketchCurves.sketchFittedSplines.add(col)

    # Cierre contra el eje: tapa trasera, eje, y tapa delantera si el morro no
    # es una punta (radio 0).
    if xr[-1][1] > TOL_RADIO_MM:
        lineas.addByTwoPoints(sk_pt(x1, xr[-1][1]), sk_pt(x1, 0.0))
    eje = lineas.addByTwoPoints(sk_pt(x1, 0.0), sk_pt(x0, 0.0))
    if xr[0][1] > TOL_RADIO_MM:
        lineas.addByTwoPoints(sk_pt(x0, 0.0), sk_pt(x0, xr[0][1]))

    sketch.isComputeDeferred = False
    sketch.isLightBulbOn = False

    perfil = _perfil_del_sketch(sketch)
    revolve = comp.features.revolveFeatures
    entrada = revolve.createInput(perfil, eje, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    entrada.setAngleExtent(False, adsk.core.ValueInput.createByReal(2.0 * math.pi))
    feature = revolve.add(entrada)
    feature.bodies.item(0).name = nombre
    return nombre


# =============================================================================
def _cuerpo_por_nombre(comp, nombre):
    for i in range(comp.bRepBodies.count):
        c = comp.bRepBodies.item(i)
        if c.name == nombre:
            return c
    return None


def _comparar_con_esperado(comp, nombres_cad, esperado):
    """Volumen y area de cada cuerpo en el CAD contra lo esperado del modelo."""
    filas = []
    for nom_cad, nom_json in nombres_cad:
        c = _cuerpo_por_nombre(comp, nom_cad)
        e = esperado.get(nom_json)
        if c is None or e is None:
            continue
        vol_L = c.volume * 1e-3          # cm3 -> L
        area_m2 = c.area * 1e-4          # cm2 -> m2
        dv = 100.0 * (vol_L - e["volumen_L"]) / max(e["volumen_L"], 1e-9)
        da = 100.0 * (area_m2 - e["area_mojada_m2"]) / max(e["area_mojada_m2"], 1e-9)
        filas.append("  %-26s vol %7.2f L (esp. %7.2f, %+.1f%%)   area %.4f m2 (esp. %.4f, %+.1f%%)"
                     % (nom_json, vol_L, e["volumen_L"], dv, area_m2, e["area_mojada_m2"], da))
    return "\n".join(filas)


def _unir_todo(comp):
    """Une todos los cuerpos en uno. Devuelve (ok, mensaje)."""
    if comp.bRepBodies.count < 2:
        return True, ""
    objetivo = comp.bRepBodies.item(0)
    herramientas = adsk.core.ObjectCollection.create()
    for i in range(1, comp.bRepBodies.count):
        herramientas.add(comp.bRepBodies.item(i))
    entrada = comp.features.combineFeatures.createInput(objetivo, herramientas)
    entrada.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
    comp.features.combineFeatures.add(entrada)
    return True, ""


def _diagnostico(app, ui, diseno):
    """Texto con el estado del entorno de Fusion, para saber POR QUE una operacion
    de geometria de construccion es rechazada ("Environment is not supported")."""
    def _seguro(f):
        try:
            return f()
        except Exception as e:  # noqa: BLE001
            return "?(%s)" % e
    return (
        "  tipo de diseno ........ %s\n"
        "  espacio de trabajo .... %s\n"
        "  objeto en edicion ..... %s\n"
        "  producto activo ....... %s"
        % (_seguro(lambda: "PARAMETRICO (con historial)" if diseno.designType ==
                   adsk.fusion.DesignTypes.ParametricDesignType else "DIRECTO (sin historial)"),
           _seguro(lambda: ui.activeWorkspace.id),
           _seguro(lambda: type(app.activeEditObject).__name__ + " " +
                   str(getattr(app.activeEditObject, "name", ""))),
           _seguro(lambda: type(app.activeProduct).__name__))
    )


def _preparar_entorno(app, ui, diseno):
    """Deja a Fusion en un estado donde se puede crear geometria de construccion.

    La API rechaza puntos y planos de construccion con
    "RuntimeError 3: Environment is not supported" cuando:
      * el diseno esta en modo DIRECTO (sin historial): se pasa a PARAMETRICO;
      * el espacio de trabajo activo no es el de Diseno (por ejemplo Render,
        Simulacion o Dibujo): se activa el de Diseno.
    Cambiar a parametrico activa la captura de historial del documento: es lo
    normal para un modelo que se va a mantener, y no borra nada."""
    cambios = []
    try:
        if diseno.designType != adsk.fusion.DesignTypes.ParametricDesignType:
            diseno.designType = adsk.fusion.DesignTypes.ParametricDesignType
            cambios.append("diseno pasado a modo parametrico (historial activado)")
    except Exception:  # noqa: BLE001
        pass
    try:
        if ui.activeWorkspace.id != "FusionSolidEnvironment":
            ui.workspaces.itemById("FusionSolidEnvironment").activate()
            cambios.append("espacio de trabajo cambiado a Diseno")
    except Exception:  # noqa: BLE001
        pass
    return cambios


def run(context):
    ui = None
    app = None
    diseno = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface

        ruta = _ruta_json(ui)
        if not ruta:
            ui.messageBox("No elegiste ningun archivo, asi que no genero nada.\n\n"
                          "El JSON se genera afuera de Fusion con:\n"
                          "    python exportar_cad_avion.py --params <ganador.json> --topologia <top>")
            return
        with open(ruta, "r") as f:
            datos = json.load(f)

        meta = datos.get("meta", {})
        if meta.get("unidades") != "mm":
            ui.messageBox("El JSON dice unidades '%s' y este script espera 'mm'. Aborto antes de "
                          "generar un avion de la escala equivocada." % meta.get("unidades"))
            return
        alas = datos.get("alas", [])
        fuselajes = datos.get("fuselajes", [])
        if not alas or not fuselajes:
            ui.messageBox("El JSON no trae alas o fuselajes. No hay nada que generar.")
            return

        diseno = app.activeProduct
        if not isinstance(diseno, adsk.fusion.Design):
            ui.messageBox("Abri un documento de Diseno antes de correr el script.")
            return

        cambios_entorno = _preparar_entorno(app, ui, diseno)

        raiz = diseno.rootComponent
        ocurrencia = raiz.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        comp = ocurrencia.component
        comp.name = "Avion optimizado (%s)" % meta.get("topologia", "")

        # ACTIVAR la ocurrencia: sin esto, crear geometria de construccion dentro
        # de un componente nuevo falla con "Environment is not supported".
        if not ocurrencia.activate():
            ui.messageBox("No pude activar el componente nuevo. Proba cerrar y reabrir el "
                          "documento, o correr el script sin nada seleccionado en el navegador.")
            return

        nombres_cad = []
        for a in alas:
            nombres_cad.append((_crear_ala(comp, a), a["nombre"]))
        for fus in fuselajes:
            nombres_cad.append((_crear_fuselaje(comp, fus), fus["nombre"]))

        # Volumen y area de cada cuerpo ANTES de unirlos.
        esperado = meta.get("verificacion_en_fusion", {})
        comparacion = _comparar_con_esperado(comp, nombres_cad, esperado)

        # CG de diseno.
        if "cg_x_mm" in meta:
            sk_cg = comp.sketches.add(comp.xYConstructionPlane)
            sk_cg.name = "CG_diseno"
            sk_cg.sketchPoints.add(sk_cg.modelToSketchSpace(_punto([meta["cg_x_mm"], 0.0, 0.0])))

        estado_union = "Cuerpos sin unir (UNIR_CUERPOS = False)."
        if UNIR_CUERPOS:
            try:
                _unir_todo(comp)
                estado_union = "Todos los cuerpos unidos en uno (%d cuerpo/s)." % comp.bRepBodies.count
            except Exception:
                estado_union = ("NO pude unir los cuerpos (%d separados). Unirlos a mano: "
                                "Modify > Combine, operacion Join.\nDetalle: %s"
                                % (comp.bRepBodies.count, traceback.format_exc().splitlines()[-1]))

        ui.messageBox(
            ("Entorno ajustado: " + "; ".join(cambios_entorno) + "\n\n" if cambios_entorno else "") +
            "Avion generado: %s\n\n"
            "Envergadura: %.0f mm   MAC: %.1f mm   Superficie: %.4f m2\n"
            "CG de diseno: x = %.1f mm\n\n"
            "CAD contra lo esperado (por cuerpo, antes de unir):\n%s\n\n%s"
            % (meta.get("nombre_topologia", ""), meta.get("envergadura_mm", 0.0),
               meta.get("mac_mm", 0.0), meta.get("superficie_m2", 0.0),
               meta.get("cg_x_mm", 0.0), comparacion or "  (sin datos de comparacion)", estado_union)
        )

    except:  # noqa: E722 -- Fusion necesita el traceback completo en el dialogo
        if ui:
            try:
                diag = "\n\nEstado del entorno:\n" + _diagnostico(app, ui, diseno)
            except Exception:  # noqa: BLE001
                diag = ""
            ui.messageBox("Fallo:\n%s%s" % (traceback.format_exc(), diag))
