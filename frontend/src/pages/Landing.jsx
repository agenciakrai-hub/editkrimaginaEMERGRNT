import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import Logo from "@/components/Logo";
import BeforeAfterSlider from "@/components/BeforeAfterSlider";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import {
  Sun, Moon, Eraser, Sofa, Wand2, SlidersHorizontal, Sparkles, ArrowRight, Zap, ShieldCheck, Layers, Check, Crown,
} from "lucide-react";

const BEFORE = "https://images.unsplash.com/photo-1605276374104-dee2a0ed3cd6?crop=entropy&cs=srgb&fm=jpg&q=85";
const AFTER = "https://images.unsplash.com/photo-1494526585095-c41746248156?crop=entropy&cs=srgb&fm=jpg&q=85";

const features = [
  { icon: Sun, title: "Reemplazo de cielo", desc: "Gris y nublado a azul soleado, controlable.", span: "lg:col-span-5" },
  { icon: Moon, title: "Día a atardecer", desc: "Fachadas al anochecer, cálidas y premium.", span: "lg:col-span-4" },
  { icon: Sparkles, title: "Luz + HDR", desc: "Interiores brillantes y balanceados.", span: "lg:col-span-3" },
  { icon: Eraser, title: "Quitar objetos", desc: "Cables, coches, basura y desorden fuera.", span: "lg:col-span-3" },
  { icon: Sofa, title: "Home staging virtual", desc: "Amuebla estancias vacías por estilo.", span: "lg:col-span-5" },
  { icon: SlidersHorizontal, title: "Enderezar perspectiva", desc: "Líneas rectas y verticales corregidas.", span: "lg:col-span-4" },
];

export default function Landing() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const cta = user ? "/app" : "/register";
  const [plans, setPlans] = useState([]);

  useEffect(() => {
    api.get("/plans").then((r) => setPlans(r.data)).catch(() => setPlans([]));
  }, []);

  const PERIODS = { monthly: "mes", yearly: "año", one_time: "pago único" };

  return (
    <div className="min-h-screen bg-background text-white grain">
      <header className="sticky top-0 z-40 backdrop-blur-xl bg-[#15131C]/70 border-b border-white/5">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <Logo />
          <nav className="flex items-center gap-3">
            {user ? (
              <Button onClick={() => navigate("/app")} data-testid="nav-app"
                className="rounded-full bg-white/10 hover:bg-white/20 text-white">Mi panel</Button>
            ) : (
              <>
                <Link to="/login" data-testid="nav-login" className="text-sm text-slate-300 hover:text-white px-3">Entrar</Link>
                <Button onClick={() => navigate("/register")} data-testid="nav-register"
                  className="rounded-full bg-gradient-to-r from-violet-600 to-cyan-500 hover:brightness-110 text-white transition-[filter]">
                  Empezar gratis
                </Button>
              </>
            )}
          </nav>
        </div>
      </header>

      {/* Hero */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 pt-16 sm:pt-24 pb-16 grid lg:grid-cols-12 gap-12 items-center">
        <motion.div
          initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}
          className="lg:col-span-6"
        >
          <span className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.2em] font-semibold text-violet-400 mb-6">
            <Sparkles className="w-3.5 h-3.5" /> Estudio inmobiliario con IA
          </span>
          <h1 className="font-display text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight leading-[1.05]">
            Fotos de inmuebles que
            <span className="bg-gradient-to-r from-violet-400 to-cyan-400 bg-clip-text text-transparent"> venden</span>.
            <br />En segundos, por IA.
          </h1>
          <p className="mt-6 text-lg text-slate-400 max-w-xl leading-relaxed">
            Reemplaza cielos, crea atardeceres, quita el desorden y amuebla estancias vacías.
            Organiza cada inmueble como un proyecto y exporta un paquete listo para publicar.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-4">
            <Button onClick={() => navigate(cta)} data-testid="hero-cta"
              className="h-12 px-7 rounded-full text-base bg-gradient-to-r from-violet-600 to-cyan-500 hover:brightness-110 text-white font-semibold transition-[filter]">
              Empezar gratis <ArrowRight className="w-4 h-4 ml-2" />
            </Button>
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <Zap className="w-4 h-4 text-cyan-400 fill-cyan-400" /> 30 créditos gratis · sin tarjeta
            </div>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.7, delay: 0.15 }}
          className="lg:col-span-6"
        >
          <div className="rounded-2xl overflow-hidden border border-white/10 shadow-[0_8px_60px_rgba(139,92,246,0.25)]">
            <BeforeAfterSlider beforePath={BEFORE} afterPath={AFTER} className="w-full aspect-[4/3] bg-black" />
          </div>
          <p className="text-center text-xs text-slate-500 mt-3">Arrastra para comparar · Antes / Después (Twilight IA)</p>
        </motion.div>
      </section>

      {/* Features bento */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 py-16">
        <h2 className="font-display text-2xl sm:text-3xl font-semibold mb-3">Todo un estudio, por foto o por lote</h2>
        <p className="text-slate-400 mb-10 max-w-2xl">Ediciones esenciales gratis. Staging, twilight y lotes grandes con créditos.</p>
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          {features.map((f, i) => (
            <motion.div
              key={f.title}
              initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
              transition={{ duration: 0.4, delay: i * 0.05 }}
              className={`${f.span} col-span-1 rounded-2xl border border-white/5 bg-[#15131C] p-6 hover:-translate-y-1 transition-transform duration-300`}
            >
              <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-violet-600/20 to-cyan-500/20 border border-white/10 flex items-center justify-center mb-4">
                <f.icon className="w-5 h-5 text-cyan-400" />
              </div>
              <h3 className="font-display text-lg font-medium">{f.title}</h3>
              <p className="text-sm text-slate-400 mt-1.5">{f.desc}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* Values */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 py-16 grid sm:grid-cols-3 gap-6">
        {[
          { icon: Layers, t: "Trabaja por propiedad", d: "Cada inmueble agrupa sus fotos, ediciones y videos en un solo proyecto." },
          { icon: Wand2, t: "Procesamiento por lotes", d: "Aplica una edición a todas las fotos del piso de una vez." },
          { icon: ShieldCheck, t: "Cumplimiento", d: "Etiqueta de divulgación 'Imagen editada digitalmente' para portales y MLS." },
        ].map((v) => (
          <div key={v.t} className="rounded-2xl border border-white/5 bg-[#15131C]/60 p-7">
            <v.icon className="w-6 h-6 text-violet-400 mb-4" />
            <h3 className="font-display text-lg font-medium">{v.t}</h3>
            <p className="text-sm text-slate-400 mt-2">{v.d}</p>
          </div>
        ))}
      </section>

      {/* Pricing (dynamic plans from admin) */}
      {plans.length > 0 && (
        <section id="planes" className="max-w-7xl mx-auto px-4 sm:px-6 py-16" data-testid="pricing-section">
          <h2 className="font-display text-2xl sm:text-3xl font-semibold mb-3">Planes a tu medida</h2>
          <p className="text-slate-400 mb-10 max-w-2xl">Elige un plan con créditos incluidos. ¿Se te acaban? Compra créditos extra cuando quieras.</p>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {plans.map((p, i) => (
              <motion.div
                key={p.id}
                initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
                transition={{ duration: 0.4, delay: i * 0.05 }}
                data-testid={`plan-card-${p.id}`}
                className={`relative rounded-2xl border p-7 bg-[#15131C] ${p.highlight ? "border-violet-500/60 shadow-[0_0_40px_rgba(139,92,246,0.25)]" : "border-white/5"}`}
              >
                {p.highlight && (
                  <span className="absolute -top-3 left-7 inline-flex items-center gap-1 text-xs font-semibold px-3 py-1 rounded-full bg-gradient-to-r from-violet-600 to-cyan-500 text-white">
                    <Crown className="w-3 h-3" /> Recomendado
                  </span>
                )}
                <h3 className="font-display text-xl font-medium">{p.name}</h3>
                <p className="mt-3 text-4xl font-bold">
                  {p.price_eur}€ <span className="text-base font-normal text-slate-400">/ {PERIODS[p.period] || p.period}</span>
                </p>
                <p className="mt-1 text-sm text-cyan-300 flex items-center gap-1.5"><Zap className="w-4 h-4 fill-cyan-300" /> {p.credits} créditos incluidos</p>
                <ul className="mt-5 space-y-2.5">
                  {(p.features || []).map((f, idx) => (
                    <li key={idx} className="flex items-start gap-2 text-sm text-slate-300">
                      <Check className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" /> {f}
                    </li>
                  ))}
                </ul>
                <Button onClick={() => navigate(cta)} data-testid={`plan-cta-${p.id}`}
                  className={`mt-7 w-full rounded-full font-semibold ${p.highlight ? "bg-gradient-to-r from-violet-600 to-cyan-500 text-white hover:brightness-110 transition-[filter]" : "bg-white/10 hover:bg-white/20 text-white"}`}>
                  Empezar
                </Button>
              </motion.div>
            ))}
          </div>
        </section>
      )}

      {/* Final CTA */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 py-20">
        <div className="rounded-3xl border border-white/10 bg-gradient-to-br from-violet-600/15 to-cyan-500/10 p-10 sm:p-16 text-center">
          <h2 className="font-display text-3xl sm:text-4xl font-bold">Publica antes. Vende más rápido.</h2>
          <p className="mt-4 text-slate-300 max-w-xl mx-auto">Sube las fotos de tu próximo inmueble y ve la diferencia en segundos.</p>
          <Button onClick={() => navigate(cta)} data-testid="footer-cta"
            className="mt-8 h-12 px-8 rounded-full text-base bg-white text-black hover:bg-slate-200 font-semibold">
            Crear mi primera propiedad <ArrowRight className="w-4 h-4 ml-2" />
          </Button>
        </div>
      </section>

      <footer className="border-t border-white/5 py-8 text-center text-sm text-slate-500">
        <Logo className="justify-center mb-3" size={26} />
        Watchful · Fotografía y video inmobiliario con IA
      </footer>
    </div>
  );
}
