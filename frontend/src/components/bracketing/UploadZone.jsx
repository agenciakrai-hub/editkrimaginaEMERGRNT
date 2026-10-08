import { useCallback, useState } from "react";
import { UploadCloud } from "lucide-react";
import { motion } from "framer-motion";

const IMAGE_EXTENSIONS = [
  ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp", ".gif",
  ".raw", ".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf", ".orf", ".rw2", ".pef", ".srw",
];

function isImageFile(f) {
  if (f.type && f.type.startsWith("image/")) return true;
  const dot = f.name.lastIndexOf(".");
  if (dot < 0) return false;
  const ext = f.name.slice(dot).toLowerCase();
  return IMAGE_EXTENSIONS.includes(ext);
}

export default function UploadZone({ onFilesSelected, disabled }) {
  const [dragOver, setDragOver] = useState(false);

  const handleDrop = useCallback(
    (e) => {
      e.preventDefault();
      setDragOver(false);
      if (disabled) return;
      const files = Array.from(e.dataTransfer.files).filter(isImageFile);
      if (files.length) onFilesSelected(files);
    },
    [onFilesSelected, disabled]
  );

  const handleSelect = (e) => {
    const files = Array.from(e.target.files || []).filter(isImageFile);
    if (files.length) onFilesSelected(files);
    e.target.value = "";
  };

  return (
    <motion.div
      whileHover={{ scale: disabled ? 1 : 1.005 }}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      className={`relative border-2 border-dashed rounded-2xl p-10 text-center transition-colors ${
        dragOver ? "border-cyan-400 bg-cyan-400/5" : "border-gray-700 bg-gray-900/50"
      } ${disabled ? "opacity-50 pointer-events-none" : ""}`}
    >
      <input
        type="file"
        multiple

        className="hidden"
        id="bracketing-upload"
        onChange={handleSelect}
        disabled={disabled}
      />
      <label htmlFor="bracketing-upload" className="cursor-pointer flex flex-col items-center gap-3">
        <div className="w-14 h-14 rounded-full bg-gradient-to-br from-blue-500 to-cyan-400 flex items-center justify-center">
          <UploadCloud className="w-7 h-7 text-white" />
        </div>
        <div>
          <p className="text-sm font-medium text-gray-200">
            Arrastra tus fotos RAW o haz clic para seleccionar
          </p>
          <p className="text-xs text-gray-500 mt-1">JPG, PNG · RAW con vista previa · Salida hasta 2400 px</p>
        </div>
      </label>
    </motion.div>
  );
}