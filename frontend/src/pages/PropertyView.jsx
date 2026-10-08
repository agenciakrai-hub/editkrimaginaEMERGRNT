import React, { useEffect, useRef, useState, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { api, apiError, fileUrl, downloadAllUrl } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import Header from "@/components/Header";
import AuthImage from "@/components/AuthImage";
import VideoStudioDialog from "@/components/VideoStudioDialog";
import VideoTimer from "@/components/VideoTimer";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuLabel, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { motion } from "framer-motion";
import {
  Upload, Loader2, ChevronRight, Trash2, Wand2, Zap, ImageOff, Layers, ShieldCheck, CheckCircle2,
  Film, Music, Clapperboard, Download, Smartphone, Monitor,
} from "lucide-react";
import { toast } from "sonner";

const PORTAL_PRESETS = [
  { key: "original", label: "Original (máxima calidad)" },
  { key: "idealista", label: "Idealista · 2048×1536" },
  { key: "fotocasa", label: "Fotocasa · 2000×1500" },
  { key: "zillow", label: "Zillow · 2048×1536" },
  { key: "mls", label: "MLS · 1024×768" },
];

export default function PropertyView() {
  const { id } = useParams();
  const navigate = useNavigate();

  const downloadZip = (preset, watermark) => {
    const a = document.createElement("a");
    a.href = downloadAllUrl(id, preset, watermark);
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
    toast.success("Preparando la descarga…");
  };
  const { updateCredits, refresh } = useAuth();
  const fileRef = useRef(null);
  const [prop, setProp] = useState(null);
  const [photos, setPhotos] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const selectedPhotos = photos.filter((p) => selectedIds.includes(p.id));
  const togglePhoto = (photoId) => setSelectedIds((prev) => prev.includes(photoId) ? prev.filter((v) => v !== photoId) : [...prev, photoId]);
  useEffect(() => { setSelectedIds([]); }, [id]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [actions, setActions] = useState([]);

  const [batchOpen, setBatchOpen] = useState(false);
  const [batchAction, setBatchAction] = useState("");
  const [job, setJob] = useState(null);

  const [videos, setVideos] = useState([]);
  const [videoOpen, setVideoOpen] = useState(false);

  const handleVideoStarted = async () => {    try {
      const me = await api.get("/auth/me");
      updateCredits(me.data.credits);
    } catch (e) {
      console.error("No se pudo actualizar créditos", e);
    }
    loadVideos();
  };

  const load = useCallback(async () => {
    try {
      const [p, ph] = await Promise.all([
        api.get(`/properties/${id}`),
        api.get(`/properties/${id}/photos`),
      ]);
      setProp(p.data);
      setPhotos(ph.data);
    } catch (err) {
      toast.error(apiError(err));
      navigate("/app");
    } finally {
      setLoading(false);
    }
  }, [id, navigate]);

  useEffect(() => {
    load();
    loadVideos();
    api.get("/actions").then(({ data }) => setActions(data)).catch(() => {});
  }, [load]);

  const loadVideos = useCallback(async () => {
    try {
      const { data } = await api.get(`/properties/${id}/videos`);
      setVideos(data);
      if (data.some((v) => v.status === "processing")) {
        setTimeout(loadVideos, 4000);
      }
    } catch (err) {
      console.error("No se pudieron cargar los videos", err);
    }
  }, [id]);

  const MAX_DIM = 2560;

  // Downscale/re-encode large images in the browser so each upload stays small (avoids 413).
  const optimizeImage = (file) =>
    new Promise((resolve) => {
      if (!file.type?.startsWith("image/")) return resolve(file);
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        URL.revokeObjectURL(url);
        const longest = Math.max(img.width, img.height);
        if (longest <= MAX_DIM && file.size < 3.5 * 1024 * 1024) return resolve(file);
        const scale = Math.min(1, MAX_DIM / longest);
        const w = Math.round(img.width * scale);
        const h = Math.round(img.height * scale);
        const canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        canvas.getContext("2d").drawImage(img, 0, 0, w, h);
        canvas.toBlob(
          (blob) => {
            if (!blob) return resolve(file);
            const name = file.name.replace(/\.(png|webp|jpeg)$/i, ".jpg");
            resolve(new File([blob], name.match(/\.jpg$/i) ? name : name + ".jpg", { type: "image/jpeg" }));
          },
          "image/jpeg",
          0.9
        );
      };
      img.onerror = () => {
        URL.revokeObjectURL(url);
        resolve(file);
      };
      img.src = url;
    });

  const handleFiles = async (files) => {
    if (!files?.length) return;
    setUploading(true);
    const arr = Array.from(files);
    let ok = 0;
    for (const f of arr) {
      try {
        const processed = await optimizeImage(f);
        const form = new FormData();
        form.append("files", processed, processed.name);
        const { data } = await api.post(`/properties/${id}/photos`, form, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        setPhotos((prev) => [...prev, ...data]);
        ok += 1;
      } catch (err) {
        toast.error(`${f.name}: ${apiError(err)}`);
      }
    }
    if (ok) toast.success(`${ok} foto(s) subidas`);
    setUploading(false);
    if (fileRef.current) fileRef.current.value = "";
  };

  const deletePhoto = async (photoId, e) => {
    e.stopPropagation();
    try {
      await api.delete(`/photos/${photoId}`);
      setPhotos((prev) => prev.filter((p) => p.id !== photoId));
      toast.success("Foto eliminada");
    } catch (err) {
      toast.error(apiError(err));
    }
  };

  const selectedAction = actions.find((a) => a.key === batchAction);
  const batchCost = selectedAction ? selectedAction.cost * selectedPhotos.length : 0;

  const startBatch = async () => {
    if (!selectedPhotos.length || job) return;
    try {
      const { data } = await api.post(`/properties/${id}/batch`, { action: batchAction, photo_ids: selectedPhotos.map((p) => p.id) });
      setBatchOpen(false);
      setJob({ ...data, done: 0, failed: 0, processed: 0, status: "processing" });
      pollJob(data.job_id);
      const me = await api.get("/auth/me");
      updateCredits(me.data.credits);
    } catch (err) {
      toast.error(apiError(err));
    }
  };

  const applyAutoAll = async () => {
    if (!selectedPhotos.length || job) return;
    try {
      const { data } = await api.post(`/properties/${id}/batch`, { action: "auto", photo_ids: selectedPhotos.map((p) => p.id) });
      setJob({ ...data, done: 0, failed: 0, processed: 0, status: "processing" });
      pollJob(data.job_id);
      toast.success(`Mejorando ${selectedPhotos.length} fotos seleccionadas…`);
    } catch (err) {
      toast.error(apiError(err));
    }
  };

  const pollJob = (jobId) => {
    const interval = setInterval(async () => {
      try {
        const { data } = await api.get(`/jobs/${jobId}`);
        setJob(data);
        if (data.status === "done") {
          clearInterval(interval);
          await load();
          await refresh();
          if (data.error_message) {
            toast.error(data.error_message, { duration: 12000 });
          } else if (data.failed) {
            toast.error(`Lote terminado · ${data.done} editadas, ${data.failed} sin completar`);
          } else {
            toast.success(`Lote completado · ${data.done} editadas`);
          }
          setTimeout(() => setJob(null), 3000);
        }
      } catch {
        clearInterval(interval);
      }
    }, 2500);
  };

  const statusBadge = (p) => {
    if (p.status === "processing")
      return <Badge className="bg-violet-500/20 text-violet-300 border-violet-500/30"><Loader2 className="w-3 h-3 mr-1 animate-spin" />Procesando</Badge>;
    if (p.edits?.length)
      return <Badge className="bg-cyan-500/20 text-cyan-300 border-cyan-500/30"><CheckCircle2 className="w-3 h-3 mr-1" />Editada</Badge>;
    return <Badge className="bg-white/5 text-slate-400 border-white/10">Original</Badge>;
  };

  return (
    <div className="min-h-screen bg-background grain">
      <Header />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
        {/* Breadcrumb */}
        <div className="flex items-center gap-1.5 text-sm text-slate-400 mb-6">
          <Link to="/app" className="hover:text-white">Propiedades</Link>
          <ChevronRight className="w-4 h-4" />
          <span className="text-white truncate">{prop?.name || "…"}</span>
        </div>

        <div className="flex items-end justify-between flex-wrap gap-4 mb-8">
          <div>
            <h1 className="font-display text-3xl font-bold text-white">{prop?.name}</h1>
            {prop?.address && <p className="text-slate-400 mt-1">{prop.address}</p>}
          </div>
          <div className="flex gap-3 flex-wrap">
            <Button onClick={applyAutoAll} disabled={!selectedPhotos.length || !!job} data-testid="auto-all-btn"
              className="rounded-full bg-gradient-to-r from-violet-600 to-cyan-500 hover:brightness-110 text-white font-semibold transition-[filter]">
              <Wand2 className="w-4 h-4 mr-1.5" /> Mejorar seleccionadas <span className="ml-1.5 text-[10px] font-bold text-emerald-200">GRATIS</span>
            </Button>
            <Button onClick={() => setBatchOpen(true)} disabled={!selectedPhotos.length || !!job} data-testid="batch-edit-btn"
              variant="outline" className="rounded-full border-white/15 bg-white/5 hover:bg-white/10 text-white">
              <Layers className="w-4 h-4 mr-1.5" /> Editar por lote
            </Button>
            <Button onClick={() => setVideoOpen(true)} disabled={!photos.length} data-testid="video-btn"
              variant="outline" className="rounded-full border-cyan-500/30 bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-200">
              <Clapperboard className="w-4 h-4 mr-1.5" /> Generar video
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button disabled={!photos.length} data-testid="download-all-btn"
                  variant="outline" className="rounded-full border-white/15 bg-white/5 hover:bg-white/10 text-white">
                  <Download className="w-4 h-4 mr-1.5" /> Descargar todas
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="bg-[#1E1A29] border-white/10 text-white w-64">
                <DropdownMenuLabel className="text-slate-400 text-xs">Tamaño / portal (ZIP)</DropdownMenuLabel>
                {PORTAL_PRESETS.map((p) => (
                  <DropdownMenuItem key={p.key} data-testid={`dl-all-${p.key}`}
                    onClick={() => downloadZip(p.key, false)} className="cursor-pointer focus:bg-white/10">
                    {p.label}
                  </DropdownMenuItem>
                ))}
                <DropdownMenuSeparator className="bg-white/10" />
                <DropdownMenuItem data-testid="dl-all-watermark"
                  onClick={() => downloadZip("original", true)} className="cursor-pointer focus:bg-white/10 text-cyan-300">
                  Original · con mi marca de agua
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            <Button onClick={() => fileRef.current?.click()} disabled={uploading} data-testid="upload-btn"
              className="rounded-full bg-gradient-to-r from-violet-600 to-cyan-500 hover:brightness-110 text-white font-semibold transition-[filter]">
              {uploading ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : <Upload className="w-4 h-4 mr-1.5" />}
              Subir fotos
            </Button>
            <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif,.cr2,.cr3,.nef,.arw,.dng,.raf,.orf,.rw2,.pef,.srw,.sr2" multiple hidden
              data-testid="file-input" onChange={(e) => handleFiles(e.target.files)} />
          </div>
        </div>

        {photos.length > 0 && (
          <div className="flex flex-wrap items-center gap-3 mb-5 rounded-xl border border-white/10 bg-white/5 p-3" data-testid="photo-selection-bar">
            <span className="text-sm text-cyan-200" aria-live="polite" data-testid="selection-count">{selectedPhotos.length} de {photos.length} fotos seleccionadas</span>
            <Button variant="ghost" size="sm" disabled={!!job} onClick={() => setSelectedIds(photos.map((p) => p.id))} data-testid="select-all-photos">Seleccionar todas</Button>
            <Button variant="ghost" size="sm" disabled={!!job || !selectedPhotos.length} onClick={() => setSelectedIds([])} data-testid="clear-photo-selection">Quitar selección</Button>
            <span className="text-xs text-slate-400">Marca las fotos de interior o exterior para editar solo ese grupo.</span>
          </div>
        )}

        {/* Job progress */}
        {job && (
          <div className="mb-6 rounded-xl border border-violet-500/30 bg-violet-500/10 p-4" data-testid="job-progress">
            <div className="flex items-center justify-between mb-2 text-sm">
              <span className="text-white font-medium flex items-center gap-2">
                <Wand2 className="w-4 h-4 text-cyan-400" /> {job.label || "Procesando lote"} · {job.processed}/{job.total}
              </span>
              <span className="text-slate-400">{job.status === "done" ? "Completado" : "Procesando…"}</span>
            </div>
            <Progress value={job.total ? (job.processed / job.total) * 100 : 0} className="h-2 bg-black/40 [&>div]:bg-gradient-to-r [&>div]:from-violet-500 [&>div]:to-cyan-400" />
          </div>
        )}

        {loading ? (
          <div className="flex justify-center py-24"><Loader2 className="w-7 h-7 animate-spin text-cyan-400" /></div>
        ) : photos.length === 0 ? (
          <div
            onClick={() => fileRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); handleFiles(e.dataTransfer.files); }}
            data-testid="upload-dropzone"
            className="rounded-2xl border-2 border-dashed border-white/10 bg-[#15131C]/50 py-24 text-center cursor-pointer hover:border-cyan-500/40 transition-colors">
            <div className="w-16 h-16 rounded-2xl mx-auto bg-gradient-to-br from-violet-600/20 to-cyan-500/20 border border-white/10 flex items-center justify-center mb-5">
              <Upload className="w-7 h-7 text-cyan-400" />
            </div>
            <h3 className="font-display text-xl font-medium text-white">Sube las fotos del inmueble</h3>
            <p className="text-slate-400 mt-2">Arrastra aquí o haz clic · JPG, PNG, WEBP, HEIC o RAW · se optimizan automáticamente</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4" data-testid="photos-grid">
            {photos.map((p, i) => (
              <motion.div key={p.id}
                initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}
                onClick={() => navigate(`/app/property/${id}/photo/${p.id}`)} data-testid={`photo-card-${p.id}`}
                className="group relative rounded-xl overflow-hidden border border-white/5 bg-secondary/40 cursor-pointer hover:ring-2 hover:ring-violet-500/50 transition-shadow">
                <div className="aspect-square overflow-hidden">
                  <AuthImage path={p.current_path} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
                </div>
                <div className="absolute top-2 left-2">{statusBadge(p)}</div>
                <label className="absolute bottom-2 right-2 z-10 flex items-center gap-1.5 rounded-full bg-black/80 px-2.5 py-1.5 text-xs text-white cursor-pointer" onClick={(e) => e.stopPropagation()}>
                  <input type="checkbox" checked={selectedIds.includes(p.id)} disabled={!!job || p.status === "processing"} onChange={() => togglePhoto(p.id)} aria-label={`Seleccionar foto ${i + 1}`} data-testid={`select-photo-${p.id}`} /> Seleccionar
                </label>
                {p.disclosure && (
                  <div className="absolute bottom-2 left-2 right-2">
                    <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-black/70 text-amber-300" title="Imagen editada digitalmente">
                      <ShieldCheck className="w-3 h-3" /> Editada digitalmente
                    </span>
                  </div>
                )}
                <button onClick={(e) => deletePhoto(p.id, e)} data-testid={`delete-photo-${p.id}`}
                  className="absolute top-2 right-2 w-7 h-7 rounded-full bg-black/60 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-500/80">
                  <Trash2 className="w-3.5 h-3.5 text-white" />
                </button>
                <div className="absolute inset-0 bg-gradient-to-t from-black/50 to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex items-end justify-center pb-3 pointer-events-none">
                  <span className="text-xs font-medium text-white flex items-center gap-1"><Wand2 className="w-3.5 h-3.5" /> Editar</span>
                </div>
              </motion.div>
            ))}
          </div>
        )}

        {/* Videos section */}
        {videos.length > 0 && (
          <div className="mt-12" data-testid="videos-section">
            <h2 className="font-display text-xl font-semibold text-white mb-4 flex items-center gap-2">
              <Film className="w-5 h-5 text-cyan-400" /> Videos de la propiedad
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
              {videos.map((v) => (
                <div key={v.id} data-testid={`video-card-${v.id}`}
                  className="rounded-xl border border-white/5 bg-[#15131C] overflow-hidden">
                  {v.status === "processing" ? (
                    <div className="aspect-video flex flex-col items-center justify-center gap-3 bg-black/40">
                      <Loader2 className="w-6 h-6 animate-spin text-cyan-400" />
                      <VideoTimer createdAt={v.created_at} etaSeconds={v.eta_seconds || 40} />
                    </div>
                  ) : v.status === "failed" ? (
                    <div className="aspect-video flex items-center justify-center bg-black/40 text-sm text-red-400">Falló · créditos reembolsados</div>
                  ) : (
                    <video src={fileUrl(v.storage_path)} controls playsInline
                      className={v.format === "reel" ? "w-full max-h-[420px] bg-black object-contain" : "w-full aspect-video bg-black object-contain"} />
                  )}
                  <div className="p-3 flex items-center justify-between">
                    <div className="flex items-center gap-2 text-sm text-white">
                      {v.format === "reel" ? <Smartphone className="w-4 h-4 text-violet-400" /> : <Monitor className="w-4 h-4 text-cyan-400" />}
                      {v.format === "reel" ? "Reel vertical" : "Video-tour"}
                      <span className="text-xs text-slate-500">· {v.photo_count} fotos</span>
                    </div>
                    {v.status === "done" && (
                      <a href={fileUrl(v.storage_path)} download data-testid={`video-download-${v.id}`}
                        className="w-8 h-8 rounded-full bg-white/5 hover:bg-white/15 flex items-center justify-center transition-colors">
                        <Download className="w-4 h-4 text-white" />
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>

      {/* Batch dialog */}
      <Dialog open={batchOpen} onOpenChange={setBatchOpen}>
        <DialogContent className="bg-[#1E1A29] border-white/10 text-white">
          <DialogHeader><DialogTitle className="font-display flex items-center gap-2"><Layers className="w-5 h-5 text-cyan-400" /> Editar por lote</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <p className="text-sm text-slate-400">Se editarán solo las {selectedPhotos.length} fotos seleccionadas. El resto conservará su edición actual.</p>
            <Select value={batchAction} onValueChange={setBatchAction}>
              <SelectTrigger data-testid="batch-action-select" className="bg-secondary/60 border-white/10">
                <SelectValue placeholder="Elige una acción" />
              </SelectTrigger>
              <SelectContent className="bg-[#1E1A29] border-white/10 text-white">
                {actions.map((a) => (
                  <SelectItem key={a.key} value={a.key} className="focus:bg-white/10">
                    {a.label} {a.cost === 0 ? "· Gratis" : `· ${a.cost} créd/foto`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {selectedAction && (
              <div className="rounded-xl bg-black/30 border border-white/10 p-4 flex items-center justify-between">
                <span className="text-sm text-slate-300">Coste total</span>
                <span className="flex items-center gap-1.5 font-semibold" data-testid="batch-cost">
                  {batchCost === 0 ? <span className="text-emerald-400">Gratis</span> :
                    <><Zap className="w-4 h-4 text-cyan-400 fill-cyan-400" />{batchCost} créditos</>}
                </span>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button onClick={startBatch} disabled={!batchAction || !selectedPhotos.length || !!job} data-testid="batch-confirm"
              className="rounded-full bg-gradient-to-r from-violet-600 to-cyan-500 hover:brightness-110 text-white font-semibold transition-[filter]">
              Aplicar a {selectedPhotos.length} fotos seleccionadas
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Video studio (per-photo controls) */}
      <VideoStudioDialog
        open={videoOpen}
        onOpenChange={setVideoOpen}
        photos={photos}
        propertyId={id}
        onStarted={handleVideoStarted}
      />
    </div>
  );
}
