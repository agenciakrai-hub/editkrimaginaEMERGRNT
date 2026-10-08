import { useRef, useEffect, useState } from "react";
import { renderComposite } from "@/lib/proEditorEngine";
import CropOverlay from "./CropOverlay";

export default function CanvasViewport({
  image, layers, previewSize, activeLayerId, tool, brush,
  transform, crop, renderVersion, onPaintMask, onCropChange,
  skyMode, skyBrush, skySelection, skyVersion, onSkyWand, onSkyPaint, onSkyStrokeBegin,
}) {
  const canvasRef = useRef(null);
  const overlayRef = useRef(null);
  const containerRef = useRef(null);
  const [displaySize, setDisplaySize] = useState({ width: 0, height: 0 });
  const [cursorPos, setCursorPos] = useState(null);
  const painting = useRef(false);
  const lastPos = useRef(null);

  useEffect(() => {
    if (!image || !containerRef.current) return;
    const compute = () => {
      const c = containerRef.current;
      if (!c) return;
      const maxW = c.clientWidth - 24;
      const maxH = c.clientHeight - 24;
      const scale = Math.min(maxW / image.naturalWidth, maxH / image.naturalHeight, 1);
      setDisplaySize({
        width: Math.max(1, Math.round(image.naturalWidth * scale)),
        height: Math.max(1, Math.round(image.naturalHeight * scale)),
      });
    };
    compute();
    window.addEventListener("resize", compute);
    return () => window.removeEventListener("resize", compute);
  }, [image]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !image || !layers.length) return;
    renderComposite(canvas.getContext("2d"), image, layers, canvas.width, canvas.height, transform);
  }, [image, layers, transform, renderVersion, displaySize]);

  // Overlay de selección para la herramienta de cielos.
  useEffect(() => {
    const ov = overlayRef.current;
    if (!ov) return;
    const ctx = ov.getContext("2d");
    ctx.clearRect(0, 0, ov.width, ov.height);
    if (tool !== "sky" || !skySelection) return;
    ctx.drawImage(skySelection, 0, 0, ov.width, ov.height);
    ctx.globalCompositeOperation = "source-in";
    ctx.fillStyle = "rgba(255,45,45,0.55)";
    ctx.fillRect(0, 0, ov.width, ov.height);
    ctx.globalCompositeOperation = "source-over";
  }, [skySelection, skyVersion, tool, displaySize]);

  const getCoords = (e) => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    return {
      x: ((e.clientX - rect.left) / rect.width) * canvas.width,
      y: ((e.clientY - rect.top) / rect.height) * canvas.height,
    };
  };

  const isSky = tool === "sky";

  const onPointerDown = (e) => {
    if (isSky) {
      const c = getCoords(e);
      if (!c) return;
      if (skyMode === "detect") {
        onSkyWand?.(c.x, c.y);
      } else {
        painting.current = true;
        lastPos.current = c;
        e.currentTarget.setPointerCapture(e.pointerId);
        onSkyStrokeBegin?.();
        onSkyPaint?.(c.x, c.y, c.x, c.y);
      }
      return;
    }
    if (tool !== "brush" || !activeLayerId) return;
    const c = getCoords(e);
    if (!c) return;
    painting.current = true;
    lastPos.current = c;
    e.currentTarget.setPointerCapture(e.pointerId);
    onPaintMask(activeLayerId, c.x, c.y, c.x, c.y);
  };

  const onPointerMove = (e) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (rect) setCursorPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
    if (!painting.current) return;
    if (!isSky && (tool !== "brush" || !activeLayerId)) return;
    const c = getCoords(e);
    if (!c) return;
    if (isSky) {
      onSkyPaint?.(lastPos.current.x, lastPos.current.y, c.x, c.y);
    } else {
      onPaintMask(activeLayerId, lastPos.current.x, lastPos.current.y, c.x, c.y);
    }
    lastPos.current = c;
  };

  const onPointerUp = (e) => {
    painting.current = false;
    try { e.currentTarget.releasePointerCapture(e.pointerId); } catch (_) {}
  };

  const showCursor = (tool === "brush" || (isSky && skyMode === "refine"));
  const cursorSize = displaySize.width > 0 && previewSize.width > 0
    ? (isSky ? skyBrush.size : brush.size) * (displaySize.width / previewSize.width)
    : (isSky ? skyBrush.size : brush.size);

  const cursorClass = isSky
    ? (skyMode === "detect" ? "cursor-crosshair" : "cursor-none")
    : (tool === "brush" ? "cursor-none" : "cursor-default");

  return (
    <div ref={containerRef} className="flex-1 relative flex items-center justify-center bg-background overflow-hidden">
      {image && displaySize.width > 0 && (
        <div className="relative" style={{ width: displaySize.width, height: displaySize.height }}>
          <canvas
            ref={canvasRef}
            width={previewSize.width}
            height={previewSize.height}
            style={{ width: displaySize.width, height: displaySize.height }}
            className={`block ${cursorClass}`}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerLeave={() => { setCursorPos(null); painting.current = false; }}
          />
          <canvas
            ref={overlayRef}
            width={previewSize.width}
            height={previewSize.height}
            style={{ width: displaySize.width, height: displaySize.height }}
            className="absolute inset-0 pointer-events-none"
          />
          {showCursor && cursorPos && (
            <div
              className="absolute pointer-events-none border-2 border-white rounded-full mix-blend-difference"
              style={{
                left: cursorPos.x - cursorSize / 2,
                top: cursorPos.y - cursorSize / 2,
                width: cursorSize,
                height: cursorSize,
              }}
            />
          )}
          {tool === "crop" && (
            <CropOverlay crop={crop} containerWidth={displaySize.width} containerHeight={displaySize.height} onChange={onCropChange} />
          )}
        </div>
      )}
    </div>
  );
}