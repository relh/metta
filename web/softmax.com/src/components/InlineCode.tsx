import { FC, PropsWithChildren } from "react";

export const InlineCode: FC<PropsWithChildren> = ({ children }) => {
  return (
    <code className="inline-block rounded-md border border-[#d8d2bf] bg-[#f6f3e4] px-2 text-[#0e2758]">
      {children}
    </code>
  );
};
