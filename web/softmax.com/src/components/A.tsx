export const linkClassName =
  "text-decoration-none text-[#4a5f8c] transition-colors duration-200 visited:text-[#4a5f8c] hover:text-[#1a3875] hover:underline";

export const A = (props: React.ComponentProps<"a">) => {
  return <a {...props} className={linkClassName} />;
};
