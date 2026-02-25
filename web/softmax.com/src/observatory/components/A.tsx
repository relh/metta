import clsx from "clsx";
import { ComponentProps, FC } from "react";

export const A: FC<ComponentProps<"a">> = ({
  className,
  children,
  ...props
}) => {
  return (
    <a
      {...props}
      className={clsx(
        className,
        "text-blue-600 no-underline hover:underline dark:text-blue-400",
      )}
    >
      {children}
    </a>
  );
};
