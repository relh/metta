import type { MDXComponents } from "mdx/types";

import { A } from "./components/A";
import { H2 } from "./components/H2";
import { P } from "./components/P";
import { ScrollToButton } from "./components/ScrollToButton";
import { UL } from "./components/UL";
import { Waveform } from "./components/Waveform";

export const commonMdxComponents: MDXComponents = {
  Waveform,
  // default typography
  // it can be overridden for blog posts (different heading styles)
  p: P,
  a: A,
  h2: H2,
  ul: UL,
  ScrollToButton,
};

export function useMDXComponents(): MDXComponents {
  return commonMdxComponents;
}
