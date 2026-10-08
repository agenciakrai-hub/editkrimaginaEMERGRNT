import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { studioApi as base44, studioAi, readDataUrl } from "@/lib/studioApi";
import { motion, AnimatePresence } from "framer-motion";
import { Layers, Play, FolderPlus } from "lucide-react";
import { useStudioToast as useToast } from "@/lib/useStudioToast";
import { groupIntoBrackets, loadImageFromFile } from "@/lib/bracketingProcessor";
import UploadZone from "./UploadZone";
import BracketSelector from "./BracketSelector";
import FilePreview from "./FilePreview";
import ProcessingPanel from "./ProcessingPanel";
import ResultsGallery from "./ResultsGallery";

export default function BracketingModule({ projects: propProjects, initialProjectId, onResultStored }) {
  const { refresh } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [files, setFiles] = useState([]);
  const workerRef = useRef(null), urlsRef = useRef([]);
  const [aiBusy, setAiBusy] = useState(false);
  useEffect(() => () => { workerRef.current?.terminate(); urlsRef.current.forEach(URL.revokeObjectURL); }, []);
  const [bracketSize, setBracketSize] = useState(3);
  const [step, setStep] = useState("idle"); // idle | upload | processing | done
  const [scenes, setScenes] = useState([]);
  const [results, setResults] = useState([]);
  const [validationError, setValidationError] = useState("");
  const [selectedProjectId, setSelectedProjectId] = useState(initialProjectId || "");
  const [projects, setProjects] = useState(propProjects || []);
  const [newProjectName, setNewProjectName] = useState("");
  const [creatingProject, setCreatingProject] = useState(false);

  useEffect(() => {
    if (!propProjects) {
      base44.entities.Project
        .list("-created_date", 50)
        .then(setProjects)
        .catch(() => {});
    }
  }, [propProjects]);

  const handleFilesSelected = (newFiles) => {
    setFiles((prev) => [...prev, ...newFiles].sort((a,b) => a.name.localeCompare(b.name,"es",{numeric:true})));
    setStep("upload");
    setValidationError("");
  };

  const handleClear = () => {
    if (aiBusy || step === "processing") return;
    urlsRef.current.forEach(URL.revokeObjectURL); urlsRef.current = [];
    setFiles([]);
    setStep("idle");
    setScenes([]);
    setResults([]);
    setValidationError("");
  };

  const createProject = async () => {
    if (!newProjectName.trim()) return;
    setCreatingProject(true);
    try {
      const p = await base44.entities.Project.create({
        name: newProjectName.trim(),
        description: "",
        photo_count: 0,
      });
      setProjects((prev) => [p, ...prev]);
      setSelectedProjectId(p.id);
      setNewProjectName("");
      toast({ title: "Proyecto creado" });
    } catch (e) {
      toast({ title: "Error al crear proyecto", description: e.message, variant: "destructive" });
    }
    setCreatingProject(false);
  };

  const runWorker = (groupImageDatas, groupIndex, onProgress) => {
    return new Promise((resolve, reject) => {
      const worker = new Worker("/bracketingWorker.js?v=krai1"); workerRef.current = worker;
      const timer = setTimeout(() => { worker.terminate(); reject(new Error("Tiempo de fusión agotado.")); },180000);
      worker.onmessage = (e) => {
        const msg = e.data;
        if (msg.type === "progress") {
          onProgress(msg.pct);
        } else if (msg.type === "done") {
          clearTimeout(timer); worker.terminate();
          resolve({ blob: msg.blob, alignment: msg.alignment, sharpness: msg.sharpness });
        } else if (msg.type === "error") {
          clearTimeout(timer); worker.terminate();
          reject(new Error(msg.message));
        }
      };
      worker.onerror = (e) => {
        clearTimeout(timer); worker.terminate();
        reject(new Error(e.message || "Worker error"));
      };
      worker.postMessage(
        { groupImageDatas, groupIndex },
        groupImageDatas.map((d) => d.data)
      );
    });
  };

  const handleProcess = async () => {
    if (step === "processing" || aiBusy) return;
    if (files.length % bracketSize) { setValidationError("Completa todos los grupos de exposiciones antes de fusionar."); return; }
    if (files.length < bracketSize) {
      setValidationError(`Necesitas al menos ${bracketSize} fotos para una escena HDR`);
      return;
    }
    setValidationError("");
    setStep("processing");
    const { groups } = groupIntoBrackets(files, bracketSize);
    const initialScenes = groups.map((g, i) => ({
      index: i,
      fileCount: g.length,
      status: "pending",
      progress: 0,
    }));
    setScenes(initialScenes);
    setResults([]);

    for (let groupIndex = 0; groupIndex < groups.length; groupIndex++) {
      const group = groups[groupIndex];
        try {
          setScenes((prev) =>
            prev.map((s) => (s.index === groupIndex ? { ...s, status: "processing" } : s))
          );
          const groupImageDatas = [];
          let targetW = null;
          let targetH = null;
          let referencePreview = null;
          for (const [fileIndex,file] of group.entries()) {
            const { imageData, width, height } = await loadImageFromFile(file, targetW, targetH);
            if (targetW === null) {
              targetW = width;
              targetH = height;
            }
            if (fileIndex === Math.floor(group.length/2)) {
              const canvas=document.createElement("canvas"); canvas.width=width; canvas.height=height;
              canvas.getContext("2d").putImageData(imageData,0,0);
              referencePreview=await new Promise((resolve)=>canvas.toBlob(resolve,"image/jpeg",0.92));
            }
            groupImageDatas.push({ data: imageData.data.buffer, width, height });
          }
          const { blob, alignment, sharpness } = await runWorker(groupImageDatas, groupIndex, (pct) => {
            setScenes((prev) =>
              prev.map((s) => (s.index === groupIndex ? { ...s, progress: pct } : s))
            );
          });
          const url = URL.createObjectURL(blob);
          const originalUrl = URL.createObjectURL(referencePreview);
          urlsRef.current.push(url,originalUrl);
          setScenes((prev) =>
            prev.map((s) => (s.index === groupIndex ? { ...s, status: "done", progress: 100 } : s))
          );
          setResults((prev) =>
            [...prev, { blob, url, originalUrl, index: groupIndex, alignment, sharpness }].sort((a, b) => a.index - b.index)
          );
          // Persistir el HDR en la carpeta del proyecto seleccionado.
          if (selectedProjectId) {
            try {
              const { file_url } = await base44.integrations.Core.UploadFile({
                file: new File([blob], `hdr_${groupIndex + 1}.jpg`, { type: "image/jpeg" }),
              });
              await base44.entities.MediaAsset.create({
                name: `HDR escena ${groupIndex + 1}`,
                type: "photo",
                url: file_url,
                project_id: selectedProjectId,
              });
              if (onResultStored) onResultStored();
            } catch (persistErr) {
              toast({title:"HDR fusionado, pero no guardado",description:persistErr.message,variant:"destructive"});
            }
          }
          // Diagnosticar trepidación
          const maxShift = Math.max(...(alignment || []).map(a => Math.max(Math.abs(a.dx), Math.abs(a.dy))));
          if (maxShift > 0) {
            toast({ title: `Escena ${groupIndex + 1}: trepidación corregida`, description: `Desplazamiento corregido: ${maxShift}px · Nitidez: ${sharpness}` });
          } else {
            toast({ title: `Escena ${groupIndex + 1} fusionada`, description: `Sin trepidación detectada · Nitidez: ${sharpness}` });
          }
        } catch (err) {
          toast({title:`Error en escena ${groupIndex+1}`,description:err.message,variant:"destructive"});
          setScenes((prev) =>
            prev.map((s) => (s.index === groupIndex ? { ...s, status: "error", progress: 0 } : s))
          );
        }
      }

    setStep("done");
  };

  const handleDownload = (result) => {
    const a = document.createElement("a");
    a.href = result.url;
    a.download = `hdr_scene_${result.index + 1}.jpg`;
    a.click();
  };

  const handleEditPhoto = async (result) => {
    try {
      const photo = await base44.entities.MediaAsset.create({ project_id:selectedProjectId, url:await readDataUrl(result.blob) });
      navigate(`/app/manual?photo_id=${photo.id}`);
    } catch(e) { toast({title:"Selecciona una propiedad para abrir la copia",description:e.message,variant:"destructive"}); }
  };
  const handleAiEdit = async (result) => {
    if(aiBusy) return; setAiBusy(true);
    try {
      const blob=await studioAi("hdr",result.blob), url=URL.createObjectURL(blob); urlsRef.current.push(url);
      setResults((prev)=>prev.map((r)=>r.index===result.index?{...r,blob,url}:r));
      toast({title:"Acabado IA aplicado",description:"Descarga o guarda una nueva copia."});
    } catch(e) { toast({title:"No se pudo aplicar IA",description:e.message,variant:"destructive"}); }
    finally {await refresh();setAiBusy(false);}
  };
  const saveResult = async (result) => {
    try {await base44.entities.MediaAsset.create({project_id:selectedProjectId,url:await readDataUrl(result.blob)});toast({title:"Copia guardada en la propiedad"});}
    catch(e) {toast({title:"No se pudo guardar",description:e.message,variant:"destructive"});}
  };

  const sceneCount = bracketSize > 0 ? Math.floor(files.length / bracketSize) : 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-400 flex items-center justify-center">
          <Layers className="w-5 h-5 text-white" />
        </div>
        <div>
          <h1 className="text-xl font-bold">Fusión HDR</h1>
          <p className="text-xs text-gray-500">Sube tus fotos y fusiona exposiciones automáticamente</p>
        </div>
      </div>

      {/* Selector de proyecto */}
      <div className="flex flex-wrap items-end gap-3 p-4 rounded-xl bg-gray-900/50 border border-gray-800">
        <div className="flex-1 min-w-[200px]">
          <label className="text-xs text-gray-400 block mb-1">Proyecto destino</label>
          <select
            value={selectedProjectId}
            onChange={(e) => setSelectedProjectId(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200"
          >
            <option value="">Sin proyecto</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <input
            value={newProjectName}
            onChange={(e) => setNewProjectName(e.target.value)}
            placeholder="Nuevo proyecto..."
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 w-44"
          />
          <button
            onClick={createProject}
            disabled={!newProjectName.trim() || creatingProject}
            className="px-3 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm flex items-center gap-1.5 disabled:opacity-50"
          >
            <FolderPlus className="w-4 h-4" /> Crear
          </button>
        </div>
      </div>

      <AnimatePresence mode="wait">
        {(step === "idle" || step === "upload") && (
          <motion.div
            key="upload"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="space-y-4"
          >
            <UploadZone onFilesSelected={handleFilesSelected} disabled={step === "processing"} />
            {files.length > 0 && (
              <>
                <div className="flex flex-wrap items-center justify-between gap-3 p-4 rounded-xl bg-gray-900/50 border border-gray-800">
                  <BracketSelector value={bracketSize} onChange={setBracketSize} totalFiles={files.length} />
                  <button
                    onClick={handleProcess}
                    disabled={files.length < bracketSize || files.length % bracketSize !== 0}
                    className="px-5 py-2 rounded-lg bg-gradient-to-r from-blue-500 to-cyan-400 text-white text-sm font-medium flex items-center gap-2 disabled:opacity-50"
                  >
                    <Play className="w-4 h-4" /> Procesar {sceneCount} escena{sceneCount !== 1 ? "s" : ""}
                  </button>
                </div>
                <FilePreview files={files} bracketSize={bracketSize} onClear={handleClear} />
                {validationError && <p className="text-sm text-destructive">{validationError}</p>}
              </>
            )}
          </motion.div>
        )}

        {step === "processing" && (
          <motion.div key="processing" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <ProcessingPanel scenes={scenes} />
          </motion.div>
        )}

        {step === "done" && (
          <motion.div
            key="done"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="space-y-4"
          >
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-gray-200">{results.length} escena(s) fusionada(s)</p>
              <button onClick={handleClear} className="text-sm text-gray-400 hover:text-gray-200">
                Nueva fusión
              </button>
            </div>
            {aiBusy && <p role="status">Aplicando acabado IA…</p>}
            <ResultsGallery results={results} onDownload={handleDownload} onEdit={handleEditPhoto} onAiEdit={handleAiEdit} onSave={saveResult} aiBusy={aiBusy} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
