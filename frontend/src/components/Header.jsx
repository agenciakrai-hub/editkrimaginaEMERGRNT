import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import Logo from "@/components/Logo";
import BuyCreditsDialog from "@/components/BuyCreditsDialog";
import { Zap, LogOut, LayoutGrid, Plus } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
  DropdownMenuLabel,
} from "@/components/ui/dropdown-menu";

export default function Header({ actions }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [buyOpen, setBuyOpen] = useState(false);

  return (
    <>
    <header className="sticky top-0 z-40 backdrop-blur-xl bg-[#15131C]/80 border-b border-white/5">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
        <Link to="/app" data-testid="header-logo" className="flex items-center">
          <Logo />
        </Link>

        <div className="flex items-center gap-3 sm:gap-4">
          {actions}
          {user && (
            <>
              <button
                onClick={() => setBuyOpen(true)}
                data-testid="credit-counter"
                title="Comprar créditos"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-violet-500/40 bg-violet-500/10 shadow-[0_0_16px_rgba(139,92,246,0.25)] hover:bg-violet-500/20 transition-colors"
              >
                <Zap className="w-4 h-4 text-cyan-400 fill-cyan-400" />
                <span className="text-sm font-semibold text-white tabular-nums" data-testid="credit-amount">
                  {user.credits}
                </span>
                <span className="hidden sm:inline text-xs text-slate-400">créditos</span>
                <Plus className="w-3.5 h-3.5 text-cyan-300 ml-0.5" />
              </button>

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    data-testid="user-menu-trigger"
                    className="w-9 h-9 rounded-full bg-gradient-to-br from-violet-600 to-cyan-500 text-black font-semibold text-sm flex items-center justify-center focus:outline-none focus:ring-2 focus:ring-cyan-500 ring-offset-2 ring-offset-[#0B0A10]"
                  >
                    {user.picture ? (
                      <img src={user.picture} alt="" className="w-full h-full rounded-full object-cover" />
                    ) : (
                      (user.name || user.email || "U").charAt(0).toUpperCase()
                    )}
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-52 bg-[#1E1A29] border-white/10 text-white">
                  <DropdownMenuLabel className="truncate text-slate-300 font-normal">{user.email}</DropdownMenuLabel>
                  <DropdownMenuSeparator className="bg-white/10" />
                  <DropdownMenuItem
                    data-testid="menu-properties"
                    onClick={() => navigate("/app")}
                    className="cursor-pointer focus:bg-white/10"
                  >
                    <LayoutGrid className="w-4 h-4 mr-2" /> Mis propiedades
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    data-testid="logout-btn"
                    onClick={async () => {
                      await logout();
                      navigate("/");
                    }}
                    className="cursor-pointer focus:bg-white/10 text-red-300"
                  >
                    <LogOut className="w-4 h-4 mr-2" /> Cerrar sesión
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </>
          )}
        </div>
      </div>
    </header>
    <BuyCreditsDialog open={buyOpen} onOpenChange={setBuyOpen} />
    </>
  );
}
