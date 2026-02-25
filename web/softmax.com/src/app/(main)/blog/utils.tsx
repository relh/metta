import "server-only";

import { MDXComponents } from "mdx/types";
import { z } from "zod";

import {
  getMdxCollection,
  getMdxDocument,
  MdxDocument,
} from "@/lib/mdxCollection";

const postSchema = z.object({
  title: z.string(),
  subtitle: z.string().optional(),
  author: z.string().optional(),
  date: z.iso.date(),
  isDraft: z.boolean().optional(),
});

export type Post = MdxDocument<typeof postSchema>;

const blogMdxComponents: MDXComponents = {
  // I'm not sure if this is useful, but Jekyll version used different heading
  // styles for blog posts.
  // Maybe this can be standardized later.
  h2: (props) => <h2 className="text-[1.75em] font-bold" {...props} />,
};

export async function getSortedPosts(): Promise<Post[]> {
  const posts = await getMdxCollection({
    dir: "src/app/(main)/blog/posts",
    schema: postSchema,
    components: blogMdxComponents,
  });

  const showDrafts = process.env.NODE_ENV === "development";

  return posts
    .filter((post) => !post.frontmatter.isDraft || showDrafts)
    .sort(
      (a, b) =>
        new Date(b.frontmatter.date).getTime() -
        new Date(a.frontmatter.date).getTime(),
    );
}

export async function getPost(slug: string): Promise<Post> {
  return await getMdxDocument({
    dir: "src/app/(main)/blog/posts",
    schema: postSchema,
    slug,
    components: blogMdxComponents,
  });
}
