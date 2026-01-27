import Link from "next/link";
import { FC } from "react";

import { linkClassName } from "./A";

export const StyledLink: FC<
  React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }
> = (props) => <Link {...props} className={linkClassName} />;
