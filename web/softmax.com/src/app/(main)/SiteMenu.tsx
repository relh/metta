"use client";
import clsx from "clsx";
import Image from "next/image";
import Link from "next/link";
import { FC, useState } from "react";

import softmaxWordmark from "../../../public/Assets/softmax_wordmark.png";
import { SiteMenuLinks } from "./SiteMenuLinks";

const HamburgerLine: FC<{ className: string | boolean }> = ({ className }) => {
  return (
    <div
      className={clsx(
        "block h-[3px] w-full rounded-[3px] bg-[#333] transition-all duration-300 ease-in-out",
        className,
      )}
    />
  );
};

const HamburgerMenu: FC<{
  isOpen: boolean;
  setIsOpen: (isOpen: boolean) => void;
}> = ({ isOpen, setIsOpen }) => {
  return (
    <div
      className={clsx(
        "z-101 cursor-pointer md:hidden",
        "flex h-[24px] w-[30px] flex-col justify-between",
      )}
      onClick={() => setIsOpen(!isOpen)}
    >
      {/* Turn into X cross when open */}
      <HamburgerLine className={isOpen && "translate-y-2.5 rotate-45"} />
      <HamburgerLine className={isOpen && "opacity-0"} />
      <HamburgerLine className={isOpen && "-translate-y-2.5 -rotate-45"} />
    </div>
  );
};

export const SiteMenu: FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  return (
    <header className="relative z-100 w-full bg-[#fffdf4]/90 py-2 backdrop-blur-[5px]">
      <div className="flex items-center justify-between px-8">
        <Link href="/" className="flex items-center">
          <img
            src="/Assets/Softmax brand mark.svg"
            alt="Softmax Logo"
            style={{
              height: 36,
              width: "auto",
              marginRight: 12,
              objectFit: "contain",
            }}
          />
          <Image
            src={softmaxWordmark}
            quality={100}
            alt="Softmax Wordmark"
            style={{ height: 24, width: "auto", objectFit: "contain" }}
          />
        </Link>
        <HamburgerMenu isOpen={isOpen} setIsOpen={setIsOpen} />
        <SiteMenuLinks isOpen={isOpen} />
      </div>
    </header>
  );
};
