import React, { useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import AuthImage from "@/components/AuthImage";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Clapperboard, Monitor, Smartphone, Music, Zap, Wand2, Info } from "lucide-react";
import { toast } from "sonner";

const STYLE_OPTIONS = [
  { v: "zoom_in", l: "Acercar cámara" },
  { v: "zoom_out", l: "Alejar cámara" },
  { v: "cinematic", l: "Zoom Cinemático" },
  { v: "pan_h", l: "Paneo Horizontal" },
  { v: "pan_v", l: "Paneo Vertical" },
  { v: "drone", l: "Drone Virtual" },
  { v: "interior_tour", l: "Tour Interior" },
  { v: "pool", l: "Piscina Animada" },
  { v: "fireplace", l: "Chimenea Encendida" },
  { v: "lights", l: "Luces Encendiéndose" },
  { v: "sky", l: "Cielo Dinámico" },
  { v: "before_after", l: "Antes y Después" },
  { v: "day_night", l: "Día a Noche" },
  { v: "empty", l: "Vacío" },
  { v: "furnished", l: "Amueblado" },
  { v: "transition", l: "Transición" },
  { v: "custom", l: "Personalizado" },
];

const MOTION_OPTIONS = [
  { v: "none", l: "Sin movimiento" },
  { v: "zoom_in", l: "Zoom In" },
  { v: "zoom_out", l: "Zoom Out" },
  { v: "pan_left", l: "Pan Izquierda" },
  { v: "pan_right", l: "Pan Derecha" },
  { v: "tilt_up", l: "Tilt Arriba" },
  { v: "tilt_down", l: "Tilt Abajo" },
  { v: "ken_burns", l: "Ken Burns" },
  { v: "dolly", l: "Dolly" },
  { v: "ai", l: "Movimiento IA" },
];

const DURATIONS = [2, 3, 4, 5, 6];

// Styles that need a real AI image-to-video engine (not camera motion). We still render them with
// a fitting camera move and store the prompt.
const AI_STYLES = new Set(["pool", "fireplace", "lights", "day_night", "before_after", "empty", "furnished"]);

const STYLE_TO_MOTION = {
  zoom_in: "zoom_in", zoom_out: "zoom_out", cinematic: "dolly", pan_h: "pan_right", pan_v: "tilt_up",
  drone: "ken_burns", interior_tour: "pan_right", pool: "ken_burns", fireplace: "none", lights: "none",
  sky: "ken_burns", before_after: "none", day_night: "none", empty: "none", furnished: "none",
  transition: "ken_burns", custom: "ken_burns",
};

const COSTS = { tour: 12, reel: 8 };
const miniSel = "h-8 text-xs bg-secondary/60 border-white/10";

export default function VideoStudioDialog({ open, onOpenChange, photos, propertyId, onStarted }) {
  const { user } = useAuth();
  const owner = user?.unlimited;
  const [format, setFormat] = useState("tour");
  const [music, setMusic] = useState(true);
  const [agencyName, setAgencyName] = useState("");
  const [configs, setConfigs] = useState({});
  const [bulkStyle, setBulkStyle] = useState("cinematic");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      const init = {};
      photos.forEach((p) => {
        init[p.id] = { style: "cinematic", motion: "dolly", duration: 3, prompt: "" };
      });
      setConfigs(init);
    }
  }, [open, photos]);

  const setCfg = (id, patch) => setConfigs((c) => ({ ...c, [id]: { ...c[id], ...patch } }));

  const onStyle = (id, style) => setCfg(id, { style, motion: STYLE_TO_MOTION[style] || "ken_burns" });

  const applyToAll = () => {
    const motion = STYLE_TO_MOTION[bulkStyle] || "ken_burns";
    setConfigs((c) => {
      const next = { ...c };
      photos.forEach((p) => {
        next[p.id] = { ...next[p.id], style: bulkStyle, motion };
      });
      return next;
    });
    toast.success("Estilo aplicado a todas las fotos");
  };

  const submit = async () => {
    setSubmitting(true);
    try {
      const clips = photos.map((p) => ({
        photo_id: p.id,
        style: configs[p.id]?.style,
        motion: configs[p.id]?.motion,
        duration: configs[p.id]?.duration,
        prompt: configs[p.id]?.prompt || "",
      }));
      const { data } = await api.post(`/properties/${propertyId}/video`, {
        format, music, agency_name: agencyName || undefined, clips,
      });
      onOpenChange(false);
      toast.success("Generando video con tus estilos…");
      onStarted?.(data);
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setSubmitting(false);
    }
  };

  const cost = owner ? 0 : COSTS[format];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[#1E1A29] border-white/10 text-white max-w-3xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2"><Clapperboard className="w-5 h-5 text-cyan-400" /> Estudio de video</DialogTitle>
          <DialogDescription className="text-slate-400">Configura estilo, movimiento, duración y prompt por cada foto.</DialogDescription>
        </DialogHeader>

        {/* Format + music */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex gap-2">
            <button onClick={() => setFormat("tour")} data-testid="video-format-tour"
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm border ${format === "tour" ? "border-cyan-500/60 bg-cyan-500/10 text-cyan-200" : "border-white/10 text-slate-300"}`}>
              <Monitor className="w-4 h-4" /> Tour 16:9
            </button>
            <button onClick={() => setFormat("reel")} data-testid="video-format-reel"
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm border ${format === "reel" ? "border-violet-500/60 bg-violet-500/10 text-violet-200" : "border-white/10 text-slate-300"}`}>
              <Smartphone className="w-4 h-4" /> Reel 9:16
            </button>
          </div>
          <div className="flex items-center gap-2 ml-auto">
            <Music className="w-4 h-4 text-cyan-400" /><span className="text-sm text-slate-300">Música</span>
            <Switch checked={music} onCheckedChange={setMusic} data-testid="video-music-toggle" />
          </div>
        </div>

        <Input value={agencyName} onChange={(e) => setAgencyName(e.target.value)} data-testid="video-agency-input"
          placeholder="Nombre de la agencia (portada, opcional)" className="bg-secondary/60 border-white/10" />

        {/* Bulk apply */}
        <div className="flex flex-wrap items-center gap-2 rounded-xl bg-black/30 border border-white/10 p-2.5">
          <span className="text-xs text-slate-400 flex items-center gap-1"><Wand2 className="w-3.5 h-3.5" /> Aplicar a todas:</span>
          <Select value={bulkStyle} onValueChange={setBulkStyle}>
            <SelectTrigger data-testid="bulk-style-select" className="h-8 text-xs bg-secondary/60 border-white/10 w-48"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-[#1E1A29] border-white/10 text-white max-h-64">
              {STYLE_OPTIONS.map((o) => <SelectItem key={o.v} value={o.v} className="text-xs focus:bg-white/10">{o.l}</SelectItem>)}
            </SelectContent>
          </Select>
          <Button onClick={applyToAll} size="sm" data-testid="apply-all-btn"
            className="h-8 rounded-full bg-white/10 hover:bg-white/20 text-white text-xs">Aplicar a todas</Button>
        </div>

        {/* Per-photo controls */}
        <div className="flex-1 overflow-y-auto -mr-2 pr-2 space-y-2" data-testid="clip-config-list">
          {photos.map((p, idx) => {
            const cfg = configs[p.id] || {};
            const aiStyle = AI_STYLES.has(cfg.style);
            return (
              <div key={p.id} data-testid={`clip-row-${p.id}`}
                className="flex items-start gap-3 rounded-xl border border-white/5 bg-[#15131C] p-2.5">
                <div className="relative w-16 h-16 shrink-0 rounded-lg overflow-hidden bg-secondary/40">
                  <AuthImage path={p.current_path} className="w-full h-full object-cover" />
                  <span className="absolute top-0.5 left-0.5 text-[9px] px-1 rounded bg-black/70 text-white">{idx + 1}</span>
                </div>
                <div className="flex-1 min-w-0 grid grid-cols-2 sm:grid-cols-3 gap-2">
                  <Select value={cfg.style} onValueChange={(v) => onStyle(p.id, v)}>
                    <SelectTrigger data-testid={`style-${p.id}`} className={miniSel}><SelectValue placeholder="Estilo" /></SelectTrigger>
                    <SelectContent className="bg-[#1E1A29] border-white/10 text-white max-h-64">
                      {STYLE_OPTIONS.map((o) => <SelectItem key={o.v} value={o.v} className="text-xs focus:bg-white/10">{o.l}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  <Select value={cfg.motion} onValueChange={(v) => setCfg(p.id, { motion: v })}>
                    <SelectTrigger data-testid={`motion-${p.id}`} className={miniSel}><SelectValue placeholder="Movimiento" /></SelectTrigger>
                    <SelectContent className="bg-[#1E1A29] border-white/10 text-white max-h-64">
                      {MOTION_OPTIONS.map((o) => <SelectItem key={o.v} value={o.v} className="text-xs focus:bg-white/10">{o.l}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  <Select value={String(cfg.duration)} onValueChange={(v) => setCfg(p.id, { duration: Number(v) })}>
                    <SelectTrigger data-testid={`duration-${p.id}`} className={miniSel}><SelectValue placeholder="Duración" /></SelectTrigger>
                    <SelectContent className="bg-[#1E1A29] border-white/10 text-white">
                      {DURATIONS.map((d) => <SelectItem key={d} value={String(d)} className="text-xs focus:bg-white/10">{d}s</SelectItem>)}
                    </SelectContent>
                  </Select>
                  <Input value={cfg.prompt || ""} onChange={(e) => setCfg(p.id, { prompt: e.target.value })}
                    data-testid={`prompt-${p.id}`} placeholder="Prompt libre (opcional)"
                    className="col-span-2 sm:col-span-3 h-8 text-xs bg-secondary/60 border-white/10" />
                  {aiStyle && (
                    <span className="col-span-2 sm:col-span-3 text-[10px] text-amber-300/80 flex items-center gap-1">
                      <Info className="w-3 h-3" /> Estilo con IA de contenido: se activará próximamente; por ahora usa movimiento de cámara + tu prompt.
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        <DialogFooter className="border-t border-white/10 pt-3">
          <div className="flex items-center gap-2 mr-auto text-sm">
            {owner ? <span className="text-emerald-400 font-semibold">Gratis (∞)</span> :
              <span className="flex items-center gap-1.5 font-semibold text-white"><Zap className="w-4 h-4 text-cyan-400 fill-cyan-400" />{cost} créditos</span>}
          </div>
          <Button onClick={submit} disabled={submitting || !photos.length} data-testid="video-confirm"
            className="rounded-full bg-gradient-to-r from-violet-600 to-cyan-500 hover:brightness-110 text-white font-semibold transition-[filter]">
            {submitting ? "Generando…" : `Generar video (${photos.length} fotos)`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
