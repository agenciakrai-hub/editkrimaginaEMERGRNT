import React, { useRef, useState, useCallback, useEffect } from "react";
import { fileUrl } from "@/lib/api";

/**
 * Draggable before/after comparison slider.
 * beforePath / afterPath are storage paths served through the authed /files endpoint.
 */
export default function BeforeAfterSlider({ beforePath, afterPath, className = "" }) {
  const containerRef = useRef(null);
  const [pos, setPos] = useState(50);
  const dragging = useRef(false);

  const move = useCallback((clientX) => {
    const el = containerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    let p = ((clientX - rect.left) / rect.width) * 100;
    p = Math.max(0, Math.min(100, p));
    setPos(p);
  }, []);

  useEffect(() => {
    const onMove = (e) => {
      if (!dragging.current) return;
      const x = e.touches ? e.touches[0].clientX : e.clientX;
      move(x);
    };
    const stop = () => (dragging.current = false);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("touchmove", onMove);
    window.addEventListener("mouseup", stop);
    window.addEventListener("touchend", stop);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("touchmove", onMove);
      window.removeEventListener("mouseup", stop);
      window.removeEventListener("touchend", stop);
    };
  }, [move]);

  const before = beforePath?.startsWith("http") ? beforePath : fileUrl(beforePath);
  const after = afterPath?.startsWith("http") ? afterPath : fileUrl(afterPath);

  return (
    <div
      ref={containerRef}
      data-testid="before-after-slider"
      className={`relative overflow-hidden select-none touch-none ${className}`}
      onMouseDown={(e) => {
        dragging.current = true;
        move(e.clientX);
      }}
      onTouchStart={(e) => {
        dragging.current = true;
        move(e.touches[0].clientX);
      }}
    >
      <img src={after} alt="Después" className="absolute inset-0 w-full h-full object-contain pointer-events-none" draggable={false} />
      <div className="absolute inset-0 overflow-hidden pointer-events-none" style={{ width: `${pos}%` }}>
        <img
          src={before}
          alt="Antes"
          className="absolute inset-0 h-full object-contain pointer-events-none"
          style={{ width: containerRef.current ? containerRef.current.getBoundingClientRect().width : "100%", maxWidth: "none" }}
          draggable={false}
        />
        <span className="absolute top-3 left-3 text-xs font-semibold px-2 py-1 rounded-full bg-black/70 text-white">Antes</span>
      </div>
      <span className="absolute top-3 right-3 text-xs font-semibold px-2 py-1 rounded-full bg-cyan-500/80 text-black z-10">Después</span>

      <div className="absolute top-0 bottom-0 w-0.5 bg-white/90 z-20 pointer-events-none" style={{ left: `${pos}%` }}>
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-9 h-9 rounded-full bg-white shadow-lg flex items-center justify-center">
          <div className="flex gap-0.5">
            <div className="w-0.5 h-3.5 bg-violet-600 rounded-full" />
            <div className="w-0.5 h-3.5 bg-cyan-500 rounded-full" />
          </div>
        </div>
      </div>
    </div>
  );
}
