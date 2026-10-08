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
            "windows and glass doors. NEVER replace or invent an exterior view. Keep frosted, textured, "
            "translucent, opaque or blown-out glass as it is: do not turn it transparent or create a "
            "landscape, sky, garden or buildings where no recoverable detail is visible. Correct lens "
            "barrel distortion and vignetting (no dark corners) and level the verticals and horizon. "
            "Increase clarity, micro-contrast and sharpness slightly and gently reduce noise. Keep it "
            "photorealistic and true to the real room: do NOT add, remove, move or duplicate furniture "
            "or objects, and never invent windows, doors, openings or views that do not already exist."
        ),
    },
}


# Complete enhancement has its own instructions: cleanup must not inherit Pro's
# prohibition on removing decor or retouching superficial surface blemishes.
ACTIONS["complete"] = {
    "label": "Mejora completa",
    "description": "Luz y color Pro, ventanas, perspectiva y limpieza completa.",
    "cost": ACTIONS["auto_pro"]["cost"], "category": "premium", "disclosure_default": True,
    "prompt": (
        "Retouch this exact real-estate photograph. Complete EVERY applicable task in this "
        "checklist in one edit, then inspect the result before returning it. "
        "1. LIGHT AND COLOR: bright, balanced professional flambient exposure; lift dark interiors "
        "and recover highlights without clipping windows. Neutral clean whites, natural warm wood, "
        "accurate material colors, gentle contrast and saturation. No grey veil, yellow/blue cast, "
        "HDR halos, plastic surfaces or excessive sharpening. Preserve natural shadows and depth. "
        "2. WINDOWS: recover exposure only in exterior detail actually present in existing windows. "
        "Keep the exact exterior, glass opacity/texture, frames, curtains and reflections. Never "
        "invent scenery or turn opaque, frosted or blown-out glass into a new view. "
        "3. CLEANUP: remove wall pictures, framed artwork, personal photos, small decorative objects "
        "and loose items from tables, shelves, cabinets and bedside tables, including ALL table centerpieces, vases, tabletop plants, ornaments, bottles and containers; leave tabletops clear; remove rubbish bins, "
        "rubbish, cleaning supplies, loose lamp cables and floor power strips. Keep EVERY door, garage door, shutter, gate and window in its EXACT original open/closed state, with the same panels, handles and frames. Never remove a door or reveal an interior hidden behind it. Keep outdoor benches, chimneys, wells, barbecues and permanent garden structures unchanged. Keep the lamps, "
        "furniture, built-in fittings and their actual shape, position and materials. Reconstruct "
        "only the exposed background surface with matching texture, lighting and shadows. "
        "4. SURFACES: remove visible stains, scuffs, peeling or chipped paint, fine surface cracks and cosmetic blemishes "
        "on walls and ceilings, including ceiling discoloration and patchy paint. Restore a clean, consistent painted finish with its natural texture and shading. Do not change the shape of the building "
        "or redesign tiles, doors, sockets or fittings. "
        "5. PERSPECTIVE: level camera roll and correct converging architectural verticals using "
        "one coherent, conservative photographic perspective correction, with only a minimal crop. "
        "Preserve the original viewpoint, depth, field of view and natural furniture proportions. "
        "Receding horizontal lines must still converge naturally: do not force all edges parallel. "
        "Never bend walls, stretch room corners, widen rooms, squash furniture, duplicate edges, "
        "apply local rubber-sheet warping or invent image borders. If a stronger correction would "
        "deform the scene, keep the safe partial correction. "
        "FINAL CHECK: verify cleanup across the whole image, straight architectural lines, natural "
        "proportions, faithful windows and clean light/color. Return only one edited photograph "
        "with the same orientation and aspect ratio as the input, without text or watermark."
    ),
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
    guard = STRICT_GUARD if action_key in STRICT_ACTIONS else GEO_GUARD
    if action_key == "complete":
        guard = (
            "Preserve the real architecture, room dimensions, furniture and fixtures. "
            "Only the listed removable items and superficial blemishes may change. "
            "A conservative global perspective adjustment and minimal crop are allowed; "
            "no stretching, local warping, invented structure, scenery or borders. "
            "Keep the source orientation and aspect ratio. Photorealistic output."
        )
    if action_key in {"auto_pro", "complete"}:
        guard += (
            " ABSOLUTE PRESERVATION: keep the exact window glass, opacity, texture, frames, "
            "curtains and the original exterior scene. Only improve its existing lighting, exposure "
            "and white balance; never replace the sky, weather, vegetation or buildings, and never "
            "invent hidden detail. Preserve mirrors, their frames, material, color and reflections; "
            "do not redesign or replace fixtures, tiles, furniture or architectural elements. "
            "These preservation rules take priority over window recovery, cleanup and enhancement."
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
