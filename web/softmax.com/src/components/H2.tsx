import { ComponentProps, FC } from "react";

export const H2: FC<ComponentProps<"h2">> = ({ className, ...props }) => {
  return (
    <h2
      {...props}
      className={`mt-0 mb-0 text-[2.2rem] font-bold text-[#0E2758]${className ? ` ${className}` : ""}`}
    />
  );
};
