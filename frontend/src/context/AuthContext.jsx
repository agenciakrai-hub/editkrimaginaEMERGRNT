import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, setToken, clearToken } from "@/lib/api";

const AuthContext = createContext(null);

export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined); // undefined = loading, null = anon, obj = user
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
      return data;
    } catch {
      setUser(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (window.location.hash?.includes("session_id=")) {
      setLoading(false);
      return;
    }
    refresh();
  }, [refresh]);

  const loginWithToken = (userObj, token) => {
    if (token) setToken(token);
    setUser(userObj);
  };

  const logout = async () => {
    try {
      await api.post("/auth/logout");
    } catch (e) {}
    clearToken();
    setUser(null);
  };

  const updateCredits = (credits) =>
    setUser((u) => (u ? { ...u, credits } : u));

  return (
    <AuthContext.Provider value={{ user, loading, refresh, loginWithToken, logout, updateCredits, setUser }}>
      {children}
    </AuthContext.Provider>
  );
}
