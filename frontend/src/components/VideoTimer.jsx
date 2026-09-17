import React, { useEffect, useState } from "react";

const fmt = (s) => {
  s = Math.max(0, Math.round(s));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${String(r).padStart(2, "0")}`;
};

/** Live countdown shown while a video is generating. createdAt = ISO string, etaSeconds = estimate. */
export default function VideoTimer({ createdAt, etaSeconds = 40 }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const start = createdAt ? new Date(createdAt).getTime() : now;
  const elapsed = Math.max(0, (now - start) / 1000);
  const remaining = etaSeconds - elapsed;
  const pct = Math.min(98, Math.max(4, (elapsed / etaSeconds) * 100));
  const finishing = remaining <= 0;

  return (
    <div className="w-full px-6" data-testid="video-timer">
      <div className="flex items-center justify-between text-xs mb-2">
        <span className="text-slate-400">Generando video…</span>
        <span className="text-cyan-300 font-medium tabular-nums" data-testid="video-timer-remaining">
          {finishing ? "casi listo…" : `~${fmt(remaining)} restantes`}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-black/40 overflow-hidden">
        <div
          className={`h-full bg-gradient-to-r from-violet-500 to-cyan-400 rounded-full transition-[width] duration-1000 ease-linear ${finishing ? "animate-pulse" : ""}`}
          style={{ width: `${finishing ? 100 : pct}%` }}
        />
      </div>
      <div className="text-[11px] text-slate-500 mt-1.5 tabular-nums">
        Transcurrido {fmt(elapsed)}
      </div>
    </div>
  );
}
