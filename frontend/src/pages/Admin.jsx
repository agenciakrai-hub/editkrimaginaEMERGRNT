import React from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import Header from "@/components/Header";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Loader2, Users, Activity, Cpu, ShieldCheck } from "lucide-react";
import AdminUsersPlans from "@/pages/admin/AdminUsersPlans";
import AdminUsage from "@/pages/admin/AdminUsage";
import AdminProviders from "@/pages/admin/AdminProviders";

export default function Admin() {
  const { user, loading } = useAuth();

  if (loading || user === undefined) {
    return <div className="min-h-screen bg-background flex items-center justify-center"><Loader2 className="w-7 h-7 animate-spin text-cyan-400" /></div>;
  }
  if (!user || !user.is_super_admin) return <Navigate to="/app" replace />;

  return (
    <div className="min-h-screen bg-background grain">
      <Header />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-10" data-testid="admin-panel">
        <div className="flex items-center gap-2 mb-8">
          <ShieldCheck className="w-6 h-6 text-violet-400" />
          <h1 className="font-display text-3xl font-bold text-white">Panel de administrador</h1>
        </div>

        <Tabs defaultValue="users">
          <TabsList className="bg-[#15131C] border border-white/5 rounded-full p-1 mb-8 flex-wrap h-auto">
            <TabsTrigger value="users" data-testid="tab-users" className="rounded-full data-[state=active]:bg-white/10 data-[state=active]:text-white text-slate-400 gap-1.5">
              <Users className="w-4 h-4" /> Usuarios y planes
            </TabsTrigger>
            <TabsTrigger value="usage" data-testid="tab-usage" className="rounded-full data-[state=active]:bg-white/10 data-[state=active]:text-white text-slate-400 gap-1.5">
              <Activity className="w-4 h-4" /> Consumo
            </TabsTrigger>
            <TabsTrigger value="providers" data-testid="tab-providers" className="rounded-full data-[state=active]:bg-white/10 data-[state=active]:text-white text-slate-400 gap-1.5">
              <Cpu className="w-4 h-4" /> Proveedores IA
            </TabsTrigger>
          </TabsList>
          <TabsContent value="users"><AdminUsersPlans /></TabsContent>
          <TabsContent value="usage"><AdminUsage /></TabsContent>
          <TabsContent value="providers"><AdminProviders /></TabsContent>
        </Tabs>
      </main>
    </div>
  );
}
