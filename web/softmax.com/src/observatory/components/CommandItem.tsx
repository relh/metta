import clsx from "clsx";
import { FC, useState } from "react";

import { SmallHeader } from "./SmallHeader";

type CommandItemProps = {
  label: string;
  command: string;
  buttonLabel?: string;
};

export const CommandItem: FC<CommandItemProps> = ({
  label,
  command,
  buttonLabel = "Copy",
}) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (
      typeof navigator === "undefined" ||
      typeof navigator.clipboard === "undefined"
    ) {
      return;
    }
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 1000);
    } catch (error) {
      console.error("Failed to copy to clipboard:", error);
    }
  };

  return (
    <div className="flex flex-col">
      <SmallHeader>{label}</SmallHeader>
      <button
        type="button"
        className={clsx(
          "flex items-center gap-3 rounded-md border px-3 py-2 text-left font-mono",
          "cursor-pointer transition-colors",
          copied
            ? "border-blue-700 bg-indigo-50 dark:bg-indigo-950"
            : "bg-surface-alt hover:border-border-strong border-blue-200 dark:border-blue-800",
        )}
        onClick={handleCopy}
      >
        <code className="text-foreground flex-1 text-xs wrap-break-word">
          {command}
        </code>
        <span className="text-xs font-semibold whitespace-nowrap text-blue-700 dark:text-blue-400">
          {copied ? "Copied!" : buttonLabel}
        </span>
      </button>
    </div>
  );
};
