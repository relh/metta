import clsx from "clsx";
import { FC, PropsWithChildren } from "react";

import { HeroLayout } from "@/components/HeroLayout";
import { S3_IMAGE_BASE } from "@/lib/constants";

import About from "./about.mdx";

export const metadata = {
  title: "Softmax - About",
};

const CollaboratorsList: FC<PropsWithChildren> = ({ children }) => {
  return (
    <div
      className={clsx(
        "[&_ul]:!m-0 [&_ul]:!p-0", // reset mdx ul styles
        "[&_li]:mb-[15px] [&_ul]:list-inside", // better spacing
        "[&_ul]:gap-10 sm:[&_ul]:columns-2", // multi-column layout for larger screens
      )}
    >
      {children}
    </div>
  );
};

export default function AboutPage() {
  return (
    <HeroLayout image={`${S3_IMAGE_BASE}/cellularity.png`}>
      <About components={{ CollaboratorsList }} />
    </HeroLayout>
  );
}
