import React, { useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";
import { Loader2, Image as ImageIcon, Film, Cpu, User } from "lucide-react";
import { toast } from "sonner";

function Stat({ icon: Icon, label, value, accent }) {
  return (
    <div className="rounded-2xl border border-white/5 bg-[#15131C] p-5">
      <div className={`w-10 h-10 rounded-xl flex items-center justify-center mb-3 ${accent}`}><Icon className="w-5 h-5" /></div>
      <p className="text-2xl font-bold text-white tabular-nums">{value}</p>
      <p className="text-xs text-slate-400 mt-0.5">{label}</p>
    </div>
  );
}

export default function AdminUsage() {
  const [data, setData] = useState(null);

  useEffect(() => {
    api.get("/admin/usage").then((r) => setData(r.data)).catch((err) => { toast.error(apiError(err)); setData({ admin: {}, users: [], totals: {} }); });
  }, []);

  if (!data) return <div className="flex justify-center py-16"><Loader2 className="w-6 h-6 animate-spin text-cyan-400" /></div>;
  const { admin, users, totals } = data;

  return (
    <div className="space-y-10">
      {/* Admin's own consumption */}
      <section>
        <h2 className="font-display text-xl font-semibold text-white mb-1 flex items-center gap-2"><User className="w-5 h-5 text-violet-400" /> Mi consumo (administrador)</h2>
        <p className="text-sm text-slate-400 mb-4">Separado del resto de usuarios.</p>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4" data-testid="admin-usage-cards">
          <Stat icon={ImageIcon} label="Créditos en foto" value={admin.photo_credits || 0} accent="bg-cyan-500/15 text-cyan-300" />
          <Stat icon={Film} label="Créditos en vídeo" value={admin.video_credits || 0} accent="bg-violet-500/15 text-violet-300" />
          <Stat icon={Cpu} label="Llamadas reales a Gemini" value={admin.gemini_calls || 0} accent="bg-amber-500/15 text-amber-300" />
          <Stat icon={ImageIcon} label="Ediciones totales" value={admin.ai_calls || 0} accent="bg-emerald-500/15 text-emerald-300" />
        </div>
      </section>

      {/* Global totals */}
      <section>
        <h2 className="font-display text-xl font-semibold text-white mb-4">Total del resto de usuarios</h2>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <Stat icon={ImageIcon} label="Créditos foto" value={totals.photo_credits || 0} accent="bg-cyan-500/15 text-cyan-300" />
          <Stat icon={Film} label="Créditos vídeo" value={totals.video_credits || 0} accent="bg-violet-500/15 text-violet-300" />
          <Stat icon={Cpu} label="Llamadas Gemini" value={totals.gemini_calls || 0} accent="bg-amber-500/15 text-amber-300" />
          <Stat icon={ImageIcon} label="Ediciones totales" value={totals.ai_calls || 0} accent="bg-emerald-500/15 text-emerald-300" />
        </div>
      </section>

      {/* Per-user breakdown */}
      <section>
        <h2 className="font-display text-xl font-semibold text-white mb-4">Consumo por usuario</h2>
        <div className="overflow-x-auto rounded-2xl border border-white/5">
          <table className="w-full text-sm" data-testid="usage-table">
            <thead className="bg-white/5 text-slate-400">
              <tr>
                <th className="text-left px-4 py-3 font-medium">Usuario</th>
                <th className="text-right px-4 py-3 font-medium">Créditos foto</th>
                <th className="text-right px-4 py-3 font-medium">Créditos vídeo</th>
                <th className="text-right px-4 py-3 font-medium">Total</th>
                <th className="text-right px-4 py-3 font-medium">Llamadas Gemini</th>
              </tr>
            </thead>
            <tbody>
              {users.length === 0 && <tr><td colSpan={5} className="px-4 py-8 text-center text-slate-500">Aún no hay consumo registrado.</td></tr>}
              {users.map((u) => (
                <tr key={u.user_id} className="border-t border-white/5 hover:bg-white/[0.02]">
                  <td className="px-4 py-3 text-white">{u.email}</td>
                  <td className="px-4 py-3 text-right text-cyan-300 tabular-nums">{u.photo_credits}</td>
                  <td className="px-4 py-3 text-right text-violet-300 tabular-nums">{u.video_credits}</td>
                  <td className="px-4 py-3 text-right text-white font-semibold tabular-nums">{u.total_credits}</td>
                  <td className="px-4 py-3 text-right text-amber-300 tabular-nums">{u.gemini_calls}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
