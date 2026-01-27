"use client";

import clsx from "clsx";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { FC, PropsWithChildren } from "react";

const MenuLink: FC<PropsWithChildren<{ href: string }>> = ({
  href,
  children,
}) => {
  const pageUrl = usePathname();

  const isActive = href === "/" ? pageUrl === href : pageUrl.startsWith(href);
  return (
    <Link
      href={href}
      className={clsx(
        "font-mono",
        "text-[1.2em] md:text-[1.3em]",
        "hover:text-shadow-(--link-text-shadow)",
        isActive
          ? "text-[#859FBE] visited:text-[#859FBE]"
          : "text-[#333] visited:text-[#333]",
      )}
    >
      {children}
    </Link>
  );
};

export const SiteMenuLinks: FC<{ isOpen: boolean }> = ({ isOpen }) => {
  return (
    <nav
      className={clsx(
        // from sm: desktop menu
        "sm:flex sm:items-center sm:gap-6 lg:gap-8",

        // up to sm: mobile menu

        // fix outside of viewport
        "max-md:fixed max-md:top-0 max-md:h-screen max-md:w-[85%] xs:max-md:w-[70%]",
        // slide in
        isOpen ? "max-md:right-0" : "max-md:-right-full",
        "transition-[right] duration-300 ease-in-out",
        // mobile menu styling
        "max-md:bg-[#fffdf4]/97 max-md:backdrop-blur-[10px]",
        "max-md:p-8 max-md:pt-20",
        "max-md:flex max-md:flex-col max-md:gap-6",
        "max-md:shadow-[-5px_0_15px_rgba(0,0,0,0.1)]",
      )}
    >
      <MenuLink href="/">home</MenuLink>
      <MenuLink href="/blog">writing</MenuLink>
      <MenuLink href="/inspiration">inspiration</MenuLink>
      <MenuLink href="/about">team</MenuLink>
      <MenuLink href="/jobs">join us</MenuLink>
    </nav>
  );
};
