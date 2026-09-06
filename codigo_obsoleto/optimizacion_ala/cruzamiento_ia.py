"""
ARCHIVADO -- ya no es el backend activo. El notebook usa
`optimizacion_ala.ga_numerico` por default desde que el equipo decidió
dejar de gastar créditos de IA en la generación de hijos. Este archivo
se conserva tal cual (funciona, se puede volver a usar pasándolo a mano
a `correr_generacion()`) por si en algún momento quieren retomarlo o
comparar resultados contra el GA numérico -- pero nada del pipeline lo
importa por default.

DESACTUALIZADO ADEMÁS respecto a la parametrización: `ChildCandidate` y
`_build_crossbreed_prompt()` de acá abajo siguen hablando de los 7
parámetros viejos (root_chord, tip_chord, half_span, le_sweep_offset,
tip_dihedral, root_twist, tip_twist), no de los 17 nuevos que usa
`geometria.py` ahora (sweep_deg, le_offset_1..3, chord_1..3, twist_0..3,
z1..5). Si en algún momento se quiere reactivar este backend, hay que
reescribir el modelo pydantic y el prompt para que hablen de los 17
parámetros nuevos -- no es un cambio menor, y no se hizo acá porque el
módulo no está en uso.

Backend de generación de hijos vía IA (Claude como operador de
cruzamiento semántico, en vez de un crossover aritmético clásico).

Ver Research Note 11 para la explicación completa de por qué funciona
así y qué gana/pierde frente a un GA numérico. Este módulo es UN
backend posible -- evolucion.py no sabe ni le importa cómo se generan
los hijos, así que agregar un backend nuevo (PyGAD/DEAP, asb.Opti) es
escribir un módulo hermano con la misma firma de función, no tocar
este archivo ni evolucion.py.

Firma común que cualquier backend de generación de hijos debe cumplir:

    generar_hijos(padre_a: Candidate, padre_b: Candidate,
                   n_crossbred: int, n_wildcard: int) -> list[dict]

    Devuelve una lista de dicts con, como mínimo, la clave "params"
    (dict de 7 parámetros ya recortado a BOUNDS). Las claves "origin" y
    "rationale" son específicas de este backend (para inspección/log)
    y no todos los backends van a poder darlas -- el resto del código
    las trata como opcionales.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from .geometria import BOUNDS, Candidate, clamp_to_bounds


class ChildCandidate(BaseModel):
    root_chord: float = Field(description="Root chord length in meters")
    tip_chord: float = Field(description="Tip chord length in meters")
    half_span: float = Field(description="Half-span in meters")
    le_sweep_offset: float = Field(
        description="How far aft (downstream) the tip leading edge is vs the root leading edge, in meters"
    )
    tip_dihedral: float = Field(description="Vertical rise of the tip vs the root, in meters")
    root_twist: float = Field(description="Root incidence angle in degrees")
    tip_twist: float = Field(description="Tip incidence angle in degrees (washout is negative)")
    origin: str = Field(description="Either 'crossbred' or 'wildcard'")
    rationale: str = Field(description="One short sentence on why this child was proposed")


class CrossbreedResult(BaseModel):
    children: List[ChildCandidate]


def _build_crossbreed_prompt(
    parent_a: Candidate,
    parent_b: Candidate,
    n_crossbred: int,
    n_wildcard: int,
    require_json_in_prose: bool = False,
) -> str:
    bounds_text = "\n".join(f"- {name}: [{lo}, {hi}]" for name, (lo, hi) in BOUNDS.items())

    output_instructions = (
        """Respond with ONLY a single JSON object -- no markdown code fences, no """
        """prose before or after -- of the exact form:
{"children": [{"root_chord": <float>, "tip_chord": <float>, "half_span": <float>, """
        """"le_sweep_offset": <float>, "tip_dihedral": <float>, "root_twist": <float>, """
        """"tip_twist": <float>, "origin": "crossbred"|"wildcard", "rationale": "<one sentence>"}, ...]}"""
        if require_json_in_prose
        else 'Give a one-sentence rationale for each child, and set each child\'s "origin" field.'
    )

    return f"""You are acting as the cross-breeding operator in an evolutionary design
search for a tailless flying-wing aircraft planform. Two parent designs have
been selected as the current best performers.

Each design has 7 parameters:
- root_chord, tip_chord [m]: chord lengths at the wing root and tip (root should exceed tip for a tapered planform)
- half_span [m]: half of the total wingspan
- le_sweep_offset [m]: how far aft the tip's leading edge is vs the root's -- controls sweep
- tip_dihedral [m]: vertical rise of the tip vs the root
- root_twist, tip_twist [deg]: incidence angle at root/tip. tip_twist more negative than root_twist is washout, which helps pitch/stall stability on a tailless design.

Design space bounds (stay within these):
{bounds_text}

Parent A (score={parent_a.score:.4f}): {parent_a.params()}
Parent B (score={parent_b.score:.4f}): {parent_b.params()}

The score being maximized is glide ratio (lift-to-drag) at a fixed flight
condition. Propose exactly {n_crossbred + n_wildcard} children total, split
into two groups:

1. {n_crossbred} "crossbred" children (origin="crossbred"): derived from
   the two parents above. Combine traits from both (e.g. one parent's span
   with the other's sweep), interpolate between them, and include some
   mutations that push slightly beyond both parents in a promising
   direction.
2. {n_wildcard} "wildcard" children (origin="wildcard"): propose these
   independently of the parents' specific values -- don't just perturb
   them. Use your own judgment about what an efficient tailless flying
   wing planform could look like within the bounds, to explore parts of
   the design space the parents may not represent at all. These exist to
   inject diversity and avoid the search converging prematurely.

Keep tip_chord < root_chord for every child. {output_instructions}"""


def _parse_crossbreed_response(text: str) -> CrossbreedResult:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return CrossbreedResult.model_validate_json(text)
    except Exception:
        start, end = text.index("{"), text.rindex("}") + 1
        return CrossbreedResult.model_validate_json(text[start:end])


def _children_from_parsed(parsed: CrossbreedResult, n_total: int) -> List[dict]:
    children = []
    for child in parsed.children[:n_total]:
        d = child.model_dump()
        rationale = d.pop("rationale", "")
        origin = d.pop("origin", "unknown")
        children.append({"params": clamp_to_bounds(d), "rationale": rationale, "origin": origin})
    return children


def generar_hijos_api(
    parent_a: Candidate,
    parent_b: Candidate,
    n_crossbred: int = 7,
    n_wildcard: int = 3,
) -> List[dict]:
    """Vía la API de Mensajes de Anthropic (pay-as-you-go, necesita
    ANTHROPIC_API_KEY)."""
    import anthropic

    client = anthropic.Anthropic()
    prompt = _build_crossbreed_prompt(parent_a, parent_b, n_crossbred, n_wildcard)

    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=4096,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
        messages=[{"role": "user", "content": prompt}],
    )
    text = next(b.text for b in response.content if b.type == "text")
    parsed = _parse_crossbreed_response(text)
    return _children_from_parsed(parsed, n_crossbred + n_wildcard)


def generar_hijos_cli(
    parent_a: Candidate,
    parent_b: Candidate,
    n_crossbred: int = 7,
    n_wildcard: int = 3,
) -> List[dict]:
    """Vía la CLI de Claude Code en modo headless -- usa el uso incluido
    de la suscripción en vez de créditos de API separados. Verificar los
    flags con `claude --help` antes de confiar en esto (no probado en
    este entorno)."""
    import json
    import shutil
    import subprocess

    if shutil.which("claude") is None:
        raise RuntimeError(
            "El CLI `claude` no se encontró en el PATH. Instalá Claude Code y "
            "corré `claude login`, o usá generar_hijos_api() en su lugar."
        )

    prompt = _build_crossbreed_prompt(
        parent_a, parent_b, n_crossbred, n_wildcard, require_json_in_prose=True
    )

    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json"],
        capture_output=True,
        text=True,
        check=True,
    )
    cli_response = json.loads(result.stdout)
    text = cli_response.get("result", cli_response.get("text", ""))
    parsed = _parse_crossbreed_response(text)
    return _children_from_parsed(parsed, n_crossbred + n_wildcard)


def generar_hijos(
    parent_a: Candidate,
    parent_b: Candidate,
    n_crossbred: int = 7,
    n_wildcard: int = 3,
    backend: str = "cli",
) -> List[dict]:
    """Dispatcher. backend="api" usa la API de pago; backend="cli" usa
    el CLI de Claude Code (uso incluido de la suscripción)."""
    if backend == "api":
        return generar_hijos_api(parent_a, parent_b, n_crossbred, n_wildcard)
    elif backend == "cli":
        return generar_hijos_cli(parent_a, parent_b, n_crossbred, n_wildcard)
    else:
        raise ValueError(f"Backend desconocido {backend!r}; usá 'api' o 'cli'.")
