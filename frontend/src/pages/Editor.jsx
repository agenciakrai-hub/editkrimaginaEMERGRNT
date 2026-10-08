import React, { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, apiError, fileUrl, exportUrl } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import BeforeAfterSlider from "@/components/BeforeAfterSlider";
import EraserDialog from "@/components/EraserDialog";
import Logo from "@/components/Logo";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuLabel, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from "@/components/ui/dialog";
import { motion } from "framer-motion";
import {
  ArrowLeft, ChevronLeft, ChevronRight, RotateCcw, Zap, Loader2, Download, Undo2, ShieldCheck, GitCompareArrows, Image as ImageIcon,
  Sun, Sparkles, SlidersHorizontal, Moon, Eraser, Trees, PanelTop, Sofa, Maximize, Wand2, Frame, Stars,
} from "lucide-react";
import { toast } from "sonner";

const ICONS = {
  auto: Wand2, sky: Sun, light: Sparkles, straighten: SlidersHorizontal, twilight: Moon,
  declutter: Eraser, lawn: Trees, window_pull: PanelTop, staging: Sofa, upscale: Maximize,
  perspective_pro: Frame, auto_pro: Stars,
};
const STYLES = [
  { key: "nordico", label: "Nórdico" },
  { key: "moderno", label: "Moderno" },
  { key: "minimal", label: "Minimalista" },
  { key: "clasico", label: "Clásico" },
];
const EXPORT_PRESETS = [
  { key: "original", label: "Original (máxima calidad)" },
  { key: "idealista", label: "Idealista · 2048×1536" },
  { key: "fotocasa", label: "Fotocasa · 2000×1500" },
  { key: "zillow", label: "Zillow · 2048×1536" },
  { key: "mls", label: "MLS · 1024×768" },
];

export default function Editor() {
  const { id, photoId } = useParams();
  const navigate = useNavigate();
  const { user, updateCredits } = useAuth();
  const [photo, setPhoto] = useState(null);
  const [actions, setActions] = useState([]);
  const [compare, setCompare] = useState(false);
  const [processing, setProcessing] = useState(false);

  const [confirmAction, setConfirmAction] = useState(null);
  const [style, setStyle] = useState("nordico");
  const [disclosure, setDisclosure] = useState(true);
  const [eraserOpen, setEraserOpen] = useState(false);
  const [wmOnExport, setWmOnExport] = useState(false);

  const doExport = (preset) => {
    const a = document.createElement("a");
    a.href = exportUrl(photoId, preset, wmOnExport && !!user?.watermark?.enabled);
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  const [photos, setPhotos] = useState([]);
  const [historyBusy, setHistoryBusy] = useState(false);
  const busy = processing || historyBusy;
  const photoIndex = photos.findIndex((p) => p.id === photoId);

  useEffect(() => {
    let cancelled = false;
    setPhoto(null);
    setConfirmAction(null);
    setEraserOpen(false);
    setCompare(false);
    Promise.all([api.get(`/photos/${photoId}`), api.get("/actions"), api.get(`/properties/${id}/photos`)])
      .then(([ph, ac, list]) => {
        if (cancelled) return;
        setPhoto(ph.data);
        setActions(ac.data);
        setPhotos(list.data);
        setCompare(ph.data.edits?.length > 0);
      }).catch((err) => {
        if (cancelled) return;
        toast.error(apiError(err));
        navigate(`/app/property/${id}`);
      });
    return () => { cancelled = true; };
  }, [photoId, id, navigate]);

  const goPhoto = useCallback((delta) => {
    if (busy || !photo || confirmAction || eraserOpen) return;
    const target = photos[photoIndex + delta];
    if (photoIndex >= 0 && target) navigate(`/app/property/${id}/photo/${target.id}`);
  }, [busy, photo, confirmAction, eraserOpen, photos, photoIndex, id, navigate]);

  useEffect(() => {
    const onKey = (event) => {
      if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey ||
          event.target.closest?.('input, textarea, select, [contenteditable="true"], [role="dialog"], [role="combobox"]')) return;
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        event.preventDefault();
        goPhoto(event.key === "ArrowLeft" ? -1 : 1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [goPhoto]);

  const openConfirm = (action) => {
    setDisclosure(action.disclosure_default);
    setConfirmAction(action);
  };

  const apply = async () => {
    const action = confirmAction;
    setConfirmAction(null);
    setProcessing(true);
    try {
      const body = { action: action.key, disclosure };
      if (action.key === "staging") body.options = { style };
      const { data } = await api.post(`/photos/${photoId}/edit`, body);
      setPhoto(data.photo);
      updateCredits(data.credits);
      setCompare(true);
      toast.success(`${action.label} aplicado`);
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setProcessing(false);
    }
  };

  const applyAuto = async () => {
    setProcessing(true);
    try {
      const { data } = await api.post(`/photos/${photoId}/edit`, { action: "auto" });
      setPhoto(data.photo);
      updateCredits(data.credits);
      setCompare(true);
      toast.success("Mejora automática aplicada ✨");
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setProcessing(false);
    }
  };

  const revert = async () => {
    if (busy) return;
    setHistoryBusy(true);
    try {
      const { data } = await api.post(`/photos/${photoId}/revert`);
      setPhoto(data);
      setCompare(false);
      toast.success("Foto restaurada al original");
    } catch (err) {
      toast.error(apiError(err));
    } finally { setHistoryBusy(false); }
  };

  const undo = async () => {
    if (busy) return;
    setHistoryBusy(true);
    try {
      const { data } = await api.post(`/photos/${photoId}/undo`);
      setPhoto(data);
      setCompare(data.edits?.length > 0);
      toast.success("Última edición deshecha");
    } catch (err) { toast.error(apiError(err)); }
    finally { setHistoryBusy(false); }
  };

  const download = async () => {
    doExport("original");
  };

  if (!photo) {
    return <div className="min-h-screen flex items-center justify-center bg-background"><Loader2 className="w-7 h-7 animate-spin text-cyan-400" /></div>;
  }

  const hasEdits = photo.edits?.length > 0;
  const esenciales = actions.filter((a) => a.category === "esencial");
  const premium = actions.filter((a) => a.category === "premium" && !["auto_pro", "complete", "complete_exterior"].includes(a.key));
  const ToolButton = ({ a }) => {
    const Icon = ICONS[a.key] || Sparkles;
    return (
      <button
        onClick={() => openConfirm(a)}
        disabled={busy}
        data-testid={`apply-${a.key}-btn`}
        className="w-full text-left rounded-xl border border-white/5 bg-[#15131C] hover:border-cyan-500/40 hover:bg-[#1E1A29] p-3 flex items-start gap-3 transition-colors disabled:opacity-50"
      >
        <div className="w-9 h-9 shrink-0 rounded-lg bg-gradient-to-br from-violet-600/20 to-cyan-500/20 border border-white/10 flex items-center justify-center">
          <Icon className="w-4 h-4 text-cyan-400" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm font-medium text-white truncate">{a.label}</span>
            {a.cost === 0 ? (
              <span className="text-[10px] font-semibold text-emerald-400 shrink-0">GRATIS</span>
            ) : (
              <span className="text-[10px] font-semibold text-cyan-300 flex items-center gap-0.5 shrink-0"><Zap className="w-2.5 h-2.5" />{a.cost}</span>
            )}
          </div>
          <p className="text-xs text-slate-500 mt-0.5 line-clamp-2">{a.description}</p>
        </div>
      </button>
    );
  };

  return (
    <div className="h-screen flex flex-col bg-background overflow-hidden">
      {/* Top bar */}
      <div className="h-14 shrink-0 border-b border-white/5 backdrop-blur-xl bg-[#15131C]/80 flex items-center justify-between px-4 gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <button disabled={busy} onClick={() => navigate(`/app/property/${id}`)} data-testid="editor-back"
            className="flex items-center gap-1.5 text-sm text-slate-300 hover:text-white">
            <ArrowLeft className="w-4 h-4" /> Volver
          </button>
          <div className="hidden sm:block"><Logo showText={false} size={26} /></div>
          <span className="hidden sm:block text-sm text-slate-400 truncate max-w-[180px]">{photo.original_filename}</span>
        </div>
        <div className="flex items-center gap-2 sm:gap-3">
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-violet-500/40 bg-violet-500/10" data-testid="editor-credits">
            <Zap className="w-3.5 h-3.5 text-cyan-400 fill-cyan-400" />
            <span className="text-sm font-semibold text-white tabular-nums">{user?.unlimited ? "∞" : user?.credits}</span>
          </div>
          {hasEdits && (
            <Button onClick={undo} disabled={busy || !photo.can_undo} variant="outline" size="sm" data-testid="undo-btn"
              aria-label="Deshacer última edición" title={photo.can_undo ? "Deshacer solo la última edición" : "Esta edición antigua no conserva el paso anterior"}
              className="rounded-full border-white/15 bg-white/5 hover:bg-white/10 text-white">
              {historyBusy ? <Loader2 className="w-4 h-4 animate-spin sm:mr-1.5" /> : <Undo2 className="w-4 h-4 sm:mr-1.5" />} <span className="hidden sm:inline">Deshacer</span>
            </Button>
          )}
          {hasEdits && (
            <Button disabled={busy} aria-label="Restaurar foto original" title="Eliminar todas las ediciones y volver al original" onClick={revert} variant="outline" size="sm" data-testid="revert-btn"
              className="rounded-full border-white/15 bg-white/5 hover:bg-white/10 text-white">
              <RotateCcw className="w-4 h-4 sm:mr-1.5" /> <span className="hidden sm:inline">Restaurar</span>
            </Button>
          )}
          <Button disabled={busy} onClick={() => setEraserOpen(true)} variant="outline" size="sm" data-testid="open-eraser-btn"
            className="rounded-full border-white/15 bg-white/5 hover:bg-white/10 text-white">
            <Eraser className="w-4 h-4 sm:mr-1.5" /> <span className="hidden sm:inline">Borrador</span>
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="sm" data-testid="download-btn"
                className="rounded-full bg-gradient-to-r from-violet-600 to-cyan-500 hover:brightness-110 text-white font-semibold transition-[filter]">
                <Download className="w-4 h-4 sm:mr-1.5" /> <span className="hidden sm:inline">Descargar</span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="bg-[#1E1A29] border-white/10 text-white w-60">
              {user?.watermark?.enabled && user?.watermark?.logo_path && (
                <>
                  <DropdownMenuItem data-testid="toggle-wm-export" onClick={(e) => { e.preventDefault(); setWmOnExport((v) => !v); }}
                    className="cursor-pointer focus:bg-white/10 justify-between">
                    <span>Marca de agua</span>
                    <span className={wmOnExport ? "text-cyan-300" : "text-slate-500"}>{wmOnExport ? "ON" : "OFF"}</span>
                  </DropdownMenuItem>
                  <DropdownMenuSeparator className="bg-white/10" />
                </>
              )}
              <DropdownMenuLabel className="text-slate-400 text-xs">Tamaño / portal</DropdownMenuLabel>
              {EXPORT_PRESETS.map((p) => (
                <DropdownMenuItem key={p.key} data-testid={`export-${p.key}`} onClick={() => doExport(p.key)}
                  className="cursor-pointer focus:bg-white/10">{p.label}</DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
        {/* Canvas */}
        <div className="flex-1 relative bg-[#050505] flex items-center justify-center p-4 sm:p-8 min-h-0">
          {photos.length > 1 && (
            <>
              <button onClick={() => goPhoto(-1)} disabled={busy || photoIndex <= 0} aria-label="Foto anterior" title="Foto anterior (←)" data-testid="previous-photo-btn"
                className="absolute left-2 sm:left-4 top-1/2 -translate-y-1/2 z-20 rounded-full p-2 bg-black/65 hover:bg-black/85 text-white border border-white/20 disabled:opacity-25 disabled:cursor-not-allowed">
                <ChevronLeft className="w-6 h-6" />
              </button>
              <button onClick={() => goPhoto(1)} disabled={busy || photoIndex < 0 || photoIndex >= photos.length - 1} aria-label="Foto siguiente" title="Foto siguiente (→)" data-testid="next-photo-btn"
                className="absolute right-2 sm:right-4 top-1/2 -translate-y-1/2 z-20 rounded-full p-2 bg-black/65 hover:bg-black/85 text-white border border-white/20 disabled:opacity-25 disabled:cursor-not-allowed">
                <ChevronRight className="w-6 h-6" />
              </button>
              <span className="absolute top-4 left-4 z-20 text-xs px-3 py-1.5 rounded-full bg-black/65 text-white border border-white/10" data-testid="photo-position">{photoIndex + 1} / {photos.length}</span>
            </>
          )}
          {processing && (
            <div className="absolute inset-0 z-30 bg-black/70 backdrop-blur-sm flex flex-col items-center justify-center gap-4" data-testid="editor-processing">
              <div className="relative">
                <Loader2 className="w-10 h-10 animate-spin text-cyan-400" />
                <Sparkles className="w-4 h-4 text-violet-400 absolute inset-0 m-auto" />
              </div>
              <p className="text-slate-300 text-sm">Aplicando IA… esto puede tardar unos segundos</p>
            </div>
          )}

          {hasEdits && compare ? (
            <BeforeAfterSlider
              beforePath={photo.original_path}
              afterPath={photo.current_path}
              className="max-w-full max-h-full w-full h-full"
            />
          ) : (
            <img src={fileUrl(photo.current_path)} alt="" className="max-w-full max-h-full object-contain" />
          )}

          {photo.disclosure && (
            <div className="absolute bottom-4 left-4 z-20">
              <span className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full bg-black/70 text-amber-300 border border-amber-500/30" data-testid="disclosure-badge">
                <ShieldCheck className="w-3.5 h-3.5" /> Imagen editada digitalmente
              </span>
            </div>
          )}

          {hasEdits && (
            <button onClick={() => setCompare((c) => !c)} data-testid="toggle-compare"
              className="absolute top-4 right-4 z-20 flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full bg-black/60 hover:bg-black/80 text-white border border-white/10 transition-colors">
              {compare ? <ImageIcon className="w-3.5 h-3.5" /> : <GitCompareArrows className="w-3.5 h-3.5" />}
              {compare ? "Ver resultado" : "Comparar"}
            </button>
          )}
        </div>

        {/* Tools panel */}
        <aside className="w-full lg:w-80 shrink-0 border-t lg:border-t-0 lg:border-l border-white/5 bg-[#0d0b13] overflow-y-auto max-h-[45vh] lg:max-h-none">
          <div className="p-4 space-y-6">
            <button
              onClick={applyAuto}
              disabled={busy}
              data-testid="apply-auto-btn"
              className="group w-full rounded-xl p-[1.5px] bg-gradient-to-r from-violet-600 to-cyan-500 disabled:opacity-50 hover:brightness-110 transition-[filter]"
            >
              <div className="rounded-[10px] bg-[#0d0b13] group-hover:bg-[#12101a] transition-colors p-4 flex items-center gap-3 text-left">
                <div className="w-10 h-10 shrink-0 rounded-lg bg-gradient-to-br from-violet-600 to-cyan-500 flex items-center justify-center">
                  <Wand2 className="w-5 h-5 text-white" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-display font-semibold text-white">Mejora rápida</span>
                    <span className="text-[10px] font-semibold text-emerald-400">GRATIS</span>
                  </div>
                  <p className="text-xs text-slate-400 mt-0.5">Luz, color y blancos limpios en un clic</p>
                </div>
                <Sparkles className="w-4 h-4 text-cyan-400 shrink-0" />
              </div>
            </button>

            {actions.find((a) => a.key === "auto_pro") && (
              <button
                onClick={() => openConfirm(actions.find((a) => a.key === "auto_pro"))}
                disabled={busy}
                data-testid="apply-auto-pro-btn"
                className="group w-full rounded-xl p-[1.5px] bg-gradient-to-r from-amber-400 via-fuchsia-500 to-cyan-400 disabled:opacity-50 hover:brightness-110 transition-[filter]"
              >
                <div className="rounded-[10px] bg-[#0d0b13] group-hover:bg-[#12101a] transition-colors p-4 flex items-center gap-3 text-left">
                  <div className="w-10 h-10 shrink-0 rounded-lg bg-gradient-to-br from-amber-400 via-fuchsia-500 to-cyan-400 flex items-center justify-center">
                    <Stars className="w-5 h-5 text-white" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-display font-semibold text-white">Mejora Pro</span>
                      <span className="text-[10px] font-semibold text-cyan-300 flex items-center gap-0.5"><Zap className="w-2.5 h-2.5" />{actions.find((a) => a.key === "auto_pro")?.cost}</span>
                    </div>
                    <p className="text-xs text-slate-400 mt-0.5">Acabado profesional con IA · recupera ventanas</p>
                  </div>
                  <Sparkles className="w-4 h-4 text-fuchsia-300 shrink-0" />
                </div>
              </button>
            )}

            {actions.find((a) => a.key === "complete") && (
              <button
                onClick={() => openConfirm(actions.find((a) => a.key === "complete"))}
                disabled={busy}
                data-testid="apply-complete-btn"
                className="group w-full rounded-xl p-[1.5px] bg-gradient-to-r from-amber-400 via-fuchsia-500 to-cyan-400 disabled:opacity-50 hover:brightness-110 transition-[filter]"
              >
                <div className="rounded-[10px] bg-[#0d0b13] group-hover:bg-[#12101a] transition-colors p-4 flex items-center gap-3 text-left">
                  <div className="w-10 h-10 shrink-0 rounded-lg bg-gradient-to-br from-amber-400 via-fuchsia-500 to-cyan-400 flex items-center justify-center">
                    <Stars className="w-5 h-5 text-white" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-display font-semibold text-white">Mejora completa · Interior</span>
                      <span className="text-[10px] font-semibold text-cyan-300 flex items-center gap-0.5"><Zap className="w-2.5 h-2.5" />{actions.find((a) => a.key === "complete")?.cost}</span>
                    </div>
                    <p className="text-xs text-slate-400 mt-0.5">Blancos neutros · ventanas, limpieza y perspectiva</p>
                  </div>
                  <Sparkles className="w-4 h-4 text-fuchsia-300 shrink-0" />
                </div>
              </button>
            )}

            {actions.find((a) => a.key === "complete_exterior") && (
              <button
                onClick={() => openConfirm(actions.find((a) => a.key === "complete_exterior"))}
                disabled={busy}
                data-testid="apply-complete_exterior-btn"
                className="group w-full rounded-xl p-[1.5px] bg-gradient-to-r from-amber-400 via-fuchsia-500 to-cyan-400 disabled:opacity-50 hover:brightness-110 transition-[filter]"
              >
                <div className="rounded-[10px] bg-[#0d0b13] group-hover:bg-[#12101a] transition-colors p-4 flex items-center gap-3 text-left">
                  <div className="w-10 h-10 shrink-0 rounded-lg bg-gradient-to-br from-amber-400 via-fuchsia-500 to-cyan-400 flex items-center justify-center">
                    <Stars className="w-5 h-5 text-white" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-display font-semibold text-white">Mejora completa · Exterior</span>
                      <span className="text-[10px] font-semibold text-cyan-300 flex items-center gap-0.5"><Zap className="w-2.5 h-2.5" />{actions.find((a) => a.key === "complete_exterior")?.cost}</span>
                    </div>
                    <p className="text-xs text-slate-400 mt-0.5">Día soleado · cielo, fachadas, limpieza y perspectiva</p>
                  </div>
                  <Sparkles className="w-4 h-4 text-fuchsia-300 shrink-0" />
                </div>
              </button>
            )}

            <div>
              <h3 className="text-xs uppercase tracking-[0.2em] font-semibold text-violet-400 mb-3">Esenciales · Gratis</h3>
              <div className="space-y-2">
                {esenciales.map((a) => <ToolButton key={a.key} a={a} />)}
              </div>
            </div>
            <div>
              <h3 className="text-xs uppercase tracking-[0.2em] font-semibold text-cyan-400 mb-3">Premium · Créditos</h3>
              <div className="space-y-2">
                {premium.map((a) => <ToolButton key={a.key} a={a} />)}
              </div>
            </div>
            {hasEdits && (
              <div className="rounded-xl border border-white/5 bg-[#15131C] p-4">
                <h4 className="text-sm font-medium text-white mb-2">Ediciones aplicadas</h4>
                <div className="flex flex-wrap gap-1.5">
                  {photo.edits.map((e, i) => (
                    <span key={`${e.action}-${e.at || i}`} className="text-[11px] px-2 py-0.5 rounded-full bg-cyan-500/15 text-cyan-300 border border-cyan-500/20">{e.label}</span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </aside>
      </div>

      {/* Confirm modal */}
      <Dialog open={!!confirmAction} onOpenChange={(o) => !o && setConfirmAction(null)}>
        <DialogContent className="bg-[#1E1A29] border-white/10 text-white">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2">
              {confirmAction && React.createElement(ICONS[confirmAction.key] || Sparkles, { className: "w-5 h-5 text-cyan-400" })}
              {confirmAction?.label}
            </DialogTitle>
            <DialogDescription className="text-slate-400">{confirmAction?.description}</DialogDescription>
          </DialogHeader>

          {confirmAction?.key === "staging" && (
            <div className="space-y-2 mt-1">
              <Label className="text-slate-300 text-sm">Estilo de mobiliario</Label>
              <Select value={style} onValueChange={setStyle}>
                <SelectTrigger data-testid="staging-style-select" className="bg-secondary/60 border-white/10">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-[#1E1A29] border-white/10 text-white">
                  {STYLES.map((s) => <SelectItem key={s.key} value={s.key} className="focus:bg-white/10">{s.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          )}

          {confirmAction && confirmAction.disclosure_default && (
            <div className="flex items-center justify-between rounded-xl bg-black/30 border border-white/10 p-3 mt-1">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-amber-300" />
                <span className="text-sm text-slate-300">Etiqueta "Editada digitalmente"</span>
              </div>
              <Switch checked={disclosure} onCheckedChange={setDisclosure} data-testid="disclosure-toggle" />
            </div>
          )}

          <div className="flex items-center justify-between rounded-xl bg-black/30 border border-white/10 p-4 mt-1">
            <span className="text-sm text-slate-300">Coste</span>
            {confirmAction?.cost === 0 ? (
              <span className="font-semibold text-emerald-400" data-testid="confirm-cost">Gratis</span>
            ) : (
              <span className="flex items-center gap-1.5 font-semibold" data-testid="confirm-cost">
                <Zap className="w-4 h-4 text-cyan-400 fill-cyan-400" />{confirmAction?.cost} créditos
              </span>
            )}
          </div>

          {confirmAction && !user?.unlimited && confirmAction.cost > (user?.credits ?? 0) ? (
            <p className="text-sm text-red-400 text-center">Créditos insuficientes.</p>
          ) : null}

          <DialogFooter>
            <Button
              onClick={apply}
              disabled={busy || (confirmAction && !user?.unlimited && confirmAction.cost > (user?.credits ?? 0))}
              data-testid="confirm-apply-btn"
              className="rounded-full bg-gradient-to-r from-violet-600 to-cyan-500 hover:brightness-110 text-white font-semibold transition-[filter] w-full">
              Aplicar {confirmAction?.cost === 0 ? "gratis" : `· ${confirmAction?.cost} créditos`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <EraserDialog
        open={eraserOpen}
        onOpenChange={setEraserOpen}
        photo={photo}
        onDone={(p) => { setPhoto(p); setCompare(true); }}
      />
    </div>
  );
}
