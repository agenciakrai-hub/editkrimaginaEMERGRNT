import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, apiError } from "@/lib/api";
import { tourDocument } from "@/lib/tourViewer";
import Header from "@/components/Header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ArrowLeft, Download, Loader2, Sparkles } from "lucide-react";

const FORMATS = ".jpg,.jpeg,.png,.webp,.tif,.tiff,.avif,.heic,.heif";
const MAX_SCENES = 20;
const MAX_UPLOAD = 40 * 1024 * 1024;
const field = "w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-white";
const angle = (value, limit) => Math.min(limit, Math.max(-limit, Number(value) || 0));

function thumbnail(url) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = 640;
      canvas.height = 320;
      canvas.getContext("2d").drawImage(image, 0, 0, 640, 320);
      resolve({ image: canvas.toDataURL("image/jpeg", 0.72) });
    };
    image.onerror = () => reject(new Error("No se pudo preparar la vista para la IA."));
    image.src = url;
  });
}

async function planTour(scenes) {
  const previews = await Promise.all(scenes.map(scene => thumbnail(scene.url)));
  const { data } = await api.post("/tours/plan", { scenes: previews });
  return data.scenes.map(({ index, name, links }) => ({
    ...scenes[index],
    name,
    links: links.map(link => ({ ...link, target: scenes[link.target].id })),
  }));
}

function asDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("No se pudo exportar una de las panorámicas."));
    reader.readAsDataURL(blob);
  });
}

export default function VirtualTour() {
  const [scenes, setScenes] = useState([]);
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const urls = useRef(new Set());
  const activeIndex = scenes.findIndex(scene => scene.id === selected);
  const active = scenes[activeIndex];
  const preview = useMemo(
    () => scenes.length ? tourDocument(scenes.map(({ id, name, url, yaw, links }) =>
      ({ id, name, url, yaw, links })), selected || scenes[0].id) : "",
    [scenes, selected]
  );

  useEffect(() => {
    const imageUrls = urls.current;
    return () => imageUrls.forEach(url => URL.revokeObjectURL(url));
  }, []);

  async function upload(event) {
    const files = Array.from(event.target.files);
    event.target.value = "";
    if (!files.length) return;
    if (files.length + scenes.length > MAX_SCENES) {
      setNotice(`Puedes incluir hasta ${MAX_SCENES} escenas en un tour.`);
      return;
    }
    setBusy("Preparando panorámicas…");
    setNotice("");
    const added = [];
    const messages = [];
    try {
      for (const file of files) {
        if (file.size > MAX_UPLOAD) {
          messages.push(`${file.name} · Cada panorama admite hasta 40 MB.`);
          continue;
        }
        const form = new FormData();
        form.append("file", file);
        try {
          const { data: blob } = await api.post("/tours/panorama", form, { responseType: "blob" });
          const url = URL.createObjectURL(blob);
          urls.current.add(url);
          added.push({
            id: crypto.randomUUID(), blob, url, yaw: 0, links: [],
            name: file.name.replace(/\.[^.]+$/, "").slice(0, 80) || "Panorama",
          });
        } catch (error) {
          let message = apiError(error);
          if (error.response?.data instanceof Blob) {
            const payload = await error.response.data.text();
            try {
              message = JSON.parse(payload).detail || message;
            } catch {
              // A proxy may return an HTML error page.
            }
          }
          messages.push(`${file.name} · ${message}`);
        }
      }

      if (added.length) {
        let next = [...scenes, ...added];
        if (!scenes.length && next.length > 1) {
          setBusy("La IA está organizando el recorrido…");
          try {
            next = await planTour(next);
          } catch (error) {
            next = next.map((scene, index) => ({
              ...scene,
              links: [next[index - 1], next[index + 1]].filter(Boolean).map((target, i) =>
                ({ target: target.id, yaw: i ? 35 : -35, pitch: 0 })),
            }));
            messages.push(`${apiError(error)} Se ha montado un borrador siguiendo el orden de subida.`);
          }
        }
        setScenes(next);
        setSelected(selected || next[0].id);
      }
      setNotice(messages.join("\n"));
    } finally {
      setBusy("");
    }
  }

  async function regenerate() {
    setBusy("La IA está organizando el recorrido…");
    setNotice("");
    try {
      const next = await planTour(scenes);
      setScenes(next);
      setSelected(next[0].id);
    } catch (error) {
      setNotice(apiError(error));
    } finally {
      setBusy("");
    }
  }

  function changeActive(patch) {
    setScenes(current => current.map(scene => scene.id === selected ? { ...scene, ...patch } : scene));
  }

  function changeLink(index, patch) {
    changeActive({ links: active.links.map((link, i) => i === index ? { ...link, ...patch } : link) });
  }

  function moveScene(offset) {
    const next = [...scenes];
    next.splice(activeIndex, 1);
    next.splice(activeIndex + offset, 0, active);
    setScenes(next);
  }

  function removeScene() {
    const next = scenes.filter(scene => scene.id !== selected).map(scene => ({
      ...scene,
      links: scene.links.filter(link => link.target !== selected),
    }));
    URL.revokeObjectURL(active.url);
    urls.current.delete(active.url);
    setScenes(next);
    setSelected(next[0]?.id || null);
  }

  async function download() {
    setBusy("Preparando la descarga…");
    setNotice("");
    try {
      const embedded = await Promise.all(scenes.map(async ({ id, name, blob, yaw, links }) => ({
        id, name, yaw, links, url: await asDataUrl(blob),
      })));
      const html = new Blob([tourDocument(embedded, scenes[0].id)], { type: "text/html;charset=utf-8" });
      const url = URL.createObjectURL(html);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "tour-virtual.html";
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (error) {
      setNotice(error.message);
    } finally {
      setBusy("");
    }
  }

  const available = scenes.filter(scene => scene.id !== selected &&
    !active?.links.some(link => link.target === scene.id));

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <Header />
      <main className="mx-auto max-w-7xl space-y-5 px-4 py-8 sm:px-8">
        <Link to="/app" className="inline-flex items-center gap-2 text-sm text-slate-400 hover:text-white">
          <ArrowLeft size={16} /> Volver al panel
        </Link>
        <header className="flex flex-wrap items-center justify-between gap-4">
          <h1 className="font-display text-3xl font-semibold">Tour virtual</h1>
          <Button disabled={!!busy || !scenes.length} onClick={download} className="gap-2">
            <Download size={16} /> Descargar tour HTML
          </Button>
        </header>
        <div className="flex flex-wrap items-end gap-3">
          <label className="block space-y-2">
            <span className="block text-sm font-medium">Añadir panorámicas 360°</span>
            <Input type="file" accept={FORMATS} multiple disabled={!!busy} onChange={upload} />
          </label>
          <Button variant="outline" disabled={!!busy || scenes.length < 2} onClick={regenerate} className="gap-2" title="Reemplaza los nombres, el orden y los enlaces por una nueva propuesta">
            <Sparkles size={16} /> {scenes.length > 1 ? "Volver a montar con IA" : "Montar con IA"}
          </Button>
        </div>
        <p className="text-sm text-slate-400">
          Panorámicas equirectangulares 2:1 en JPG, PNG, WebP, TIFF, AVIF o HEIC/HEIF.
          Hasta 20 escenas y 40 MB por foto. El montaje con IA envía vistas reducidas al motor configurado. Descarga el tour antes de salir.
        </p>
        {busy && <p role="status" className="flex items-center gap-2"><Loader2 size={16} className="animate-spin" />{busy}</p>}
        {notice && <p role="status" className="whitespace-pre-line rounded-lg bg-amber-950/40 p-3 text-sm text-amber-200">{notice}</p>}
        {active && (
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
            <section>
              <iframe title="Vista previa del tour virtual" srcDoc={preview}
                sandbox="allow-scripts allow-same-origin"
                className="min-h-[370px] w-full rounded-xl border border-slate-800 bg-slate-900"
                style={{ height: "min(65vh, 650px)" }} />
            </section>
            <fieldset disabled={!!busy} className="space-y-4 rounded-xl border border-slate-800 bg-slate-900/60 p-4">
              <legend className="px-2 font-semibold">Editar recorrido</legend>
              <label className="block space-y-1 text-sm">
                <span>Escena a editar</span>
                <select className={field} value={selected} onChange={event => setSelected(event.target.value)}>
                  {scenes.map((scene, index) => <option key={scene.id} value={scene.id}>{index + 1}. {scene.name}</option>)}
                </select>
              </label>
              <label className="block space-y-1 text-sm">
                <span>Nombre de la escena</span>
                <Input maxLength={80} value={active.name} onChange={event => changeActive({ name: event.target.value })} />
              </label>
              <label className="block space-y-1 text-sm">
                <span>Orientación inicial ({active.yaw}°)</span>
                <input className="w-full" type="range" min="-180" max="180" value={active.yaw}
                  onChange={event => changeActive({ yaw: Number(event.target.value) })} />
              </label>
              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="outline" size="sm" disabled={scenes[0].id === selected}
                  onClick={() => setScenes([active, ...scenes.filter(scene => scene.id !== selected)])}>
                  Fijar como inicio
                </Button>
                <Button type="button" variant="outline" size="sm" disabled={activeIndex === 0}
                  onClick={() => moveScene(-1)}>Subir</Button>
                <Button type="button" variant="outline" size="sm" disabled={activeIndex === scenes.length - 1}
                  onClick={() => moveScene(1)}>Bajar</Button>
                <Button type="button" variant="ghost" size="sm" onClick={removeScene}>Quitar escena</Button>
              </div>
              <h2 className="font-semibold">Puntos de navegación</h2>
              {active.links.map((link, index) => (
                <div key={link.target} className="space-y-2 rounded-lg border border-slate-700 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm">{scenes.find(scene => scene.id === link.target)?.name}</span>
                    <Button type="button" variant="ghost" size="sm"
                      onClick={() => changeActive({ links: active.links.filter(item => item.target !== link.target) })}>Quitar</Button>
                  </div>
                  <label className="block space-y-1 text-sm">
                    <span>Horizontal ({Math.round(link.yaw)}°)</span>
                    <input className="w-full" type="range" min="-180" max="180" value={Math.round(link.yaw)}
                      onChange={event => changeLink(index, { yaw: angle(event.target.value, 180) })} />
                  </label>
                  <label className="block space-y-1 text-sm">
                    <span>Vertical ({Math.round(link.pitch)}°)</span>
                    <input className="w-full" type="range" min="-85" max="85" value={Math.round(link.pitch)}
                      onChange={event => changeLink(index, { pitch: angle(event.target.value, 85) })} />
                  </label>
                </div>
              ))}
              <select aria-label="Añadir enlace a otra escena" className={field} value="" disabled={!available.length}
                onChange={event => changeActive({ links: [...active.links, { target: event.target.value, yaw: active.yaw, pitch: 0 }] })}>
                <option value="" disabled>Añadir enlace a otra escena</option>
                {available.map(scene => <option key={scene.id} value={scene.id}>{scene.name}</option>)}
              </select>
            </fieldset>
          </div>
        )}
      </main>
    </div>
  );
}
