// bracketingProcessor.js — Utilidades para el módulo de fusión HDR por bracketing.

const RAW_EXTENSIONS = [
  ".raw", ".cr2", ".nef", ".arw", ".dng", ".raf", ".orf", ".rw2", ".pef", ".srw", ".cr3",
];

export function isRawFile(file) {
  const dot = file.name.lastIndexOf(".");
  if (dot < 0) return false;
  return RAW_EXTENSIONS.includes(file.name.slice(dot).toLowerCase());
}

/**
 * Los archivos RAW (CR2, NEF, ARW, DNG…) contienen un JPEG embebido a resolución
 * completa que la cámara usa para previsualización. Lo extraemos escaneando los
 * marcadores JPEG: SOI (0xFF 0xD8) y EOI (0xFF 0xD9).
 * En datos JPEG comprimidos, los 0xFF van seguidos de 0x00 (byte stuffing),
 * así que 0xFF 0xD9 solo puede ser un EOI real.
 */
export async function extractEmbeddedJpeg(file) {
  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  const segments = [];

  for (let i = 0; i < bytes.length - 1; i++) {
    if (bytes[i] === 0xff && bytes[i + 1] === 0xd8) {
      // Buscar EOI correspondiente
      for (let j = i + 2; j < bytes.length - 1; j++) {
        if (bytes[j] === 0xff && bytes[j + 1] === 0xd9) {
          segments.push({ start: i, end: j + 2 });
          break;
        }
      }
    }
  }

  if (segments.length === 0) return null;
  // El segmento más grande suele ser el preview a resolución completa
  segments.sort((a, b) => (b.end - b.start) - (a.end - a.start));
  const largest = segments[0];
  const jpegBytes = bytes.slice(largest.start, largest.end);
  return new Blob([jpegBytes], { type: "image/jpeg" });
}

/**
 * Lee un File de imagen, lo carga, lo dibuja en un canvas
 * y devuelve { imageData, width, height }.
 * Soporta JPG, PNG, TIFF, HEIC y archivos RAW (extrayendo el JPEG embebido).
 */
export async function loadImageFromFile(file, targetWidth, targetHeight) {
  let decodeSource = file;

  // Si es RAW, extraer el JPEG embebido antes de decodificar
  if (isRawFile(file)) {
    try {
      const jpegBlob = await extractEmbeddedJpeg(file);
      if (jpegBlob) decodeSource = jpegBlob;
    } catch {
      // Si falla la extracción, intentar con el archivo original
    }
  }

  const drawToCanvas = (source, sw, sh) => {
    if (targetWidth && Math.abs((sw/sh)/(targetWidth/targetHeight)-1) > 0.01) throw new Error("Las exposiciones deben tener la misma proporción y encuadre.");
    let w = targetWidth || sw;
    let h = targetHeight || sh;
    if (!targetWidth) {
      const MAX_DIM = 2400;
      const maxSide = Math.max(w, h);
      if (maxSide > MAX_DIM) {
        const s = MAX_DIM / maxSide;
        w = Math.round(w * s);
        h = Math.round(h * s);
      }
    }
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(source, 0, 0, w, h);
    const imageData = ctx.getImageData(0, 0, w, h);
    return { imageData, width: w, height: h };
  };

  // Intentar createImageBitmap primero (más formatos)
  if (typeof createImageBitmap === "function") {
    try {
      const bitmap = await createImageBitmap(decodeSource);
      const result = drawToCanvas(bitmap, bitmap.width, bitmap.height);
      bitmap.close();
      return result;
    } catch {
      // Continuar al fallback
    }
  }

  // Fallback a Image
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(decodeSource);
    const img = new Image();
    img.onload = () => {
      let result;
      try { result = drawToCanvas(img, img.naturalWidth, img.naturalHeight); } catch (e) { URL.revokeObjectURL(url); reject(e); return; }
      URL.revokeObjectURL(url);
      resolve(result);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error(`No se pudo decodificar "${file.name}".`));
    };
    img.src = url;
  });
}

/**
 * Agrupa archivos consecutivos en arrays de tamaño bracketSize.
 * Devuelve { groups, remainder } donde remainder es el número de fotos que sobran.
 */
export function groupIntoBrackets(files, bracketSize) {
  const groups = [];
  for (let i = 0; i + bracketSize <= files.length; i += bracketSize) {
    groups.push(files.slice(i, i + bracketSize));
  }
  const remainder = files.length % bracketSize;
  return { groups, remainder };
}