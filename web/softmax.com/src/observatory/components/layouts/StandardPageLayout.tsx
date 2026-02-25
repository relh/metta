import { FC, PropsWithChildren } from "react";

export const StandardPageLayout: FC<PropsWithChildren> = ({ children }) => {
  return <div className="mx-auto max-w-6xl space-y-6 p-6">{children}</div>;
};
