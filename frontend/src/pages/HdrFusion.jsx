import Header from "@/components/Header";
import { Link, useSearchParams } from "react-router-dom";
import BracketingModule from "@/components/bracketing/BracketingModule";
export default function HdrFusion() {
  const [params] = useSearchParams();
  return <div className="min-h-screen bg-background text-white"><Header /><main className="max-w-7xl mx-auto px-4 py-8"><Link to="/app" className="text-slate-400 hover:text-white inline-block mb-6">← Dashboard</Link><BracketingModule initialProjectId={params.get("property_id") || ""} /></main></div>;
}
