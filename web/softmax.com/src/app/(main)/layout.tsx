import "./globals.css";

import type { Metadata } from "next";
import { PropsWithChildren } from "react";

import { SiteFooter } from "./SiteFooter";

export const metadata: Metadata = {
  title: "Softmax - Scaling alignment",
};

export default function RootLayout({ children }: PropsWithChildren) {
  return (
    <html lang="en">
      <body className="flex min-h-screen flex-col items-center bg-[#fffdf4] leading-[1.6]">
        {children}
        <SiteFooter />
      </body>
    </html>
  );
}
