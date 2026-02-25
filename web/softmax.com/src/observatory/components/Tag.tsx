import { FC, PropsWithChildren } from "react";

export const Tag: FC<PropsWithChildren> = ({ children }) => {
  return (
    <span className="rounded border border-blue-300 bg-blue-50 px-2 py-0.5 text-xs leading-none text-blue-700 dark:border-blue-700 dark:bg-blue-950 dark:text-blue-300">
      {children}
    </span>
  );
};
