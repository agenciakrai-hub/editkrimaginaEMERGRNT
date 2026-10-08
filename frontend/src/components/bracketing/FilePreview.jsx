import { useEffect, useMemo } from "react";
import { X } from "lucide-react";

export default function FilePreview({ files, bracketSize, onClear }) {
  const scenes = bracketSize > 0 ? Math.floor(files.length / bracketSize) : 0;
  const remainder = bracketSize > 0 ? files.length % bracketSize : 0;
  const previews = useMemo(() => files.map((f) => URL.createObjectURL(f)), [files]);

  useEffect(() => {
    return () => previews.forEach((u) => URL.revokeObjectURL(u));
  }, [previews]);

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs text-gray-400">
          {files.length} archivo(s) · <span className="text-cyan-400">{scenes} escena(s) HDR</span>
          {remainder > 0 && <span className="text-amber-400"> · {remainder} sobran</span>}
        </p>
        <button onClick={onClear} className="text-xs text-gray-500 hover:text-gray-300 flex items-center gap-1">
          <X className="w-3 h-3" /> Limpiar
        </button>
      </div>
      <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 gap-2 max-h-48 overflow-y-auto scrollbar-thin p-1">
        {previews.map((url, i) => (
          <div key={i} className="relative aspect-square rounded-lg overflow-hidden border border-gray-800 bg-gray-900">
            <img src={url} alt="" className="w-full h-full object-cover" />
            <span className="absolute top-0.5 left-0.5 text-[9px] font-mono bg-black/70 text-cyan-300 px-1 rounded">
              {i + 1}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}