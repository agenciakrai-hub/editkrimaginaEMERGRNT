import React, { useRef, useState, useEffect } from "react";
import { api, apiError, fileUrl } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Loader2, Eraser, Undo2 } from "lucide-react";
import { toast } from "sonner";

export default function EraserDialog({ open, onOpenChange, photo, onDone }) {
  const canvasRef = useRef(null);
  const imgRef = useRef(null);
  const drawing = useRef(false);
  const [brush, setBrush] = useState(40);
  const [busy, setBusy] = useState(false);
  const [hasStrokes, setHasStrokes] = useState(false);

  useEffect(() => {
    if (!open) setHasStrokes(false);
  }, [open]);

  const onImgLoad = () => {
    const img = imgRef.current;
    const canvas = canvasRef.current;
    if (!img || !canvas) return;
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
    setHasStrokes(false);
  };

  const pos = (e) => {
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const cx = (e.touches ? e.touches[0].clientX : e.clientX) - rect.left;
    const cy = (e.touches ? e.touches[0].clientY : e.clientY) - rect.top;
    return { x: cx * (canvas.width / rect.width), y: cy * (canvas.height / rect.height) };
  };

  const paint = (e) => {
    if (!drawing.current) return;
    e.preventDefault();
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    const { x, y } = pos(e);
    const r = brush * (canvas.width / canvas.getBoundingClientRect().width) / 2;
    ctx.fillStyle = "rgba(255,60,60,0.55)";
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
    setHasStrokes(true);
  };

  const start = (e) => { drawing.current = true; paint(e); };
  const end = () => { drawing.current = false; };

  const clear = () => {
    const c = canvasRef.current;
    c.getContext("2d").clearRect(0, 0, c.width, c.height);
    setHasStrokes(false);
  };

  const apply = async () => {
    if (!hasStrokes) return;
    setBusy(true);
    try {
      const mask = canvasRef.current.toDataURL("image/png");
      const { data } = await api.post(`/photos/${photo.id}/inpaint`, { mask });
      toast.success("Objeto eliminado ✨ (gratis)");
      onDone(data.photo);
      onOpenChange(false);
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[#1E1A29] border-white/10 text-white max-w-3xl">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2"><Eraser className="w-5 h-5 text-cyan-400" /> Borrador · Quitar objetos (gratis)</DialogTitle>
          <DialogDescription className="text-slate-400">Pinta encima de cables, enchufes u objetos pequeños y se rellenarán automáticamente. Sin coste.</DialogDescription>
        </DialogHeader>

        <div className="relative w-full max-h-[55vh] overflow-auto rounded-lg bg-black flex items-center justify-center">
          {photo && (
            <div className="relative inline-block">
              <img ref={imgRef} src={fileUrl(photo.current_path)} alt="" onLoad={onImgLoad}
                className="block max-w-full max-h-[55vh] select-none pointer-events-none" draggable={false} />
              <canvas
                ref={canvasRef}
                data-testid="eraser-canvas"
                className="absolute inset-0 w-full h-full cursor-crosshair touch-none"
                onMouseDown={start} onMouseMove={paint} onMouseUp={end} onMouseLeave={end}
                onTouchStart={start} onTouchMove={paint} onTouchEnd={end}
              />
            </div>
          )}
        </div>

        <div className="flex items-center gap-4">
          <span className="text-sm text-slate-400 shrink-0">Pincel</span>
          <Slider min={10} max={120} step={5} value={[brush]} onValueChange={(v) => setBrush(v[0])} className="flex-1" data-testid="eraser-brush" />
          <Button onClick={clear} variant="ghost" size="sm" className="text-slate-300 hover:bg-white/10"><Undo2 className="w-4 h-4 mr-1" /> Limpiar</Button>
        </div>

        <DialogFooter>
          <Button onClick={apply} disabled={!hasStrokes || busy} data-testid="eraser-apply"
            className="rounded-full bg-gradient-to-r from-violet-600 to-cyan-500 text-white font-semibold w-full">
            {busy ? <Loader2 className="w-4 h-4 animate-spin mr-1.5" /> : <Eraser className="w-4 h-4 mr-1.5" />} Borrar zona pintada
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
