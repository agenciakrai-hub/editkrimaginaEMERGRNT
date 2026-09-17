import React, { useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { Zap, Loader2, Check, Sparkles } from "lucide-react";
import { toast } from "sonner";

export default function BuyCreditsDialog({ open, onOpenChange }) {
  const [packages, setPackages] = useState([]);
  const [loadingKey, setLoadingKey] = useState(null);

  useEffect(() => {
    if (open) api.get("/payments/packages").then(({ data }) => setPackages(data)).catch(() => {});
  }, [open]);

  const buy = async (lookup_key) => {
    setLoadingKey(lookup_key);
    try {
      const { data } = await api.post("/payments/checkout", {
        lookup_key,
        origin_url: window.location.origin,
      });
      window.location.href = data.checkout_url;
    } catch (err) {
      toast.error(apiError(err));
      setLoadingKey(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[#1E1A29] border-white/10 text-white max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2">
            <Zap className="w-5 h-5 text-cyan-400 fill-cyan-400" /> Comprar créditos
          </DialogTitle>
          <DialogDescription className="text-slate-400">
            Usa créditos para twilight, staging virtual, lotes grandes y videos.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 mt-2">
          {packages.map((p) => (
            <div key={p.lookup_key} data-testid={`package-${p.lookup_key}`}
              className={`relative rounded-xl border p-4 flex items-center justify-between transition-colors ${
                p.popular ? "border-cyan-500/50 bg-cyan-500/5" : "border-white/10 bg-black/20"}`}>
              {p.popular && (
                <span className="absolute -top-2 left-4 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-gradient-to-r from-violet-600 to-cyan-500 text-white flex items-center gap-1">
                  <Sparkles className="w-2.5 h-2.5" /> Popular
                </span>
              )}
              <div>
                <div className="flex items-center gap-2 font-semibold text-white">
                  <Zap className="w-4 h-4 text-cyan-400 fill-cyan-400" /> {p.label}
                </div>
                <div className="text-sm text-slate-400 mt-0.5">{p.eur}</div>
              </div>
              <Button onClick={() => buy(p.lookup_key)} disabled={loadingKey === p.lookup_key}
                data-testid={`buy-${p.lookup_key}`}
                className="rounded-full bg-gradient-to-r from-violet-600 to-cyan-500 hover:brightness-110 text-white font-semibold transition-[filter]">
                {loadingKey === p.lookup_key ? <Loader2 className="w-4 h-4 animate-spin" /> : "Comprar"}
              </Button>
            </div>
          ))}
        </div>
        <p className="text-xs text-slate-500 flex items-center gap-1.5 mt-2">
          <Check className="w-3.5 h-3.5 text-emerald-400" /> Pago seguro con Stripe · tarjeta de prueba 4242 4242 4242 4242
        </p>
      </DialogContent>
    </Dialog>
  );
}
