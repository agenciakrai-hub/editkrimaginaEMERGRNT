import { Check } from "lucide-react";

export default function BatchFilmstrip({ images, currentIndex, editedIds, onSelect }) {
  return (
    <div className="shrink-0 h-20 border-t border-border bg-card overflow-x-auto scrollbar-thin">
      <div className="flex items-center gap-1.5 h-full px-2">
        {images.map((img, i) => (
          <button
            key={img.id}
            onClick={() => onSelect(i)}
            className={`relative shrink-0 h-16 w-16 rounded-md overflow-hidden border-2 transition-colors ${
              i === currentIndex ? "border-primary" : "border-transparent hover:border-border"
            }`}
          >
            <img src={img.url} className="w-full h-full object-cover" alt="" />
            <span className="absolute bottom-0 left-0 right-0 text-[9px] text-center bg-black/60 text-white py-0.5">{i + 1}</span>
            {editedIds.has(img.id) && (
              <span className="absolute top-0 right-0 bg-primary text-primary-foreground rounded-bl px-1">
                <Check className="w-2.5 h-2.5" />
              </span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}