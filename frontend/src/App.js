import "@/App.css";
import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/context/AuthContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import Landing from "@/pages/Landing";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import AuthCallback from "@/pages/AuthCallback";
import Dashboard from "@/pages/Dashboard";
import PropertyView from "@/pages/PropertyView";
import Editor from "@/pages/Editor";
import Admin from "@/pages/Admin";
import Settings from "@/pages/Settings";
import PaymentSuccess from "@/pages/PaymentSuccess";
import PaymentCancel from "@/pages/PaymentCancel";

function AppRouter() {
  const location = useLocation();
  if (location.hash?.includes("session_id=")) {
    return <AuthCallback />;
  }
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/payment/success" element={<PaymentSuccess />} />
      <Route path="/payment/cancel" element={<PaymentCancel />} />
      <Route
        path="/app"
        element={
          <ProtectedRoute>
            <Dashboard />
          </ProtectedRoute>
        }
      />
      <Route
        path="/app/property/:id"
        element={
          <ProtectedRoute>
            <PropertyView />
          </ProtectedRoute>
        }
      />
      <Route
        path="/app/property/:id/photo/:photoId"
        element={
          <ProtectedRoute>
            <Editor />
          </ProtectedRoute>
        }
      />
      <Route
        path="/app/admin"
        element={
          <ProtectedRoute>
            <Admin />
          </ProtectedRoute>
        }
      />
      <Route
        path="/app/settings"
        element={
          <ProtectedRoute>
            <Settings />
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <AuthProvider>
          <AppRouter />
          <Toaster position="top-right" theme="dark" richColors />
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
