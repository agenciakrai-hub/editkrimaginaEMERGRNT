import { useState } from "react";
import { Sun, Cloud, Upload, Trash2, Eraser, Wand2, Brush, Check, Undo2, ScanSearch, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";

const inputCls = "w-full accent-primary";

export default function SkyReplacerPanel({
  photoMode,
  onPhotoModeChange,
  mode,
  onModeChange,
  tolerance,
  onToleranceChange,
  brush,
  onBrushChange,
  selectionCount,
  onClearSelection,
  onUndo,
  canUndo,
  onAutoDetectGlass,
  detecting,
  catalog,
  selectedSkyId,
  onSelectSky,
  onAddSky,
  onRemoveSky,
  onApply,
  applying,
  skyLayer,
  onSkyAdjust,
}) {
  const [uploading, setUploading] = useState(false);

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      await onAddSky(file);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="p-3 space-y-4 text-sm">
      <div>
        <h3 className="font-heading font-semibold text-base flex items-center gap-2">
          <Cloud className="w-4 h-4 text-primary" /> Reemplazo de cielos
        </h3>
        <p className="text-xs text-muted-foreground mt-1">
          Detecta solo el cristal o el cielo y conserva los bastidores.
        </p>
      </div>

      {/* Tipo de foto */}
      <div>
        <label className="block text-xs font-medium text-muted-foreground mb-1.5">Tipo de foto</label>
        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={() => onPhotoModeChange("exterior")}
            className={`flex items-center justify-center gap-1.5 px-2 py-2 rounded-lg border text-xs font-medium transition-colors ${
              photoMode === "exterior" ? "border-primary bg-primary/10 text-primary" : "border-border hover:bg-secondary"
            }`}
          >
            <Sun className="w-3.5 h-3.5" /> Exterior (cielo)
          </button>
          <button
            onClick={() => onPhotoModeChange("interior")}
            className={`flex items-center justify-center gap-1.5 px-2 py-2 rounded-lg border text-xs font-medium transition-colors ${
              photoMode === "interior" ? "border-primary bg-primary/10 text-primary" : "border-border hover:bg-secondary"
            }`}
          >
            <Cloud className="w-3.5 h-3.5" /> Interior (ventana)
          </button>
        </div>
        <p className="text-[11px] text-muted-foreground mt-1.5">
          {photoMode === "exterior"
            ? "Haz clic sobre el cielo para seleccionarlo."
            : "Haz clic sobre el cristal de cada ventana para seleccionarlo."}
        </p>
      </div>

      {/* Modo: detectar / refinar */}
      <div>
        <label className="block text-xs font-medium text-muted-foreground mb-1.5">Modo</label>
        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={() => onModeChange("detect")}
            className={`flex items-center justify-center gap-1.5 px-2 py-2 rounded-lg border text-xs font-medium transition-colors ${
              mode === "detect" ? "border-primary bg-primary/10 text-primary" : "border-border hover:bg-secondary"
            }`}
          >
            <Wand2 className="w-3.5 h-3.5" /> Detectar
          </button>
          <button
            onClick={() => onModeChange("refine")}
            className={`flex items-center justify-center gap-1.5 px-2 py-2 rounded-lg border text-xs font-medium transition-colors ${
              mode === "refine" ? "border-primary bg-primary/10 text-primary" : "border-border hover:bg-secondary"
            }`}
          >
            <Brush className="w-3.5 h-3.5" /> Refinar
          </button>
        </div>
      </div>

      {mode === "detect" ? (
        <div className="space-y-2">
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1.5">
              Tolerancia de color: {tolerance}
            </label>
            <input
              type="range"
              min={4}
              max={96}
              value={tolerance}
              onChange={(e) => onToleranceChange(Number(e.target.value))}
              className={inputCls}
            />
            <p className="text-[11px] text-muted-foreground mt-1">
              Más alto = selección más amplia. La detección respeta los marcos de las ventanas y puedes hacer clic en varias zonas para sumar.
            </p>
          </div>
          <Button
            variant="default"
            size="sm"
            className="w-full"
            onClick={onAutoDetectGlass}
            disabled={detecting}
          >
            {detecting ? (
              <span className="inline-block w-3.5 h-3.5 border-2 border-primary-foreground border-t-transparent rounded-full animate-spin mr-1.5" />
            ) : (
              <Sparkles className="w-3.5 h-3.5 mr-1.5" />
            )}
            {detecting
              ? "Detectando con IA…"
              : photoMode === "interior"
              ? "Detectar cristal con IA · 1 crédito"
              : "Detectar cielo con IA · 1 crédito"}
          </Button>
          <p className="text-[11px] text-muted-foreground">
            Detección con el proveedor seleccionado en administración. Si ya elegiste un cielo del catálogo, se aplicará directamente.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1.5">
              Tamaño del pincel: {brush.size}
            </label>
            <input
              type="range"
              min={8}
              max={240}
              value={brush.size}
              onChange={(e) => onBrushChange({ ...brush, size: Number(e.target.value) })}
              className={inputCls}
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <button
              onClick={() => onBrushChange({ ...brush, mode: "add" })}
              className={`px-2 py-2 rounded-lg border text-xs font-medium transition-colors ${
                brush.mode === "add" ? "border-primary bg-primary/10 text-primary" : "border-border hover:bg-secondary"
              }`}
            >
              + Añadir
            </button>
            <button
              onClick={() => onBrushChange({ ...brush, mode: "remove" })}
              className={`px-2 py-2 rounded-lg border text-xs font-medium transition-colors ${
                brush.mode === "remove" ? "border-primary bg-primary/10 text-primary" : "border-border hover:bg-secondary"
              }`}
            >
              − Quitar
            </button>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground whitespace-nowrap">
          Selección: {selectionCount.toLocaleString("es-ES")} px
        </span>
        <div className="flex items-center gap-1">
          <Button
            size="sm"
            variant="ghost"
            onClick={onUndo}
            disabled={!canUndo}
            className="h-7 text-xs"
            title="Deshacer (⌘Z / Ctrl+Z)"
          >
            <Undo2 className="w-3.5 h-3.5 mr-1" /> Deshacer
          </Button>
          <Button size="sm" variant="ghost" onClick={onClearSelection} className="h-7 text-xs">
            <Eraser className="w-3.5 h-3.5 mr-1" /> Limpiar
          </Button>
        </div>
      </div>

      {/* Catálogo de cielos */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="block text-xs font-medium text-muted-foreground">Catálogo de cielos</label>
          <label className="cursor-pointer">
            <input type="file" accept="image/*" className="hidden" onChange={handleFile} />
            <span className="inline-flex items-center gap-1 text-xs text-primary hover:underline">
              {uploading ? (
                <span className="inline-block w-3.5 h-3.5 border-2 border-primary border-t-transparent rounded-full animate-spin" />
              ) : (
                <Upload className="w-3.5 h-3.5" />
              )}
              Añadir
            </span>
          </label>
        </div>
        {catalog.length === 0 ? (
          <p className="text-[11px] text-muted-foreground p-3 rounded-lg border border-dashed border-border text-center">
            Sube tus propios cielos para crear el catálogo.
          </p>
        ) : (
          <div className="grid grid-cols-3 gap-1.5">
            {catalog.map((s) => (
              <div key={s.id} className="relative group">
                <button
                  onClick={() => onSelectSky(s.id)}
                  className={`block w-full aspect-video overflow-hidden rounded-md border-2 transition-colors ${
                    selectedSkyId === s.id ? "border-primary" : "border-transparent hover:border-border"
                  }`}
                  title={s.name}
                >
                  <img src={s.url} alt={s.name} className="w-full h-full object-cover" />
                </button>
                <button
                  onClick={() => onRemoveSky(s.id)}
                  className="absolute top-0.5 right-0.5 p-1 rounded bg-black/60 text-white opacity-0 group-hover:opacity-100 transition-opacity"
                  title="Eliminar"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <Button
        className="w-full"
        onClick={onApply}
        disabled={applying || selectionCount === 0 || !selectedSkyId}
      >
        {applying ? (
          <span className="inline-block w-4 h-4 border-2 border-primary-foreground border-t-transparent rounded-full animate-spin mr-2" />
        ) : (
          <Check className="w-4 h-4 mr-1" />
        )}
        Reemplazar exterior
      </Button>

      {skyLayer && onSkyAdjust && (
        <div className="space-y-3 pt-3 border-t border-border">
          <p className="text-xs font-medium text-muted-foreground">Ajustes del cielo añadido</p>
          <div>
            <label className="block text-xs text-muted-foreground mb-1.5">
              Opacidad: {Math.round((skyLayer.opacity ?? 1) * 100)}%
            </label>
            <input
              type="range"
              min={0}
              max={100}
              value={Math.round((skyLayer.opacity ?? 1) * 100)}
              onChange={(e) => onSkyAdjust("opacity", Number(e.target.value) / 100)}
              className={inputCls}
            />
          </div>
          <div>
            <label className="block text-xs text-muted-foreground mb-1.5">
              Desenfoque: {(skyLayer.blur || 0).toFixed(1)} px
            </label>
            <input
              type="range"
              min={0}
              max={20}
              step={0.5}
              value={skyLayer.blur || 0}
              onChange={(e) => onSkyAdjust("blur", Number(e.target.value))}
              className={inputCls}
            />
            <p className="text-[11px] text-muted-foreground mt-1">
              Desvanece y desenfoca el cielo para integrarlo con la escena.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}