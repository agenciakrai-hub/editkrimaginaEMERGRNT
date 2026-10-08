import { useState, useEffect } from "react";
import { Download, Edit3, GitCompare, Cpu, X, ZoomIn, Save } from "lucide-react";
import { motion } from "framer-motion";
import ComparisonDialog from "./ComparisonDialog";

export default function ResultsGallery({ results, onDownload, onEdit, onAiEdit, onSave, aiBusy }) {
  const [compareResult, setCompareResult] = useState(null);
  const [viewResult, setViewResult] = useState(null);

  useEffect(() => {
    if (!viewResult) return;
    const onKey = (e) => { if (e.key === "Escape") setViewResult(null); };
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [viewResult]);

  return (
    <>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {results.map((r) => (
          <motion.div
            key={r.index}
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="rounded-xl overflow-hidden border border-gray-800 bg-gray-900/50"
          >
            <div
              className="aspect-[4/3] bg-gray-950 relative group cursor-zoom-in"
              onClick={() => setViewResult(r)}
            >
              <img src={r.url} alt={`HDR ${r.index + 1}`} className="w-full h-full object-cover" />
              <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors flex items-center justify-center">
                <ZoomIn className="w-8 h-8 text-white opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
            </div>
            <div className="p-3 flex items-center justify-between">
              <span className="text-xs font-mono text-gray-400">Escena {r.index + 1}</span>
              <div className="flex gap-2"><button onClick={() => onSave(r)} title="Guardar copia en propiedad" className="p-1.5 rounded-lg bg-gray-800 text-cyan-300"><Save className="w-3.5 h-3.5" /></button>
                <button
                  onClick={() => setCompareResult(r)}
                  className="p-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-cyan-300"
                  title="Comparar original vs fusionada"
                >
                  <GitCompare className="w-3.5 h-3.5" />
                </button>
                <button
                  disabled={aiBusy} onClick={() => onAiEdit(r)}
                  className="p-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-violet-300"
                  title="Acabado IA · 1 crédito"
                >
                  <Cpu className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => onDownload(r)}
                  className="p-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300"
                  title="Descargar"
                >
                  <Download className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => onEdit(r)}
                  className="p-1.5 rounded-lg bg-gradient-to-r from-blue-500 to-cyan-400 text-white"
                  title="Editor manual"
                >
                  <Edit3 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          </motion.div>
        ))}
      </div>
      <ComparisonDialog result={compareResult} onClose={() => setCompareResult(null)} />

      {viewResult && (
        <div
          className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4"
          onClick={() => setViewResult(null)}
        >
          <button
            className="absolute top-4 right-4 p-2 rounded-full bg-white/10 hover:bg-white/20 text-white transition"
            onClick={() => setViewResult(null)}
          >
            <X className="w-6 h-6" />
          </button>
          <img
            src={viewResult.url}
            alt={`HDR ${viewResult.index + 1}`}
            className="max-w-full max-h-full object-contain rounded-lg"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </>
  );
}