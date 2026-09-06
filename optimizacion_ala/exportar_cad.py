"""
Exportador de la geometría a CAD (Fusion).

==========================================================================
POR QUÉ ESTE MÓDULO EXISTE, Y POR QUÉ NO CALCULA NADA PROPIO
==========================================================================
La regla que se sigue acá es una sola: **el CAD tiene que ser exactamente la
geometría que evaluó el solver, no una reconstrucción parecida.**

Es fácil equivocarse en esto. Uno tiene la tentación de escribir en el script
de Fusion "cuerda por acá, torsión por allá, diedro por allá" y rearmar el ala
a mano desde los parámetros. Eso produce, sin falta, un ala levemente distinta
de la que se optimizó: alcanza con aplicar la torsión respecto de otro eje, o
con no reproducir el bisel que AeroSandbox mete en los quiebres, para que el
sólido que se fabrica no sea el que se analizó. Y la diferencia no se ve --
se descubre cuando el avión no vuela como decía el informe.

Así que acá NO se recalcula nada. Se le pide a AeroSandbox el marco de
referencia de cada sección (`Wing._compute_frame_of_WingXSec`), que es el
mismo que usa internamente para armar la malla del solver, y se emiten las
coordenadas 3D de cada punto del perfil ya ubicadas en el espacio. El script
de Fusion no hace geometría: dibuja puntos.

Qué incluye ese marco, y que uno reproduciría mal a mano:
- La torsión rota alrededor del eje de ENVERGADURA LOCAL (que sigue el
  diedro), no alrededor del eje Y global.
- En cada estación interior, el marco es el promedio de las direcciones de
  envergadura de antes y después, con un factor `z_scale` que ENSANCHA la
  sección en los quiebres. Es el equivalente de cortar a inglete: sin eso, un
  ala con quiebre queda más fina justo en el quiebre.
- Las secciones del winglet se orientan según la dirección del winglet, no
  según el eje Y. Con un winglet casi vertical, la diferencia no es un detalle:
  una sección en un plano de Y constante sería casi paralela a la superficie.

==========================================================================
FORMATO DE SALIDA
==========================================================================
Un JSON con las secciones ya en coordenadas 3D, EN MILÍMETROS:

    {
      "meta": {...},
      "secciones_ala":     [ {perfil, cuerda_mm, puntos:[[x,y,z], ...]}, ... ],
      "secciones_winglet": [ ... ]
    }

Se separan ala y winglet a propósito: son dos lofts distintos en Fusion. Con
`winglet_radio = 0` la unión es un quiebre vivo, y un loft único a través de
un quiebre así produce una superficie retorcida. Dos lofts que comparten la
sección de la punta se unen limpio.

Los puntos van de borde de fuga (extradós) -> borde de ataque -> borde de fuga
(intradós), es decir el orden Selig de siempre. El lazo queda ABIERTO en el
borde de fuga (ver ESPESOR_BORDE_FUGA_MM); lo cierra el script de Fusion con
un segmento recto, que es lo que le da al borde de fuga su arista viva.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .geometria import N_SECCIONES_LOFT, HALF_SPAN, CG_FRAC_MAC, construir_avion

# Cuántos puntos por perfil se emiten al CAD. Los perfiles internos tienen 200;
# para un spline de Fusion eso es innecesario y lento. 120 con espaciado tipo
# coseno (denso en los bordes) reproduce la nariz sin que se note la diferencia.
N_PUNTOS_CAD = 120

# Espesor del BORDE DE FUGA que se le da al modelo de CAD, en milímetros.
#
# POR QUÉ HAY QUE TOCAR ESTO, Y POR QUÉ ESTÁ ACÁ ARRIBA Y NO ESCONDIDO.
# Los perfiles de la base UIUC, tal como los repanela AeroSandbox, cierran el
# borde de fuga en un FILO EXACTO: el primer y el último punto del contorno son
# el mismo punto, con separación medida de 0.0 mm. Eso trae dos problemas:
#
# 1. FABRICACIÓN. Un filo de espesor cero no existe. En espuma, en impresión 3D
#    o en laminado, el borde de fuga real va a terminar teniendo entre medio
#    milímetro y un milímetro. Si el CAD dice cero, la pieza que sale no es la
#    del CAD y nadie sabe cuánto se apartó.
# 2. CAD. Un contorno cuyo primer y último punto coinciden es ambiguo para
#    Fusion: puede interpretarlo como una spline abierta cuyos extremos se
#    tocan, o como una spline cerrada y periódica -- y en el segundo caso
#    REDONDEA el pico del borde de fuga, cambiando la geometría sin avisar.
#
# Abrir el borde de fuga una cantidad chica y DECLARADA resuelve los dos. Se
# aplica como el clásico repartido lineal en la cuerda (el espesor agregado
# crece con x/c y vale `t` en el borde de fuga), que es como se abre un perfil
# en la práctica. 0.6 mm sobre la cuerda de raíz de 500 mm es 0.12%; sobre la
# cuerda de punta de 80 mm es 0.75%, que sigue siendo despreciable
# aerodinámicamente y es del orden de lo que se puede construir.
#
# Poner 0.0 acá desactiva la apertura y devuelve el filo exacto: el JSON queda
# fiel al análisis, pero el loft de Fusion puede redondear el borde de fuga.
ESPESOR_BORDE_FUGA_MM = 0.6


def _abrir_borde_de_fuga(coords: np.ndarray, espesor_frac: float) -> np.ndarray:
    """Abre el borde de fuga de un perfil normalizado, repartiendo el espesor
    linealmente con la cuerda.

    El contorno viene en orden Selig: borde de fuga -> borde de ataque por el
    EXTRADÓS, y vuelta por el INTRADÓS. El borde de ataque es el punto de x
    mínimo, y separa las dos ramas. A cada rama se le suma (o resta) la mitad
    del espesor escalado por x/c, así el borde de ataque no se toca y el efecto
    se concentra donde tiene que estar."""
    if espesor_frac <= 0:
        return coords
    out = coords.copy()
    i_le = int(np.argmin(out[:, 0]))
    x = out[:, 0]
    signo = np.where(np.arange(len(out)) <= i_le, 1.0, -1.0)
    out[:, 1] = out[:, 1] + signo * 0.5 * espesor_frac * x
    return out


def _resamplear_perfil(coords: np.ndarray, n: int) -> np.ndarray:
    """Reduce un contorno de perfil a `n` puntos conservando los extremos.

    Se resamplea por LONGITUD DE ARCO acumulada, no por índice: así los puntos
    se reparten parejo sobre el contorno y la nariz -- donde los puntos vienen
    muy juntos -- no se queda sin resolución."""
    d = np.sqrt(np.sum(np.diff(coords, axis=0) ** 2, axis=1))
    s = np.concatenate([[0.0], np.cumsum(d)])
    s_new = np.linspace(0.0, s[-1], n)
    return np.stack([np.interp(s_new, s, coords[:, 0]),
                     np.interp(s_new, s, coords[:, 1])], axis=1)


def secciones_3d(params: dict, n_puntos: int = N_PUNTOS_CAD,
                 espesor_te_mm: float = ESPESOR_BORDE_FUGA_MM) -> dict:
    """Coordenadas 3D de todas las secciones, en METROS, tal como las ve el
    solver.

    Devuelve un dict con las secciones del ala y las del winglet por separado,
    más la sección de la punta repetida en las dos listas (es la que las une)."""
    avion = construir_avion(params)
    ala = avion.wings[0]
    n_total = len(ala.xsecs)

    secciones = []
    for i, xsec in enumerate(ala.xsecs):
        xg, yg, zg = ala._compute_frame_of_WingXSec(i)
        xg, yg, zg = np.asarray(xg, float), np.asarray(yg, float), np.asarray(zg, float)
        origen = np.asarray(xsec.xyz_le, dtype=float)

        co = _resamplear_perfil(np.asarray(xsec.airfoil.coordinates, dtype=float), n_puntos)
        # El espesor de borde de fuga se pide en mm ABSOLUTOS y se convierte a
        # fracción de la cuerda LOCAL: así todas las secciones tienen el mismo
        # borde de fuga en milímetros, que es lo que importa para construirlo.
        co = _abrir_borde_de_fuga(co, espesor_te_mm / 1000.0 / max(float(xsec.chord), 1e-6))
        # Misma fórmula que Wing._compute_xyz_of_WingXSec: el punto (x/c, z/c)
        # del perfil se ubica en el marco local de la sección.
        pts = origen[None, :] + xsec.chord * (
            co[:, 0:1] * xg[None, :] + co[:, 1:2] * zg[None, :]
        )
        secciones.append({
            "indice": i,
            "perfil": xsec.airfoil.name,
            "cuerda_m": float(xsec.chord),
            "torsion_deg": float(xsec.twist),
            "xyz_le_m": [float(v) for v in origen],
            "normal": [float(v) for v in yg],
            "puntos_m": pts.tolist(),
        })

    n_ala = min(N_SECCIONES_LOFT, n_total)
    return {
        "secciones_ala": secciones[:n_ala],
        # El winglet arranca EN la punta del ala (sección compartida), para que
        # los dos lofts tengan una cara coincidente y se unan sin costura.
        "secciones_winglet": secciones[n_ala - 1:] if n_total > n_ala else [],
    }


def exportar_json(params: dict, ruta="wing_geometry_cad.json",
                  n_puntos: int = N_PUNTOS_CAD, score=None,
                  espesor_te_mm: float = ESPESOR_BORDE_FUGA_MM) -> Path:
    """Escribe el JSON que consume `fusion_generar_ala.py`.

    Todo sale en MILÍMETROS. El motivo de fijar la unidad acá y no allá es que
    la API de Fusion trabaja internamente en CENTÍMETROS, que no es la unidad
    que muestra la interfaz -- es una fuente clásica de alas 10 veces más
    grandes. Emitiendo mm, la conversión queda en UN solo lugar del script de
    Fusion, explícita y comentada."""
    datos = secciones_3d(params, n_puntos, espesor_te_mm)
    avion = construir_avion(params)
    ala = avion.wings[0]

    def a_mm(sec):
        return {
            "indice": sec["indice"],
            "perfil": sec["perfil"],
            "cuerda_mm": 1000.0 * sec["cuerda_m"],
            "torsion_deg": sec["torsion_deg"],
            "xyz_le_mm": [1000.0 * v for v in sec["xyz_le_m"]],
            "puntos_mm": [[1000.0 * c for c in p] for p in sec["puntos_m"]],
            # Normal UNITARIA del plano de la sección (no lleva escala: es una
            # dirección, no una longitud). Es `yg_local` de AeroSandbox --
            # perpendicular al plano que arman xg/zg, que es donde caen todos
            # los puntos del perfil. Se exporta para que Fusion pueda definir
            # el plano de construcción por punto+normal en vez de por tres
            # puntos: `setByThreePoints` exige que los tres puntos sean
            # ENTIDADES del documento (SketchPoint), no coordenadas sueltas, y
            # falla adentro con un error interno poco claro si se le pasan
            # puntos crudos. Punto+normal no tiene ese problema.
            "normal_seccion": [float(v) for v in sec["normal"]],
        }

    salida = {
        "meta": {
            "unidades": "mm",
            "generado_por": "optimizacion_ala.exportar_cad",
            "score": score,
            "semi_envergadura_mm": 1000.0 * HALF_SPAN,
            "envergadura_ala_mm": 2000.0 * HALF_SPAN,
            # OJO: `span()` incluye lo que el winglet se extiende hacia afuera,
            # así que es MAYOR que la envergadura del ala. Se informan las dos
            # para que nadie confunde una con la otra al cotizar un fuselaje.
            "envergadura_total_con_winglets_mm": 1000.0 * float(ala.span()),
            "superficie_m2": float(ala.area()),
            "mac_mm": 1000.0 * float(ala.mean_aerodynamic_chord()),
            "cg_x_mm": 1000.0 * float(avion.xyz_ref[0]),
            "cg_frac_mac": CG_FRAC_MAC,
            "n_puntos_por_perfil": n_puntos,
            "espesor_borde_fuga_mm": espesor_te_mm,
            "_nota_borde_fuga": ("el borde de fuga se abrio a este espesor: el perfil "
                                 "analizado cierra en filo exacto, que no es fabricable "
                                 "ni loftea sin ambiguedad. Ver exportar_cad.ESPESOR_BORDE_FUGA_MM"),
            "_nota_simetria": ("solo se exporta la SEMIALA derecha (y >= 0). "
                               "El script de Fusion la espeja respecto del plano XZ."),
        },
        "secciones_ala": [a_mm(s) for s in datos["secciones_ala"]],
        "secciones_winglet": [a_mm(s) for s in datos["secciones_winglet"]],
    }

    ruta = Path(ruta)
    ruta.write_text(json.dumps(salida, indent=1))
    return ruta


# =====================================================================
# Verificación -- correr esto ANTES de mandar nada a Fusion
# =====================================================================
def verificar(params: dict, n_puntos: int = N_PUNTOS_CAD,
              espesor_te_mm: float = ESPESOR_BORDE_FUGA_MM) -> dict:
    """Chequeos baratos que atrapan los errores que en Fusion se ven recién
    cuando el loft falla o sale retorcido.

    1. PLANARIDAD: cada sección tiene que ser plana. Si no lo fuera, el sketch
       de Fusion aplastaría los puntos contra su plano y la sección saldría
       deformada sin avisar.
    2. ORDEN CONSISTENTE: todas las secciones tienen que arrancar en el mismo
       lugar del contorno. Si una arranca en el borde de fuga y la siguiente en
       el de ataque, el loft sale retorcido -- es EL error clásico.
    3. SIN CRUCES: dos secciones consecutivas no se pueden intersecar.
    4. CUERDA MÍNIMA: una sección de cuerda ~0 rompe el loft.
    5. BORDE DE FUGA ABIERTO: si cierra en filo exacto, Fusion puede
       interpretar el contorno como una spline cerrada y redondear el pico."""
    datos = secciones_3d(params, n_puntos, espesor_te_mm)
    todas = datos["secciones_ala"] + datos["secciones_winglet"][1:]

    plan_max = 0.0
    for sec in todas:
        p = np.array(sec["puntos_m"])
        nrm = np.array(sec["normal"])
        # Distancia de cada punto al plano de la sección.
        d = np.abs((p - np.array(sec["xyz_le_m"])) @ nrm)
        plan_max = max(plan_max, float(np.max(d)))

    # Todas las secciones deben arrancar en el borde de fuga del extradós.
    arranques = [float(np.array(s["puntos_m"])[0] @ np.array([1.0, 0, 0])
                 - np.array(s["xyz_le_m"])[0]) / max(s["cuerda_m"], 1e-9)
                 for s in todas]
    orden_ok = all(a > 0.9 for a in arranques)

    cuerda_min = min(s["cuerda_m"] for s in todas)

    gaps = [float(np.linalg.norm(np.array(s["puntos_m"])[0] - np.array(s["puntos_m"])[-1]))
            for s in todas]

    # Separación entre secciones consecutivas (si es <= 0 se cruzan).
    seps = []
    for a, b in zip(todas[:-1], todas[1:]):
        pa, pb = np.array(a["xyz_le_m"]), np.array(b["xyz_le_m"])
        seps.append(float(np.linalg.norm(pb - pa)))

    return {
        "planaridad_max_mm": 1000.0 * plan_max,
        "planaridad_ok": plan_max < 1e-9,
        "orden_consistente_ok": orden_ok,
        "cuerda_min_mm": 1000.0 * cuerda_min,
        "cuerda_min_ok": cuerda_min > 0.02,
        "separacion_min_mm": 1000.0 * min(seps) if seps else 0.0,
        "separacion_ok": (min(seps) > 1e-4) if seps else True,
        "borde_fuga_min_mm": 1000.0 * min(gaps),
        "borde_fuga_ok": min(gaps) > 1e-5,
        "n_secciones_ala": len(datos["secciones_ala"]),
        "n_secciones_winglet": len(datos["secciones_winglet"]),
    }
