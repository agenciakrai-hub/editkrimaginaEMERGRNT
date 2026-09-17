import React from "react";

/**
 * Watchful wordmark: an eye/aperture "watching" glyph + text. All CSS/SVG, no assets.
 */
export default function Logo({ className = "", showText = true, size = 32 }) {
  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <svg width={size} height={size} viewBox="0 0 40 40" fill="none" className="shrink-0">
        <defs>
          <linearGradient id="wf-grad" x1="0" y1="0" x2="40" y2="40">
            <stop offset="0%" stopColor="#8B5CF6" />
            <stop offset="100%" stopColor="#06B6D4" />
          </linearGradient>
        </defs>
        <rect x="1" y="1" width="38" height="38" rx="11" stroke="url(#wf-grad)" strokeWidth="2" />
        <path
          d="M8 20c3.5-6 20.5-6 24 0-3.5 6-20.5 6-24 0Z"
          stroke="url(#wf-grad)"
          strokeWidth="2.2"
          strokeLinejoin="round"
        />
        <circle cx="20" cy="20" r="4.5" fill="url(#wf-grad)" />
      </svg>
      {showText && (
        <span className="font-display font-bold text-xl tracking-tight text-white">
          Watchful
        </span>
      )}
    </div>
  );
}
