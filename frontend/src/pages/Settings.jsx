import React, { useEffect, useRef, useState } from "react";
import { api, apiError } from "@/lib/api";
import Header from "@/components/Header";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Loader2, Upload, Stamp, Check } from "lucide-react";
import { toast } from "sonner";

const POSITIONS = [
  { key: "bottom-right", label: "Abajo derecha" },
  { key: "bottom-left", label: "Abajo izquierda" },
  { key: "top-right", label: "Arriba derecha" },
  { key: "top-left", label: "Arriba izquierda" },
  { key: "center", label: "Centro" },
];

export default function Settings() {
  const [wm, setWm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);

  useEffect(() => {
    api.get("/settings/watermark").then((r) => setWm(r.data)).catch((e) => { toast.error(apiError(e)); setWm({}); });
  }, []);

  const save = async (patch) => {
    setSaving(true);
    try {
      const { data } = await api.put("/settings/watermark", patch);
      setWm(data);
      toast.success("Ajustes guardados");
    } catch (e) { toast.error(apiError(e)); } finally { setSaving(false); }
  };

  const uploadLogo = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/settings/watermark/logo", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setWm(data);
      toast.success("Logo subido");
    } catch (e) { toast.error(apiError(e)); } finally { setUploading(false); }
  };

  if (!wm) return <div className="min-h-screen bg-background flex items-center justify-center"><Loader2 className="w-7 h-7 animate-spin text-cyan-400" /></div>;

  return (
    <div className="min-h-screen bg-background grain">
      <Header />
      <main className="max-w-2xl mx-auto px-4 sm:px-6 py-10" data-testid="settings-page">
        <div className="flex items-center gap-2 mb-8">
          <Stamp className="w-6 h-6 text-violet-400" />
          <h1 className="font-display text-3xl font-bold text-white">Ajustes</h1>
        </div>

        <section className="rounded-2xl border border-white/5 bg-[#15131C] p-6 space-y-6">
          <div>
            <h2 className="font-display text-xl font-semibold text-white">Marca de agua de la agencia</h2>
            <p className="text-sm text-slate-400 mt-1">Superpón tu logo en las fotos (al exportar) y en los vídeos.</p>
          </div>

          <div className="flex items-center justify-between">
            <Label className="text-slate-300">Activar marca de agua</Label>
            <Switch data-testid="wm-enabled" checked={!!wm.enabled} onCheckedChange={(v) => save({ enabled: v })} />
          </div>

          <div className="space-y-2">
            <Label className="text-slate-300">Logo {wm.logo_path && <span className="text-emerald-400 text-xs inline-flex items-center gap-1"><Check className="w-3 h-3" /> cargado</span>}</Label>
            <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" hidden data-testid="wm-logo-input"
              onChange={(e) => uploadLogo(e.target.files?.[0])} />
            <Button onClick={() => fileRef.current?.click()} disabled={uploading} data-testid="wm-upload-btn"
              variant="outline" className="rounded-full border-white/15 bg-white/5 hover:bg-white/10 text-white">
              {uploading ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : <Upload className="w-4 h-4 mr-1.5" />}
              {wm.logo_path ? "Cambiar logo" : "Subir logo (PNG con transparencia)"}
            </Button>
          </div>

          <div className="space-y-2">
            <Label className="text-slate-300">Posición</Label>
            <Select value={wm.position || "bottom-right"} onValueChange={(v) => save({ position: v })}>
              <SelectTrigger data-testid="wm-position" className="bg-secondary/60 border-white/10"><SelectValue /></SelectTrigger>
              <SelectContent className="bg-[#1E1A29] border-white/10 text-white">
                {POSITIONS.map((p) => <SelectItem key={p.key} value={p.key}>{p.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label className="text-slate-300">Opacidad</Label>
              <span className="text-sm text-slate-400 tabular-nums">{Math.round((wm.opacity ?? 0.75) * 100)}%</span>
            </div>
            <Slider data-testid="wm-opacity" min={10} max={100} step={5} value={[Math.round((wm.opacity ?? 0.75) * 100)]}
              onValueCommit={(v) => save({ opacity: v[0] / 100 })} />
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label className="text-slate-300">Tamaño</Label>
              <span className="text-sm text-slate-400 tabular-nums">{Math.round((wm.scale ?? 0.18) * 100)}%</span>
            </div>
            <Slider data-testid="wm-scale" min={5} max={50} step={1} value={[Math.round((wm.scale ?? 0.18) * 100)]}
              onValueCommit={(v) => save({ scale: v[0] / 100 })} />
          </div>

          {saving && <p className="text-xs text-slate-500 flex items-center gap-1.5"><Loader2 className="w-3 h-3 animate-spin" /> Guardando…</p>}
        </section>
      </main>
    </div>
  );
}
