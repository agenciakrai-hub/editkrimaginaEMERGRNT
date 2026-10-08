import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { studioApi as base44, studioAi, readDataUrl } from "@/lib/studioApi";
import { Loader2, Download, Save, Upload, X, SlidersHorizontal, Wand2, Layers } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { useStudioToast as useToast } from "@/lib/useStudioToast";
import {
  computePreviewSize, getDefaultAdjustments, createMaskCanvas, paintBrushOnMask,
  renderComposite, exportToBlob, clearLayerCache, invalidateLayerCache, genId,
} from "@/lib/proEditorEngine";
import EditorToolbar from "@/components/proeditor/EditorToolbar";
import BrushSettings from "@/components/proeditor/BrushSettings";
import SkyReplacerPanel from "@/components/proeditor/SkyReplacerPanel";
import {
  magicWand, unionSelection, paintSelection, newSelectionCanvas,
  buildHideMask, countSelected, loadSkyCatalog, saveSkyCatalog,
  cloneSelection, selectionFromMasks,
} from "@/lib/skyReplacer";
import CanvasViewport from "@/components/proeditor/CanvasViewport";
import AdjustmentsPanel from "@/components/proeditor/AdjustmentsPanel";
import LayersPanel from "@/components/proeditor/LayersPanel";
import TransformPanel from "@/components/proeditor/TransformPanel";
import BatchFilmstrip from "@/components/proeditor/BatchFilmstrip";

export default function ManualEditor() {
  const { refresh } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [image, setImage] = useState(null);
  const [previewSize, setPreviewSize] = useState({ width: 0, height: 0 });
  const [layers, setLayers] = useState([]);
  const [activeLayerId, setActiveLayerId] = useState(null);
  const [tool, setTool] = useState("move");
  const [brush, setBrush] = useState({ size: 80, hardness: 0.5, mode: "hide" });
  const [transform, setTransform] = useState({ rotation: 0, perspectiveX: 0, perspectiveY: 0 });
  const [crop, setCrop] = useState({ x: 0, y: 0, width: 1, height: 1 });
  const [activePanel, setActivePanel] = useState("adjustments");
  const [renderTick, setRenderTick] = useState(0);
  const [exporting, setExporting] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const [projects, setProjects] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");

  // Herramienta Cielos / Ventanas
  const [skyPhotoMode, setSkyPhotoMode] = useState("exterior");
  const [skyMode, setSkyMode] = useState("detect");
  const [skyTolerance, setSkyTolerance] = useState(32);
  const [skyBrush, setSkyBrush] = useState({ size: 60, mode: "add" });
  const [skyVersion, setSkyVersion] = useState(0);
  const [skyCatalog, setSkyCatalog] = useState([]);
  const [selectedSkyId, setSelectedSkyId] = useState(null);
  const [skyApplying, setSkyApplying] = useState(false);
  const [skyDetecting, setSkyDetecting] = useState(false);
  const [skyLayerId, setSkyLayerId] = useState(null);

  // Batch mode
  const [batch, setBatch] = useState(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [savingAll, setSavingAll] = useState(false);
  const [editedIds, setEditedIds] = useState(new Set());
  const editStatesRef = useRef(new Map());

  const layersRef = useRef([]);
  const transformRef = useRef(transform);
  const cropRef = useRef(crop);
  const rafRef = useRef(null);
  useEffect(() => { layersRef.current = layers; }, [layers]);
  useEffect(() => { transformRef.current = transform; }, [transform]);
  useEffect(() => { cropRef.current = crop; }, [crop]);

  const skySelRef = useRef(null);
  const skyHistoryRef = useRef([]);
  const [skyHistoryLen, setSkyHistoryLen] = useState(0);
  useEffect(() => { setSkyCatalog(loadSkyCatalog()); }, []);
  const skySelCount = useMemo(
    () => (skySelRef.current ? countSelected(skySelRef.current) : 0),
    // Recalcular cuando cambia el lienzo de selección mutable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [skyVersion]
  );

  const pushSkyHistory = useCallback(() => {
    const snap = skySelRef.current ? cloneSelection(skySelRef.current) : null;
    skyHistoryRef.current.push(snap);
    if (skyHistoryRef.current.length > 40) skyHistoryRef.current.shift();
    setSkyHistoryLen(skyHistoryRef.current.length);
  }, []);

  const undoSky = useCallback(() => {
    const hist = skyHistoryRef.current;
    if (hist.length === 0) return;
    const prev = hist.pop();
    skySelRef.current = prev ? cloneSelection(prev) : null;
    setSkyHistoryLen(hist.length);
    setSkyVersion((v) => v + 1);
  }, []);

  // Deshacer con Cmd/Ctrl+Z mientras la herramienta de cielos está activa.
  useEffect(() => {
    if (tool !== "sky") return;
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === "z" || e.key === "Z")) {
        e.preventDefault();
        undoSky();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [tool, undoSky]);

  useEffect(() => {
    base44.entities.Project.list("-created_date", 50).then(setProjects).catch(() => {});
  }, []);

  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const jobId = urlParams.get("property_id");
    const photoId = urlParams.get("photo_id");
    if (photoId) { loadPhoto(photoId); return; }
    if (jobId) { loadBatch(jobId); return; }
    const imageUrl = urlParams.get('image_url');
    if (!imageUrl) return;
    loadImageEl(imageUrl).then(initEditor).catch(() => {
      toast({ title: "No se pudo cargar la imagen", variant: "destructive" });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Descarga la imagen como blob y la carga desde una URL local (blob:) — evita que
  // el canvas quede "tainted" por CORS al exportar/editar imágenes de otro dominio.
  const loadPhoto = async (photoId) => {
    try {
      const { api, fileUrl } = await import("@/lib/api");
      const p = (await api.get(`/photos/${photoId}`)).data;
      setSelectedProjectId(p.property_id);
      initEditor(await loadImageEl(fileUrl(p.current_path || p.original_path)));
    } catch (e) { toast({ title: "No se pudo cargar la foto", description: e.message, variant: "destructive" }); }
  };
  const loadImageEl = async (url) => {
    const res = await fetch(url);
    if (!res.ok) throw new Error("No se pudo cargar la imagen");
    const blob = await res.blob();
    const objUrl = URL.createObjectURL(blob);
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => { URL.revokeObjectURL(objUrl); resolve(img); };
      img.onerror = () => { URL.revokeObjectURL(objUrl); reject(new Error("load failed")); };
      img.src = objUrl;
    });
  };

  const loadBatch = async (jobId) => {
    try {
      const imgs = await base44.entities.EditingImage.filter({ job_id: jobId });
      const completed = imgs
        .filter((i) => i.status === "completed" && i.edited_url)
        .sort((a, b) => a.order - b.order);
      if (completed.length === 0) {
        toast({ title: "No hay fotos completadas para editar", variant: "destructive" });
        return;
      }
      const loaded = [];
      for (const img of completed) {
        const el = await loadImageEl(img.edited_url);
        loaded.push({ id: img.id, url: img.edited_url, imageEl: el });
      }
      setSelectedProjectId(jobId);
      setBatch(loaded);
      setCurrentIndex(0);
      initEditor(loaded[0].imageEl);
    } catch (e) {
      toast({ title: "No se pudo cargar el lote", description: e.message, variant: "destructive" });
    }
  };

  const persistCurrentState = () => {
    if (!batch) return;
    const current = batch[currentIndex];
    if (current) {
      editStatesRef.current.set(current.id, {
        layers: layersRef.current,
        transform: transformRef.current,
        crop: cropRef.current,
      });
    }
  };

  const switchToImage = (index) => {
    if (!batch || index === currentIndex) return;
    persistCurrentState();
    const entry = batch[index];
    const saved = editStatesRef.current.get(entry.id);
    clearLayerCache();
    setImage(entry.imageEl);
    setPreviewSize(computePreviewSize(entry.imageEl.naturalWidth, entry.imageEl.naturalHeight));
    if (saved) {
      setLayers(saved.layers);
      setTransform(saved.transform);
      setCrop(saved.crop);
      setActiveLayerId(saved.layers[0]?.id || null);
    } else {
      const baseLayer = {
        id: genId(), name: "Capa base", adjustments: getDefaultAdjustments(),
        maskCanvas: null, opacity: 1, visible: true,
      };
      setLayers([baseLayer]);
      setActiveLayerId(baseLayer.id);
      setTransform({ rotation: 0, perspectiveX: 0, perspectiveY: 0 });
      setCrop({ x: 0, y: 0, width: 1, height: 1 });
    }
    setSkyLayerId(null);
    skySelRef.current = null; skyHistoryRef.current = []; setSkyHistoryLen(0); setSkyVersion((v) => v + 1);
    setCurrentIndex(index);
  };

  const applyToAll = () => {
    if (!batch || batch.length <= 1) return;
    persistCurrentState();
    const current = batch[currentIndex];
    const currentAdjustments = layersRef.current[0]?.adjustments
      ? { ...layersRef.current[0].adjustments }
      : getDefaultAdjustments();
    let count = 0;
    for (const entry of batch) {
      if (entry.id === current.id) continue;
      const baseLayer = {
        id: genId(), name: "Capa base", adjustments: { ...currentAdjustments },
        maskCanvas: null, opacity: 1, visible: true,
      };
      editStatesRef.current.set(entry.id, {
        layers: [baseLayer],
        transform: { ...transformRef.current },
        crop: { ...cropRef.current },
      });
      count++;
    }
    toast({ title: `Corrección aplicada a ${count} fotos`, description: "Pulsa «Guardar todas» para conservar los cambios" });
  };

  const saveAll = async () => {
    if (!batch) return;
    setSavingAll(true);
    persistCurrentState();
    try {
      let savedCount = 0;
      for (let i = 0; i < batch.length; i++) {
        const entry = batch[i];
        const state = editStatesRef.current.get(entry.id);
        if (!state) continue;
        clearLayerCache();
        const blob = await exportToBlob(entry.imageEl, state.layers, state.transform, state.crop);
        const { file_url } = await base44.integrations.Core.UploadFile({
          file: new File([blob], `pro_edited_${i + 1}.jpg`, { type: "image/jpeg" }),
        });
        await base44.entities.EditingImage.update(entry.id, { edited_url: file_url });
        savedCount++;
        setEditedIds((prev) => new Set(prev).add(entry.id));
      }
      toast({ title: `${savedCount} copias guardadas`, description: "Los originales se conservan en la propiedad" });
    } catch (e) {
      toast({ title: "Error al guardar", description: e.message, variant: "destructive" });
    }
    setSavingAll(false);
  };

  const requestRender = useCallback(() => {
    if (rafRef.current) return;
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null;
      setRenderTick((t) => t + 1);
    });
  }, []);

  const initEditor = (img) => {
    setImage(img);
    const ps = computePreviewSize(img.naturalWidth, img.naturalHeight);
    setPreviewSize(ps);
    clearLayerCache();
    skySelRef.current = null; skyHistoryRef.current = []; setSkyHistoryLen(0); setSkyVersion((v) => v + 1);
    setSkyLayerId(null);
    const baseLayer = {
      id: genId(), name: "Capa base", adjustments: getDefaultAdjustments(),
      maskCanvas: null, opacity: 1, visible: true,
    };
    setLayers([baseLayer]);
    setActiveLayerId(baseLayer.id);
    setTransform({ rotation: 0, perspectiveX: 0, perspectiveY: 0 });
    setCrop({ x: 0, y: 0, width: 1, height: 1 });
  };

  const handleFileSelect = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => { initEditor(img); URL.revokeObjectURL(url); };
    img.onerror = () => { toast({ title: "No se pudo cargar la imagen", variant: "destructive" }); };
    img.src = url;
    e.target.value = "";
  };

  const addLayer = () => {
    const layer = {
      id: genId(), name: `Capa ${layers.length + 1}`, adjustments: getDefaultAdjustments(),
      maskCanvas: null, opacity: 1, visible: true,
    };
    setLayers((p) => [...p, layer]);
    setActiveLayerId(layer.id);
  };

  const deleteLayer = (id) => {
    if (layers.length <= 1) return;
    invalidateLayerCache(id);
    setLayers((p) => p.filter((l) => l.id !== id));
    if (activeLayerId === id) setActiveLayerId(layers.find((l) => l.id !== id)?.id || null);
  };

  const duplicateLayer = (id) => {
    setLayers((p) => {
      const idx = p.findIndex((l) => l.id === id);
      if (idx < 0) return p;
      const src = p[idx];
      const copy = {
        id: genId(), name: `${src.name} (copia)`, adjustments: { ...src.adjustments },
        maskCanvas: src.maskCanvas ? cloneSelection(src.maskCanvas) : null, opacity: src.opacity, visible: src.visible,
        imageEl: src.imageEl, imageFit: src.imageFit, blur: src.blur,
      };
      const next = [...p];
      next.splice(idx + 1, 0, copy);
      return next;
    });
  };

  const toggleVisibility = (id) => {
    setLayers((p) => p.map((l) => (l.id === id ? { ...l, visible: !l.visible } : l)));
  };

  const setLayerOpacity = (id, value) => {
    setLayers((p) => p.map((l) => (l.id === id ? { ...l, opacity: value } : l)));
  };

  const handleAdjustmentChange = (key, value) => {
    setLayers((p) => p.map((l) => (l.id === activeLayerId ? { ...l, adjustments: { ...l.adjustments, [key]: value } } : l)));
    requestRender();
  };

  const resetAdjustments = () => {
    setLayers((p) => p.map((l) => (l.id === activeLayerId ? { ...l, adjustments: getDefaultAdjustments() } : l)));
    requestRender();
  };

  const clearMask = (id) => {
    setLayers((p) => p.map((l) => (l.id === id ? { ...l, maskCanvas: null } : l)));
    requestRender();
  };

  const handlePaintMask = useCallback((layerId, fromX, fromY, toX, toY) => {
    const layer = layersRef.current.find((l) => l.id === layerId);
    if (!layer) return;
    if (!layer.maskCanvas) {
      const mask = createMaskCanvas(previewSize.width, previewSize.height);
      layersRef.current = layersRef.current.map((l) => (l.id === layerId ? { ...l, maskCanvas: mask } : l));
      setLayers((p) => p.map((l) => (l.id === layerId ? { ...l, maskCanvas: mask } : l)));
      paintBrushOnMask(mask, fromX, fromY, toX, toY, brush.size, brush.hardness, brush.mode);
    } else {
      paintBrushOnMask(layer.maskCanvas, fromX, fromY, toX, toY, brush.size, brush.hardness, brush.mode);
      requestRender();
    }
  }, [previewSize, brush, requestRender]);

  // --- Herramienta Cielos / Ventanas ---
  const onSkyWand = useCallback((x, y) => {
    if (!image) return;
    pushSkyHistory();
    const c = document.createElement("canvas");
    c.width = previewSize.width;
    c.height = previewSize.height;
    const ctx = c.getContext("2d");
    ctx.drawImage(image, 0, 0, image.naturalWidth, image.naturalHeight, 0, 0, previewSize.width, previewSize.height);
    const sel = magicWand(c, x, y, skyTolerance);
    if (!skySelRef.current) skySelRef.current = sel;
    else unionSelection(skySelRef.current, sel);
    setSkyVersion((v) => v + 1);
  }, [image, previewSize, skyTolerance, pushSkyHistory]);

  const onSkyStrokeBegin = useCallback(() => {
    pushSkyHistory();
  }, [pushSkyHistory]);

  const onSkyPaint = useCallback((fx, fy, tx, ty) => {
    if (!skySelRef.current) skySelRef.current = newSelectionCanvas(previewSize.width, previewSize.height);
    paintSelection(skySelRef.current, fx, fy, tx, ty, skyBrush.size, skyBrush.mode);
    setSkyVersion((v) => v + 1);
  }, [previewSize, skyBrush]);

  const clearSkySelection = useCallback(() => {
    pushSkyHistory();
    skySelRef.current = null;
    setSkyVersion((v) => v + 1);
  }, [pushSkyHistory]);

  // Selección automática usando exclusivamente el motor de KRAI asignado.
  // Detecta "window" (interior) o "sky" (exterior) y, si ya hay un cielo del
  // catálogo elegido, lo aplica directamente en un solo paso.
  const autoDetectGlass = async () => {
    if (!image) return;
    setSkyDetecting(true);
    try {
      // Enviar la foto al servidor autenticado para obtener la máscara de KRAI.
      const c = document.createElement("canvas");
      c.width = image.naturalWidth;
      c.height = image.naturalHeight;
      c.getContext("2d").drawImage(image, 0, 0);
      const blob = await new Promise((res) => c.toBlob(res, "image/jpeg", 0.92));
      const maskBlob = await studioAi("manual", blob, skyPhotoMode);
      const r = { masks: [{ mask: await readDataUrl(maskBlob) }] };
      pushSkyHistory();
      const sel = await selectionFromMasks(
        r.masks.map((m) => m.mask),
        previewSize.width,
        previewSize.height
      );
      if (!countSelected(sel)) { toast({title:"No se ha detectado una zona",description:"Puedes seleccionarla con la varita o el pincel."}); return; }
      skySelRef.current = sel;
      setSkyVersion((v) => v + 1);

      const sky = skyCatalog.find((s) => s.id === selectedSkyId);
      if (sky) {
        await applySkyReplacement();
      } else {
        toast({ title: "Selección IA lista", description: "Elige un cielo del catálogo y pulsa Reemplazar" });
      }
    } catch (e) {
      toast({ title: "Error en detección IA", description: e.message, variant: "destructive" });
    } finally {
      await refresh();
      setSkyDetecting(false);
    }
  };

  const addSkyToCatalog = async (file) => {
    if (!file) return;
    try {
      const bitmap = await createImageBitmap(file);
      const c = document.createElement("canvas"); const scale = Math.min(1,1024 / Math.max(bitmap.width,bitmap.height));
      c.width = Math.round(bitmap.width*scale); c.height = Math.round(bitmap.height*scale); c.getContext("2d").drawImage(bitmap,0,0,c.width,c.height); bitmap.close();
      const small = await new Promise((resolve) => c.toBlob(resolve,"image/jpeg",0.85));
      if (!small) throw new Error("No se pudo cargar el cielo");
      const file_url = await readDataUrl(small);
      const entry = { id: genId(), name: file.name, url: file_url };
      const next = [...skyCatalog, entry];
      saveSkyCatalog(next);
      setSkyCatalog(next);
      setSelectedSkyId(entry.id);
    } catch (e) {
      toast({ title: "Error subiendo cielo", description: e.message, variant: "destructive" });
    }
  };

  const removeSky = (id) => {
    const next = skyCatalog.filter((s) => s.id !== id);
    setSkyCatalog(next);
    saveSkyCatalog(next);
    if (selectedSkyId === id) setSelectedSkyId(null);
  };

  const applySkyReplacement = async () => {
    const sel = skySelRef.current;
    if (!sel) { toast({ title: "Selecciona el área a reemplazar", variant: "destructive" }); return; }
    const sky = skyCatalog.find((s) => s.id === selectedSkyId);
    if (!sky) { toast({ title: "Elige un cielo del catálogo", variant: "destructive" }); return; }
    setSkyApplying(true);
    try {
      const img = await loadImageEl(sky.url);
      const hideMask = buildHideMask(sel, previewSize.width, previewSize.height);
      const skyLayer = {
        id: genId(), name: "Cielo", imageEl: img, imageFit: "cover",
        adjustments: getDefaultAdjustments(), maskCanvas: null, opacity: 1, visible: true,
      };
      setLayers((prev) => {
        const remaining = prev.filter((l) => l.id !== skyLayerId);
        const baseWithMask = { ...remaining[0], maskCanvas: hideMask };
        return [skyLayer, baseWithMask, ...remaining.slice(1)];
      });
      setSkyLayerId(skyLayer.id);
      toast({ title: "Exterior reemplazado", description: "Ajusta opacidad y desenfoque, o refina la máscara de la capa base" });
    } catch (e) {
      toast({ title: "Error al reemplazar", description: e.message, variant: "destructive" });
    }
    setSkyApplying(false);
  };

  const handleSkyAdjust = useCallback((key, value) => {
    if (!skyLayerId) return;
    setLayers((prev) => prev.map((l) => (l.id === skyLayerId ? { ...l, [key]: value } : l)));
    invalidateLayerCache(skyLayerId);
    requestRender();
  }, [skyLayerId, requestRender]);

  const handleDownload = async () => {
    setExporting(true);
    try {
      const blob = await exportToBlob(image, layers, transform, crop);
      if (!blob) throw new Error("No se pudo exportar la imagen");
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "edited.jpg";
      a.click();
      setTimeout(() => URL.revokeObjectURL(url),1000);
    } catch (e) {
      toast({ title: "Error al exportar", description: e.message, variant: "destructive" });
    }
    setExporting(false);
  };

  const handleSaveToProject = async () => {
    if (!selectedProjectId) { toast({ title: "Selecciona una propiedad para guardar una copia", variant: "destructive" }); return; }
    setExporting(true);
    try {
      const blob = await exportToBlob(image, layers, transform, crop);
      if (!blob) throw new Error("No se pudo exportar la imagen");
      const { file_url } = await base44.integrations.Core.UploadFile({
        file: new File([blob], "edited.jpg", { type: "image/jpeg" }),
      });
      await base44.entities.Photo.create({
        name: "Edición manual",
        project_id: selectedProjectId || null,
        processed_image: file_url,
        status: "completed",
      });
      toast({ title: "Copia guardada en la propiedad" });
    } catch (e) {
      toast({ title: "Error al guardar", description: e.message, variant: "destructive" });
    }
    setExporting(false);
  };

  useEffect(() => () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); clearLayerCache(); }, []);

  const activeLayer = layers.find((l) => l.id === activeLayerId);
  const isBatch = !!batch;

  return (
    <div className="fixed inset-0 z-30 flex flex-col bg-background text-white">
      <div className="shrink-0 flex flex-wrap items-center justify-between gap-2 px-3 py-2 border-b border-border">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => navigate("/app")}>
            <X className="w-4 h-4 mr-1" /> Dashboard
          </Button>
          {!isBatch && (
            <label className="cursor-pointer">
              <input type="file" accept="image/*" className="hidden" onChange={handleFileSelect} />
              <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-border hover:bg-secondary transition-colors">
                <Upload className="w-3.5 h-3.5" /> Abrir imagen
              </span>
            </label>
          )}
          {isBatch && (
            <span className="text-xs text-muted-foreground">
              Foto {currentIndex + 1} de {batch.length}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {image && (
            <>
              {isBatch ? (
                <>
                  <Button size="sm" variant="outline" onClick={applyToAll} disabled={savingAll || batch.length <= 1}>
                    <Wand2 className="w-3.5 h-3.5 mr-1" /> <span className="hidden sm:inline">Aplicar a todas</span>
                  </Button>
                  <Button size="sm" onClick={saveAll} disabled={savingAll}>
                    {savingAll ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <Layers className="w-3.5 h-3.5 mr-1" />}
                    <span className="hidden sm:inline">Guardar copias</span>
                  </Button>
                </>
              ) : (
                <>
                  <select
                    value={selectedProjectId}
                    onChange={(e) => setSelectedProjectId(e.target.value)}
                    className="bg-card border border-border rounded-lg px-2 py-1.5 text-xs hidden sm:block"
                  >
                    <option value="">Propiedad destino</option>
                    {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                  <Button size="sm" variant="outline" disabled={!selectedProjectId || exporting} onClick={() => loadBatch(selectedProjectId)}>Cargar fotos</Button>
                  <Button size="sm" onClick={handleSaveToProject} disabled={exporting || !selectedProjectId}>
                    {exporting ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <Save className="w-3.5 h-3.5 mr-1" />} <span className="hidden sm:inline">Guardar copia</span>
                  </Button>
                </>
              )}
              <Button size="sm" variant="outline" onClick={handleDownload} disabled={exporting || savingAll}>
                {exporting ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <Download className="w-3.5 h-3.5 mr-1" />}
                <span className="hidden sm:inline">Descargar</span>
              </Button>
              <button onClick={() => setPanelOpen(true)} className="sm:hidden p-2 rounded-lg border border-border text-muted-foreground" title="Paneles">
                <SlidersHorizontal className="w-4 h-4" />
              </button>
            </>
          )}
        </div>
      </div>

      {!image ? (
        <div className="flex-1 flex flex-col items-center justify-center gap-5">
          <label className="cursor-pointer flex flex-col items-center gap-3 p-12 rounded-2xl border-2 border-dashed border-border hover:border-primary/50 transition-colors">
            <input type="file" accept="image/*" className="hidden" onChange={handleFileSelect} />
            <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center">
              <Upload className="w-8 h-8 text-primary" />
            </div>
            <div className="text-center">
              <p className="text-sm font-medium">Abre una imagen para empezar</p>
              <p className="text-xs text-muted-foreground mt-1">Edición manual · JPG, PNG y WebP · Se conservan los originales</p>
            </div>
          </label>
          <div className="flex flex-wrap items-center justify-center gap-2 px-4">
            <select aria-label="Propiedad de origen" value={selectedProjectId} onChange={(e) => setSelectedProjectId(e.target.value)} className="bg-card border border-border rounded-lg px-3 py-2 text-sm">
              <option value="">Selecciona una propiedad</option>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            <Button variant="outline" disabled={!selectedProjectId} onClick={() => loadBatch(selectedProjectId)}>Abrir fotos de la propiedad</Button>
          </div>
        </div>
      ) : (
        <div className="flex-1 flex overflow-hidden relative">
          <EditorToolbar tool={tool} onToolChange={setTool} />
          <CanvasViewport
            image={image}
            layers={layers}
            previewSize={previewSize}
            activeLayerId={activeLayerId}
            tool={tool}
            brush={brush}
            transform={transform}
            crop={crop}
            renderVersion={renderTick}
            onPaintMask={handlePaintMask}
            onCropChange={setCrop}
            skyMode={skyMode}
            skyBrush={skyBrush}
            skySelection={skySelRef.current}
            skyVersion={skyVersion}
            onSkyWand={onSkyWand}
            onSkyPaint={onSkyPaint}
            onSkyStrokeBegin={onSkyStrokeBegin}
          />
          {panelOpen && (
            <div className="sm:hidden absolute inset-0 bg-black/50 z-40" onClick={() => setPanelOpen(false)} />
          )}
          <div className={`
            absolute sm:relative inset-y-0 right-0 z-50
            w-72 max-w-[85vw] sm:max-w-none
            shrink-0 border-l border-border bg-card overflow-y-auto scrollbar-thin
            transition-transform duration-200
            ${panelOpen ? "translate-x-0" : "translate-x-full sm:translate-x-0"}
          `}>
            <div className="sm:hidden flex justify-end p-2">
              <button onClick={() => setPanelOpen(false)} className="p-1.5 rounded-lg hover:bg-secondary">
                <X className="w-4 h-4" />
              </button>
            </div>
            {tool === "brush" && <BrushSettings brush={brush} onChange={setBrush} />}
            {tool === "sky" ? (
              <SkyReplacerPanel
                photoMode={skyPhotoMode}
                onPhotoModeChange={setSkyPhotoMode}
                mode={skyMode}
                onModeChange={setSkyMode}
                tolerance={skyTolerance}
                onToleranceChange={setSkyTolerance}
                brush={skyBrush}
                onBrushChange={setSkyBrush}
                selectionCount={skySelCount}
                onClearSelection={clearSkySelection}
                onUndo={undoSky}
                canUndo={skyHistoryLen > 0}
                onAutoDetectGlass={autoDetectGlass}
                detecting={skyDetecting}
                catalog={skyCatalog}
                selectedSkyId={selectedSkyId}
                onSelectSky={setSelectedSkyId}
                onAddSky={addSkyToCatalog}
                onRemoveSky={removeSky}
                onApply={applySkyReplacement}
                applying={skyApplying}
                skyLayer={layers.find((l) => l.id === skyLayerId)}
                onSkyAdjust={handleSkyAdjust}
              />
            ) : (
              <Tabs value={activePanel} onValueChange={setActivePanel} className="w-full">
                <TabsList className="w-full rounded-none border-b border-border bg-transparent h-9">
                  <TabsTrigger value="adjustments" className="flex-1 text-xs">Ajustes</TabsTrigger>
                  <TabsTrigger value="layers" className="flex-1 text-xs">Capas</TabsTrigger>
                  <TabsTrigger value="transform" className="flex-1 text-xs">Transformar</TabsTrigger>
                </TabsList>
                <TabsContent value="adjustments" className="mt-0">
                  <AdjustmentsPanel layer={activeLayer} onChange={handleAdjustmentChange} onReset={resetAdjustments} />
                </TabsContent>
                <TabsContent value="layers" className="mt-0">
                  <LayersPanel
                    layers={layers}
                    activeLayerId={activeLayerId}
                    onSelect={setActiveLayerId}
                    onAdd={addLayer}
                    onDelete={deleteLayer}
                    onDuplicate={duplicateLayer}
                    onToggleVisibility={toggleVisibility}
                    onOpacityChange={setLayerOpacity}
                    onClearMask={clearMask}
                  />
                </TabsContent>
                <TabsContent value="transform" className="mt-0">
                  <TransformPanel
                    transform={transform}
                    onTransformChange={setTransform}
                    onResetTransform={() => setTransform({ rotation: 0, perspectiveX: 0, perspectiveY: 0 })}
                    onResetCrop={() => setCrop({ x: 0, y: 0, width: 1, height: 1 })}
                  />
                </TabsContent>
              </Tabs>
            )}
          </div>
        </div>
      )}

      {isBatch && (
        <BatchFilmstrip
          images={batch}
          currentIndex={currentIndex}
          editedIds={editedIds}
          onSelect={switchToImage}
        />
      )}
    </div>
  );
}
