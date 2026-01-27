"use client";

import { Button } from "./Button";

type ScrollToButtonProps = {
  targetId: string;
  children: React.ReactNode;
  theme?: "primary" | "outline";
};

export function ScrollToButton({
  targetId,
  children,
  theme = "primary",
}: ScrollToButtonProps) {
  const handleClick = () => {
    const element = document.getElementById(targetId);
    if (element) {
      element.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  return (
    <Button onClick={handleClick} theme={theme}>
      {children}
    </Button>
  );
}
