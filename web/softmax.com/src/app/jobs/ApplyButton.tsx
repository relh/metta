import clsx from "clsx";

export const ApplyButton = () => {
  return (
    <a
      href="https://form.asana.com/?k=Bud764ZSBAtkdcbfkI-fHQ&d=1209016784099267"
      className={clsx(
        "inline-block rounded-lg border-2 border-softblue-900 bg-softblue-900",
        "px-6 py-3 text-lg font-semibold tracking-[0.02em] text-[#fffdf4]",
        "shadow-button shadow-softblue-900/20",
        "transition-all duration-300 ease-in-out",
        "hover:-translate-y-[3px] hover:border-softblue-800 hover:bg-softblue-800 hover:shadow-[0_6px_16px_rgba(14,39,88,0.3)]",
        "active:-translate-y-[1px] active:shadow-[0_2px_8px_rgba(14,39,88,0.2)]",
        "font-mono",
      )}
    >
      Apply for this position
    </a>
  );
};
