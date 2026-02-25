"use client";
import clsx from "clsx";
import Link from "next/link";
import { FC, ReactNode } from "react";

import { getButtonClassName } from "./Button";

export const LinkButton: FC<{
  href: string;
  children: ReactNode;
  theme?: "primary" | "secondary" | "tertiary";
  type?: "button" | "submit";
  size?: "sm" | "md";
  disabled?: boolean;
}> = ({
  href,
  children,
  theme = "secondary",
  type = "button",
  size = "md",
  disabled = false,
}) => {
  return (
    <Link
      href={disabled ? "#" : href}
      onClick={disabled ? (e) => e.preventDefault() : undefined}
      className={clsx(
        getButtonClassName(size, theme, disabled),
        "no-underline",
      )}
      type={type}
    >
      {children}
    </Link>
  );
};
