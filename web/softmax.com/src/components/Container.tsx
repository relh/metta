import { FC, PropsWithChildren } from "react";

export const Container: FC<PropsWithChildren> = ({ children }) => {
  return (
    <div className="w-full max-w-[1200px] px-4 pt-4 xs:px-6 md:px-4">
      {children}
    </div>
  );
};
