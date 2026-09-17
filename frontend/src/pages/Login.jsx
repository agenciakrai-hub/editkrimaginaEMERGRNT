import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import Logo from "@/components/Logo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const { loginWithToken } = useAuth();
  const navigate = useNavigate();

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await api.post("/auth/login", { email, password });
      loginWithToken(data.user, data.token);
      toast.success("¡Bienvenido de nuevo!");
      navigate("/app");
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setLoading(false);
    }
  };

  const google = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + "/app";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-background">
      <div className="hidden lg:block relative overflow-hidden grain">
        <img
          src="https://images.unsplash.com/photo-1494526585095-c41746248156?crop=entropy&cs=srgb&fm=jpg&q=85"
          alt=""
          className="absolute inset-0 w-full h-full object-cover opacity-60"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-[#0B0A10] via-[#0B0A10]/60 to-transparent" />
        <div className="absolute bottom-0 p-12">
          <h2 className="font-display text-4xl font-bold text-white leading-tight">
            Fotos que <span className="text-cyan-400">venden</span>.<br />En segundos.
          </h2>
          <p className="mt-4 text-slate-300 max-w-md">
            Edita fotos de inmuebles con IA y genera videos-tour por propiedad. Sin editores complejos.
          </p>
        </div>
      </div>

      <div className="flex flex-col justify-center px-6 sm:px-16 py-12">
        <Link to="/" className="mb-10">
          <Logo size={38} />
        </Link>
        <h1 className="font-display text-3xl font-bold text-white">Inicia sesión</h1>
        <p className="text-slate-400 mt-2 mb-8">Accede a tus propiedades y ediciones.</p>

        <form onSubmit={submit} className="space-y-5 max-w-sm">
          <div className="space-y-2">
            <Label htmlFor="email" className="text-slate-300">Email</Label>
            <Input
              id="email" type="email" required data-testid="login-email"
              value={email} onChange={(e) => setEmail(e.target.value)}
              placeholder="tu@agencia.com"
              className="bg-secondary/60 border-white/10 h-11"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password" className="text-slate-300">Contraseña</Label>
            <Input
              id="password" type="password" required data-testid="login-password"
              value={password} onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="bg-secondary/60 border-white/10 h-11"
            />
          </div>
          <Button
            type="submit" disabled={loading} data-testid="login-submit"
            className="w-full h-11 rounded-full bg-gradient-to-r from-violet-600 to-cyan-500 hover:brightness-110 text-white font-semibold transition-[filter]"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Entrar"}
          </Button>
        </form>

        <div className="flex items-center gap-3 my-6 max-w-sm">
          <div className="h-px flex-1 bg-white/10" />
          <span className="text-xs text-slate-500">o</span>
          <div className="h-px flex-1 bg-white/10" />
        </div>

        <Button
          onClick={google} variant="outline" data-testid="google-login"
          className="max-w-sm h-11 rounded-full border-white/15 bg-white/5 hover:bg-white/10 text-white"
        >
          <img src="https://www.google.com/favicon.ico" alt="" className="w-4 h-4 mr-2" />
          Continuar con Google
        </Button>

        <p className="text-slate-400 mt-8 text-sm">
          ¿No tienes cuenta?{" "}
          <Link to="/register" className="text-cyan-400 hover:underline" data-testid="go-register">Regístrate gratis</Link>
        </p>
      </div>
    </div>
  );
}
