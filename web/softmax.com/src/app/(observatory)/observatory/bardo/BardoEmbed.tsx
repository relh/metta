"use client";

import { useEffect, useState } from "react";

function resolveThemedSrc(src: string): string {
  try {
    const url = new URL(src, window.location.origin);
    const isDark = document.documentElement.classList.contains("dark");
    url.searchParams.set("theme", isDark ? "dark" : "light");
    return url.toString();
  } catch {
    return src;
  }
}

export function BardoEmbed({ src }: { src: string }) {
  const [themedSrc, setThemedSrc] = useState(src);

  useEffect(() => {
    const updateThemedSrc = () => {
      setThemedSrc(resolveThemedSrc(src));
    };

    updateThemedSrc();
    const observer = new MutationObserver(updateThemedSrc);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });

    return () => {
      observer.disconnect();
    };
  }, [src]);

  return (
    <iframe
      title="Policy Bardo"
      src={themedSrc}
      className="bg-background h-full w-full border-0"
      referrerPolicy="no-referrer"
    />
  );
}
