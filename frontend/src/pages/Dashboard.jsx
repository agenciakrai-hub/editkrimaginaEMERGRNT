import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import Header from "@/components/Header";
import AuthImage from "@/components/AuthImage";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { motion } from "framer-motion";
import { Plus, Home, Images, Loader2, Trash2, MapPin } from "lucide-react";
import { toast } from "sonner";

export default function Dashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [properties, setProperties] = useState(null);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [creating, setCreating] = useState(false);

  const load = async () => {
    try {
      const { data } = await api.get("/properties");
      setProperties(data);
    } catch (err) {
      toast.error(apiError(err));
      setProperties([]);
    }
  };

  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault();
    setCreating(true);
    try {
      const { data } = await api.post("/properties", { name, address });
      setOpen(false); setName(""); setAddress("");
      toast.success("Propiedad creada");
      navigate(`/app/property/${data.id}`);
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setCreating(false);
    }
  };

  const remove = async (id) => {
    try {
      await api.delete(`/properties/${id}`);
      setProperties((p) => p.filter((x) => x.id !== id));
      toast.success("Propiedad eliminada");
    } catch (err) {
      toast.error(apiError(err));
    }
  };

  return (
    <div className="min-h-screen bg-background grain">
      <Header />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-10">
        <div className="flex items-end justify-between flex-wrap gap-4 mb-8">
          <div>
            <h1 className="font-display text-3xl font-bold text-white">Mis propiedades</h1>
            <p className="text-slate-400 mt-1">Hola {user?.name?.split(" ")[0] || "👋"}, gestiona tus inmuebles y ediciones.</p>
          </div>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button data-testid="new-property-btn"
                className="rounded-full bg-gradient-to-r from-violet-600 to-cyan-500 hover:brightness-110 text-white font-semibold transition-[filter]">
                <Plus className="w-4 h-4 mr-1.5" /> Nueva propiedad
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-[#1E1A29] border-white/10 text-white">
              <DialogHeader><DialogTitle className="font-display">Crear propiedad</DialogTitle></DialogHeader>
              <form onSubmit={create} className="space-y-4 mt-2">
                <div className="space-y-2">
                  <Label className="text-slate-300">Nombre / referencia</Label>
                  <Input required data-testid="property-name" value={name} onChange={(e) => setName(e.target.value)}
                    placeholder="Ático Calle Mayor 12" className="bg-secondary/60 border-white/10" />
                </div>
                <div className="space-y-2">
                  <Label className="text-slate-300">Dirección (opcional)</Label>
                  <Input data-testid="property-address" value={address} onChange={(e) => setAddress(e.target.value)}
                    placeholder="Madrid, España" className="bg-secondary/60 border-white/10" />
                </div>
                <DialogFooter>
                  <Button type="submit" disabled={creating} data-testid="property-create-submit"
                    className="rounded-full bg-cyan-500 hover:bg-cyan-400 text-black font-semibold">
                    {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : "Crear y subir fotos"}
                  </Button>
                </DialogFooter>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        {properties === null ? (
          <div className="flex justify-center py-24"><Loader2 className="w-7 h-7 animate-spin text-cyan-400" /></div>
        ) : properties.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-white/10 bg-[#15131C]/50 py-24 text-center" data-testid="empty-state">
            <div className="w-16 h-16 rounded-2xl mx-auto bg-gradient-to-br from-violet-600/20 to-cyan-500/20 border border-white/10 flex items-center justify-center mb-5">
              <Home className="w-7 h-7 text-cyan-400" />
            </div>
            <h3 className="font-display text-xl font-medium text-white">Aún no tienes propiedades</h3>
            <p className="text-slate-400 mt-2">Crea tu primer inmueble y sube sus fotos para empezar a editar.</p>
            <Button onClick={() => setOpen(true)} className="mt-6 rounded-full bg-white/10 hover:bg-white/20 text-white">
              <Plus className="w-4 h-4 mr-1.5" /> Nueva propiedad
            </Button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6" data-testid="properties-grid">
            {properties.map((p, i) => (
              <motion.div key={p.id}
                initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}
                className="group relative rounded-2xl border border-white/5 bg-[#15131C] overflow-hidden hover:-translate-y-1 transition-transform duration-300">
                <button onClick={() => navigate(`/app/property/${p.id}`)} data-testid={`property-card-${p.id}`}
                  className="block w-full text-left">
                  <div className="aspect-[4/3] bg-secondary/40 overflow-hidden">
                    {p.cover_path ? (
                      <AuthImage path={p.cover_path} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center"><Home className="w-8 h-8 text-slate-600" /></div>
                    )}
                  </div>
                  <div className="p-4">
                    <h3 className="font-medium text-white truncate">{p.name}</h3>
                    {p.address && (
                      <p className="text-xs text-slate-500 mt-1 flex items-center gap-1 truncate">
                        <MapPin className="w-3 h-3 shrink-0" /> {p.address}
                      </p>
                    )}
                    <div className="flex items-center gap-1.5 mt-3 text-xs text-slate-400">
                      <Images className="w-3.5 h-3.5" /> {p.photo_count} fotos
                    </div>
                  </div>
                </button>
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <button data-testid={`delete-property-${p.id}`}
                      className="absolute top-3 right-3 w-8 h-8 rounded-full bg-black/60 backdrop-blur flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-500/80">
                      <Trash2 className="w-4 h-4 text-white" />
                    </button>
                  </AlertDialogTrigger>
                  <AlertDialogContent className="bg-[#1E1A29] border-white/10 text-white">
                    <AlertDialogHeader>
                      <AlertDialogTitle>¿Eliminar propiedad?</AlertDialogTitle>
                      <AlertDialogDescription className="text-slate-400">
                        Se eliminará "{p.name}" y todas sus fotos. Esta acción no se puede deshacer.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel className="bg-white/5 border-white/10 hover:bg-white/10 text-white">Cancelar</AlertDialogCancel>
                      <AlertDialogAction onClick={() => remove(p.id)} data-testid={`confirm-delete-${p.id}`}
                        className="bg-red-500 hover:bg-red-400 text-white">Eliminar</AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </motion.div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
