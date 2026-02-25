import clsx from "clsx";
import Link, { LinkProps } from "next/link";
import { ComponentProps, FC } from "react";

export const StyledLink: FC<
  LinkProps & ComponentProps<"a"> & { theme?: "normal" | "muted" }
> = ({ className, theme = "normal", ...props }) => (
  <Link
    {...props}
    className={clsx(
      className,
      theme === "normal"
        ? "text-blue-600 no-underline hover:underline dark:text-blue-400"
        : "text-foreground no-underline transition-colors hover:text-blue-600 dark:hover:text-blue-400",
    )}
  />
);
