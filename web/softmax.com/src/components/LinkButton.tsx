import clsx from "clsx";
import Link from "next/link";
import { FC, PropsWithChildren } from "react";

type Props = PropsWithChildren<{
  href: string;
  theme?: "primary" | "outline";
}>;

export const LinkButton: FC<Props> = ({
  href,
  children,
  theme = "outline",
}) => {
  return (
    <Link
      href={href}
      className={clsx(
        "rounded-md px-[0.6em] py-[0.4em] xs:px-3 xs:py-2",
        "text-[0.9em] font-bold",
        "border border-softblue-400/30",
        "transition-all duration-300 ease-in-out",
        theme === "primary"
          ? "shadow-button shadow-softblue-900/30"
          : "hover:shadow-button hover:shadow-softblue-900/15",
        "hover:underline",
        theme === "primary" && "bg-softblue-900 text-softblue-300",
        theme === "outline" &&
          "bg-softblue-300/20 text-softblue-900 hover:bg-softblue-300/30",
        "hover:translate-y-[-2px]",
      )}
    >
      {children}
    </Link>
  );
};
