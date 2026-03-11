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
  snippet: z.string().optional(),
});

export type Post = MdxDocument<typeof postSchema>;

const blogMdxComponents: MDXComponents = {
  h2: ({ children }) => (
    <h2
      style={{
        font: "700 24px/32px 'Merriweather Sans', sans-serif",
        color: "#0E2758",
        margin: "2.5rem 0 0.75rem",
      }}
    >
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3
      style={{
        font: "600 19px/28px 'Merriweather Sans', sans-serif",
        color: "#0E2758",
        margin: "2rem 0 0.5rem",
      }}
    >
      {children}
    </h3>
  ),
  p: ({ children }) => (
    <p
      style={{
        font: "400 18px/32px 'Merriweather', serif",
        margin: "0 0 1.2rem",
        maxWidth: "38rem",
      }}
    >
      {children}
    </p>
  ),
  ul: ({ children }) => (
    <ul
      style={{
        font: "400 18px/32px 'Merriweather', serif",
        margin: "0 0 1.2rem",
        paddingLeft: "1.4rem",
        maxWidth: "38rem",
      }}
    >
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol
      style={{
        font: "400 18px/32px 'Merriweather', serif",
        margin: "0 0 1.2rem",
        paddingLeft: "1.4rem",
        maxWidth: "38rem",
      }}
    >
      {children}
    </ol>
  ),
  blockquote: ({ children }) => (
    <blockquote
      style={{
        borderLeft: "3px solid #e8e4dc",
        margin: "1.5rem 0",
        paddingLeft: "1.2rem",
        color: "#555",
        fontStyle: "italic",
        maxWidth: "38rem",
      }}
    >
      {children}
    </blockquote>
  ),
  hr: () => (
    <hr
      style={{
        border: "none",
        borderTop: "1px solid #e8e4dc",
        margin: "2.5rem 0",
      }}
    />
  ),
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
