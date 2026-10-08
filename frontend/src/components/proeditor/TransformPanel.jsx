import { RotateCcw, Crop as CropIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";

const ITEMS = [
  { key: "rotation", label: "Rotación", min: -45, max: 45, suffix: "°" },
  { key: "perspectiveX", label: "Perspectiva horizontal", min: -50, max: 50, suffix: "" },
  { key: "perspectiveY", label: "Perspectiva vertical", min: -50, max: 50, suffix: "" },
];

export default function TransformPanel({ transform, onTransformChange, onResetTransform, onResetCrop }) {
  return (
    <div className="p-3 space-y-4">
      <div className="space-y-3">
        {ITEMS.map((item) => (
          <div key={item.key} className="space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">{item.label}</span>
              <span className="text-xs font-mono text-foreground/70">
                {transform[item.key] || 0}{item.suffix}
              </span>
            </div>
            <Slider
              value={[transform[item.key] || 0]}
              onValueChange={([v]) => onTransformChange({ ...transform, [item.key]: v })}
              min={item.min}
              max={item.max}
              step={1}
            />
          </div>
        ))}
      </div>
      <p className="text-[10px] text-muted-foreground">
        Usa la herramienta Recortar (izquierda) para arrastrar los límites del recorte sobre la imagen.
      </p>
      <div className="flex gap-2">
        <Button variant="outline" size="sm" className="flex-1" onClick={onResetTransform}>
          <RotateCcw className="w-3.5 h-3.5 mr-1.5" /> Transformar
        </Button>
        <Button variant="outline" size="sm" className="flex-1" onClick={onResetCrop}>
          <CropIcon className="w-3.5 h-3.5 mr-1.5" /> Recorte
        </Button>
      </div>
    </div>
  );
}