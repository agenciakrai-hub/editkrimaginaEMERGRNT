import { Loader2, CheckCircle2, AlertCircle, Clock } from "lucide-react";
import { motion } from "framer-motion";

const STATUS_ICON = {
  pending: <Clock className="w-4 h-4 text-gray-500" />,
  processing: <Loader2 className="w-4 h-4 text-cyan-400 animate-spin" />,
  done: <CheckCircle2 className="w-4 h-4 text-emerald-400" />,
  error: <AlertCircle className="w-4 h-4 text-destructive" />,
};

export default function ProcessingPanel({ scenes }) {
  return (
    <div className="space-y-2">
      <p className="text-sm font-medium text-gray-200 mb-3">
        Procesando {scenes.length} escena(s) HDR en paralelo...
      </p>
      {scenes.map((s) => (
        <motion.div
          key={s.index}
          initial={{ opacity: 0, x: -10 }}
          animate={{ opacity: 1, x: 0 }}
          className="flex items-center gap-3 p-3 rounded-lg bg-gray-900/50 border border-gray-800"
        >
          <span className="text-xs font-mono text-gray-500 w-20">Escena {s.index + 1}</span>
          <div className="flex-1">
            <div className="h-2 rounded-full bg-gray-800 overflow-hidden">
              <motion.div
                className="h-full bg-gradient-to-r from-blue-500 to-cyan-400"
                animate={{ width: `${s.progress}%` }}
                transition={{ duration: 0.3 }}
              />
            </div>
          </div>
          <span className="text-xs text-gray-400 w-10 text-right">{s.progress}%</span>
          {STATUS_ICON[s.status]}
        </motion.div>
      ))}
    </div>
  );
}