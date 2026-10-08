import { Slider } from "@/components/ui/slider";
import { Button } from "@/components/ui/button";

const GROUPS = [
  {
    title: "Luz",
    items: [
      { key: "exposure", label: "Exposición" },
      { key: "contrast", label: "Contraste" },
      { key: "highlights", label: "Altas luces" },
      { key: "shadows", label: "Sombras" },
      { key: "whites", label: "Blancos" },
      { key: "blacks", label: "Negros" },
    ],
  },
  {
    title: "Color",
    items: [
      { key: "temperature", label: "Temperatura" },
      { key: "saturation", label: "Saturación" },
      { key: "vibrance", label: "Vibrancia" },
    ],
  },
];

function AdjustmentSlider({ label, value, onChange }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">{label}</span>
        <span className="text-xs font-mono text-foreground/70">{value > 0 ? "+" : ""}{value}</span>
      </div>
      <Slider value={[value]} onValueChange={([v]) => onChange(v)} min={-100} max={100} step={1} />
    </div>
  );
}

export default function AdjustmentsPanel({ layer, onChange, onReset }) {
  if (!layer) return <p className="text-xs text-muted-foreground p-4">Selecciona una capa</p>;
  return (
    <div className="p-3 space-y-4">
      {GROUPS.map((group) => (
        <div key={group.title} className="space-y-2.5">
          <h3 className="text-[11px] font-semibold text-foreground/80 uppercase tracking-wide">{group.title}</h3>
          {group.items.map((item) => (
            <AdjustmentSlider
              key={item.key}
              label={item.label}
              value={layer.adjustments[item.key] || 0}
              onChange={(v) => onChange(item.key, v)}
            />
          ))}
        </div>
      ))}
      <Button variant="outline" size="sm" className="w-full" onClick={onReset}>Restablecer ajustes</Button>
    </div>
  );
}