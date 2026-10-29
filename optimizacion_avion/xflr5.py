"""
Exporta un avión a XFLR5 (probado contra el formato de XFLR5 v6.62).

    import optimizacion_avion as av
    av.exportar_xflr5(params, "v_tail", "carpeta_destino")

Escribe en la carpeta:

    <familia>_avion.xml       el avión (alas, cola, derivas) en el formato XML de XFLR5 ("explane"),
                              con la masa total como masa puntual en el CG
    perfiles/<perfil>.dat     cada perfil que usa el avión, en formato Selig
    condiciones.txt           velocidad, densidad, viscosidad, masa, CG y alpha de crucero, para
                              configurar los análisis de XFLR5, y los pasos para importarlo
    LEEME.txt                 los mismos pasos, cortos

QUÉ SE EXPORTA Y QUÉ NO
- La geometría de las superficies es la que analizó el optimizador: el avión TRIMADO
  (incidencia de cola resuelta), con las 11 secciones del ala y los winglets como secciones con
  diedro. Cada tramo entre dos secciones va con su diedro, su flecha (xOffset) y la torsión de
  cada sección.
- El fuselaje NO se exporta: los análisis VLM de XFLR5 no lo usan, y el formato de cuerpos de
  XFLR5 es otro. La masa total sí va, como masa puntual en el CG de diseño, para los análisis
  de sustentación fija (tipo 2) y de estabilidad.
- Los perfiles se exportan con la forma con que se analizaron, incluido el borde de fuga de 2 mm
  de cada sección. Un perfil que aparece en dos cuerdas distintas sale dos veces (la segunda con
  la cuerda en mm en el nombre, p. ej. `fx63137_c92`), porque 2 mm son otra fracción de cuerda. Las mezclas entre dos perfiles del
  catálogo salen como perfiles propios (por ejemplo `naca6412_40_fx63137` = 60 % naca6412 + 40 %
  fx63137).
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np

from . import mision_avion as _ma
from .geometria_avion import TOPOLOGIAS, construir_avion

# Paneles por defecto para el VLM de XFLR5.
PANELES_CUERDA = 13
LARGO_PANEL_ENVERGADURA = 0.05      # [m] -> número de paneles por tramo
COLORES = {"MAINWING": (47, 111, 176), "ELEVATOR": (224, 138, 46), "FIN": (224, 138, 46)}


def _nombre_seguro(nombre: str) -> str:
    """'60% naca6412, 40% fx63137' -> 'naca6412_40_fx63137'; 'naca0010' -> 'naca0010'."""
    m = re.match(r"\s*(\d+)%\s*([^,]+),\s*(\d+)%\s*(.+)$", nombre)
    if m:
        return f"{m.group(2).strip()}_{m.group(3)}_{m.group(4).strip()}".replace(" ", "")
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", nombre.strip())


def _tipo(nombre: str, es_primera: bool) -> str:
    n = nombre.lower()
    if es_primera:
        return "MAINWING"
    if "deriva" in n or "vertical" in n:
        return "FIN"
    return "ELEVATOR"


def _secciones(ala, perfiles: dict) -> list:
    """Secciones en el formato de XFLR5: posición a lo largo de la envergadura DESARROLLADA,
    offset del borde de ataque respecto de la raíz, diedro del tramo que empieza en la sección,
    torsión y perfil."""
    xs = ala.xsecs
    P = np.array([[float(v) for v in s.xyz_le] for s in xs])
    es_vertical = (not ala.symmetric) and abs(P[-1, 2] - P[0, 2]) > abs(P[-1, 1] - P[0, 1])
    filas, s_acum = [], 0.0
    for i, s in enumerate(xs):
        if i < len(xs) - 1:
            d = P[i + 1] - P[i]
            if es_vertical:      # una deriva: su "envergadura" es la altura
                largo, diedro = float(np.hypot(d[2], d[1])), 0.0
            else:
                largo = float(np.hypot(d[1], d[2]))
                diedro = float(np.degrees(np.arctan2(d[2], d[1]))) if largo > 1e-9 else 0.0
        else:
            largo, diedro = 0.0, 0.0
        nombre = _nombre_seguro(s.airfoil.name)
        # Desde V54.2 cada sección lleva su propio borde de fuga de 2 mm absolutos, así que
        # el mismo perfil en dos cuerdas distintas tiene coordenadas distintas (otra fracción
        # de cuerda en el borde de fuga). Cada variante sale como un .dat propio, con la
        # cuerda en mm en el nombre; antes se exportaba una sola, la de la cuerda mayor, y en
        # la cuerda menor el borde de fuga quedaba más fino que 2 mm.
        co = np.asarray(s.airfoil.coordinates, float)
        if nombre in perfiles and not np.allclose(np.asarray(perfiles[nombre][0].coordinates, float), co):
            nombre = f"{nombre}_c{round(1000 * float(s.chord))}"
        if nombre not in perfiles:
            perfiles[nombre] = (s.airfoil, float(s.chord))
        filas.append({"y": s_acum, "cuerda": float(s.chord), "xoff": float(P[i, 0] - P[0, 0]),
                      "diedro": diedro, "torsion": float(s.twist), "perfil": nombre,
                      "n_y": max(1, min(20, math.ceil(largo / LARGO_PANEL_ENVERGADURA)))})
        s_acum += largo
    return filas, P[0], es_vertical


def _xml_ala(ala, es_primera: bool, perfiles: dict, sangria: str = "        ", doble: bool = False) -> str:
    filas, raiz, es_vertical = _secciones(ala, perfiles)
    tipo = _tipo(ala.name, es_primera)
    es_fin = tipo == "FIN" or es_vertical
    r, g, b = COLORES["FIN" if es_fin else tipo]
    S = sangria
    L = [f"{S}<wing>",
         f"{S}    <Name>{ala.name}</Name>",
         f"{S}    <Type>{'FIN' if es_fin else tipo}</Type>",
         f"{S}    <Color><red>{r}</red><green>{g}</green><blue>{b}</blue><alpha>255</alpha></Color>",
         f"{S}    <Description></Description>",
         f"{S}    <Position>{raiz[0]:.6f}, {raiz[1]:.6f}, {raiz[2]:.6f}</Position>",
         f"{S}    <Tilt_angle>0.000</Tilt_angle>",
         f"{S}    <Symetric>{'true' if ala.symmetric else 'false'}</Symetric>",
         f"{S}    <isFin>{'true' if es_fin else 'false'}</isFin>",
         f"{S}    <isDoubleFin>{'true' if doble else 'false'}</isDoubleFin>",
         f"{S}    <isSymFin>false</isSymFin>",
         f"{S}    <Inertia><Volume_Mass>0.000</Volume_Mass></Inertia>",
         f"{S}    <Sections>"]
    for f in filas:
        L += [f"{S}        <Section>",
              f"{S}            <y_position>{f['y']:.6f}</y_position>",
              f"{S}            <Chord>{f['cuerda']:.6f}</Chord>",
              f"{S}            <xOffset>{f['xoff']:.6f}</xOffset>",
              f"{S}            <Dihedral>{f['diedro']:.4f}</Dihedral>",
              f"{S}            <Twist>{f['torsion']:.4f}</Twist>",
              f"{S}            <x_number_of_panels>{PANELES_CUERDA}</x_number_of_panels>",
              f"{S}            <x_panel_distribution>COSINE</x_panel_distribution>",
              f"{S}            <y_number_of_panels>{f['n_y']}</y_number_of_panels>",
              f"{S}            <y_panel_distribution>UNIFORM</y_panel_distribution>",
              f"{S}            <Left_Side_FoilName>{f['perfil']}</Left_Side_FoilName>",
              f"{S}            <Right_Side_FoilName>{f['perfil']}</Right_Side_FoilName>",
              f"{S}        </Section>"]
    L += [f"{S}    </Sections>", f"{S}</wing>"]
    return "\n".join(L)


def _dat(nombre: str, airfoil) -> str:
    co = np.asarray(airfoil.coordinates, float)
    return nombre + "\n" + "\n".join(f" {x:.6f}  {y:.6f}" for x, y in co) + "\n"


def exportar_xflr5(params: dict, topologia: str, carpeta, nombre: str | None = None) -> Path:
    """Escribe el avión (trimado), sus perfiles y las condiciones de crucero para XFLR5 en
    `carpeta` y devuelve la ruta del XML. Si el avión es infactible igual se exporta la
    geometría (con la incidencia de cola que trae), y condiciones.txt lo avisa."""
    carpeta = Path(carpeta)
    (carpeta / "perfiles").mkdir(parents=True, exist_ok=True)
    a = _ma.analizar_mision_avion(params, topologia)
    p = a["params_trimados"] if a is not None else params
    avion = construir_avion(p, topologia)
    nombre = nombre or f"{topologia}_{_ma.PUNTAJE_MODO}"

    perfiles: dict = {}
    # XFLR5 admite UNA deriva por avión: las dos derivas del doble boom van como una sola con
    # isDoubleFin (XFLR5 la espeja respecto de y = 0).
    derivas = [w for w in avion.wings[1:] if not w.symmetric]
    alas_xml = []
    for i, w in enumerate(avion.wings):
        if w in derivas and len(derivas) == 2:
            if float(w.xsecs[0].xyz_le[1]) < 0:
                continue
            alas_xml.append(_xml_ala(w, False, perfiles, doble=True))
        else:
            alas_xml.append(_xml_ala(w, i == 0, perfiles))
    masa = a["masa_total"] if a is not None else float("nan")
    x_cg = float(avion.xyz_ref[0])
    inercia = ("        <Inertia>\n"
               "            <Point_Mass>\n"
               "                <Tag>masa total en el CG</Tag>\n"
               f"                <Mass>{masa:.4f}</Mass>\n"
               f"                <coordinates>{x_cg:.6f}, 0.000000, 0.000000</coordinates>\n"
               "            </Point_Mass>\n"
               "        </Inertia>") if a is not None else "        <Inertia></Inertia>"
    xml = "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<!DOCTYPE explane>",
        '<explane version="1.0">',
        "    <Units>",
        "        <length_unit_to_meter>1</length_unit_to_meter>",
        "        <mass_unit_to_kg>1</mass_unit_to_kg>",
        "    </Units>",
        "    <Plane>",
        f"        <Name>{nombre}</Name>",
        f"        <Description>Exportado de optimizacion_avion ({TOPOLOGIAS[topologia]['nombre']}). "
        "Sin fuselaje.</Description>",
        inercia,
        "        <has_body>false</has_body>",
        *alas_xml,
        "    </Plane>",
        "</explane>", ""])
    ruta_xml = carpeta / f"{topologia}_avion.xml"
    ruta_xml.write_text(xml, encoding="utf-8")
    for n, (af, _) in perfiles.items():
        (carpeta / "perfiles" / f"{n}.dat").write_text(_dat(n, af), encoding="utf-8")

    pasos = [
        "COMO ABRIRLO EN XFLR5 (v6.6x)",
        "1. Modulo Direct Foil Design / XFoil Direct Analysis: File > Open, y cargar TODOS los .dat",
        "   de la carpeta perfiles/ (XFLR5 busca los perfiles por nombre al importar el avion).",
        "2. En XFoil Direct Analysis, generar polares de cada perfil (Analysis > Batch analysis,",
        "   tipo 1, Reynolds de ~1e5 a ~1e6) si se van a hacer analisis viscosos.",
        "3. Modulo Wing and Plane Design: Plane > Import plane definition from xml file",
        f"   (elegir {ruta_xml.name}).",
        "4. Definir el analisis con las condiciones de abajo.",
        "",
        "Unidades del XML: metros y kilogramos. Sin fuselaje (el VLM de XFLR5 no lo usa).",
    ]
    cond = ["CONDICIONES DE CRUCERO DEL OPTIMIZADOR (para configurar el analisis en XFLR5)", ""]
    if a is None:
        cond += ["OJO: el avion es INFACTIBLE con el modelo actual; se exporto la geometria igual.",
                 f"Motivo: {_ma.describir_puntaje(_ma.evaluar_mision_avion(params, topologia))}", ""]
    else:
        nu = float(_ma._atmosfera().kinematic_viscosity())
        cond += [f"Familia ............... {topologia}",
                 f"Escenario ............. viento {'on' if _ma.VIENTO_ACTIVO else 'off'}, "
                 f"bateria {'on' if _ma.BATERIA_ACTIVA else 'off'}",
                 f"Velocidad de crucero .. {_ma.V_CRUCERO:.3f} m/s ({3.6*_ma.V_CRUCERO:.0f} km/h)",
                 f"Velocidad maxima ...... {_ma.V_MAX:.3f} m/s",
                 f"Densidad .............. {a['rho']:.4f} kg/m3",
                 f"Viscosidad cinematica . {nu:.3e} m2/s",
                 f"Masa total ............ {a['masa_total']:.3f} kg (como masa puntual en el CG)",
                 f"CG .................... x = {x_cg:.4f} m desde el morro "
                 f"({100*a['cg_frac_mac']:.1f} % de la MAC)",
                 f"Superficie de ref. .... {a['S']:.4f} m2   MAC {a['MAC']:.4f} m   envergadura del ala {a['envergadura']:.3f} m "
                 f"(total con winglets {a.get('envergadura_total', a['envergadura']):.3f} m)",
                 f"Alpha de crucero ...... {a['alpha_crucero']:.3f} grados   CL {a['CL_crucero']:.4f}",
                 f"Incidencia de cola .... {a.get('incidencia_trim_deg', float('nan')):+.3f} grados (trim)",
                 f"Margen estatico ....... {100*a['SM']:.1f} %   (AeroBuildup)",
                 f"CD crucero ............ {a['CD_crucero']:.5f}   L/D {a['LD_crucero']:.2f}   (AeroBuildup)",
                 "",
                 "Sugerencia: analisis tipo 2 (sustentacion fija), VLM2, con estas densidad y viscosidad;",
                 "el alpha de equilibrio de XFLR5 se puede comparar con el de arriba."]
    (carpeta / "condiciones.txt").write_text("\n".join(cond + [""] + pasos) + "\n", encoding="utf-8")
    (carpeta / "LEEME.txt").write_text("\n".join(pasos) + "\n", encoding="utf-8")
    return ruta_xml
