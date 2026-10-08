import React, { useState } from "react";
import { fileUrl } from "@/lib/api";
import { ImageOff } from "lucide-react";

/** Image that loads a protected storage path via query-param auth. */
export default function AuthImage({ path, alt = "", className = "", ...rest }) {
  const [errorPath, setErrorPath] = useState(null);
  if (!path || errorPath === path) {
    return (
      <div className={`flex items-center justify-center bg-secondary/50 ${className}`}>
        <ImageOff className="w-6 h-6 text-muted-foreground" />
      </div>
    );
  }
  return (
    <img
      src={fileUrl(path)}
      alt={alt}
      loading="lazy"
      onError={() => setErrorPath(path)}
      className={className}
      {...rest}
    />
  );
}
