import { api, fileUrl, apiError } from "@/lib/api";

export const readDataUrl = (blob) => new Promise((resolve, reject) => {
  const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(blob);
});
export async function saveStudioPhoto(projectId, blob, name = "Edición manual.jpg") {
  if (!projectId) throw new Error("Selecciona una propiedad donde guardar la copia.");
  const form = new FormData(); form.append("files", new File([blob], name, { type: blob.type || "image/jpeg" }));
  const { data } = await api.post(`/properties/${projectId}/photos`, form);
  return data[0];
}
export async function studioAi(tool, blob, mode = "exterior") {
  const form = new FormData(); form.append("file", blob, "photo.jpg"); form.append("mode", mode);
  try {
    const { data } = await api.post(`/tools/${tool}/assist`, form, { responseType: "blob" });
    return data;
  } catch (error) {
    if (error.response?.data instanceof Blob) {
      try { const body = JSON.parse(await error.response.data.text()); throw new Error(body.detail || "La IA no pudo completar la operación."); }
      catch (parsed) { if (parsed instanceof SyntaxError) throw new Error("La IA no pudo completar la operación."); throw parsed; }
    }
    throw new Error(apiError(error));
  }
}
// Compatibility limited to the imported studio modules. Uses this app's authenticated API.
export const studioApi = {
  entities: {
    Project: {
      list: async () => (await api.get("/properties")).data,
      create: async (value) => (await api.post("/properties", { name: value.name, address: "" })).data,
    },
    Photo: { create: async (value) => saveStudioPhoto(value.project_id, await (await fetch(value.processed_image)).blob(), "edicion-manual.jpg") },
    MediaAsset: { create: async (value) => saveStudioPhoto(value.project_id, await (await fetch(value.url)).blob(), "fusion-hdr.jpg") },
    EditingImage: {
      filter: async ({ job_id }) => (await api.get(`/properties/${job_id}/photos`)).data.map((p, i) => ({ ...p, status: "completed", edited_url: fileUrl(p.current_path || p.original_path), order: i })),
      update: async (id, value) => { const p = (await api.get(`/photos/${id}`)).data; return saveStudioPhoto(p.property_id, await (await fetch(value.edited_url)).blob(), "edicion-manual.jpg"); },
    },
  },
  integrations: { Core: { UploadFile: async ({ file }) => ({ file_url: await readDataUrl(file) }) } },
};
