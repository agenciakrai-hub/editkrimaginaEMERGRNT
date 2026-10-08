import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import BeforeAfterSlider from "./HdrBeforeAfterSlider";

export default function ComparisonDialog({ result, onClose }) {
  return (
    <Dialog open={!!result} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-5xl p-0 overflow-hidden bg-gray-950 border-gray-800">
        <DialogHeader className="px-4 pt-4">
          <DialogTitle className="text-sm">Comparación — Escena {result ? result.index + 1 : ""}</DialogTitle>
        </DialogHeader>
        {result && (
          <BeforeAfterSlider
            originalUrl={result.originalUrl}
            editedUrl={result.url}
            order={result.index + 1}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}