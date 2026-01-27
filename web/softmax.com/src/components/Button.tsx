import clsx from "clsx";
import { FC, PropsWithChildren } from "react";

export const Button: FC<
  PropsWithChildren<{
    onClick?: () => void;
    theme?: "primary" | "outline";
    type?: "button" | "submit";
    disabled?: boolean;
  }>
> = ({
  onClick,
  children,
  theme = "outline",
  type = "button",
  disabled = false,
}) => {
  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      className={clsx(
        "inline-flex items-center justify-center",
        "rounded-lg border-2 border-[#0e2758]",
        "text-sm font-semibold tracking-[0.06em] uppercase",
        "px-[1.5rem] py-[0.6rem] transition-all duration-150 ease-in-out",
        // cursor and animation on hover if not disabled
        disabled
          ? "cursor-not-allowed opacity-60"
          : "cursor-pointer hover:-translate-y-px hover:shadow-button",
        // themes
        theme === "primary" && "bg-[#0e2758] text-[#fffdf4] hover:bg-[#1a3875]",
        theme === "outline" &&
          "bg-transparent text-[#0e2758] hover:border-[#1a3875] hover:text-[#1a3875]",
      )}
    >
      {children}
    </button>
  );
};
