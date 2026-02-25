import clsx from "clsx";
import { FC, PropsWithChildren, ReactNode } from "react";

export const Card: FC<
  PropsWithChildren<{
    title?: ReactNode;
    padding?: "sm" | "md";
  }>
> = ({ children, title, padding = "md" }) => {
  return (
    <div className="bg-surface border-border rounded-lg border shadow-sm">
      {title && (
        <div
          className={clsx(
            "border-border flex items-center justify-between border-b py-2",
            padding === "sm" ? "px-3" : "px-5",
          )}
        >
          <div>
            <h2 className="text-foreground my-2 text-2xl font-bold">{title}</h2>
          </div>
        </div>
      )}
      <div className={clsx(padding === "sm" ? "p-3" : "p-5")}>{children}</div>
    </div>
  );
};
