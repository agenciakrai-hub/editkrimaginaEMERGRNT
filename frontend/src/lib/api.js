import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const TOKEN_KEY = "watchful_token";

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t) => localStorage.setItem(TOKEN_KEY, t);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

export const api = axios.create({
  baseURL: API,
  withCredentials: true,
});

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Build a direct file URL for <img src> using query-param auth.
export const fileUrl = (path) => {
  if (!path) return null;
  const token = getToken();
  return `${API}/files/${path}?token=${encodeURIComponent(token || "")}`;
};

export function apiError(err, fallback = "Algo salió mal. Inténtalo de nuevo.") {
  const detail = err?.response?.data?.detail;
  if (detail == null) return err?.message || fallback;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((e) => (e?.msg ? e.msg : JSON.stringify(e))).join(" ");
  if (detail?.msg) return detail.msg;
  return String(detail);
}
