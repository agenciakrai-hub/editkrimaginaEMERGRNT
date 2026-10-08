import { Slider } from "@/components/ui/slider";
import { Button } from "@/components/ui/button";

export default function BrushSettings({ brush, onChange }) {
  return (
    <div className="p-3 border-b border-border space-y-3">
      <div className="space-y-1">
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">Tamaño del pincel</span>
          <span className="text-xs font-mono">{brush.size}px</span>
        </div>
        <Slider value={[brush.size]} onValueChange={([v]) => onChange({ ...brush, size: v })} min={5} max={400} step={1} />
      </div>
      <div className="space-y-1">
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">Dureza</span>
          <span className="text-xs font-mono">{Math.round(brush.hardness * 100)}%</span>
        </div>
        <Slider value={[brush.hardness * 100]} onValueChange={([v]) => onChange({ ...brush, hardness: v / 100 })} min={0} max={100} step={1} />
      </div>
      <div className="flex gap-2">
        <Button size="sm" variant={brush.mode === "hide" ? "default" : "outline"} onClick={() => onChange({ ...brush, mode: "hide" })} className="flex-1">
          Ocultar
        </Button>
        <Button size="sm" variant={brush.mode === "reveal" ? "default" : "outline"} onClick={() => onChange({ ...brush, mode: "reveal" })} className="flex-1">
          Revelar
        </Button>
      </div>
    </div>
  );
}