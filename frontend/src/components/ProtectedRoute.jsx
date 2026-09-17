import React from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Loader2 } from "lucide-react";

export default function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();

  if (loading || user === undefined) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" data-testid="auth-loading" />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return children;
}
