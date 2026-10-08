import { useState, useRef, useCallback } from "react";

/**
 * Comparador antes/después con slider arrastrable.
 * Usado por Editor IA (ResultViewerModal) y Fusión HDR (ComparisonDialog).
 */
export default function BeforeAfterSlider({ originalUrl, editedUrl, order }) {
  const [position, setPosition] = useState(50);
  const [ratio,setRatio]=useState(1.5);
  const containerRef = useRef(null);

  const updatePosition = useCallback((clientX) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const pct = ((clientX - rect.left) / rect.width) * 100;
    setPosition(Math.max(0, Math.min(100, pct)));
  }, []);

  return (
    <div
      ref={containerRef}
      style={{aspectRatio:ratio}}
      className="relative w-full overflow-hidden select-none cursor-ew-resize bg-black"
      onMouseMove={(e) => e.buttons === 1 && updatePosition(e.clientX)}
      onMouseDown={(e) => updatePosition(e.clientX)}
      onTouchStart={(e) => e.touches[0] && updatePosition(e.touches[0].clientX)}
      onTouchMove={(e) => e.touches[0] && updatePosition(e.touches[0].clientX)}
    >
      <img
        src={editedUrl}
        alt="Editada"
        onLoad={(e)=>setRatio(e.currentTarget.naturalWidth/e.currentTarget.naturalHeight)}
        className="absolute inset-0 w-full h-full object-contain"
        draggable={false}
      />
      <img
        src={originalUrl}
        alt="Original"
        className="absolute inset-0 w-full h-full object-contain"
        draggable={false}
        style={{ clipPath: `inset(0 ${100 - position}% 0 0)` }}
      />
      <div className="absolute top-2 left-2 px-2 py-0.5 rounded text-xs font-medium bg-black/60 text-white pointer-events-none">
        Original
      </div>
      <div className="absolute top-2 right-2 px-2 py-0.5 rounded text-xs font-medium bg-black/60 text-white pointer-events-none">
        Editada
      </div>
      <div
        className="absolute top-0 bottom-0 w-0.5 bg-white pointer-events-none"
        style={{ left: `${position}%` }}
      >
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-8 h-8 rounded-full bg-white shadow-lg flex items-center justify-center">
          <svg className="w-4 h-4 text-gray-800" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M8 7l-5 5 5 5M16 7l5 5-5 5" />
          </svg>
        </div>
      </div>
    </div>
  );
}