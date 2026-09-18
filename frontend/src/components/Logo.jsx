import React from "react";

/**
 * edit KRimagina brand: KR logo badge + wordmark.
 */
export default function Logo({ className = "", showText = true, size = 36 }) {
  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <span
        className="shrink-0 rounded-xl bg-white overflow-hidden ring-1 ring-white/20 shadow-[0_0_18px_rgba(139,92,246,0.25)]"
        style={{
          width: size,
          height: size,
          backgroundImage: `url(${process.env.PUBLIC_URL || ""}/logo-krimagina.jpg)`,
          backgroundRepeat: "no-repeat",
          backgroundSize: "255%",
          backgroundPosition: "46% 24%",
        }}
        aria-label="edit KRimagina"
      />
      {showText && (
        <span className="font-display font-bold text-xl tracking-tight text-white whitespace-nowrap">
          edit <span className="bg-gradient-to-r from-violet-400 to-cyan-400 bg-clip-text text-transparent">KR</span>imagina
        </span>
      )}
    </div>
  );
}
