// bracketingWorker.js — Fusión HDR con pirámide laplaciana (Mertens et al.)
//
// El algoritmo de pirámide laplaciana es la solución definitiva a los artefactos
// "bloquete": descompone cada imagen en bandas de frecuencia (pirámide laplaciana)
// y mezcla cada banda con la versión suavizada correspondiente de los mapas de peso
// (pirámide gaussiana).
//
//   - Frecuencias bajas (brillo global) → pesos muy suaves → sin bloquete
//   - Frecuencias altas (detalle, bordes) → pesos detallados → máxima nitidez
//
// Esto es lo que usan Lightroom/Photomatix internamente.

self.onmessage = (e) => {
  try {
    const { groupImageDatas, groupIndex } = e.data;
    if (!groupImageDatas || groupImageDatas.length === 0) {
      self.postMessage({ type: "error", message: "No images to fuse" });
      return;
    }

    const numImages = groupImageDatas.length;
    const width = groupImageDatas[0].width;
    const height = groupImageDatas[0].height;
    const numPixels = width * height;

    self.postMessage({ type: "progress", pct: 10 });

    // --- Cargar imágenes como Float32Array [0,1], solo RGB ---
    const images = [];
    for (let img = 0; img < numImages; img++) {
      const src = new Uint8ClampedArray(groupImageDatas[img].data);
      const f = new Float32Array(numPixels * 3);
      for (let p = 0; p < numPixels; p++) {
        const s4 = p * 4;
        const d3 = p * 3;
        f[d3] = src[s4] / 255;
        f[d3 + 1] = src[s4 + 1] / 255;
        f[d3 + 2] = src[s4 + 2] / 255;
      }
      images.push(f);
    }

    // --- Alinear imágenes a la primera (corrección de trepidación) ---
    // Alineación de tres niveles: coarse (128×128) → fine (512×512) → full-res (centro)
    // Resolución final: 1px exacto
    const alignmentInfo = [{ dx: 0, dy: 0 }];
    const refCoarse = normalizeThumbnail(makeThumbnail(images[0], width, height, 128));
    const refFine = normalizeThumbnail(makeThumbnail(images[0], width, height, 512));
    // Nivel 3: crop central a resolución completa
    const cropSize = Math.min(400, width, height);
    const cropX = Math.floor((width - cropSize) / 2);
    const cropY = Math.floor((height - cropSize) / 2);
    const refCrop = normalizeThumbnail(extractLuminanceCrop(images[0], width, cropX, cropY, cropSize));
    for (let img = 1; img < numImages; img++) {
      // Nivel 1: coarse
      const thumbCoarse = normalizeThumbnail(makeThumbnail(images[img], width, height, 128));
      const s1 = findBestShift(refCoarse, thumbCoarse, 128, 8);
      const dx1 = Math.round(s1.dx * (width / 128));
      const dy1 = Math.round(s1.dy * (height / 128));
      // Nivel 2: fine (thumbnail con offset coarse aplicado al muestreo)
      const thumbFine = normalizeThumbnail(makeThumbnailWithOffset(images[img], width, height, 512, dx1, dy1));
      const s2 = findBestShift(refFine, thumbFine, 512, 4);
      const dx2 = Math.round(s2.dx * (width / 512));
      const dy2 = Math.round(s2.dy * (height / 512));
      let totalDx = dx1 + dx2;
      let totalDy = dy1 + dy2;
      // Nivel 3: full-res refinement (búsqueda ±5px alrededor del shift actual)
      let bestDx = totalDx, bestDy = totalDy, bestSAD = Infinity;
      for (let ry = -5; ry <= 5; ry++) {
        for (let rx = -5; rx <= 5; rx++) {
          const testCrop = normalizeThumbnail(extractLuminanceCropWithShift(images[img], width, height, cropX, cropY, cropSize, totalDx + rx, totalDy + ry));
          const sad = sadArrays(refCrop, testCrop);
          if (sad < bestSAD) {
            bestSAD = sad;
            bestDx = totalDx + rx;
            bestDy = totalDy + ry;
          }
        }
      }
      totalDx = bestDx;
      totalDy = bestDy;
      if (totalDx !== 0 || totalDy !== 0) {
        images[img] = shiftImage3ch(images[img], width, height, totalDx, totalDy);
      }
      alignmentInfo.push({ dx: totalDx, dy: totalDy });
    }

    // --- Calcular pesos por píxel (well-exposedness) ---
    const sigma = 0.2;
    const sigma2 = 2 * sigma * sigma;
    const weights = [];
    for (let img = 0; img < numImages; img++) {
      const w = new Float32Array(numPixels);
      const data = images[img];
      for (let p = 0; p < numPixels; p++) {
        const idx = p * 3;
        const lum = 0.299 * data[idx] + 0.587 * data[idx + 1] + 0.114 * data[idx + 2];
        w[p] = Math.exp(-((lum - 0.5) * (lum - 0.5)) / sigma2) + 1e-8;
      }
      weights.push(w);
    }

    self.postMessage({ type: "progress", pct: 25 });

    // --- Dimensiones de la pirámide ---
    const levels = Math.min(5, Math.max(3, Math.floor(Math.log2(Math.min(width, height))) - 2));
    const dims = [{ w: width, h: height }];
    {
      let cw = width, ch = height;
      for (let l = 1; l < levels; l++) {
        cw = Math.ceil(cw / 2);
        ch = Math.ceil(ch / 2);
        dims.push({ w: cw, h: ch });
      }
    }

    // --- Pirámide gaussiana de pesos (1 canal) ---
    const weightPyramids = [];
    for (let img = 0; img < numImages; img++) {
      const pyr = [weights[img]];
      let cur = weights[img];
      let cw = width, ch = height;
      for (let l = 1; l < levels; l++) {
        const nw = Math.ceil(cw / 2);
        const nh = Math.ceil(ch / 2);
        cur = downsample1ch(cur, cw, ch, nw, nh);
        pyr.push(cur);
        cw = nw; ch = nh;
      }
      weightPyramids.push(pyr);
    }

    self.postMessage({ type: "progress", pct: 40 });

    // --- Pirámide laplaciana de imágenes (3 canales) ---
    const imagePyramids = [];
    for (let img = 0; img < numImages; img++) {
      imagePyramids.push(laplacianPyramid3ch(images[img], width, height, levels, dims));
      images[img] = null;
    }

    self.postMessage({ type: "progress", pct: 55 });

    // --- Mezclar cada nivel ---
    const blended = [];
    for (let l = 0; l < levels; l++) {
      const lw = dims[l].w;
      const lh = dims[l].h;
      const lpix = lw * lh;
      const blendedLevel = new Float32Array(lpix * 3);

      for (let p = 0; p < lpix; p++) {
        let totalW = 0;
        for (let img = 0; img < numImages; img++) totalW += weightPyramids[img][l][p];

        const p3 = p * 3;
        for (let c = 0; c < 3; c++) {
          let sum = 0;
          for (let img = 0; img < numImages; img++) {
            sum += (weightPyramids[img][l][p] / totalW) * imagePyramids[img][l][p3 + c];
          }
          blendedLevel[p3 + c] = sum;
        }
      }

      // Liberar este nivel
      for (let img = 0; img < numImages; img++) {
        imagePyramids[img][l] = null;
        weightPyramids[img][l] = null;
      }

      blended.push(blendedLevel);
    }

    self.postMessage({ type: "progress", pct: 75 });

    // --- Reconstruir desde la pirámide mezclada ---
    let result = blended[levels - 1];
    for (let l = levels - 2; l >= 0; l--) {
      const up = upsample3ch(result, dims[l + 1].w, dims[l + 1].h, dims[l].w, dims[l].h);
      const recon = new Float32Array(dims[l].w * dims[l].h * 3);
      for (let i = 0; i < recon.length; i++) {
        recon[i] = up[i] + blended[l][i];
      }
      blended[l] = null;
      result = recon;
    }

    self.postMessage({ type: "progress", pct: 85 });

    // --- Sharpening (unsharp mask sobre luminancia) ---
    // La fusión de múltiples exposiciones suaviza los bordes; esto los recupera.
    const sharpRadius = 3;
    const sharpAmount = 0.35;

    const lum = new Float32Array(numPixels);
    for (let p = 0; p < numPixels; p++) {
      const p3 = p * 3;
      lum[p] = 0.299 * result[p3] + 0.587 * result[p3 + 1] + 0.114 * result[p3 + 2];
    }
    const blurred = boxBlur1ch(lum, width, height, sharpRadius);
    for (let p = 0; p < numPixels; p++) {
      const p3 = p * 3;
      const highPass = lum[p] - blurred[p];
      const sharpenedLum = lum[p] + sharpAmount * highPass;
      const ratio = lum[p] > 1e-6 ? sharpenedLum / lum[p] : 1;
      result[p3] *= ratio;
      result[p3 + 1] *= ratio;
      result[p3 + 2] *= ratio;
    }

    // Métrica de nitidez: energía de alta frecuencia pre-sharpening
    // (si es baja, la fusión salió blanda = trepidación residual)
    let hfEnergy = 0;
    for (let p = 0; p < numPixels; p++) {
      const diff = lum[p] - blurred[p];
      hfEnergy += diff * diff;
    }
    const sharpnessScore = Math.round((hfEnergy / numPixels) * 10000) / 10;

    self.postMessage({ type: "progress", pct: 90 });

    // --- Post-procesamiento global (sin artefactos espaciales) ---
    // Operaciones per-píxel uniformes: no pueden generar bloquete ni halos.
    const gamma = 0.92;            // ligero brillo para sombras HDR
    const contrastAmount = 0.15;   // S-curve moderada
    const satBoost = 1.18;         // saturación necesaria tras fusión HDR

    const pixelData = new Uint8ClampedArray(numPixels * 4);
    for (let p = 0; p < numPixels; p++) {
      const p3 = p * 3;
      const p4 = p * 4;
      let r = result[p3];
      let g = result[p3 + 1];
      let b = result[p3 + 2];

      // Gamma
      r = Math.pow(Math.max(0, Math.min(1, r)), gamma);
      g = Math.pow(Math.max(0, Math.min(1, g)), gamma);
      b = Math.pow(Math.max(0, Math.min(1, b)), gamma);

      // Contraste (mezcla con smoothstep)
      r = r * (1 - contrastAmount) + (r * r * (3 - 2 * r)) * contrastAmount;
      g = g * (1 - contrastAmount) + (g * g * (3 - 2 * g)) * contrastAmount;
      b = b * (1 - contrastAmount) + (b * b * (3 - 2 * b)) * contrastAmount;

      // Saturación
      const lum = 0.299 * r + 0.587 * g + 0.114 * b;
      r = lum + (r - lum) * satBoost;
      g = lum + (g - lum) * satBoost;
      b = lum + (b - lum) * satBoost;

      pixelData[p4]     = Math.max(0, Math.min(255, r * 255));
      pixelData[p4 + 1] = Math.max(0, Math.min(255, g * 255));
      pixelData[p4 + 2] = Math.max(0, Math.min(255, b * 255));
      pixelData[p4 + 3] = 255;
    }

    // Liberar memoria de entrada
    for (let i = 0; i < groupImageDatas.length; i++) {
      groupImageDatas[i].data = null;
    }

    const canvas = new OffscreenCanvas(width, height);
    const ctx = canvas.getContext("2d");
    const imageData = new ImageData(pixelData, width, height);
    ctx.putImageData(imageData, 0, 0);

    canvas.convertToBlob({ type: "image/jpeg", quality: 1.0 }).then((blob) => {
      self.postMessage({ type: "done", blob, groupIndex, alignment: alignmentInfo, sharpness: sharpnessScore });
    }).catch((err) => {
      self.postMessage({ type: "error", message: err.message });
    });

  } catch (err) {
    self.postMessage({ type: "error", message: err.message || "Unknown error" });
  }
};

// ============================================================
// Operaciones de pirámide
// ============================================================

// Downsample 2x por promedio de bloque 2x2 (1 canal)
function downsample1ch(data, sw, sh, tw, th) {
  const out = new Float32Array(tw * th);
  for (let y = 0; y < th; y++) {
    const sy0 = Math.min(sh - 1, y * 2);
    const sy1 = Math.min(sh - 1, sy0 + 1);
    for (let x = 0; x < tw; x++) {
      const sx0 = Math.min(sw - 1, x * 2);
      const sx1 = Math.min(sw - 1, sx0 + 1);
      const i00 = sy0 * sw + sx0;
      const i01 = sy0 * sw + sx1;
      const i10 = sy1 * sw + sx0;
      const i11 = sy1 * sw + sx1;
      out[y * tw + x] = (data[i00] + data[i01] + data[i10] + data[i11]) * 0.25;
    }
  }
  return out;
}

// Downsample 2x por promedio de bloque 2x2 (3 canales)
function downsample3ch(data, sw, sh, tw, th) {
  const out = new Float32Array(tw * th * 3);
  for (let y = 0; y < th; y++) {
    const sy0 = Math.min(sh - 1, y * 2);
    const sy1 = Math.min(sh - 1, sy0 + 1);
    for (let x = 0; x < tw; x++) {
      const sx0 = Math.min(sw - 1, x * 2);
      const sx1 = Math.min(sw - 1, sx0 + 1);
      const i00 = (sy0 * sw + sx0) * 3;
      const i01 = (sy0 * sw + sx1) * 3;
      const i10 = (sy1 * sw + sx0) * 3;
      const i11 = (sy1 * sw + sx1) * 3;
      const o = (y * tw + x) * 3;
      out[o]     = (data[i00]     + data[i01]     + data[i10]     + data[i11])     * 0.25;
      out[o + 1] = (data[i00 + 1] + data[i01 + 1] + data[i10 + 1] + data[i11 + 1]) * 0.25;
      out[o + 2] = (data[i00 + 2] + data[i01 + 2] + data[i10 + 2] + data[i11 + 2]) * 0.25;
    }
  }
  return out;
}

// Upsample por interpolación bilineal (3 canales)
function upsample3ch(data, sw, sh, tw, th) {
  const out = new Float32Array(tw * th * 3);
  const sxRatio = sw / tw;
  const syRatio = sh / th;

  for (let y = 0; y < th; y++) {
    const sy = (y + 0.5) * syRatio - 0.5;
    let y0 = Math.floor(sy);
    const fy = sy - y0;
    const y0c = Math.max(0, Math.min(sh - 1, y0));
    const y1c = Math.max(0, Math.min(sh - 1, y0 + 1));

    for (let x = 0; x < tw; x++) {
      const sx = (x + 0.5) * sxRatio - 0.5;
      let x0 = Math.floor(sx);
      const fx = sx - x0;
      const x0c = Math.max(0, Math.min(sw - 1, x0));
      const x1c = Math.max(0, Math.min(sw - 1, x0 + 1));

      const i00 = (y0c * sw + x0c) * 3;
      const i01 = (y0c * sw + x1c) * 3;
      const i10 = (y1c * sw + x0c) * 3;
      const i11 = (y1c * sw + x1c) * 3;
      const o = (y * tw + x) * 3;

      const w00 = (1 - fx) * (1 - fy);
      const w01 = fx * (1 - fy);
      const w10 = (1 - fx) * fy;
      const w11 = fx * fy;

      out[o]     = w00 * data[i00]     + w01 * data[i01]     + w10 * data[i10]     + w11 * data[i11];
      out[o + 1] = w00 * data[i00 + 1] + w01 * data[i01 + 1] + w10 * data[i10 + 1] + w11 * data[i11 + 1];
      out[o + 2] = w00 * data[i00 + 2] + w01 * data[i01 + 2] + w10 * data[i10 + 2] + w11 * data[i11 + 2];
    }
  }
  return out;
}

// Box blur separable (1 canal) para unsharp mask
function boxBlur1ch(data, width, height, radius) {
  const tmp = new Float32Array(data.length);
  const out = new Float32Array(data.length);
  const windowSize = radius * 2 + 1;

  // Horizontal pass
  for (let y = 0; y < height; y++) {
    const rowStart = y * width;
    let sum = 0;
    for (let dx = -radius; dx <= radius; dx++) {
      const x = Math.min(width - 1, Math.max(0, dx));
      sum += data[rowStart + x];
    }
    for (let x = 0; x < width; x++) {
      tmp[rowStart + x] = sum / windowSize;
      const xOut = Math.min(width - 1, Math.max(0, x - radius));
      const xIn = Math.min(width - 1, Math.max(0, x + radius + 1));
      sum += data[rowStart + xIn] - data[rowStart + xOut];
    }
  }

  // Vertical pass
  for (let x = 0; x < width; x++) {
    let sum = 0;
    for (let dy = -radius; dy <= radius; dy++) {
      const y = Math.min(height - 1, Math.max(0, dy));
      sum += tmp[y * width + x];
    }
    for (let y = 0; y < height; y++) {
      out[y * width + x] = sum / windowSize;
      const yOut = Math.min(height - 1, Math.max(0, y - radius));
      const yIn = Math.min(height - 1, Math.max(0, y + radius + 1));
      sum += tmp[yIn * width + x] - tmp[yOut * width + x];
    }
  }

  return out;
}

// --- Funciones de alineación (corrección de trepidación) ---

// Crear thumbnail de luminancia (downscale a size×size)
function makeThumbnail(data, width, height, size) {
  const thumb = new Float32Array(size * size);
  const xStep = width / size;
  const yStep = height / size;
  for (let y = 0; y < size; y++) {
    const sy = Math.min(height - 1, Math.floor(y * yStep));
    for (let x = 0; x < size; x++) {
      const sx = Math.min(width - 1, Math.floor(x * xStep));
      const idx = (sy * width + sx) * 3;
      thumb[y * size + x] = 0.299 * data[idx] + 0.587 * data[idx + 1] + 0.114 * data[idx + 2];
    }
  }
  return thumb;
}

// Crear thumbnail con offset de píxeles aplicado (para alineación multi-nivel)
function makeThumbnailWithOffset(data, width, height, size, offsetX, offsetY) {
  const thumb = new Float32Array(size * size);
  const xStep = width / size;
  const yStep = height / size;
  for (let y = 0; y < size; y++) {
    const sy = Math.min(height - 1, Math.max(0, Math.floor(y * yStep - offsetY)));
    for (let x = 0; x < size; x++) {
      const sx = Math.min(width - 1, Math.max(0, Math.floor(x * xStep - offsetX)));
      const idx = (sy * width + sx) * 3;
      thumb[y * size + x] = 0.299 * data[idx] + 0.587 * data[idx + 1] + 0.114 * data[idx + 2];
    }
  }
  return thumb;
}

// Extraer crop de luminancia a resolución completa (para refinamiento pixel-exacto)
function extractLuminanceCrop(data, width, cropX, cropY, cropSize) {
  const crop = new Float32Array(cropSize * cropSize);
  for (let y = 0; y < cropSize; y++) {
    for (let x = 0; x < cropSize; x++) {
      const idx = ((cropY + y) * width + (cropX + x)) * 3;
      crop[y * cropSize + x] = 0.299 * data[idx] + 0.587 * data[idx + 1] + 0.114 * data[idx + 2];
    }
  }
  return crop;
}

// Extraer crop de luminancia con offset de píxeles (búsqueda full-res)
function extractLuminanceCropWithShift(data, width, height, cropX, cropY, cropSize, shiftX, shiftY) {
  const crop = new Float32Array(cropSize * cropSize);
  for (let y = 0; y < cropSize; y++) {
    const sy = Math.min(height - 1, Math.max(0, cropY + y - shiftY));
    for (let x = 0; x < cropSize; x++) {
      const sx = Math.min(width - 1, Math.max(0, cropX + x - shiftX));
      const idx = (sy * width + sx) * 3;
      crop[y * cropSize + x] = 0.299 * data[idx] + 0.587 * data[idx + 1] + 0.114 * data[idx + 2];
    }
  }
  return crop;
}

// SAD entre dos arrays de igual longitud
function sadArrays(a, b) {
  let sad = 0;
  for (let i = 0; i < a.length; i++) {
    sad += Math.abs(a[i] - b[i]);
  }
  return sad;
}

// Normalizar thumbnail (zero-mean, unit-variance)
// CRÍTICO: los brackets HDR tienen exposiciones diferentes; sin normalización,
// el SAD encuentra falsos óptimos porque la diferencia de brillo domina.
function normalizeThumbnail(thumb) {
  let mean = 0;
  for (let i = 0; i < thumb.length; i++) mean += thumb[i];
  mean /= thumb.length;
  let variance = 0;
  for (let i = 0; i < thumb.length; i++) {
    const d = thumb[i] - mean;
    variance += d * d;
  }
  const std = Math.sqrt(variance / thumb.length) || 1;
  const out = new Float32Array(thumb.length);
  for (let i = 0; i < thumb.length; i++) {
    out[i] = (thumb[i] - mean) / std;
  }
  return out;
}

// Buscar el mejor desplazamiento (dx, dy) entre ref y thumb usando SAD
function findBestShift(ref, thumb, size, maxShift) {
  let bestDx = 0, bestDy = 0, bestSAD = Infinity;
  for (let dy = -maxShift; dy <= maxShift; dy++) {
    for (let dx = -maxShift; dx <= maxShift; dx++) {
      let sad = 0, count = 0;
      for (let y = maxShift; y < size - maxShift; y++) {
        const ry = y - dy;
        for (let x = maxShift; x < size - maxShift; x++) {
          const rx = x - dx;
          sad += Math.abs(ref[y * size + x] - thumb[ry * size + rx]);
          count++;
        }
      }
      const avgSAD = sad / count;
      if (avgSAD < bestSAD) {
        bestSAD = avgSAD;
        bestDx = dx;
        bestDy = dy;
      }
    }
  }
  return { dx: bestDx, dy: bestDy };
}

// Aplicar desplazamiento entero a imagen completa (3 canales)
function shiftImage3ch(data, width, height, dx, dy) {
  if (dx === 0 && dy === 0) return data;
  const out = new Float32Array(data.length);
  for (let y = 0; y < height; y++) {
    const sy = y - dy;
    if (sy < 0 || sy >= height) continue;
    for (let x = 0; x < width; x++) {
      const sx = x - dx;
      if (sx < 0 || sx >= width) continue;
      const srcIdx = (sy * width + sx) * 3;
      const dstIdx = (y * width + x) * 3;
      out[dstIdx] = data[srcIdx];
      out[dstIdx + 1] = data[srcIdx + 1];
      out[dstIdx + 2] = data[srcIdx + 2];
    }
  }
  return out;
}

// Construir pirámide laplaciana (3 canales)
function laplacianPyramid3ch(data, width, height, levels, dims) {
  // Pirámide gaussiana
  const gaussian = [data];
  for (let l = 1; l < levels; l++) {
    const prev = gaussian[l - 1];
    const pw = dims[l - 1].w;
    const ph = dims[l - 1].h;
    const nw = dims[l].w;
    const nh = dims[l].h;
    gaussian.push(downsample3ch(prev, pw, ph, nw, nh));
  }

  // Pirámide laplaciana: diferencia entre nivel y versión upsampled del siguiente
  const laplacian = [];
  for (let l = 0; l < levels - 1; l++) {
    const nw = dims[l + 1].w;
    const nh = dims[l + 1].h;
    const up = upsample3ch(gaussian[l + 1], nw, nh, dims[l].w, dims[l].h);
    const lap = new Float32Array(dims[l].w * dims[l].h * 3);
    for (let i = 0; i < lap.length; i++) {
      lap[i] = gaussian[l][i] - up[i];
    }
    laplacian.push(lap);
    gaussian[l] = null; // liberar nivel inferior
  }
  laplacian.push(gaussian[levels - 1]); // el nivel más grueso se queda como residual

  return laplacian;
}
