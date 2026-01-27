import { FC } from "react";

import { A } from "@/components/A";

export const SiteFooter: FC = () => {
  return (
    <footer className="pb-8 text-center">
      <p className="my-[1em]">may we all find alignment - softmax, 2025</p>
      <p className="my-[1em]">
        contact us at{" "}
        <A href="mailto:contact@softmax.com">contact@softmax.com</A>
      </p>
    </footer>
  );
};
