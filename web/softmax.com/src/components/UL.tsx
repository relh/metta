import { FC } from "react";

export const UL: FC<React.ComponentProps<"ul">> = (props) => {
  return <ul {...props} className="my-4 list-disc pl-10" />;
};
