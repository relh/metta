import { format } from "date-fns";

import { type Post } from "./utils";

export const BlogPostMeta = ({
  post,
  boldAuthor,
}: {
  post: Post;
  boldAuthor?: boolean;
}) => {
  return (
    <div className="mb-[0.6rem] font-mono text-[0.9em] text-[#666]">
      <span className={boldAuthor ? "font-semibold" : ""}>
        {post.frontmatter.author}
      </span>
      {" • "}
      <time dateTime={post.frontmatter.date}>
        {format(new Date(post.frontmatter.date + "T00:00:00"), "MMMM dd, yyyy")}
      </time>
    </div>
  );
};
