import clsx from "clsx";
import { FC } from "react";

export const Input: FC<{
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  size?: "sm" | "md";
}> = ({ value, onChange, placeholder, size = "md" }) => {
  return (
    <input
      type="text"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className={clsx(
        "border-border-strong bg-surface text-foreground box-border w-full border",
        "focus:border-blue-500 focus:ring-2 focus:ring-blue-500 focus:outline-none",
        size === "sm" && "rounded-sm px-2 py-1 text-xs",
        size === "md" && "rounded-md px-3 py-2 text-sm",
      )}
    />
  );
};
