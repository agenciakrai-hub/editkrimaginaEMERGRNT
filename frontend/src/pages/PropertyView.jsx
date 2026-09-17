import React, { useEffect, useRef, useState, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import Header from "@/components/Header";
import AuthImage from "@/components/AuthImage";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { motion } from "framer-motion";
import {
  Upload, Loader2, ChevronRight, Trash2, Wand2, Zap, ImageOff, Layers, ShieldCheck, CheckCircle2,
} from "lucide-react";
import { toast } from "sonner";

export default function PropertyView() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { updateCredits, refresh } = useAuth();
  const fileRef = useRef(null);
  const [prop, setProp] = useState(null);
  const [photos, setPhotos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [actions, setActions] = useState([]);

  const [batchOpen, setBatchOpen] = useState(false);
  const [batchAction, setBatchAction] = useState("");
  const [job, setJob] = useState(null);

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
    api.get("/actions").then(({ data }) => setActions(data)).catch(() => {});
  }, [load]);

  const handleFiles = async (files) => {
    if (!files?.length) return;
    setUploading(true);
    const form = new FormData();
    Array.from(files).forEach((f) => form.append("files", f));
    try {
      const { data } = await api.post(`/properties/${id}/photos`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setPhotos((prev) => [...prev, ...data]);
      toast.success(`${data.length} foto(s) subidas`);
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
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
  const batchCost = selectedAction ? selectedAction.cost * photos.length : 0;

  const startBatch = async () => {
    try {
      const { data } = await api.post(`/properties/${id}/batch`, { action: batchAction });
      setBatchOpen(false);
      setJob({ ...data, done: 0, failed: 0, processed: 0, status: "processing" });
      pollJob(data.job_id);
      const me = await api.get("/auth/me");
      updateCredits(me.data.credits);
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
          toast.success(`Lote completado · ${data.done} editadas${data.failed ? `, ${data.failed} fallidas` : ""}`);
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
          <div className="flex gap-3">
            <Button onClick={() => setBatchOpen(true)} disabled={!photos.length} data-testid="batch-edit-btn"
              variant="outline" className="rounded-full border-white/15 bg-white/5 hover:bg-white/10 text-white">
              <Layers className="w-4 h-4 mr-1.5" /> Editar por lote
            </Button>
            <Button onClick={() => fileRef.current?.click()} disabled={uploading} data-testid="upload-btn"
              className="rounded-full bg-gradient-to-r from-violet-600 to-cyan-500 hover:brightness-110 text-white font-semibold transition-[filter]">
              {uploading ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : <Upload className="w-4 h-4 mr-1.5" />}
              Subir fotos
            </Button>
            <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" multiple hidden
              data-testid="file-input" onChange={(e) => handleFiles(e.target.files)} />
          </div>
        </div>

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
            <p className="text-slate-400 mt-2">Arrastra aquí o haz clic · JPG, PNG o WEBP (máx. 25MB)</p>
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
      </main>

      {/* Batch dialog */}
      <Dialog open={batchOpen} onOpenChange={setBatchOpen}>
        <DialogContent className="bg-[#1E1A29] border-white/10 text-white">
          <DialogHeader><DialogTitle className="font-display flex items-center gap-2"><Layers className="w-5 h-5 text-cyan-400" /> Editar por lote</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <p className="text-sm text-slate-400">Aplica una edición a las {photos.length} fotos de esta propiedad.</p>
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
            <Button onClick={startBatch} disabled={!batchAction} data-testid="batch-confirm"
              className="rounded-full bg-gradient-to-r from-violet-600 to-cyan-500 hover:brightness-110 text-white font-semibold transition-[filter]">
              Aplicar a {photos.length} fotos
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
