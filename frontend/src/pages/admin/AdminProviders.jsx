import React, { useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogTrigger,
} from "@/components/ui/dialog";
import { Plus, RefreshCw, Trash2, Loader2, Image as ImageIcon, Film, Server } from "lucide-react";
import { toast } from "sonner";

const TYPES = {
  openai_compatible: "Compatible con OpenAI (OpenAI, OpenRouter, Nvidia, Groq…)",
  fal: "fal.ai",
  custom: "Personalizado (URL /models)",
};
const PRESETS = {
  "https://api.openai.com/v1": "OpenAI",
  "https://openrouter.ai/api/v1": "OpenRouter",
  "https://integrate.api.nvidia.com/v1": "Nvidia",
  "https://api.groq.com/openai/v1": "Groq",
};

const STATUS = {
  valid: { label: "Válido", cls: "bg-emerald-500/15 text-emerald-300" },
  no_credits: { label: "Sin créditos", cls: "bg-amber-500/15 text-amber-300" },
  invalid_key: { label: "Clave inválida", cls: "bg-red-500/15 text-red-300" },
  error: { label: "Error", cls: "bg-red-500/15 text-red-300" },
  unknown: { label: "Sin comprobar", cls: "bg-slate-500/15 text-slate-300" },
};

function AddProviderDialog({ onSaved }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", type: "openai_compatible", base_url: "", api_key: "" });
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      await api.post("/admin/providers", form);
      toast.success("Proveedor añadido y modelos detectados");
      setOpen(false);
      setForm({ name: "", type: "openai_compatible", base_url: "", api_key: "" });
      onSaved();
    } catch (err) { toast.error(apiError(err)); } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button data-testid="add-provider-btn" className="rounded-full bg-gradient-to-r from-violet-600 to-cyan-500 text-white">
          <Plus className="w-4 h-4 mr-1.5" /> Añadir proveedor
        </Button>
      </DialogTrigger>
      <DialogContent className="bg-[#1E1A29] border-white/10 text-white max-w-lg">
        <DialogHeader><DialogTitle className="font-display">Nuevo proveedor de IA</DialogTitle>
          <DialogDescription className="text-slate-400">La app detectará los modelos disponibles y validará la clave.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 mt-1">
          <div className="space-y-1.5"><Label className="text-slate-300">Nombre</Label>
            <Input data-testid="provider-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="OpenAI producción" className="bg-secondary/60 border-white/10" /></div>
          <div className="space-y-1.5"><Label className="text-slate-300">Tipo</Label>
            <Select value={form.type} onValueChange={(v) => setForm({ ...form, type: v })}>
              <SelectTrigger data-testid="provider-type" className="bg-secondary/60 border-white/10"><SelectValue /></SelectTrigger>
              <SelectContent className="bg-[#1E1A29] border-white/10 text-white">
                {Object.entries(TYPES).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
              </SelectContent>
            </Select></div>
          {form.type !== "fal" && (
            <div className="space-y-1.5"><Label className="text-slate-300">URL base de la API</Label>
              <Input data-testid="provider-url" value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })}
                placeholder="https://api.openai.com/v1" className="bg-secondary/60 border-white/10" />
              <div className="flex flex-wrap gap-1.5 pt-1">
                {Object.entries(PRESETS).map(([url, name]) => (
                  <button key={url} type="button" onClick={() => setForm({ ...form, base_url: url, name: form.name || name })}
                    className="text-xs px-2 py-1 rounded-full bg-white/5 hover:bg-white/10 text-slate-300">{name}</button>
                ))}
              </div>
            </div>
          )}
          <div className="space-y-1.5"><Label className="text-slate-300">API key</Label>
            <Input data-testid="provider-key" type="password" value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })}
              placeholder="sk-..." className="bg-secondary/60 border-white/10" /></div>
          <p className="text-xs text-slate-500">Al guardar, la app llamará al proveedor para listar sus modelos y validar la clave.</p>
        </div>
        <DialogFooter>
          <Button onClick={save} disabled={saving || !form.name || !form.api_key} data-testid="save-provider-btn"
            className="rounded-full bg-cyan-500 hover:bg-cyan-400 text-black font-semibold">
            {saving ? <><Loader2 className="w-4 h-4 animate-spin mr-1.5" /> Detectando…</> : "Guardar y detectar modelos"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CapBadge({ children, cls }) {
  return <span className={`text-[9px] font-semibold px-1.5 py-0.5 rounded ${cls}`}>{children}</span>;
}

function ModelRow({ m }) {
  const c = m.capabilities || {};
  return (
    <div className="flex items-center justify-between gap-2 rounded-lg bg-white/[0.03] px-3 py-2" data-testid={`model-row-${m.id}`}>
      <p className="text-sm text-white truncate min-w-0">{m.name}</p>
      <div className="flex items-center gap-1 shrink-0">
        {c.image_edit && <CapBadge cls="bg-cyan-500/20 text-cyan-300">EDICIÓN</CapBadge>}
        {c.image_generation && <CapBadge cls="bg-violet-500/20 text-violet-300">GENERACIÓN</CapBadge>}
        {c.video && <CapBadge cls="bg-fuchsia-500/20 text-fuchsia-300">VÍDEO</CapBadge>}
      </div>
    </div>
  );
}

function ProviderCard({ provider, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [showOthers, setShowOthers] = useState(false);
  const st = STATUS[provider.status] || STATUS.unknown;

  const refresh = async () => {
    setBusy(true);
    try { await api.post(`/admin/providers/${provider.id}/refresh`); toast.success("Modelos actualizados"); onChanged(); }
    catch (err) { toast.error(apiError(err)); } finally { setBusy(false); }
  };
  const del = async () => {
    try { await api.delete(`/admin/providers/${provider.id}`); toast.success("Proveedor eliminado"); onChanged(); }
    catch (err) { toast.error(apiError(err)); }
  };

  const models = provider.models || [];
  const imageModels = models.filter((m) => m.capabilities?.image_edit || m.capabilities?.image_generation);
  const videoModels = models.filter((m) => m.capabilities?.video);
  const others = models.filter((m) => !m.capabilities?.image_edit && !m.capabilities?.image_generation && !m.capabilities?.video);

  return (
    <div className="rounded-2xl border border-white/5 bg-[#15131C] p-5" data-testid={`provider-card-${provider.id}`}>
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Server className="w-4 h-4 text-cyan-400" />
            <h3 className="font-display text-lg text-white">{provider.name}</h3>
            <Badge className={`${st.cls} border-0`} data-testid={`provider-status-${provider.id}`}>{st.label}</Badge>
          </div>
          <p className="text-xs text-slate-500 mt-1">{TYPES[provider.type]} · clave {provider.key_hint}</p>
          {provider.error && <p className="text-xs text-red-400 mt-1">{provider.error}</p>}
        </div>
        <div className="flex gap-1">
          <button onClick={refresh} disabled={busy} data-testid={`refresh-provider-${provider.id}`} className="p-2 rounded-lg hover:bg-white/10 text-slate-300">
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
          </button>
          <button onClick={del} data-testid={`delete-provider-${provider.id}`} className="p-2 rounded-lg hover:bg-red-500/20 text-red-300"><Trash2 className="w-4 h-4" /></button>
        </div>
      </div>

      <div className="mt-4 max-h-80 overflow-y-auto pr-1 space-y-3">
        {models.length === 0 && <p className="text-sm text-slate-500">No se detectaron modelos.</p>}

        {imageModels.length > 0 && (
          <div>
            <p className="flex items-center gap-1.5 text-xs uppercase tracking-wide text-slate-400 mb-1.5">
              <ImageIcon className="w-3.5 h-3.5 text-cyan-400" /> Imagen · {imageModels.length}
            </p>
            <div className="space-y-1.5">{imageModels.map((m) => <ModelRow key={m.id} m={m} />)}</div>
          </div>
        )}

        {videoModels.length > 0 && (
          <div>
            <p className="flex items-center gap-1.5 text-xs uppercase tracking-wide text-slate-400 mb-1.5">
              <Film className="w-3.5 h-3.5 text-fuchsia-400" /> Vídeo · {videoModels.length}
            </p>
            <div className="space-y-1.5">{videoModels.map((m) => <ModelRow key={m.id} m={m} />)}</div>
          </div>
        )}

        {others.length > 0 && (
          <div>
            <button data-testid={`toggle-others-${provider.id}`} onClick={() => setShowOthers((v) => !v)}
              className="text-xs text-slate-500 hover:text-slate-300">
              {showOthers ? "▾" : "▸"} Otros modelos detectados · {others.length} (texto/visión, no usables en foto/vídeo)
            </button>
            {showOthers && <div className="space-y-1.5 mt-1.5 opacity-70">{others.map((m) => (
              <div key={m.id} className="flex items-center justify-between rounded-lg bg-white/[0.02] px-3 py-1.5">
                <p className="text-xs text-slate-400 truncate">{m.name}</p>
                <span className="text-[9px] text-slate-600 uppercase">{m.kind}</span>
              </div>
            ))}</div>}
          </div>
        )}
      </div>
    </div>
  );
}

function ToolOverrides() {
  const [data, setData] = useState(null);
  const [resetting, setResetting] = useState(false);
  const load = async () => {
    try { const { data } = await api.get("/admin/tool-overrides"); setData(data); }
    catch (err) { toast.error(apiError(err)); }
  };
  useEffect(() => { load(); }, []);

  const resetAll = async () => {
    if (!window.confirm("¿Restablecer TODAS las herramientas al motor por defecto (Gemini Nano Banana)? Las ediciones volverán a comportarse como en vista previa.")) return;
    setResetting(true);
    try {
      await api.post("/admin/reset-engines");
      toast.success("Todas las herramientas usan de nuevo Gemini Nano Banana");
      load();
    } catch (err) { toast.error(apiError(err)); } finally { setResetting(false); }
  };

  const setOverride = async (action, value) => {
    try {
      if (value === "default") await api.put("/admin/tool-overrides", { action, provider_id: null, model_id: null });
      else {
        const [provider_id, model_id] = value.split("::");
        await api.put("/admin/tool-overrides", { action, provider_id, model_id });
      }
      toast.success("Motor de la herramienta actualizado");
      load();
    } catch (err) { toast.error(apiError(err)); }
  };

  if (!data) return <div className="flex justify-center py-10"><Loader2 className="w-6 h-6 animate-spin text-cyan-400" /></div>;
  const { tools, overrides, photo_models } = data;
  const activeCount = Object.keys(overrides || {}).length;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <p className="text-sm text-slate-400">
          {activeCount > 0
            ? `${activeCount} herramienta(s) usan un motor personalizado (no Gemini por defecto).`
            : "Todas las herramientas usan Gemini Nano Banana por defecto."}
        </p>
        <Button onClick={resetAll} disabled={resetting || activeCount === 0} data-testid="reset-engines-btn"
          className="rounded-full bg-white/10 hover:bg-white/20 text-white">
          {resetting ? <Loader2 className="w-4 h-4 animate-spin mr-1.5" /> : <RefreshCw className="w-4 h-4 mr-1.5" />}
          Restablecer a Gemini por defecto
        </Button>
      </div>
      <div className="rounded-2xl border border-white/5 overflow-hidden">
      <table className="w-full text-sm" data-testid="tool-overrides-table">
        <thead className="bg-white/5 text-slate-400">
          <tr>
            <th className="text-left px-4 py-3 font-medium">Herramienta de foto</th>
            <th className="text-left px-4 py-3 font-medium">Motor asignado</th>
          </tr>
        </thead>
        <tbody>
          {tools.map((t) => {
            const ov = overrides[t.action];
            const current = ov ? `${ov.provider_id}::${ov.model_id}` : "default";
            return (
              <tr key={t.action} className="border-t border-white/5">
                <td className="px-4 py-3 text-white">{t.label}<span className="text-xs text-slate-500 ml-2">{t.cost} créd.</span></td>
                <td className="px-4 py-3">
                  <Select value={current} onValueChange={(v) => setOverride(t.action, v)}>
                    <SelectTrigger data-testid={`tool-select-${t.action}`} className="bg-secondary/60 border-white/10 max-w-xs"><SelectValue /></SelectTrigger>
                    <SelectContent className="bg-[#1E1A29] border-white/10 text-white">
                      <SelectItem value="default">Por defecto (Gemini Nano Banana)</SelectItem>
                      {photo_models.map((m) => (
                        <SelectItem key={`${m.provider_id}::${m.model_id}`} value={`${m.provider_id}::${m.model_id}`}>
                          {m.provider_name} · {m.model_name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {photo_models.length === 0 && (
        <p className="px-4 py-3 text-xs text-slate-500 border-t border-white/5">
          Añade un proveedor con un modelo de <b>edición de imagen</b> (imagen → imagen, p. ej. FLUX Kontext, FLUX.2 Klein o Qwen Image Edit) para poder asignarlo a una herramienta.
        </p>
      )}
      </div>
    </div>
  );
}

export default function AdminProviders() {
  const [providers, setProviders] = useState(null);
  const [tick, setTick] = useState(0);
  const load = async () => {
    try { const { data } = await api.get("/admin/providers"); setProviders(data); }
    catch (err) { toast.error(apiError(err)); setProviders([]); }
  };
  useEffect(() => { load(); }, []);
  const onChanged = () => { load(); setTick((t) => t + 1); };

  return (
    <div className="space-y-10">
      <section>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="font-display text-xl font-semibold text-white">Proveedores de IA</h2>
            <p className="text-sm text-slate-400">Añade fuentes de modelos (OpenAI, OpenRouter, Nvidia, fal.ai…) y actívalos por herramienta.</p>
          </div>
          <AddProviderDialog onSaved={onChanged} />
        </div>
        {providers === null ? (
          <div className="flex justify-center py-16"><Loader2 className="w-6 h-6 animate-spin text-cyan-400" /></div>
        ) : providers.length === 0 ? (
          <p className="text-slate-500 text-sm">Aún no hay proveedores. La app usa Gemini Nano Banana por defecto.</p>
        ) : (
          <div className="grid lg:grid-cols-2 gap-4" data-testid="providers-grid">
            {providers.map((p) => <ProviderCard key={p.id} provider={p} onChanged={onChanged} />)}
          </div>
        )}
      </section>

      <section>
        <h2 className="font-display text-xl font-semibold text-white mb-1">Motor por herramienta</h2>
        <p className="text-sm text-slate-400 mb-4">Elige qué modelo usa cada herramienta de edición. Por defecto usa Gemini Nano Banana; puedes volver al modelo por defecto cuando quieras.</p>
        <ToolOverrides key={tick} />
      </section>
    </div>
  );
}
