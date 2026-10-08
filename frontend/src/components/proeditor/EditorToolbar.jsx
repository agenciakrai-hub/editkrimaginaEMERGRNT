import { Move, Brush, Crop, Cloud } from "lucide-react";

const TOOLS = [
  { id: "move", icon: Move, label: "Mover" },
  { id: "brush", icon: Brush, label: "Pincel" },
  { id: "crop", icon: Crop, label: "Recortar" },
  { id: "sky", icon: Cloud, label: "Cielos / Ventanas" },
];

export default function EditorToolbar({ tool, onToolChange }) {
  return (
    <div className="w-14 shrink-0 flex flex-col items-center gap-1.5 py-3 border-r border-border bg-card">
      {TOOLS.map((t) => {
        const Icon = t.icon;
        const active = tool === t.id;
        return (
          <button
            key={t.id}
            onClick={() => onToolChange(t.id)}
            title={t.label}
            className={`w-10 h-10 rounded-lg flex items-center justify-center transition-colors ${
              active ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-secondary hover:text-foreground"
            }`}
          >
            <Icon className="w-5 h-5" />
          </button>
        );
      })}
    </div>
  );
}