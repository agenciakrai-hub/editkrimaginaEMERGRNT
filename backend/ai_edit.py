import os
import base64
import logging
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

logger = logging.getLogger(__name__)

# Nano Banana "Pro" gives higher fidelity, sharper detail and fewer hallucinations
# than the flash model — important for client-ready real-estate photos.
MODEL = os.environ.get("AI_IMAGE_MODEL", "gemini-3-pro-image-preview")

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
STRICT_ACTIONS = {"auto", "light", "straighten", "upscale"}

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
    return f"{prompt}\n\n{guard}"


async def run_edit(image_bytes: bytes, action_key: str, options: dict, session_id: str) -> bytes:
    api_key = os.environ["EMERGENT_LLM_KEY"]
    chat = LlmChat(
        api_key=api_key,
        session_id=session_id,
        system_message=(
            "You are an award-winning professional real-estate photo editor. You always return a "
            "single photorealistic, high-resolution edited version of the provided image, faithful "
            "to the original scene."
        ),
    )
    chat.with_model("gemini", MODEL).with_params(modalities=["image", "text"])
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    msg = UserMessage(text=build_prompt(action_key, options), file_contents=[ImageContent(b64)])
    text, images = await chat.send_message_multimodal_response(msg)
    if images:
        return base64.b64decode(images[0]["data"])
    logger.error("Nano Banana returned no image. text=%s", (text or "")[:120])
    return None
