import os
import base64
import logging
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

logger = logging.getLogger(__name__)

MODEL = "gemini-3.1-flash-image-preview"

# Real-estate AI edit catalogue. cost=0 -> free "esencial". disclosure_default toggles the
# "Imagen editada digitalmente / Amueblado virtualmente" compliance tag.
ACTIONS = {
    "auto": {
        "label": "Mejora automática",
        "description": "Aplica todas las mejoras esenciales en un solo clic.",
        "cost": 0, "category": "auto", "disclosure_default": False,
        "prompt": (
            "Act as a professional real estate photo editor and automatically enhance this property photo "
            "in a single pass, applying ALL of these improvements as appropriate to the scene: "
            "1) HDR light and color correction — brighten shadows, balance exposure, recover highlights, "
            "neutral white balance, bright and inviting interiors; "
            "2) If a dull/grey/overcast sky is visible, replace it with a clear blue sky with soft white clouds and natural sunlight; "
            "3) Correct perspective and lens distortion so vertical lines (walls, doors, windows) are perfectly straight; "
            "4) If there is a lawn or garden, make the grass a healthy lush green and tidy the landscaping; "
            "5) Recover blown-out window views (window pull) so the exterior is visible and balanced; "
            "6) Remove small distracting clutter (cables, trash, minor mess) without altering the structure or furniture; "
            "7) Increase overall sharpness, detail and clarity, reduce noise. "
            "Keep the architecture, layout and all real furniture exactly intact. The result must be photorealistic, "
            "natural and never over-processed, as a top real estate listing photo."
        ),
    },
    "sky": {
        "label": "Reemplazo de cielo",
        "description": "Cielo gris a azul soleado, controlable.",
        "cost": 0, "category": "esencial", "disclosure_default": False,
        "prompt": "Replace the dull, grey or overcast sky in this real estate photo with a beautiful clear blue sky with a few soft white clouds and warm natural sunlight. Keep the building, foreground and all architectural details perfectly intact and photorealistic. Do not alter the structure.",
    },
    "light": {
        "label": "Luz y color + HDR",
        "description": "Interiores brillantes y balanceados.",
        "cost": 0, "category": "esencial", "disclosure_default": False,
        "prompt": "Apply professional real estate HDR light and color correction to this photo: brighten shadows, balance exposure, recover highlights, correct white balance to neutral, and make interiors bright, clean and inviting. Keep it photorealistic and natural, no over-saturation.",
    },
    "straighten": {
        "label": "Enderezar perspectiva",
        "description": "Líneas rectas y verticales, corrección de lente.",
        "cost": 0, "category": "esencial", "disclosure_default": False,
        "prompt": "Correct the perspective and lens distortion of this real estate photo so that vertical lines (walls, doors, windows) are perfectly straight and verticals are aligned, as a professional architectural photographer would. Keep the image photorealistic.",
    },
    "twilight": {
        "label": "Atardecer / Twilight",
        "description": "Fachadas al anochecer, cálidas y premium.",
        "cost": 2, "category": "premium", "disclosure_default": True,
        "prompt": "Transform this daytime real estate exterior photo into a stunning twilight / dusk scene: deep blue-to-orange gradient sky, warm glowing interior and exterior lights turned on in the windows, soft ambient dusk lighting on the facade. Make it luxurious and photorealistic.",
    },
    "declutter": {
        "label": "Quitar objetos",
        "description": "Cables, coches, basura, señales y desorden.",
        "cost": 2, "category": "premium", "disclosure_default": False,
        "prompt": "Remove clutter and distracting objects from this real estate photo: cables, wires, trash bins, cars, traffic signs, personal items and mess. Cleanly fill the removed areas so the result looks natural, tidy and photorealistic.",
    },
    "lawn": {
        "label": "Mejorar césped/jardín",
        "description": "Césped verde y jardín cuidado.",
        "cost": 1, "category": "premium", "disclosure_default": False,
        "prompt": "Enhance the lawn and garden in this real estate photo: make the grass a healthy lush green, tidy the plants and landscaping, remove dead patches. Keep everything else unchanged and photorealistic.",
    },
    "window_pull": {
        "label": "Window pull",
        "description": "Recuperar la vista por la ventana.",
        "cost": 2, "category": "premium", "disclosure_default": False,
        "prompt": "Perform a professional window pull on this interior real estate photo: recover the blown-out overexposed view through the windows so the exterior scenery is visible and balanced, while keeping the interior bright and natural. Photorealistic result.",
    },
    "staging": {
        "label": "Home staging virtual",
        "description": "Amuebla habitaciones vacías por estilo.",
        "cost": 3, "category": "premium", "disclosure_default": True,
        "prompt": "Virtually stage this empty room with tasteful {style} style furniture and decor appropriate for the room type (sofa, table, rug, lamps, art, plants). Keep the walls, floor, windows and architecture exactly the same. Make it photorealistic and inviting.",
    },
    "upscale": {
        "label": "Mejorar nitidez",
        "description": "Upscale y nitidez de la foto.",
        "cost": 1, "category": "premium", "disclosure_default": False,
        "prompt": "Upscale and enhance the sharpness, detail and clarity of this real estate photo. Reduce noise and blur, keep colors natural. Photorealistic result.",
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
    return prompt


async def run_edit(image_bytes: bytes, action_key: str, options: dict, session_id: str) -> bytes:
    api_key = os.environ["EMERGENT_LLM_KEY"]
    chat = LlmChat(
        api_key=api_key,
        session_id=session_id,
        system_message="You are an expert professional real estate photo editor. You always return a photorealistic edited version of the provided image.",
    )
    chat.with_model("gemini", MODEL).with_params(modalities=["image", "text"])
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    msg = UserMessage(text=build_prompt(action_key, options), file_contents=[ImageContent(b64)])
    text, images = await chat.send_message_multimodal_response(msg)
    if images:
        return base64.b64decode(images[0]["data"])
    logger.error("Nano Banana returned no image. text=%s", (text or "")[:120])
    return None
