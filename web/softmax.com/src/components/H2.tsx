import { ComponentProps, FC } from "react";

export const H2: FC<ComponentProps<"h2">> = (props) => {
  return <h2 {...props} className="text-[2.2rem] font-bold text-[#0E2758]" />;
};
