import React, { useEffect, useState, useRef } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import Logo from "@/components/Logo";
import { Button } from "@/components/ui/button";
import { CheckCircle2, Loader2, XCircle, Zap } from "lucide-react";

export default function PaymentSuccess() {
  const navigate = useNavigate();
  const location = useLocation();
  const { refresh } = useAuth();
  const [state, setState] = useState("checking"); // checking | paid | failed
  const [credits, setCredits] = useState(null);
  const attempts = useRef(0);

  useEffect(() => {
    const sessionId = new URLSearchParams(location.search).get("session_id");
    if (!sessionId) {
      setState("failed");
      return;
    }
    let timer;
    const poll = async () => {
      attempts.current += 1;
      try {
        const { data } = await api.get(`/payments/status/${sessionId}`);
        if (data.payment_status === "paid") {
          setCredits(data.credits);
          await refresh();
          setState("paid");
          return;
        }
        if (["failed", "expired"].includes(data.payment_status) || attempts.current > 8) {
          setState("failed");
          return;
        }
      } catch {
        if (attempts.current > 8) { setState("failed"); return; }
      }
      timer = setTimeout(poll, 2000);
    };
    poll();
    return () => clearTimeout(timer);
  }, [location, refresh]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-6 bg-background grain px-6 text-center">
      <Logo size={40} />
      {state === "checking" && (
        <div className="flex flex-col items-center gap-3" data-testid="payment-checking">
          <Loader2 className="w-10 h-10 animate-spin text-cyan-400" />
          <p className="text-slate-300">Confirmando tu pago…</p>
        </div>
      )}
      {state === "paid" && (
        <div className="flex flex-col items-center gap-4" data-testid="payment-success">
          <div className="w-16 h-16 rounded-full bg-emerald-500/15 border border-emerald-500/40 flex items-center justify-center">
            <CheckCircle2 className="w-9 h-9 text-emerald-400" />
          </div>
          <h1 className="font-display text-2xl font-bold text-white">¡Pago completado!</h1>
          {credits != null && (
            <p className="text-slate-300 flex items-center gap-1.5">
              <Zap className="w-4 h-4 text-cyan-400 fill-cyan-400" /> +{credits} créditos añadidos a tu cuenta
            </p>
          )}
          <Button onClick={() => navigate("/app")} data-testid="back-to-app"
            className="rounded-full bg-gradient-to-r from-violet-600 to-cyan-500 hover:brightness-110 text-white font-semibold transition-[filter]">
            Volver al panel
          </Button>
        </div>
      )}
      {state === "failed" && (
        <div className="flex flex-col items-center gap-4" data-testid="payment-failed">
          <div className="w-16 h-16 rounded-full bg-red-500/15 border border-red-500/40 flex items-center justify-center">
            <XCircle className="w-9 h-9 text-red-400" />
          </div>
          <h1 className="font-display text-2xl font-bold text-white">No pudimos confirmar el pago</h1>
          <p className="text-slate-400 max-w-md">Si el cargo se realizó, los créditos se añadirán automáticamente. Revisa tu panel en unos minutos.</p>
          <Button onClick={() => navigate("/app")} className="rounded-full bg-white/10 hover:bg-white/20 text-white">Volver al panel</Button>
        </div>
      )}
    </div>
  );
}
