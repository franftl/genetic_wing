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

       python herramientas/exportar_cad_avion.py --params <ganador.json> --topologia pod_boom

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

================================================================================
QUE HACE PARA QUE LA GEOMETRIA SEA MALLABLE (v2)
================================================================================
Un avion que "se ve bien" en Fusion puede no mallar en Ansys: Fluent Meshing
protesta por autointersecciones, "Front could not be closed" o "Duplicate front
edge". Las causas que este script evita:

  1. UN LOFT POR TRAMO. Un solo loft por las 12 secciones del ala obliga a Fusion a
     interpolar una superficie SUAVE a traves de todas; con secciones muy
     desparejas (175 mm entre unas, 26 mm entre las ultimas, con ~30 grados de giro
     en cada tramo) la superficie hace sobreimpulso y se cruza cerca del borde de
     fuga de la punta. El solver de AeroSandbox interpola LINEALMENTE entre
     secciones, asi que un loft de dos secciones por tramo es la misma geometria
     que se analizo y no puede hacer sobreimpulso. Los tramos se unen despues.
  2. BORDE DE FUGA CON ESPESOR MINIMO (ESPESOR_TE_MM). Un borde de fuga de menos de
     ~1 mm obliga al mallador a celdas de decimas de mm. Se lleva el espesor a un
     valor uniforme en todas las secciones. Efecto sobre el drag: resistencia de
     base chica (del orden de 1-3 % del CD total); si se quiere comparar contra
     el modelo, ponerlo en None para no tocar el espesor del JSON.
  3. CHEQUEO DE SECCIONES QUE SE CRUZAN. Si dos secciones vecinas se atraviesan
     dentro de su contorno, el loft entre ellas se pliega sobre si mismo. Si pasa
     en la ultima seccion de una superficie, se descarta esa seccion y se avisa; si
     pasa en el interior, el script se detiene y dice en cual.
  4. PUNTOS REPETIDOS: se eliminan los puntos consecutivos casi coincidentes de
     cada perfil (un spline con puntos duplicados genera aristas de largo cero).
  5. ESPEJO SIN FUSION. Las mitades se espejan SIN combinar: las raices quedan
     dentro del fuselaje y se unen todas juntas al final, en vez de pelear
     con superficies casi coincidentes en el plano de simetria.
  6. UNION ROBUSTA: si "unir todo" falla, se prueba cuerpo por cuerpo y se dice
     cual es el que no se deja unir.
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
RUTA_JSON = r"C:\Users\felip\Desktop\UAV FP bateria\resultados\avion_geometry_cad.json"
NOMBRE_JSON = "avion_geometry_cad.json"

# La API de Fusion trabaja SIEMPRE en CENTIMETROS, sin importar las unidades que
# muestre la interfaz. El JSON viene en milimetros y la conversion pasa por
# aca, una sola vez.
MM_A_UNIDADES_API = 0.1

# Unir todo en un solo cuerpo al final (para mallar en Ansys).
UNIR_CUERPOS = True

# Espesor de borde de fuga que se impone a TODAS las secciones, en mm. El JSON
# trae 0.6-1.1 mm segun la seccion. None = no tocarlo. Mas grueso = malla mas facil
# (el mallador necesita ~3 celdas en el espesor) pero mas resistencia de base.
ESPESOR_TE_MM = 2.0   # = manufactura.ESPESOR_BORDE_FUGA_M del modelo (el JSON ya trae 2 mm)

# Un loft por tramo entre secciones vecinas (recomendado). False = un solo loft
# por todas las secciones (lo que hacia la version anterior).
# Radio de los dos vertices del borde de fuga romo [mm]. Redondea las esquinas del
# espesor de 2 mm (extrados-cara y cara-intrados) con arcos tangentes, asi el
# contorno del perfil no tiene aristas vivas en el borde de fuga. None = sin redondear.
RADIO_BORDE_FUGA_MM = None   # sin redondeo: borde de fuga plano de 2 mm (ESPESOR_TE_MM)
LOFT_POR_TRAMOS = False   # False = UN loft por superficie (pedido de Felipe); True = un loft por tramo

# Tramos mas cortos que esto (mm, distancia entre bordes de ataque de dos secciones
# consecutivas) se consideran degenerados: la ultima seccion se descarta si el
# tramo final es mas corto. 0 = no descartar nada por esta causa.
TRAMO_MIN_MM = 0.0

# Dos puntos consecutivos de un perfil mas cerca que esto (mm) se funden en uno.
TOL_PUNTOS_MM = 1e-3

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
# PREPARACION DE LA GEOMETRIA (python puro: no toca Fusion)
# =============================================================================
def _sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _add(a, b):
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def _mul(a, k):
    return [a[0] * k, a[1] * k, a[2] * k]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _norma(a):
    return math.sqrt(_dot(a, a))


def _unit(a):
    n = _norma(a)
    return [c / n for c in a] if n > 1e-12 else [0.0, 0.0, 0.0]


def _limpiar_puntos(pts):
    """Saca los puntos consecutivos casi coincidentes (un spline con puntos
    repetidos genera aristas de largo cero). Conserva primero y ultimo."""
    out = [pts[0]]
    for p in pts[1:-1]:
        if _norma(_sub(p, out[-1])) > TOL_PUNTOS_MM:
            out.append(p)
    if _norma(_sub(pts[-1], out[-1])) > TOL_PUNTOS_MM or len(out) == 1:
        out.append(pts[-1])
    return out


def _ajustar_borde_de_fuga(seccion, espesor_mm):
    """Lleva el espesor del borde de fuga de la seccion a `espesor_mm`.

    El perfil viene del borde de fuga superior (primer punto), da la vuelta por el
    borde de ataque y vuelve por el inferior (ultimo punto). Se desplaza cada punto
    en la direccion del espesor, proporcional a su distancia al borde de ataque, y
    con signo + en el extrados y - en el intrados (la misma apertura lineal que usa
    el exportador, ahora hasta el espesor pedido). La direccion del espesor sale de
    los propios puntos: de TE inferior a TE superior."""
    pts = seccion["puntos_mm"]
    le = seccion["xyz_le_mm"]
    n = _unit(seccion["normal_seccion"])
    gap_vec = _sub(pts[0], pts[-1])
    gap = _norma(gap_vec)
    te = _mul(_add(pts[0], pts[-1]), 0.5)
    cuerda = _sub(te, le)
    cuerda = _sub(cuerda, _mul(n, _dot(cuerda, n)))          # dentro del plano
    largo = _norma(cuerda)
    if largo < 1e-6:
        return 0.0
    xg = _unit(cuerda)
    zg = _unit(_cross(xg, n))                                 # espesor, hacia el extrados
    if gap > 1e-9 and _dot(gap_vec, zg) < 0:
        zg = _mul(zg, -1.0)                                   # el primer punto es el extrados
    xs = [_dot(_sub(p, le), xg) for p in pts]
    i_le = xs.index(min(xs))
    dif = espesor_mm - gap
    nuevos = []
    for i, p in enumerate(pts):
        frac = max(0.0, min(1.0, xs[i] / largo))
        signo = 1.0 if i <= i_le else -1.0
        nuevos.append(_add(p, _mul(zg, signo * 0.5 * dif * frac)))
    seccion["puntos_mm"] = nuevos
    return dif


def _intervalos_en_recta(pts, n, p0, d):
    """Tramos de la recta p0 + t*d (d unitario, dentro del plano de la seccion)
    que quedan dentro del contorno `pts` (regla par-impar)."""
    m = _unit(_cross(n, d))
    s = [_dot(_sub(p, p0), m) for p in pts]
    ts = []
    N = len(pts)
    for i in range(N):
        j = (i + 1) % N
        if (s[i] < 0) != (s[j] < 0):
            f = s[i] / (s[i] - s[j])
            q = _add(pts[i], _mul(_sub(pts[j], pts[i]), f))
            ts.append(_dot(_sub(q, p0), d))
    ts.sort()
    return [(ts[k], ts[k + 1]) for k in range(0, len(ts) - 1, 2)]


def _secciones_se_cruzan(sa, sb):
    """True si los contornos de dos secciones se atraviesan entre si: la recta donde
    se cortan sus planos pasa por dentro de AMBOS perfiles. Un loft entre dos
    secciones asi se pliega sobre si mismo. Devuelve (cruzan, longitud_solapada_mm)."""
    na, nb = _unit(sa["normal_seccion"]), _unit(sb["normal_seccion"])
    d = _cross(na, nb)
    if _norma(d) < 1e-6:
        return False, 0.0                                     # planos paralelos
    d = _unit(d)
    oa, ob = sa["xyz_le_mm"], sb["xyz_le_mm"]
    ma = _cross(na, d)                                        # en el plano A, perpendicular a la recta
    den = _dot(ma, nb)
    if abs(den) < 1e-12:
        return False, 0.0
    p0 = _add(oa, _mul(ma, _dot(_sub(ob, oa), nb) / den))
    ia = _intervalos_en_recta(sa["puntos_mm"], na, p0, d)
    ib = _intervalos_en_recta(sb["puntos_mm"], nb, p0, d)
    solape = 0.0
    for a0, a1 in ia:
        for b0, b1 in ib:
            solape = max(solape, min(a1, b1) - max(a0, b0))
    return solape > 0.0, solape


def _preparar_ala(ala, avisos):
    """Deja las secciones de una superficie listas para lofts sin sorpresas:
    puntos sin duplicados, borde de fuga al espesor pedido y sin secciones que se
    crucen. Modifica `ala` y agrega lo que hizo a `avisos`."""
    nom = ala["nombre"]
    secs = ala["secciones"]
    for s in secs:
        s["puntos_mm"] = _limpiar_puntos(s["puntos_mm"])
        if ESPESOR_TE_MM is not None:
            _ajustar_borde_de_fuga(s, ESPESOR_TE_MM)

    # Tramos finales degenerados (muy cortos o cuyas secciones se cruzan): descartar
    # la ultima seccion hasta que el ultimo tramo sea sano.
    while len(secs) > 2:
        corto = (TRAMO_MIN_MM > 0 and
                 _norma(_sub(secs[-1]["xyz_le_mm"], secs[-2]["xyz_le_mm"])) < TRAMO_MIN_MM)
        cruzan, solape = _secciones_se_cruzan(secs[-2], secs[-1])
        if not (corto or cruzan):
            break
        causa = ("se cruzan %.1f mm dentro del perfil" % solape) if cruzan else "tramo mas corto que %.0f mm" % TRAMO_MIN_MM
        avisos.append("%s: se descarto la ultima seccion (indice %d): %s." % (nom, secs[-1]["indice"], causa))
        secs.pop()

    # Cruces en el interior: no se pueden arreglar sin cambiar el diseno.
    for i in range(len(secs) - 1):
        cruzan, solape = _secciones_se_cruzan(secs[i], secs[i + 1])
        if cruzan:
            raise RuntimeError(
                "En '%s' las secciones %d y %d se atraviesan %.1f mm dentro de su perfil: el loft "
                "entre ellas se plegaria sobre si mismo y Ansys lo va a rechazar. Hay que cambiar "
                "el diseno (mas separacion o menos giro entre esas secciones)."
                % (nom, secs[i]["indice"], secs[i + 1]["indice"], solape))


# =============================================================================
# SUPERFICIES SUSTENTADORAS (ala, estabilizadores, deriva)
# =============================================================================
def _punto_a_distancia(pts, desde_fin, dist):
    """Recorre la polilinea desde un extremo (`desde_fin` = True: desde el ultimo punto;
    False: desde el primero) y devuelve (indice_primer_punto_que_se_conserva, punto A)
    donde A esta a `dist` mm del extremo medido sobre la polilinea."""
    n = len(pts)
    idx = range(n - 1, 0, -1) if desde_fin else range(0, n - 1)
    acum = 0.0
    for i in idx:
        j = i - 1 if desde_fin else i + 1
        seg = _norma(_sub(pts[j], pts[i]))
        if acum + seg >= dist and seg > 1e-12:
            t = (dist - acum) / seg
            A = _add(pts[i], _mul(_sub(pts[j], pts[i]), t))
            return j, A
        acum += seg
    return None, None


def _redondeo_borde_de_fuga(pts, radio):
    """Redondea las dos esquinas del borde de fuga romo con arcos tangentes.

    Devuelve (nucleo, arco_sup, arco_inf) o None si no se puede:
      nucleo   : puntos del spline, de A_sup (sobre el extrados) a A_inf (sobre el intrados)
      arco_sup : (A_sup, medio, B_sup)   B_sup = punto de tangencia sobre la cara del borde de fuga
      arco_inf : (A_inf, medio, B_inf)
    La cara del borde de fuga es el segmento recto entre B_sup y B_inf."""
    if radio is None or radio <= 0 or len(pts) < 8:
        return None
    P0, P1 = pts[0], pts[-1]
    cara = _norma(_sub(P0, P1))
    if cara < 1e-6:
        return None
    r = min(radio, 0.40 * cara)                               # deja >= 20 % de cara plana (sin aristas diminutas)
    resultado = []
    for extremo_sup in (True, False):
        P = P0 if extremo_sup else P1
        Q = P1 if extremo_sup else P0                         # el otro vertice de la cara
        vecino = pts[1] if extremo_sup else pts[-2]
        u = _unit(_sub(vecino, P))                            # sobre la superficie, hacia el interior
        f = _unit(_sub(Q, P))                                 # a lo largo de la cara
        cos_t = max(-1.0, min(1.0, _dot(u, f)))
        theta = math.acos(cos_t)
        if theta < 0.2 or theta > math.pi - 0.2:
            return None
        d = r / math.tan(theta / 2.0)
        if d > 3.0 * r:
            return None
        biseccion = _unit(_add(u, f))
        centro = _add(P, _mul(biseccion, r / math.sin(theta / 2.0)))
        medio = _add(centro, _mul(_unit(_sub(P, centro)), r))
        B = _add(P, _mul(f, d))
        j, A = _punto_a_distancia(pts, not extremo_sup, d)
        if A is None:
            return None
        resultado.append((j, A, medio, B))
    (js, As, ms, Bs), (ji, Ai, mi, Bi) = resultado
    if ji < js + 3:
        return None
    # js / ji: primer punto del lado del borde de ataque que se conserva en cada extremo
    nucleo = _limpiar_puntos([As] + list(pts[js:ji + 1]) + [Ai])
    return nucleo, (As, ms, Bs), (Ai, mi, Bi)


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

    d = sum((a - b) ** 2 for a, b in zip(pts[0], pts[-1])) ** 0.5
    redondeo = _redondeo_borde_de_fuga(pts, RADIO_BORDE_FUGA_MM) if d > TOL_CIERRE_MM else None

    if redondeo is not None:
        nucleo, arco_sup, arco_inf = redondeo
        coleccion = adsk.core.ObjectCollection.create()
        for p in nucleo:
            coleccion.add(sketch.modelToSketchSpace(_punto(p)))
        spline = sketch.sketchCurves.sketchFittedSplines.add(coleccion)
        espacio = sketch.modelToSketchSpace
        a_sup = sketch.sketchCurves.sketchArcs.addByThreePoints(
            spline.startSketchPoint, espacio(_punto(arco_sup[1])), espacio(_punto(arco_sup[2])))
        a_inf = sketch.sketchCurves.sketchArcs.addByThreePoints(
            spline.endSketchPoint, espacio(_punto(arco_inf[1])), espacio(_punto(arco_inf[2])))
        sketch.sketchCurves.sketchLines.addByTwoPoints(a_sup.endSketchPoint, a_inf.endSketchPoint)
        sketch.isComputeDeferred = False
        sketch.isLightBulbOn = False
        return sketch

    coleccion = adsk.core.ObjectCollection.create()
    for p in pts:
        coleccion.add(sketch.modelToSketchSpace(_punto(p)))
    sketch.sketchCurves.sketchFittedSplines.add(coleccion)

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
    """Un loft solido por las secciones dadas (en orden). Con dos sketches es una
    interpolacion lineal entre ambas: no puede hacer sobreimpulso."""
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


def _unir_cuerpos(comp, cuerpos):
    """Une una lista de cuerpos en el primero. Devuelve (cuerpo, ok, detalle)."""
    if len(cuerpos) < 2:
        return cuerpos[0], True, ""
    objetivo = cuerpos[0]
    herramientas = adsk.core.ObjectCollection.create()
    for c in cuerpos[1:]:
        herramientas.add(c)
    try:
        entrada = comp.features.combineFeatures.createInput(objetivo, herramientas)
        entrada.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
        comp.features.combineFeatures.add(entrada)
        return objetivo, True, ""
    except Exception:  # noqa: BLE001
        return objetivo, False, traceback.format_exc().splitlines()[-1]


def _espejar(comp, cuerpo, nombre):
    """Espeja un cuerpo respecto del plano XZ (y = 0) SIN unirlo con el original.
    Las raices de las dos mitades quedan dentro del fuselaje y se unen todas juntas
    al final: unirlas aca obliga a Fusion a resolver superficies casi coincidentes
    sobre el plano de simetria (el ala tiene un diedro en la raiz y la cola en V
    tiene sus raices inclinadas), que es una fuente tipica de autointersecciones."""
    antes = set(comp.bRepBodies.item(i).entityToken for i in range(comp.bRepBodies.count))
    cuerpos = adsk.core.ObjectCollection.create()
    cuerpos.add(cuerpo)
    entrada = comp.features.mirrorFeatures.createInput(cuerpos, comp.xZConstructionPlane)
    entrada.isCombine = False
    feature = comp.features.mirrorFeatures.add(entrada)
    # Los cuerpos nuevos se buscan por diferencia contra los que habia antes: no
    # depender de feature.bodies, que en algunos documentos viene vacio.
    nuevos = [comp.bRepBodies.item(i) for i in range(comp.bRepBodies.count)
              if comp.bRepBodies.item(i).entityToken not in antes]
    for c in nuevos:
        c.name = nombre + "_espejo"
    return len(nuevos)


def _crear_ala(comp, ala, avisos):
    """Construye la superficie y devuelve su nombre. Un loft por tramo entre
    secciones vecinas (LOFT_POR_TRAMOS) o uno solo por todas (version anterior)."""
    nombre = _nombre_seguro(ala["nombre"])
    secciones = ala["secciones"]
    sketches = [_crear_sketch_seccion(comp, s, nombre) for s in secciones]

    if LOFT_POR_TRAMOS and len(sketches) > 2:
        tramos = []
        for k in range(len(sketches) - 1):
            try:
                tramos.append(_loft(comp, [sketches[k], sketches[k + 1]], "%s_t%02d" % (nombre, k)))
            except Exception:  # noqa: BLE001
                raise RuntimeError(
                    "Fallo el loft del tramo %d (secciones %d y %d) de '%s':\n%s"
                    % (k, secciones[k]["indice"], secciones[k + 1]["indice"], ala["nombre"],
                       traceback.format_exc().splitlines()[-1]))
        cuerpo, ok, detalle = _unir_cuerpos(comp, tramos)
        if ok:
            cuerpo.name = nombre
        else:
            avisos.append("%s: no pude unir los %d tramos (%s). Quedan separados; se unen al final."
                          % (ala["nombre"], len(tramos), detalle))
            cuerpo = None
    else:
        cuerpo = _loft(comp, sketches, nombre)

    if ala.get("simetrica", False):
        if cuerpo is not None:
            if _espejar(comp, cuerpo, nombre) == 0:
                avisos.append("%s: el espejo NO creo ningun cuerpo; el CAD tiene solo medio ala." % ala["nombre"])
        else:
            sueltos = [comp.bRepBodies.item(i) for i in range(comp.bRepBodies.count)
                       if comp.bRepBodies.item(i).name.startswith(nombre + "_t")]
            for c in sueltos:
                _espejar(comp, c, c.name)
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
def _cuerpos_de(comp, nombre):
    """Todos los cuerpos que pertenecen a una superficie: el cuerpo, su espejo y,
    si los tramos no pudieron unirse, los tramos sueltos."""
    out = []
    for i in range(comp.bRepBodies.count):
        c = comp.bRepBodies.item(i)
        if c.name == nombre or c.name == nombre + "_espejo" or c.name.startswith(nombre + "_t"):
            out.append(c)
    return out


def _comparar_con_esperado(comp, nombres_cad, esperado):
    """Volumen y area de cada superficie/fuselaje en el CAD contra lo esperado del
    modelo (para las superficies simetricas, suma de las dos mitades)."""
    filas = []
    for nom_cad, nom_json in nombres_cad:
        cuerpos = _cuerpos_de(comp, nom_cad)
        e = esperado.get(nom_json)
        if not cuerpos or e is None:
            continue
        vol_L = sum(c.volume for c in cuerpos) * 1e-3          # cm3 -> L
        area_m2 = sum(c.area for c in cuerpos) * 1e-4          # cm2 -> m2
        dv = 100.0 * (vol_L - e["volumen_L"]) / max(e["volumen_L"], 1e-9)
        da = 100.0 * (area_m2 - e["area_mojada_m2"]) / max(e["area_mojada_m2"], 1e-9)
        filas.append("  %-26s vol %7.2f L (esp. %7.2f, %+.1f%%)   area %.4f m2 (esp. %.4f, %+.1f%%)   [%d cuerpo/s: %s]"
                     % (nom_json, vol_L, e["volumen_L"], dv, area_m2, e["area_mojada_m2"], da,
                        len(cuerpos), ", ".join(c.name for c in cuerpos)))
    return "\n".join(filas)


def _unir_todo(comp):
    """Une todos los cuerpos en uno. Devuelve (ok, mensaje).

    Primero intenta todos juntos. Si Fusion lo rechaza, une de a un cuerpo (el mas
    grande es el objetivo) y cuenta cuales no se dejaron unir, para saber donde
    esta el problema de geometria."""
    if comp.bRepBodies.count < 2:
        return True, ""
    lista = [comp.bRepBodies.item(i) for i in range(comp.bRepBodies.count)]
    lista.sort(key=lambda c: -c.volume)                       # el mayor (fuselaje o ala) de objetivo
    _, ok, detalle = _unir_cuerpos(comp, lista)
    if ok:
        return True, ""

    fallidos = []
    objetivo = lista[0]
    for c in lista[1:]:
        try:
            herramientas = adsk.core.ObjectCollection.create()
            herramientas.add(c)
            entrada = comp.features.combineFeatures.createInput(objetivo, herramientas)
            entrada.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
            comp.features.combineFeatures.add(entrada)
        except Exception:  # noqa: BLE001
            fallidos.append(c.name)
    if fallidos:
        return False, ("no se pudieron unir: %s. Tienen una interseccion que Fusion no resuelve; "
                       "probar Modify > Combine a mano con esos cuerpos, o revisar su forma. "
                       "Detalle del primer intento: %s" % (", ".join(fallidos), detalle))
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
                          "    python herramientas/exportar_cad_avion.py --params <ganador.json> --topologia <top>")
            return
        with open(ruta, "r") as f:
            datos = json.load(f)

        meta = datos.get("meta", {})
        if "meta" not in datos or "alas" not in datos:
            ui.messageBox("Este JSON no es el de geometria para CAD (le faltan 'meta' y 'alas'). "
                          "Probablemente elegiste los parametros de diseno (avion_design_params_*.json) "
                          "o un caso CFD.\n\nEl archivo que va aca es 'avion_geometry_cad.json' y se genera afuera de Fusion con:\n"
                          "    python herramientas/exportar_cad_avion.py --params resultados/avion_design_params_<top>.json --topologia <top>\n\n"
                          "Archivo elegido:\n%s" % ruta)
            return
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

        # Preparacion en python puro (antes de tocar el documento): borde de fuga,
        # puntos repetidos, secciones que se cruzan. Si algo no tiene arreglo, falla
        # aca, sin dejar un componente a medio hacer.
        avisos = []
        for a in alas:
            _preparar_ala(a, avisos)

        cambios_entorno = _preparar_entorno(app, ui, diseno)

        raiz = diseno.rootComponent
        # Un documento "Part Design" solo admite UN componente (el raiz): addNewComponent
        # falla con "Part Design documents can only contain one component". En ese caso
        # se trabaja directo en el componente raiz, que ya esta activo. Los cuerpos
        # quedan igual (cuerpos nombrados dentro del raiz).
        ocurrencia = None
        try:
            ocurrencia = raiz.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        except RuntimeError as e:
            if "Part Design" not in str(e) and "one component" not in str(e):
                raise
        if ocurrencia is not None:
            comp = ocurrencia.component
            comp.name = "Avion optimizado (%s)" % meta.get("topologia", "")
            # ACTIVAR la ocurrencia: sin esto, crear geometria de construccion dentro
            # de un componente nuevo falla con "Environment is not supported".
            if not ocurrencia.activate():
                ui.messageBox("No pude activar el componente nuevo. Proba cerrar y reabrir el "
                              "documento, o correr el script sin nada seleccionado en el navegador.")
                return
        else:
            comp = raiz

        nombres_cad = []
        for a in alas:
            nombres_cad.append((_crear_ala(comp, a, avisos), a["nombre"]))
        for fus in fuselajes:
            nombres_cad.append((_crear_fuselaje(comp, fus), fus["nombre"]))

        # Volumen y area de cada cuerpo ANTES de unirlos.
        esperado = meta.get("verificacion_en_fusion", {})
        comparacion = _comparar_con_esperado(comp, nombres_cad, esperado)

        # Envergadura real del CAD (caja que contiene todos los cuerpos, en Y).
        try:
            ys = []
            for i in range(comp.bRepBodies.count):
                bb = comp.bRepBodies.item(i).boundingBox
                ys += [bb.minPoint.y, bb.maxPoint.y]
            span_cad = 10.0 * (max(ys) - min(ys))                # cm -> mm
            comparacion += "\n  Envergadura en CAD: %.0f mm (esperada %.0f mm)" % (span_cad, meta.get("envergadura_mm", 0.0))
        except Exception:  # noqa: BLE001
            pass

        # CG de diseno.
        if "cg_x_mm" in meta:
            sk_cg = comp.sketches.add(comp.xYConstructionPlane)
            sk_cg.name = "CG_diseno"
            sk_cg.sketchPoints.add(sk_cg.modelToSketchSpace(_punto([meta["cg_x_mm"], 0.0, 0.0])))

        estado_union = "Cuerpos sin unir (UNIR_CUERPOS = False)."
        if UNIR_CUERPOS:
            try:
                ok_union, msg_union = _unir_todo(comp)
                if ok_union:
                    estado_union = "Todos los cuerpos unidos en uno (%d cuerpo/s)." % comp.bRepBodies.count
                else:
                    estado_union = ("UNION PARCIAL (%d cuerpos quedan): %s" % (comp.bRepBodies.count, msg_union))
            except Exception:
                estado_union = ("NO pude unir los cuerpos (%d separados). Unirlos a mano: "
                                "Modify > Combine, operacion Join.\nDetalle: %s"
                                % (comp.bRepBodies.count, traceback.format_exc().splitlines()[-1]))

        resumen_prep = ("Preparacion: " +
                        ("borde de fuga a %.2f mm; " % ESPESOR_TE_MM if ESPESOR_TE_MM is not None else
                         "borde de fuga sin tocar; ") +
                        ("lofts por tramo" if LOFT_POR_TRAMOS else "un loft por superficie") +
                        ("; bordes de fuga con radio %.2f mm" % RADIO_BORDE_FUGA_MM if RADIO_BORDE_FUGA_MM else "") + ".\n" +
                        ("".join("  AVISO: %s\n" % a for a in avisos)))
        ui.messageBox(
            ("Entorno ajustado: " + "; ".join(cambios_entorno) + "\n\n" if cambios_entorno else "") +
            resumen_prep + "\n"
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
