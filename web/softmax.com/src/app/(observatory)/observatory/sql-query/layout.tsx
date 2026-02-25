import type { Metadata } from "next";
import { PropsWithChildren } from "react";

export const metadata: Metadata = {
  title: "SQL Query | Observatory",
};

export default function Layout({ children }: PropsWithChildren) {
  return children;
}
