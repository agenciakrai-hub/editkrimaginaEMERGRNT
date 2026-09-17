import React, { useEffect, useRef } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { api, setToken } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import Logo from "@/components/Logo";
import { Loader2 } from "lucide-react";

export default function AuthCallback() {
  const navigate = useNavigate();
  const location = useLocation();
  const { setUser } = useAuth();
  const processed = useRef(false);

  useEffect(() => {
    if (processed.current) return;
    processed.current = true;

    const hash = location.hash || window.location.hash;
    const sessionId = new URLSearchParams(hash.replace(/^#/, "")).get("session_id");
    if (!sessionId) {
      navigate("/login", { replace: true });
      return;
    }

    (async () => {
      try {
        const { data } = await api.post("/auth/session", { session_id: sessionId });
        if (data.token) setToken(data.token);
        setUser(data.user);
        window.history.replaceState(null, "", "/app");
        navigate("/app", { replace: true });
      } catch (e) {
        navigate("/login", { replace: true });
      }
    })();
  }, [location, navigate, setUser]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-6 bg-background grain">
      <Logo size={44} />
      <div className="flex items-center gap-2 text-slate-400">
        <Loader2 className="w-5 h-5 animate-spin text-cyan-400" />
        Iniciando sesión…
      </div>
    </div>
  );
}
