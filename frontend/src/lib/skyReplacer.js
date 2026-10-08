// skyReplacer.js — Motor de la herramienta de reemplazo de cielos/ventanas.
// Detección tipo "varita mágica" consciente de los bordes (respeta los marcos de
// las ventanas) + refinado con pincel + autodetección del cristal. Construye
// máscaras precisas que conservan los bastidores de la ventana.

const CATALOG_KEY = "sky_replacer_catalog";

export function loadSkyCatalog() {
  try {
    const raw = localStorage.getItem(CATALOG_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function saveSkyCatalog(list) {
  localStorage.setItem(CATALOG_KEY, JSON.stringify(list));
}

export function newSelectionCanvas(w, h) {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  return c;
}

// Copia profunda de un canvas de selección (o null).
export function cloneSelection(canvas) {
  if (!canvas) return null;
  const c = document.createElement("canvas");
  c.width = canvas.width;
  c.height = canvas.height;
  c.getContext("2d").drawImage(canvas, 0, 0);
  return c;
}

// --- Utilidades de imagen ---

function toGray(data, w, h) {
  const gray = new Float32Array(w * h);
  for (let i = 0; i < w * h; i++) {
    const di = i * 4;
    gray[i] = 0.299 * data[di] + 0.587 * data[di + 1] + 0.114 * data[di + 2];
  }
  return gray;
}

// Magnitud de borde Sobel (0..~1020). Valores altos = borde fuerte (marco).
function sobelEdges(gray, w, h) {
  const edge = new Float32Array(w * h);
  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      const i = y * w + x;
      const gx =
        -gray[i - w - 1] - 2 * gray[i - 1] - gray[i + w - 1] +
        gray[i - w + 1] + 2 * gray[i + 1] + gray[i + w + 1];
      const gy =
        -gray[i - w - 1] - 2 * gray[i - w] - gray[i - w + 1] +
        gray[i + w - 1] + 2 * gray[i + w] + gray[i + w + 1];
      edge[i] = Math.hypot(gx, gy);
    }
  }
  return edge;
}

// Erosión binaria de la máscara (inset) para no comerse el marco de la ventana.
function erodeMask(sel, w, h, r) {
  for (let pass = 0; pass < r; pass++) {
    const copy = sel.slice();
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const i = y * w + x;
        if (!copy[i]) continue;
        if (
          x === 0 || y === 0 || x === w - 1 || y === h - 1 ||
          !copy[i - 1] || !copy[i + 1] || !copy[i - w] || !copy[i + w]
        ) {
          sel[i] = 0;
        }
      }
    }
  }
}

function selectedToCanvas(selected, w, h) {
  const out = document.createElement("canvas");
  out.width = w;
  out.height = h;
  const octx = out.getContext("2d");
  const outImg = octx.createImageData(w, h);
  for (let i = 0; i < w * h; i++) {
    if (selected[i]) {
      outImg.data[i * 4] = 255;
      outImg.data[i * 4 + 1] = 255;
      outImg.data[i * 4 + 2] = 255;
      outImg.data[i * 4 + 3] = 255;
    }
  }
  octx.putImageData(outImg, 0, 0);
  return out;
}

// Varita mágica precisa: flood fill por similitud de color al punto semilla,
// pero deteniéndose en los bordes fuertes (marcos de la ventana). Erosiona 1px
// el resultado para que la selección quede dentro del cristal y respete el marco.
// tolerance: similitud de color (0-100 aprox). edgeStop: umbral de borde (0-1020).
export function magicWand(sourceCanvas, startX, startY, tolerance, edgeStop = 80, inset = 1) {
  const w = sourceCanvas.width;
  const h = sourceCanvas.height;
  const ctx = sourceCanvas.getContext("2d");
  const imgData = ctx.getImageData(0, 0, w, h);
  const data = imgData.data;
  const gray = toGray(data, w, h);
  const edge = sobelEdges(gray, w, h);

  const sx = Math.max(0, Math.min(w - 1, Math.round(startX)));
  const sy = Math.max(0, Math.min(h - 1, Math.round(startY)));
  const si = (sy * w + sx) * 4;
  const tr = data[si];
  const tg = data[si + 1];
  const tb = data[si + 2];
  const tol2 = tolerance * tolerance * 3;

  const visited = new Uint8Array(w * h);
  const selected = new Uint8Array(w * h);
  const stack = [[sx, sy]];
  while (stack.length) {
    const [x, y] = stack.pop();
    if (x < 0 || y < 0 || x >= w || y >= h) continue;
    const idx = y * w + x;
    if (visited[idx]) continue;
    visited[idx] = 1;
    // No cruzar bordes fuertes: respeta el marco de la ventana.
    if (edge[idx] > edgeStop) continue;
    const di = idx * 4;
    const dr = data[di] - tr;
    const dg = data[di + 1] - tg;
    const db = data[di + 2] - tb;
    if (dr * dr + dg * dg + db * db > tol2) continue;
    selected[idx] = 1;
    stack.push([x + 1, y], [x - 1, y], [x, y + 1], [x, y - 1]);
  }

  if (inset > 0) erodeMask(selected, w, h, inset);
  return selectedToCanvas(selected, w, h);
}

// Autodetección del cristal de las ventanas: solo cristal quemado (blown-out) o
// con tinte azulado claro (cielo visto a través del cristal), SIEMPRE con tinte
// frío (b >= r - tolerancia). Excluye paredes/muebles/ropa cálidos o neutros
// brillantes que no sean cristal. Limitado por los marcos (bordes fuertes).
export function detectWindowGlass(sourceCanvas, opts = {}) {
  const {
    edgeStop = 70,
    minAreaFraction = 0.004,
    inset = 1,
    blownL = 225,        // cristal quemado: casi blanco
    blownSat = 22,       // y poco saturado
    coolTol = 10,        // b >= r - coolTol (tinte frío)
    blueSat = 28,        // azul del cielo
    blueExcess = 18,     // b bastante mayor que r,g
    blueL = 120,         // luminancia mínima del azul
  } = opts;
  const w = sourceCanvas.width;
  const h = sourceCanvas.height;
  const ctx = sourceCanvas.getContext("2d");
  const data = ctx.getImageData(0, 0, w, h).data;
  const gray = toGray(data, w, h);
  const edge = sobelEdges(gray, w, h);

  const candidate = new Uint8Array(w * h);
  for (let i = 0; i < w * h; i++) {
    const di = i * 4;
    const r = data[di];
    const g = data[di + 1];
    const b = data[di + 2];
    const mx = Math.max(r, g, b);
    const mn = Math.min(r, g, b);
    const sat = mx - mn;
    const L = gray[i];
    // Cristal quemado (blanco casi puro) o azul del cielo; siempre tinte frío.
    const isBlown = L > blownL && sat < blownSat && b >= r - coolTol;
    const isBlue = L > blueL && sat > blueSat && b - Math.max(r, g) > blueExcess && b >= r;
    if ((isBlown || isBlue) && edge[i] < edgeStop) candidate[i] = 1;
  }

  // Componentes conexos: descarta zonas diminutas (ruido).
  const minArea = Math.max(200, Math.floor(w * h * minAreaFraction));
  const visited = new Uint8Array(w * h);
  const selected = new Uint8Array(w * h);
  const stack = [];
  const comp = [];
  for (let start = 0; start < w * h; start++) {
    if (!candidate[start] || visited[start]) continue;
    stack.length = 0;
    comp.length = 0;
    stack.push(start);
    visited[start] = 1;
    while (stack.length) {
      const idx = stack.pop();
      comp.push(idx);
      const x = idx % w;
      const y = (idx - x) / w;
      if (x > 0 && candidate[idx - 1] && !visited[idx - 1]) { visited[idx - 1] = 1; stack.push(idx - 1); }
      if (x < w - 1 && candidate[idx + 1] && !visited[idx + 1]) { visited[idx + 1] = 1; stack.push(idx + 1); }
      if (y > 0 && candidate[idx - w] && !visited[idx - w]) { visited[idx - w] = 1; stack.push(idx - w); }
      if (y < h - 1 && candidate[idx + w] && !visited[idx + w]) { visited[idx + w] = 1; stack.push(idx + w); }
    }
    if (comp.length >= minArea) {
      for (let k = 0; k < comp.length; k++) selected[comp[k]] = 1;
    }
  }

  if (inset > 0) erodeMask(selected, w, h, inset);
  return selectedToCanvas(selected, w, h);
}

// Autodetección del cielo en fotos de exterior: zonas brillantes/azuladas
// (cielo) limitadas por la línea de horizonte/edificios (bordes fuertes).
export function detectSky(sourceCanvas, opts = {}) {
  const {
    edgeStop = 85,
    minAreaFraction = 0.03,
    inset = 1,
    blownL = 215,
    blownSat = 28,
    coolTol = 14,
    blueSat = 24,
    blueExcess = 10,
    blueL = 110,
  } = opts;
  return detectWindowGlass(sourceCanvas, {
    edgeStop,
    minAreaFraction,
    inset,
    blownL,
    blownSat,
    coolTol,
    blueSat,
    blueExcess,
    blueL,
  });
}

// Une una nueva selección a la existente (muta y devuelve la existente).
export function unionSelection(existing, next) {
  if (!existing) return next;
  const ctx = existing.getContext("2d");
  ctx.globalCompositeOperation = "source-over";
  ctx.drawImage(next, 0, 0);
  return existing;
}

// Pincel sobre la selección. mode: "add" | "remove".
export function paintSelection(selectionCanvas, fromX, fromY, toX, toY, size, mode) {
  const ctx = selectionCanvas.getContext("2d");
  ctx.save();
  ctx.globalCompositeOperation = mode === "remove" ? "destination-out" : "source-over";
  const dist = Math.hypot(toX - fromX, toY - fromY);
  const steps = Math.max(1, Math.ceil(dist / (size * 0.2)));
  const r = Math.max(1, size / 2);
  ctx.fillStyle = "rgba(255,255,255,1)";
  for (let i = 0; i <= steps; i++) {
    const t = steps === 0 ? 0 : i / steps;
    const x = fromX + (toX - fromX) * t;
    const y = fromY + (toY - fromY) * t;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

// Construye la máscara de la capa base: opaca en todo salvo donde la selección
// marca el cristal/cielo (ahí transparente → deja ver el cielo de la capa inferior).
export function buildHideMask(selectionCanvas, w, h) {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  const ctx = c.getContext("2d");
  ctx.fillStyle = "rgb(255,255,255)";
  ctx.fillRect(0, 0, w, h);
  ctx.globalCompositeOperation = "destination-out";
  ctx.drawImage(selectionCanvas, 0, 0, w, h);
  return c;
}

export function countSelected(selectionCanvas) {
  if (!selectionCanvas) return 0;
  const { width, height } = selectionCanvas;
  const d = selectionCanvas.getContext("2d").getImageData(0, 0, width, height).data;
  let n = 0;
  for (let i = 3; i < d.length; i += 4) if (d[i] > 16) n++;
  return n;
}

// Construye un canvas de selección a partir de las máscaras PNG (base64) que
// devuelve Hugging Face (Segmentación IA gratuita). Cada máscara se escala al
// tamaño del editor y se umbraliza: píxel seleccionado = blanco opaco.
export function selectionFromMasks(maskBase64List, w, h) {
  return new Promise((resolve) => {
    const out = newSelectionCanvas(w, h);
    if (!maskBase64List || maskBase64List.length === 0) return resolve(out);
    const octx = out.getContext("2d");
    let pending = maskBase64List.length;
    const onLoad = (img) => {
      const tmp = document.createElement("canvas");
      tmp.width = w;
      tmp.height = h;
      const tctx = tmp.getContext("2d");
      tctx.drawImage(img, 0, 0, w, h);
      const d = tctx.getImageData(0, 0, w, h).data;
      const sel = octx.getImageData(0, 0, w, h);
      // Las máscaras de Hugging Face son PNG en escala de grises (sin canal alfa):
      // el navegador las carga con alpha=255 en todos los píxeles, así que NO
      // podemos usar el alfa para decidir la selección. Usamos solo el brillo:
      // píxel claro (máscara) = seleccionado, píxel oscuro = no.
      for (let i = 0; i < w * h; i++) {
        const lum = d[i * 4] + d[i * 4 + 1] + d[i * 4 + 2];
        if (lum > 384) {
          sel.data[i * 4] = 255;
          sel.data[i * 4 + 1] = 255;
          sel.data[i * 4 + 2] = 255;
          sel.data[i * 4 + 3] = 255;
        }
      }
      octx.putImageData(sel, 0, 0);
      pending -= 1;
      if (pending === 0) resolve(out);
    };
    maskBase64List.forEach((b64) => {
      const img = new Image();
      img.onload = () => onLoad(img);
      img.onerror = () => { pending -= 1; if (pending === 0) resolve(out); };
      img.src = b64.startsWith("data:") ? b64 : `data:image/png;base64,${b64}`;
    });
  });
}