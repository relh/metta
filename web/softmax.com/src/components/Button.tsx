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
        "rounded-lg border-2 border-softblue-900",
        "text-sm font-semibold tracking-[0.06em] uppercase",
        "px-6 py-[0.6rem] transition-all duration-150 ease-in-out",
        // cursor and animation on hover if not disabled
        disabled
          ? "cursor-not-allowed opacity-60"
          : "cursor-pointer hover:-translate-y-px hover:shadow-button",
        // themes
        theme === "primary" &&
          "bg-softblue-900 text-[#fffdf4] hover:bg-softblue-800",
        theme === "outline" &&
          "bg-transparent text-softblue-900 hover:border-softblue-800 hover:text-softblue-800",
      )}
    >
      {children}
    </button>
  );
};
