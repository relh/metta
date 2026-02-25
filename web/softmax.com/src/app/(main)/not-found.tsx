import clsx from "clsx";
import Link from "next/link";

import { Container } from "@/components/Container";

export default function NotFound() {
  return (
    <Container>
      <div className="mx-auto flex min-h-[60vh] flex-col items-center justify-center py-20 text-center">
        <h1 className="mb-4 text-6xl font-bold text-[#0e2758] lowercase">
          404
        </h1>
        <h2 className="mb-6 text-2xl text-[#4a5f8c] lowercase">
          page not found
        </h2>
        <p className="mb-8 text-[#666]">
          the page you're looking for doesn't exist
        </p>
        <Link
          href="/"
          className={clsx(
            "rounded-lg border-2 border-[#0e2758] bg-[#0e2758]",
            "px-6 py-2",
            "font-semibold text-[#fffdf4]! transition-all hover:-translate-y-1 hover:bg-[#1a3875] hover:no-underline hover:shadow-lg",
          )}
        >
          return home
        </Link>
      </div>
    </Container>
  );
}
