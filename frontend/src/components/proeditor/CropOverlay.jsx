import { useRef } from "react";

export default function CropOverlay({ crop, containerWidth, containerHeight, onChange }) {
  const dragging = useRef(null);

  const getNorm = (clientX, clientY, rect) => ({
    x: Math.max(0, Math.min(1, (clientX - rect.left) / rect.width)),
    y: Math.max(0, Math.min(1, (clientY - rect.top) / rect.height)),
  });

  const startDrag = (handle) => (e) => {
    e.stopPropagation();
    const parent = e.currentTarget.parentElement;
    const rect = parent.getBoundingClientRect();
    const p = getNorm(e.clientX, e.clientY, rect);
    dragging.current = { handle, rect, startPointer: p, startCrop: { ...crop } };
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const onMove = (e) => {
    const d = dragging.current;
    if (!d) return;
    const { x, y } = getNorm(e.clientX, e.clientY, d.rect);
    let { x: cx, y: cy, width: cw, height: ch } = d.startCrop;

    if (d.handle === "tl") {
      cx = Math.min(x, cx + cw - 0.05);
      cy = Math.min(y, cy + ch - 0.05);
      cw = d.startCrop.x + d.startCrop.width - cx;
      ch = d.startCrop.y + d.startCrop.height - cy;
    } else if (d.handle === "tr") {
      cy = Math.min(y, cy + ch - 0.05);
      cw = Math.max(0.05, x - d.startCrop.x);
      ch = d.startCrop.y + d.startCrop.height - cy;
    } else if (d.handle === "bl") {
      cx = Math.min(x, d.startCrop.x + d.startCrop.width - 0.05);
      cw = d.startCrop.x + d.startCrop.width - cx;
      ch = Math.max(0.05, y - d.startCrop.y);
    } else if (d.handle === "br") {
      cw = Math.max(0.05, x - d.startCrop.x);
      ch = Math.max(0.05, y - d.startCrop.y);
    } else if (d.handle === "move") {
      const dx = x - d.startPointer.x;
      const dy = y - d.startPointer.y;
      cx = Math.max(0, Math.min(1 - cw, d.startCrop.x + dx));
      cy = Math.max(0, Math.min(1 - ch, d.startCrop.y + dy));
    }
    onChange({ x: cx, y: cy, width: cw, height: ch });
  };

  const onUp = (e) => {
    dragging.current = null;
    try { e.currentTarget.releasePointerCapture(e.pointerId); } catch (_) {}
  };

  const left = crop.x * containerWidth;
  const top = crop.y * containerHeight;
  const width = crop.width * containerWidth;
  const height = crop.height * containerHeight;
  const hs = 5;

  return (
    <div className="absolute inset-0" onPointerMove={onMove} onPointerUp={onUp}>
      <div className="absolute bg-black/50" style={{ left: 0, top: 0, width: "100%", height: top }} />
      <div className="absolute bg-black/50" style={{ left: 0, top: top + height, width: "100%", height: containerHeight - top - height }} />
      <div className="absolute bg-black/50" style={{ left: 0, top, width: left, height }} />
      <div className="absolute bg-black/50" style={{ left: left + width, top, width: containerWidth - left - width, height }} />

      <div
        className="absolute border border-white/80 cursor-move"
        style={{ left, top, width, height }}
        onPointerDown={startDrag("move")}
      />
      {["tl", "tr", "bl", "br"].map((h) => {
        const cx = h.includes("l") ? left : left + width;
        const cy = h.includes("t") ? top : top + height;
        const cursor = h === "tl" || h === "br" ? "nwse-resize" : "nesw-resize";
        return (
          <div
            key={h}
            onPointerDown={startDrag(h)}
            className="absolute w-3 h-3 bg-white border border-black rounded-sm"
            style={{ left: cx - 6, top: cy - 6, cursor }}
          />
        );
      })}
    </div>
  );
}