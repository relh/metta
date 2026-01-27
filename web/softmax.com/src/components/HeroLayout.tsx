import clsx from "clsx";
import Image from "next/image";
import { FC, PropsWithChildren, ReactNode } from "react";

import { Container } from "./Container";

const HeroSentence: FC<{ text: string }> = ({ text }) => {
  return (
    <div
      className={clsx(
        "px-8 text-center leading-[1.1] font-bold tracking-[-0.03em] text-[#fffdf4] lowercase",
        "text-[2.2rem]",
        "xs:text-[2.8rem]",
        "sm:text-[3.5rem]",
        "md:text-[7.5rem]",
      )}
    >
      {text}
    </div>
  );
};

const HeroBackground = ({
  image,
  fade = false,
  children,
}: PropsWithChildren<{
  image: string;
  fade?: boolean;
}>) => {
  return (
    <div
      // Hero image starts from top of the page, its top part is obscured by the semi-transparent header.
      // Because the header participates in the normal flow, and we don't want to hardcode its height here,
      // we position the hero image absolutely.
      // (This adds some extra complexity, TODO - refactor?)
      className={clsx(
        "absolute top-0 left-0 -z-1 w-full bg-cover bg-center bg-no-repeat",
        "h-[40vh] xs:h-[45vh] sm:h-[60vh] md:h-[80vh]",
      )}
    >
      <Image
        src={image}
        alt=""
        fill
        sizes="100vw"
        quality={100}
        style={{
          objectFit: "cover",
        }}
      />
      {fade && (
        /* Add gradient overlay that fades to background color */
        <div
          className="absolute bottom-0 left-0 h-[35%] w-full"
          style={{
            background: `linear-gradient(
                to bottom,
                rgba(255, 253, 244, 0) 0%,
                rgba(255, 253, 244, 0.5) 50%,
                rgba(255, 253, 244, 1) 100%
            )`,
          }}
        />
      )}
      {children}
    </div>
  );
};

export const HeroLayout: FC<
  PropsWithChildren<{
    image: string;
    heroContent?: ReactNode;
    fade?: boolean;
    sentence?: string;
  }>
> = ({ image, heroContent, fade, sentence, children }) => {
  return (
    <div className="flex w-full flex-col items-center">
      <HeroBackground image={image} fade={fade} />

      <div className="grid h-[30vh] w-full place-items-center xs:h-[35vh] sm:h-[50vh] md:h-[60vh]">
        {heroContent}
        {sentence && <HeroSentence text={sentence} />}
      </div>

      <div className="mb-24 w-full max-w-[1200px] rounded-sm bg-[#fffdf4]">
        <Container>{children}</Container>
      </div>
    </div>
  );
};
