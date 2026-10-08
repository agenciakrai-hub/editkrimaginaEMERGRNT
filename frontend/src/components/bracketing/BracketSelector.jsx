export default function BracketSelector({ value, onChange, totalFiles }) {
  const scenes = totalFiles > 0 && value > 0 ? Math.floor(totalFiles / value) : 0;
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-gray-400">Exposiciones por escena:</span>
      <div className="flex gap-2">
        {[3, 5].map((n) => (
          <button
            key={n}
            onClick={() => onChange(n)}
            className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${
              value === n
                ? "bg-gradient-to-r from-blue-500 to-cyan-400 text-white"
                : "bg-gray-800 text-gray-400 hover:text-gray-200"
            }`}
          >
            {n}
          </button>
        ))}
      </div>
      {totalFiles > 0 && (
        <span className="text-xs text-cyan-400 ml-2">→ {scenes} escena{scenes !== 1 ? "s" : ""} HDR</span>
      )}
    </div>
  );
}