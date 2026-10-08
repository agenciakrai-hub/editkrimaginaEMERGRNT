import os
import asyncio
import base64
import logging
import io
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

# Flash is fast and reliable in production; Pro is used automatically as a fallback
# (and can be promoted to primary via AI_IMAGE_MODEL when the key balance is healthy).
MODEL = os.environ.get("AI_IMAGE_MODEL", "gemini-3.1-flash-image-preview")
# Higher-fidelity fallback used automatically only if the primary model errors out.
FALLBACK_MODEL = os.environ.get("AI_IMAGE_FALLBACK_MODEL", "gemini-3-pro-image-preview")
EDIT_TIMEOUT = int(os.environ.get("AI_EDIT_TIMEOUT", "150"))

# Applied to every edit: keep the building/architecture and framing identical.
GEO_GUARD = (
    "Preserve the exact building architecture, structure, walls, ceiling, floor, room geometry, "
    "framing and composition of the original photo. The output must be photorealistic, ultra "
    "high-resolution and sharp, free of artifacts, warping or distortion, with no added text, "
    "logos or watermarks."
)
# Extra rules for adjustment-only tools that must NOT alter any content.
STRICT_GUARD = (
    GEO_GUARD + " CRITICAL: do NOT add, remove, replace, move, duplicate or invent any windows, "
    "doors, walls, furniture, decor or objects, and never create a window, opening, view, sky or "
    "scene that is not already visible in the original. Keep every existing item identical in "
    "shape, position, material and color. Only apply the requested photographic adjustment."
)
STRICT_ACTIONS = {"auto", "light", "straighten", "upscale", "perspective_pro"}

ACTIONS = {
    "auto": {
        "label": "Mejora automática",
        "description": "Aplica todas las mejoras esenciales en un solo clic.",
        "cost": 0, "category": "auto", "disclosure_default": False,
        "prompt": (
            "Act as a top professional real-estate photo retoucher and apply a natural, "
            "magazine-quality enhancement pass to this photograph. Perform ONLY these adjustments: "
            "balance the exposure and expand dynamic range with a clean HDR look by lifting shadows "
            "and recovering blown highlights; set an accurate neutral white balance and remove any "
            "color cast (yellow/green); make interiors bright, crisp, airy and inviting; boost "
            "micro-contrast, clarity, sharpness and fine detail; gently reduce noise; and subtly "
            "straighten the verticals so wall corners and door/window frames are plumb, correcting "
            "only mild lens distortion. Keep it realistic and true to the room — do not re-light the "
            "scene dramatically and do not change, add or remove any content."
        ),
    },
    "sky": {
        "label": "Reemplazo de cielo",
        "description": "Cielo gris a azul soleado, controlable.",
        "cost": 0, "category": "esencial", "disclosure_default": False,
        "prompt": (
            "Replace ONLY the existing dull, grey or overcast sky visible in this real-estate photo "
            "with a beautiful clear blue sky with a few soft white clouds and warm natural sunlight, "
            "adjusting the ambient light on the building to match. Do not add sky where there is none."
        ),
    },
    "light": {
        "label": "Luz y color + HDR",
        "description": "Interiores brillantes y balanceados.",
        "cost": 0, "category": "esencial", "disclosure_default": False,
        "prompt": (
            "Apply a strong yet natural professional real-estate HDR light and color grade to this "
            "photo so the improvement is clearly visible: noticeably lift the shadows, recover "
            "highlights, balance the exposure, correct the white balance to neutral, add depth and "
            "clarity, and make the interior bright, clean, warm and inviting. No over-saturation, "
            "no HDR halos."
        ),
    },
    "straighten": {
        "label": "Enderezar perspectiva",
        "description": "Líneas rectas y verticales, corrección de lente.",
        "cost": 0, "category": "esencial", "disclosure_default": False,
        "prompt": (
            "Correct the perspective, keystone and lens distortion of this real-estate photo like a "
            "professional architectural tilt-shift lens: make every vertical line (wall corners, "
            "door frames, window frames, cabinets) perfectly vertical and the horizon level. Keep "
            "the walls straight and the proportions natural without stretching furniture."
        ),
    },
    "twilight": {
        "label": "Atardecer / Twilight",
        "description": "Fachadas al anochecer, cálidas y premium.",
        "cost": 2, "category": "premium", "disclosure_default": True,
        "prompt": (
            "Transform this daytime real-estate exterior into a stunning twilight/dusk scene: deep "
            "blue-to-orange gradient sky, warm glowing lights turned on inside the existing windows "
            "and on the facade, soft ambient dusk lighting. Luxurious and photorealistic."
        ),
    },
    "declutter": {
        "label": "Quitar objetos",
        "description": "Cables, coches, basura, señales y desorden.",
        "cost": 2, "category": "premium", "disclosure_default": False,
        "prompt": (
            "Remove clutter and distracting objects from this real-estate photo: cables, wires, "
            "trash bins, cars, traffic signs, personal items and mess. Cleanly and seamlessly fill "
            "the removed areas by extending the existing surfaces so the result looks natural."
        ),
    },
    "lawn": {
        "label": "Mejorar césped/jardín",
        "description": "Césped verde y jardín cuidado.",
        "cost": 1, "category": "premium", "disclosure_default": False,
        "prompt": (
            "Enhance the existing lawn and garden in this real-estate photo: make the grass a "
            "healthy lush green, tidy the plants and landscaping and remove dead patches. Keep "
            "everything else unchanged."
        ),
    },
    "window_pull": {
        "label": "Window pull",
        "description": "Recuperar la vista por la ventana.",
        "cost": 2, "category": "premium", "disclosure_default": False,
        "prompt": (
            "Perform a professional window pull ONLY on windows that already exist and are "
            "overexposed/blown-out in this interior photo: recover a realistic, balanced exterior "
            "view through those windows while keeping the interior bright and natural. Do NOT create "
            "any new window."
        ),
    },
    "staging": {
        "label": "Home staging virtual",
        "description": "Amuebla habitaciones vacías por estilo.",
        "cost": 3, "category": "premium", "disclosure_default": True,
        "prompt": (
            "Virtually stage this empty room with tasteful {style} style furniture and decor "
            "appropriate to the room type (sofa, table, rug, lamps, art, plants). Keep the walls, "
            "floor, windows, doors and architecture exactly the same. Photorealistic and inviting."
        ),
    },
    "upscale": {
        "label": "Mejorar nitidez",
        "description": "Upscale y nitidez de la foto.",
        "cost": 1, "category": "premium", "disclosure_default": False,
        "prompt": (
            "Upscale this real-estate photo and enhance its sharpness, resolution, fine detail and "
            "clarity. Reduce noise, blur and compression artifacts while keeping colors natural."
        ),
    },
    "perspective_pro": {
        "label": "Perspectiva Pro (IA)",
        "description": "Verticales perfectamente a plomo con IA, como un objetivo tilt-shift.",
        "cost": 2, "category": "premium", "disclosure_default": False,
        "prompt": (
            "Act as a professional architectural photographer using a high-end tilt-shift lens "
            "combined with Photoshop perspective/keystone correction. Aggressively but realistically "
            "correct the perspective, keystone and lens distortion of this real-estate photo so that "
            "EVERY vertical line (wall corners, door frames, window frames, columns, cabinets, "
            "furniture edges) becomes perfectly vertical and plumb, and the horizon is perfectly "
            "level. Fix converging verticals and any barrel/pincushion lens distortion so walls are "
            "straight. Keep the proportions natural and the result photorealistic without stretching, "
            "squashing or duplicating furniture, people or architectural elements."
        ),
    },
    "auto_pro": {
        "label": "Mejora Pro (IA)",
        "description": "Acabado profesional de revista con IA: como tu referencia.",
        "cost": 1, "category": "premium", "disclosure_default": False,
        "prompt": (
            "Professionally edit this real-estate photograph into a bright, clean, natural "
            "magazine-quality 'flambient' look. Do ALL of the following: balance the exposure with a "
            "clean, subtle HDR; lift the shadows and recover highlights so the room is bright, airy and "
            "inviting; set an accurate neutral white balance so walls and ceiling read as clean, even "
            "white with no grey/blue/yellow cast; keep wood floors and warm materials naturally warm; "
            "adjust exposure and highlights ONLY in the exterior detail already visible through existing "
            "windows and glass doors, retaining every visible real landscape element. If a window area is "
            "completely white with no recoverable detail, add ONLY a very subtle pale sky-blue gradient "
            "within that white glass area; keep it luminous, nearly white, without invented scenery. "
            "Keep frosted, textured, translucent or opaque glass non-transparent. For exterior photos, "
            "replace the existing rainy or overcast sky with a natural clear blue sunny-day sky, and "
            "harmonize the building, vegetation and ground with realistic daylight and coherent soft "
            "sunlight, shadows and optional subtle sun effects. Preserve the actual property and vegetation. Correct lens "
            "barrel distortion and vignetting (no dark corners) and level the verticals and horizon. "
            "Increase clarity, micro-contrast and sharpness slightly and gently reduce noise. Keep it "
            "photorealistic and true to the real room: do NOT add, remove, move or duplicate furniture "
            "or objects, and never invent windows, doors, openings or views that do not already exist."
        ),
    },
}


# Independent tools: exterior sunshine must never color interior white paint.
ACTIONS["complete"] = {
    "label": "Mejora completa · Interior",
    "description": "Interiores: blancos neutros, luz equilibrada, ventanas, limpieza y perspectiva.",
    "cost": 1,
    "category": "premium",
    "disclosure_default": True,
    "prompt": "Edit this INTERIOR real-estate photograph with a clean neutral daylight flambient finish. This is an interior-only tool: do not apply a sunny exterior grade, warm sunlight, golden-hour lighting, sun rays, warm ambience, sepia or yellow/orange tint to the room.\nPRIORITY 1 — CLEAN WHITE PAINT: Walls and ceilings that are white in the original must read as PURE NEUTRAL WHITE after editing, never cream, beige, ivory or yellow. Neutralize tungsten/yellow light reflected from wood and lamps on white paint, curtains and white bedding. Preserve subtle neutral grey shading and texture, avoiding flat clipped white. Keep genuinely colored paint, wood and fabrics their authentic colors. Brighten the room with soft neutral daylight; reduce artificial lamp glow if it causes yellow casts. Remove stains, dark marks, patchy paint, scuffs and cosmetic fine cracks across ALL walls and ceilings.\nPRIORITY 2 — MANDATORY DECLUTTER: Remove EVERY wall picture, framed artwork, personal photograph and small decorative object; remove ALL vases, flower arrangements, table centerpieces, tabletop plants, ornaments, bottles, containers and loose items from tables, bedside tables, shelves and furniture tops. Leave these surfaces empty. Remove rubbish bins, cleaning supplies, loose lamp cables, floor cables and power strips. Do not leave flowers or vases as decoration. Reconstruct only the existing surface behind removed items. Keep furniture, beds, sofas, chairs, lamps, built-in fittings, mirrors and their real reflections. Do not add replacement decor.\nPRIORITY 3 — WINDOWS: Recover highlights and balance exposure of the EXISTING windows and exterior view, retaining all real visible details. Do not leave blown white glass where recoverable detail exists. In completely white glass with no detail, add ONLY a very subtle pale sky-blue-to-white gradient restricted to that glass, luminous and almost white; never invent a landscape, buildings or trees. Preserve curtains, frames, shutters and glazing texture. Keep frosted, textured or opaque glass non-transparent. Never turn a mirror into a window.\nPRIORITY 4 — PERSPECTIVE: Level camera roll and conservatively correct converging verticals with one coherent photographic perspective correction and minimal crop. Keep the real viewpoint, room dimensions, depth, furniture proportions and orientation/aspect ratio. No stretched corners, bent walls, rubber-sheet warping, duplicated edges or invented borders. Keep every door/window in its original open/closed state.\nFINAL AUDIT: inspect every white wall and ceiling for yellow casts, all tables and furniture tops for remaining objects, every window for blown highlights, and all vertical lines. Complete all four priorities before returning a single photorealistic image without text or watermark. Natural material detail, gentle contrast, no HDR halos or excessive sharpening. Record the real property faithfully. No interior sky replacement or added sunlight."
}
ACTIONS["complete_exterior"] = {
    "label": "Mejora completa · Exterior",
    "description": "Exteriores: cielo despejado, día soleado, fachadas, limpieza y perspectiva.",
    "cost": 1,
    "category": "premium",
    "disclosure_default": True,
    "prompt": "Edit this EXTERIOR real-estate photograph into a bright natural CLEAR SUNNY DAY. This is the exterior-only tool; do not use interior flambient relighting.\n1. SKY AND DAYLIGHT: Replace only an existing grey/rainy/overcast sky with a natural clear blue sky, subtle atmospheric gradient and optional small soft white clouds. Harmonize building, vegetation and ground with neutral daylight and coherent realistic soft sunlight/shadows. Subtle sun glow is allowed, no dramatic rays, lens flare, sunset, orange/yellow grade or oversaturation. Do not create sky where there is a building, wall, roof or tree.\n2. COLOR: White facades and trim stay CLEAN NEUTRAL WHITE, never yellow, cream or beige. Preserve authentic colored materials, stone, tile and wood. Balance exposure and recover highlights and shadows without HDR halos.\n3. CLEANUP: Remove loose rubbish, bins, cables, power strips, cleaning supplies and small distracting loose objects. Repair superficial stains and cosmetic paint defects without redesigning the property. Preserve permanent garden structures, benches, wells, barbecues, chimneys, trees, planting, architecture and boundary walls. Keep ALL doors, garage doors, shutters, gates and windows in their exact original open/closed state and shape. Never reveal a hidden interior or change panels/handles.\n4. WINDOWS: Preserve real glazing/reflections and recover visible detail. For completely white glass only, allow a VERY SUBTLE pale sky-blue-to-white gradient; never invent a landscape or make frosted/opaque glass transparent.\n5. PERSPECTIVE: Level camera roll and conservatively correct architectural verticals with one coherent photographic correction and minimal crop. Preserve viewpoint, proportions, depth, orientation and aspect ratio. No local stretching, bent walls, warped roofs, duplicated structures or invented borders.\nFINAL AUDIT: verify sunny coherent lighting, neutral white facades, clean surfaces, faithful door states and straight architectural lines. Return one photorealistic photograph without text or watermark."
}

STAGING_STYLES = {
    "nordico": "Scandinavian / Nordic",
    "moderno": "modern contemporary",
    "minimal": "minimalist",
    "clasico": "classic elegant",
}


def build_prompt(action_key: str, options: dict) -> str:
    action = ACTIONS[action_key]
    prompt = action["prompt"]
    if action_key == "staging":
        style_key = (options or {}).get("style", "nordico")
        prompt = prompt.replace("{style}", STAGING_STYLES.get(style_key, "modern contemporary"))
    if action_key in {"complete", "complete_exterior"}:
        # Each complete tool owns its scene rules, with no contradictory global grade.
        return prompt
    guard = STRICT_GUARD if action_key in STRICT_ACTIONS else GEO_GUARD
    if action_key == "auto_pro":
        guard += (
            " Preserve frames, curtains, glazing texture, real exterior details and mirrors. "
            "For completely white glass only, allow a subtle pale sky-blue-to-white gradient; "
            "never invent a landscape. Exterior sunny sky and matching daylight are allowed "
            "only outside, never as a warm color cast on interior white paint."
        )
    return f"{prompt}\n\n{guard}"


def _validate_complete_result(source: bytes, result: bytes) -> None:
    """Reject corrupt outputs and format changes instead of stretching them to fit.

    This guards dimensions only; semantic/geometry fidelity still needs visual QA.
    """
    with Image.open(io.BytesIO(source)) as src, Image.open(io.BytesIO(result)) as out:
        sw, sh = ImageOps.exif_transpose(src).size
        ow, oh = ImageOps.exif_transpose(out).size
        out.load()
        if (sw > sh) != (ow > oh) or abs((ow / oh) / (sw / sh) - 1) > 0.03:
            raise ValueError("complete_result_aspect_ratio_changed")



async def run_edit(image_bytes: bytes, action_key: str, options: dict, session_id: str) -> bytes:
    """Disabled: all generative edits must use the selected KRAI adapter."""
    raise RuntimeError("La edición directa está deshabilitada. Usa la API de KRAI seleccionada.")
