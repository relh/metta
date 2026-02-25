import { FC, PropsWithChildren } from "react";

export const SmallHeader: FC<PropsWithChildren> = ({ children }) => {
  return (
    <div className="text-foreground-muted mb-1 text-xs font-semibold tracking-wide uppercase">
      {children}
    </div>
  );
};
