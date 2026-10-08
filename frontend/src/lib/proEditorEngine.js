import { projectPerspective } from "@/lib/manualProjective";
// proEditorEngine.js — Motor del editor profesional: ajustes pixel-level,
// caché de capas, máscaras de pincel, composición y exportación a resolución total.

const MAX_PREVIEW_DIM = 1400;
const layerCanvasCache = new Map();

export function genId() {
  return typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `id-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function getDefaultAdjustments() {
  return {
    exposure: 0, contrast: 0, saturation: 0, temperature: 0,
    highlights: 0, shadows: 0, whites: 0, blacks: 0, vibrance: 0,
  };
}

export function computePreviewSize(naturalWidth, naturalHeight) {
  const maxDim = Math.max(naturalWidth, naturalHeight);
  if (maxDim <= MAX_PREVIEW_DIM) return { width: naturalWidth, height: naturalHeight };
  const scale = MAX_PREVIEW_DIM / maxDim;
  return { width: Math.round(naturalWidth * scale), height: Math.round(naturalHeight * scale) };
}

function clamp255(v) { return v < 0 ? 0 : v > 255 ? 255 : v; }

export function hasAdjustments(adj) {
  if (!adj) return false;
  return Object.values(adj).some((v) => v !== 0);
}

export function applyAdjustmentsToImageData(imageData, adj) {
  const data = imageData.data;
  const exp = Math.pow(2, (adj.exposure || 0) / 100);
  const con = 1 + (adj.contrast || 0) / 100;
  const sat = 1 + (adj.saturation || 0) / 100;
  const vib = 1 + (adj.vibrance || 0) / 100;
  const temp = (adj.temperature || 0) / 100;
  const hl = adj.highlights || 0;
  const sh = adj.shadows || 0;
  const wh = adj.whites || 0;
  const bl = adj.blacks || 0;

  for (let i = 0; i < data.length; i += 4) {
    let r = data[i], g = data[i + 1], b = data[i + 2];

    r *= exp; g *= exp; b *= exp;
    r += wh * 0.5; g += wh * 0.5; b += wh * 0.5;
    r += bl * 0.5; g += bl * 0.5; b += bl * 0.5;
    r += temp * 25; b -= temp * 25;
    r = clamp255(r); g = clamp255(g); b = clamp255(b);

    const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
    if (lum > 0.5) {
      const amt = (lum - 0.5) * 2 * hl * 0.4;
      r -= amt; g -= amt; b -= amt;
    } else {
      const amt = (0.5 - lum) * 2 * sh * 0.4;
      r += amt; g += amt; b += amt;
    }

    r = (r - 128) * con + 128;
    g = (g - 128) * con + 128;
    b = (b - 128) * con + 128;

    const gray = 0.299 * r + 0.587 * g + 0.114 * b;
    r = gray + (r - gray) * sat;
    g = gray + (g - gray) * sat;
    b = gray + (b - gray) * sat;

    const satDist = Math.sqrt((r - gray) ** 2 + (g - gray) ** 2 + (b - gray) ** 2);
    const vibScale = satDist < 50 ? vib : 1 + (vib - 1) * (1 - satDist / 128);
    r = gray + (r - gray) * vibScale;
    g = gray + (g - gray) * vibScale;
    b = gray + (b - gray) * vibScale;

    data[i] = clamp255(r);
    data[i + 1] = clamp255(g);
    data[i + 2] = clamp255(b);
  }
}

export function createMaskCanvas(width, height) {
  const c = document.createElement("canvas");
  c.width = width;
  c.height = height;
  const ctx = c.getContext("2d");
  ctx.fillStyle = "rgb(255,255,255)";
  ctx.fillRect(0, 0, width, height);
  return c;
}

export function paintBrushOnMask(maskCanvas, fromX, fromY, toX, toY, size, hardness, mode) {
  const ctx = maskCanvas.getContext("2d");
  ctx.save();
  ctx.globalCompositeOperation = mode === "hide" ? "destination-out" : "source-over";
  const dist = Math.hypot(toX - fromX, toY - fromY);
  const steps = Math.max(1, Math.ceil(dist / (size * 0.2)));
  const r = size / 2;
  for (let i = 0; i <= steps; i++) {
    const t = steps === 0 ? 0 : i / steps;
    const x = fromX + (toX - fromX) * t;
    const y = fromY + (toY - fromY) * t;
    const grad = ctx.createRadialGradient(x, y, r * hardness, x, y, r);
    grad.addColorStop(0, "rgba(0,0,0,1)");
    grad.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

export function drawImageFit(ctx, img, w, h, fit = "cover") {
  const iw = img.naturalWidth || img.width;
  const ih = img.naturalHeight || img.height;
  if (!iw || !ih || fit === "stretch") {
    ctx.drawImage(img, 0, 0, iw, ih, 0, 0, w, h);
    return;
  }
  const scale = fit === "contain" ? Math.min(w / iw, h / ih) : Math.max(w / iw, h / ih);
  const dw = iw * scale;
  const dh = ih * scale;
  ctx.drawImage(img, 0, 0, iw, ih, (w - dw) / 2, (h - dh) / 2, dw, dh);
}

function getLayerCanvas(layer, image, width, height) {
  const blurRaw = layer.blur || 0;
  const cacheKey = (layer.imageEl
    ? "img:" + (layer.imageEl.src || "") + ":" + (layer.imageFit || "cover") + ":blur:" + blurRaw
    : JSON.stringify(layer.adjustments)) + "|" + width + "x" + height;
  const cached = layerCanvasCache.get(layer.id);
  if (cached && cached.key === cacheKey) return cached.canvas;

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (blurRaw > 0) {
    const blurScale = Math.max(1, Math.max(width, height) / MAX_PREVIEW_DIM);
    ctx.filter = `blur(${blurRaw * blurScale}px)`;
  }
  if (layer.imageEl) {
    drawImageFit(ctx, layer.imageEl, width, height, layer.imageFit || "cover");
  } else {
    ctx.drawImage(image, 0, 0, image.naturalWidth, image.naturalHeight, 0, 0, width, height);
  }
  ctx.filter = "none";
  if (hasAdjustments(layer.adjustments)) {
    const imgData = ctx.getImageData(0, 0, width, height);
    applyAdjustmentsToImageData(imgData, layer.adjustments);
    ctx.putImageData(imgData, 0, 0);
  }
  layerCanvasCache.set(layer.id, { key: cacheKey, canvas });
  return canvas;
}

export function clearLayerCache() {
  layerCanvasCache.clear();
}

export function invalidateLayerCache(layerId) {
  layerCanvasCache.delete(layerId);
}

export function renderComposite(ctx, image, layers, width, height, transform) {
  ctx.clearRect(0, 0, width, height);
  const base = document.createElement("canvas");
  base.width = width;
  base.height = height;
  const baseCtx = base.getContext("2d");

  for (const layer of layers) {
    if (!layer.visible || layer.opacity <= 0) continue;
    const layerCanvas = getLayerCanvas(layer, image, width, height);

    if (layer.maskCanvas) {
      const masked = document.createElement("canvas");
      masked.width = width;
      masked.height = height;
      const mctx = masked.getContext("2d");
      mctx.drawImage(layerCanvas, 0, 0);
      mctx.globalCompositeOperation = "destination-in";
      mctx.drawImage(layer.maskCanvas, 0, 0, width, height);
      baseCtx.globalAlpha = layer.opacity;
      baseCtx.drawImage(masked, 0, 0);
    } else {
      baseCtx.globalAlpha = layer.opacity;
      baseCtx.drawImage(layerCanvas, 0, 0);
    }
  }
  baseCtx.globalAlpha = 1;

  const projected=projectPerspective(base,transform.perspectiveX||0,transform.perspectiveY||0);
  ctx.save();
  ctx.translate(width / 2, height / 2);
  if (transform.rotation) ctx.rotate((transform.rotation * Math.PI) / 180);
  ctx.translate(-width / 2, -height / 2);
  ctx.drawImage(projected, 0, 0);
  ctx.restore();
}

export async function exportToBlob(image, layers, transform, crop) {
  const fullW = image.naturalWidth;
  const fullH = image.naturalHeight;
  const base = document.createElement("canvas");
  base.width = fullW;
  base.height = fullH;
  renderComposite(base.getContext("2d"), image, layers, fullW, fullH, transform);

  let output = base;
  if (crop && (crop.x > 0 || crop.y > 0 || crop.width < 1 || crop.height < 1)) {
    const cw = Math.round(crop.width * fullW);
    const ch = Math.round(crop.height * fullH);
    const cx = Math.round(crop.x * fullW);
    const cy = Math.round(crop.y * fullH);
    output = document.createElement("canvas");
    output.width = cw;
    output.height = ch;
    output.getContext("2d").drawImage(base, cx, cy, cw, ch, 0, 0, cw, ch);
  }

  return new Promise((resolve) => output.toBlob((blob) => blob ? resolve(blob) : resolve(null), "image/jpeg", 0.95));
}