import { Eye, EyeOff, Plus, Trash2, Copy, Brush } from "lucide-react";
import { Slider } from "@/components/ui/slider";

export default function LayersPanel({
  layers, activeLayerId, onSelect, onAdd, onDelete, onDuplicate,
  onToggleVisibility, onOpacityChange, onClearMask,
}) {
  return (
    <div className="p-3 space-y-2">
      <button
        onClick={onAdd}
        className="w-full flex items-center justify-center gap-1.5 py-2 rounded-lg border border-dashed border-border text-xs text-muted-foreground hover:text-foreground hover:border-primary/50 transition-colors"
      >
        <Plus className="w-3.5 h-3.5" /> Añadir capa
      </button>
      <div className="space-y-1.5">
        {[...layers].reverse().map((layer) => {
          const active = layer.id === activeLayerId;
          return (
            <div
              key={layer.id}
              onClick={() => onSelect(layer.id)}
              className={`rounded-lg border p-2.5 cursor-pointer transition-colors ${
                active ? "border-primary bg-primary/10" : "border-border bg-card hover:border-border/80"
              }`}
            >
              <div className="flex items-center gap-2">
                <button
                  onClick={(e) => { e.stopPropagation(); onToggleVisibility(layer.id); }}
                  className="text-muted-foreground hover:text-foreground"
                >
                  {layer.visible ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
                </button>
                <span className="text-xs font-medium flex-1 truncate">{layer.name}</span>
                {layer.maskCanvas && <Brush className="w-3.5 h-3.5 text-primary" />}
                <button onClick={(e) => { e.stopPropagation(); onDuplicate(layer.id); }} className="text-muted-foreground hover:text-foreground" title="Duplicar">
                  <Copy className="w-3.5 h-3.5" />
                </button>
                <button onClick={(e) => { e.stopPropagation(); onDelete(layer.id); }} className="text-muted-foreground hover:text-destructive" title="Eliminar">
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
              <div className="mt-2 flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                <span className="text-[10px] text-muted-foreground w-12">Opacidad</span>
                <Slider
                  value={[Math.round(layer.opacity * 100)]}
                  onValueChange={([v]) => onOpacityChange(layer.id, v / 100)}
                  min={0}
                  max={100}
                  step={1}
                />
                <span className="text-[10px] font-mono text-muted-foreground w-8 text-right">{Math.round(layer.opacity * 100)}</span>
              </div>
              {layer.maskCanvas && (
                <button
                  onClick={(e) => { e.stopPropagation(); onClearMask(layer.id); }}
                  className="mt-1.5 text-[10px] text-muted-foreground hover:text-destructive"
                >
                  Limpiar máscara
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}