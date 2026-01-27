export const P = (props: React.ComponentProps<"p">) => {
  // Paragraph with better typography, for MDX content and other text.
  return (
    <p
      {...props}
      className="my-4 text-justify text-[1.1em] leading-[1.7] first:mt-0 last:mb-0"
    />
  );
};
