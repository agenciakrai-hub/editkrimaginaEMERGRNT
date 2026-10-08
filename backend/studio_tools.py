"""Isolated AI assistance for the imported manual and HDR studios."""
import asyncio
import io
from fastapi import Depends, File, Form, HTTPException, Response, UploadFile
from PIL import Image
import providers
import ai_edit

STUDIO_TOOLS = {
    "manual": {"label": "Edición manual · detección IA", "cost": 1, "category": "studio"},
    "hdr": {"label": "Fusión HDR · acabado IA", "cost": 1, "category": "studio"},
    "video": {"label": "Vídeo · proveedor IA", "cost": 0, "category": "video"},
}

def validate_mask(data):
    with Image.open(io.BytesIO(data)) as img:
        img.thumbnail((256,256))
        pixels=list(img.convert("RGB").getdata())
        if not pixels or sum(max(p)-min(p) for p in pixels)/len(pixels)>8:
            raise ValueError("not_a_mask")
        if sum(1 for p in pixels if min(p)>220 or max(p)<35)/len(pixels)<0.8:
            raise ValueError("not_a_binary_mask")
        selected=sum(1 for p in pixels if min(p)>220)/len(pixels)
        if selected==0 or selected>0.95:
            raise ValueError("empty_or_unbounded_mask")

def register_studio_routes(api, db, current_user, get_override, is_owner, log_usage):
    @api.post("/tools/{tool}/assist")
    async def studio_assist(tool: str, file: UploadFile = File(...), mode: str = Form("exterior"), user: dict = Depends(current_user)):
        if tool not in {"manual","hdr"}:
            raise HTTPException(404,"Herramienta no encontrada")
        data=await file.read(8*1024*1024+1)
        if not data or len(data)>8*1024*1024:
            raise HTTPException(400,"Usa una imagen de hasta 8 MiB")
        try:
            providers.image_mime(data)
            with Image.open(io.BytesIO(data)) as img:
                if img.width*img.height>30000000: raise ValueError()
                img.verify()
        except Exception:
            raise HTTPException(400,"La fotografía no es válida")
        try:
            engine=await get_override(tool)
        except Exception:
            raise HTTPException(503,"Revisa el proveedor seleccionado para esta herramienta")
        if not engine or not providers.is_krai_gateway(engine[0].get("base_url")):
            raise HTTPException(400,"Selecciona un modelo de KRAI para esta herramienta en Proveedores IA")
        provider, model=engine
        if tool=="manual":
            area="only transparent window glass" if mode=="interior" else "only visible outdoor sky"
            prompt=f"Return ONLY a binary black-and-white segmentation mask of the input photograph at the same aspect ratio. Paint {area} solid pure white. Everything else must be pure black, including window frames, curtains, buildings, trees, furniture, doors, mirrors and walls. Preserve exact pixel alignment and camera geometry. No photograph, colors, text, labels or legends. Do not include opaque or frosted glass."
        else:
            prompt="Polish this already fused HDR real-estate photo with neutral daylight, balanced highlights and shadows, clean neutral white paint and natural authentic materials. Preserve exact framing, perspective, architecture, furniture, all objects, windows and real exterior details. No added or removed content, invented scenery, warm yellow cast, halos, oversaturation or local distortion. Return only the photograph."
        charge=0 if is_owner(user) else 1
        if charge:
            result=await db.users.update_one({"user_id":user["user_id"],"credits":{"$gte":charge}},{"$inc":{"credits":-charge}})
            if not result.modified_count: raise HTTPException(402,"Necesitas 1 crédito para esta asistencia IA")
        try:
            result=await asyncio.to_thread(providers.run_image_edit,provider,model,data,prompt)
            ai_edit._validate_complete_result(data,result)
            if tool=="manual": validate_mask(result)
            mime=providers.image_mime(result)
        except Exception as error:
            if charge: await db.users.update_one({"user_id":user["user_id"]},{"$inc":{"credits":charge}})
            status=error.status_code if isinstance(error,providers.ProviderRequestError) else 502
            reason=str(error) if isinstance(error,providers.ProviderRequestError) else "KRAI no devolvió un resultado válido. Se conserva la foto y se reembolsa el crédito."
            raise HTTPException(status,reason)
        await log_usage(user["user_id"],"photo",tool,charge,0,provider.get("name","KRAI"),model,ai_calls=1)
        return Response(result,media_type=mime,headers={"Cache-Control":"no-store"})
