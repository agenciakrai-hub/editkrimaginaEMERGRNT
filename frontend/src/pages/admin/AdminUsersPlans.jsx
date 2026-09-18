import React, { useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Plus, Pencil, Trash2, Loader2, Crown, Zap } from "lucide-react";
import { toast } from "sonner";

const PERIODS = { monthly: "Mensual", yearly: "Anual", one_time: "Pago único" };
const emptyPlan = { name: "", price_eur: 0, credits: 0, period: "monthly", features: "", highlight: false, active: true, sort_order: 0 };

function PlanDialog({ plan, onSaved }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(emptyPlan);
  const [saving, setSaving] = useState(false);
  const editing = !!plan;

  useEffect(() => {
    if (open) {
      setForm(plan
        ? { ...plan, features: (plan.features || []).join("\n") }
        : emptyPlan);
    }
  }, [open, plan]);

  const save = async () => {
    setSaving(true);
    try {
      const payload = {
        name: form.name, price_eur: Number(form.price_eur) || 0, credits: Number(form.credits) || 0,
        period: form.period, features: form.features.split("\n").map((s) => s.trim()).filter(Boolean),
        highlight: !!form.highlight, active: !!form.active, sort_order: Number(form.sort_order) || 0,
      };
      if (editing) await api.put(`/admin/plans/${plan.id}`, payload);
      else await api.post("/admin/plans", payload);
      toast.success(editing ? "Plan actualizado" : "Plan creado");
      setOpen(false);
      onSaved();
    } catch (err) { toast.error(apiError(err)); } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {editing ? (
          <button data-testid={`edit-plan-${plan.id}`} className="p-2 rounded-lg hover:bg-white/10 text-slate-300">
            <Pencil className="w-4 h-4" />
          </button>
        ) : (
          <Button data-testid="new-plan-btn" className="rounded-full bg-gradient-to-r from-violet-600 to-cyan-500 text-white">
            <Plus className="w-4 h-4 mr-1.5" /> Nuevo plan
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="bg-[#1E1A29] border-white/10 text-white max-w-lg">
        <DialogHeader><DialogTitle className="font-display">{editing ? "Editar plan" : "Crear plan"}</DialogTitle>
          <DialogDescription className="text-slate-400">Define nombre, precio, créditos y características del plan.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 mt-1 max-h-[70vh] overflow-y-auto pr-1">
          <div className="space-y-1.5"><Label className="text-slate-300">Nombre</Label>
            <Input data-testid="plan-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="Pro" className="bg-secondary/60 border-white/10" /></div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5"><Label className="text-slate-300">Precio (€)</Label>
              <Input data-testid="plan-price" type="number" value={form.price_eur} onChange={(e) => setForm({ ...form, price_eur: e.target.value })} className="bg-secondary/60 border-white/10" /></div>
            <div className="space-y-1.5"><Label className="text-slate-300">Créditos incluidos</Label>
              <Input data-testid="plan-credits" type="number" value={form.credits} onChange={(e) => setForm({ ...form, credits: e.target.value })} className="bg-secondary/60 border-white/10" /></div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5"><Label className="text-slate-300">Periodo</Label>
              <Select value={form.period} onValueChange={(v) => setForm({ ...form, period: v })}>
                <SelectTrigger data-testid="plan-period" className="bg-secondary/60 border-white/10"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-[#1E1A29] border-white/10 text-white">
                  {Object.entries(PERIODS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
                </SelectContent>
              </Select></div>
            <div className="space-y-1.5"><Label className="text-slate-300">Orden</Label>
              <Input type="number" value={form.sort_order} onChange={(e) => setForm({ ...form, sort_order: e.target.value })} className="bg-secondary/60 border-white/10" /></div>
          </div>
          <div className="space-y-1.5"><Label className="text-slate-300">Características (una por línea)</Label>
            <Textarea data-testid="plan-features" rows={4} value={form.features} onChange={(e) => setForm({ ...form, features: e.target.value })}
              placeholder={"300 créditos al mes\nSoporte prioritario"} className="bg-secondary/60 border-white/10" /></div>
          <div className="flex items-center gap-6">
            <label className="flex items-center gap-2 text-sm text-slate-300">
              <Switch data-testid="plan-highlight" checked={form.highlight} onCheckedChange={(v) => setForm({ ...form, highlight: v })} /> Destacado
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-300">
              <Switch data-testid="plan-active" checked={form.active} onCheckedChange={(v) => setForm({ ...form, active: v })} /> Activo (visible en landing)
            </label>
          </div>
        </div>
        <DialogFooter>
          <Button onClick={save} disabled={saving || !form.name} data-testid="save-plan-btn"
            className="rounded-full bg-cyan-500 hover:bg-cyan-400 text-black font-semibold">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : "Guardar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AssignPlanDialog({ user, plans, onSaved }) {
  const [open, setOpen] = useState(false);
  const [planId, setPlanId] = useState(user.plan_id || "none");
  const [expires, setExpires] = useState(user.plan_expires_at ? user.plan_expires_at.slice(0, 10) : "");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      await api.post(`/admin/users/${user.user_id}/plan`, {
        plan_id: planId === "none" ? null : planId,
        expires_at: planId === "none" || !expires ? null : new Date(expires).toISOString(),
      });
      toast.success("Plan del usuario actualizado");
      setOpen(false);
      onSaved();
    } catch (err) { toast.error(apiError(err)); } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button data-testid={`assign-plan-${user.user_id}`} size="sm" variant="ghost" className="h-8 text-xs text-cyan-300 hover:bg-white/10">Asignar plan</Button>
      </DialogTrigger>
      <DialogContent className="bg-[#1E1A29] border-white/10 text-white">
        <DialogHeader><DialogTitle className="font-display">Plan de {user.email}</DialogTitle>
          <DialogDescription className="text-slate-400">Asigna un plan y su fecha de vencimiento a este usuario.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 mt-1">
          <div className="space-y-1.5"><Label className="text-slate-300">Plan</Label>
            <Select value={planId} onValueChange={setPlanId}>
              <SelectTrigger data-testid="assign-plan-select" className="bg-secondary/60 border-white/10"><SelectValue placeholder="Sin plan" /></SelectTrigger>
              <SelectContent className="bg-[#1E1A29] border-white/10 text-white">
                <SelectItem value="none">Sin plan</SelectItem>
                {plans.map((p) => <SelectItem key={p.id} value={p.id}>{p.name} · {p.credits} créditos</SelectItem>)}
              </SelectContent>
            </Select></div>
          <div className="space-y-1.5"><Label className="text-slate-300">Vence el</Label>
            <Input data-testid="assign-plan-expires" type="date" value={expires} onChange={(e) => setExpires(e.target.value)}
              disabled={planId === "none"} className="bg-secondary/60 border-white/10" /></div>
          <p className="text-xs text-slate-500">Al asignar un plan con créditos se añadirán automáticamente al saldo del usuario.</p>
        </div>
        <DialogFooter>
          <Button onClick={save} disabled={saving} data-testid="save-assign-plan"
            className="rounded-full bg-cyan-500 hover:bg-cyan-400 text-black font-semibold">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : "Guardar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function AdminUsersPlans() {
  const [users, setUsers] = useState(null);
  const [plans, setPlans] = useState([]);

  const load = async () => {
    try {
      const [u, p] = await Promise.all([api.get("/admin/users"), api.get("/admin/plans")]);
      setUsers(u.data); setPlans(p.data);
    } catch (err) { toast.error(apiError(err)); setUsers([]); }
  };
  useEffect(() => { load(); }, []);

  const deletePlan = async (id) => {
    try { await api.delete(`/admin/plans/${id}`); toast.success("Plan eliminado"); load(); }
    catch (err) { toast.error(apiError(err)); }
  };

  return (
    <div className="space-y-10">
      {/* Plans */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="font-display text-xl font-semibold text-white">Planes de suscripción</h2>
            <p className="text-sm text-slate-400">Los planes activos se muestran automáticamente en la landing pública.</p>
          </div>
          <PlanDialog onSaved={load} />
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="plans-grid">
          {plans.length === 0 && <p className="text-slate-500 text-sm">Aún no hay planes. Crea el primero.</p>}
          {plans.map((p) => (
            <div key={p.id} className={`rounded-2xl border p-5 bg-[#15131C] ${p.highlight ? "border-violet-500/50 shadow-[0_0_24px_rgba(139,92,246,0.2)]" : "border-white/5"}`}>
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-display text-lg text-white">{p.name}</h3>
                    {p.highlight && <Crown className="w-4 h-4 text-violet-400" />}
                    {!p.active && <Badge className="bg-slate-600/40 text-slate-300 border-0">Oculto</Badge>}
                  </div>
                  <p className="text-2xl font-bold text-white mt-1">{p.price_eur}€ <span className="text-sm font-normal text-slate-400">/ {PERIODS[p.period]}</span></p>
                  <p className="text-xs text-cyan-300 mt-1 flex items-center gap-1"><Zap className="w-3 h-3 fill-cyan-300" /> {p.credits} créditos</p>
                </div>
                <div className="flex gap-1">
                  <PlanDialog plan={p} onSaved={load} />
                  <button data-testid={`delete-plan-${p.id}`} onClick={() => deletePlan(p.id)} className="p-2 rounded-lg hover:bg-red-500/20 text-red-300"><Trash2 className="w-4 h-4" /></button>
                </div>
              </div>
              <ul className="mt-3 space-y-1">
                {(p.features || []).map((f, i) => <li key={i} className="text-sm text-slate-400">· {f}</li>)}
              </ul>
            </div>
          ))}
        </div>
      </section>

      {/* Users */}
      <section>
        <h2 className="font-display text-xl font-semibold text-white mb-4">Usuarios registrados</h2>
        {users === null ? (
          <div className="flex justify-center py-16"><Loader2 className="w-6 h-6 animate-spin text-cyan-400" /></div>
        ) : (
          <div className="overflow-x-auto rounded-2xl border border-white/5">
            <table className="w-full text-sm" data-testid="users-table">
              <thead className="bg-white/5 text-slate-400">
                <tr>
                  <th className="text-left px-4 py-3 font-medium">Email</th>
                  <th className="text-left px-4 py-3 font-medium">Rol</th>
                  <th className="text-right px-4 py-3 font-medium">Créditos</th>
                  <th className="text-left px-4 py-3 font-medium">Plan</th>
                  <th className="text-left px-4 py-3 font-medium">Vence</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.user_id} className="border-t border-white/5 hover:bg-white/[0.02]">
                    <td className="px-4 py-3 text-white">{u.email}</td>
                    <td className="px-4 py-3"><Badge className="bg-white/10 text-slate-200 border-0 capitalize">{u.role}</Badge></td>
                    <td className="px-4 py-3 text-right text-cyan-300 tabular-nums">{u.role === "owner" ? "∞" : u.credits}</td>
                    <td className="px-4 py-3 text-slate-300">{u.plan_name || <span className="text-slate-600">—</span>}</td>
                    <td className="px-4 py-3 text-slate-400">{u.plan_expires_at ? u.plan_expires_at.slice(0, 10) : <span className="text-slate-600">—</span>}</td>
                    <td className="px-4 py-3 text-right"><AssignPlanDialog user={u} plans={plans} onSaved={load} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
