import React from "react";
import { useNavigate } from "react-router-dom";
import Logo from "@/components/Logo";
import { Button } from "@/components/ui/button";
import { XCircle } from "lucide-react";

export default function PaymentCancel() {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-6 bg-background grain px-6 text-center">
      <Logo size={40} />
      <div className="w-16 h-16 rounded-full bg-white/5 border border-white/10 flex items-center justify-center">
        <XCircle className="w-9 h-9 text-slate-400" />
      </div>
      <h1 className="font-display text-2xl font-bold text-white">Pago cancelado</h1>
      <p className="text-slate-400 max-w-md">No se ha realizado ningún cargo. Puedes comprar créditos cuando quieras.</p>
      <Button onClick={() => navigate("/app")} data-testid="cancel-back"
        className="rounded-full bg-gradient-to-r from-violet-600 to-cyan-500 hover:brightness-110 text-white font-semibold transition-[filter]">
        Volver al panel
      </Button>
    </div>
  );
}
