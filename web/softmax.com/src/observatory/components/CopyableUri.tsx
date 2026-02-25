"use client";
import clsx from "clsx";
import { FC, useState } from "react";

type CopyableUriProps = {
  uri: string;
  label?: string;
};

export const CopyableUri: FC<CopyableUriProps> = ({ uri, label = "Copy" }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (
      typeof navigator === "undefined" ||
      typeof navigator.clipboard === "undefined"
    ) {
      return;
    }
    try {
      await navigator.clipboard.writeText(uri);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      console.error("Failed to copy to clipboard:", error);
    }
  };

  return (
    <button
      type="button"
      onClick={handleCopy}
      className={clsx(
        "bg-surface flex items-center gap-3 rounded border px-3 py-2 text-left font-mono text-sm",
        "w-full max-w-xl cursor-pointer transition-colors",
        copied
          ? "border-blue-500 bg-blue-50 dark:bg-blue-950"
          : "border-border-strong bg-surface-alt hover:border-foreground-muted",
      )}
    >
      <code className="text-foreground flex-1 text-xs break-all">{uri}</code>
      <span
        className={clsx(
          "text-xs font-semibold whitespace-nowrap",
          copied ? "text-blue-600 dark:text-blue-400" : "text-foreground-muted",
        )}
      >
        {copied ? "Copied!" : label}
      </span>
    </button>
  );
};
