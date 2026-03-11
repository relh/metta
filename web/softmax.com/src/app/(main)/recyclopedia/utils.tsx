import "server-only";

import { MDXComponents } from "mdx/types";
import { z } from "zod";

import {
  getMdxCollection,
  getMdxDocument,
  MdxDocument,
} from "@/lib/mdxCollection";

const relatedLinkSchema = z.object({
  label: z.string(),
  href: z.string(),
});

const noteSchema = z.object({
  title: z.string(),
  snippet: z.string().optional(),
  excerpt: z.string().optional(),
  author: z.string(),
  date: z.iso.date(),
  period: z.string().optional(),
  listDate: z.string().optional(),
  related: z.array(relatedLinkSchema).optional(),
  featured: z.boolean().optional(),
  isDraft: z.boolean().optional(),
});

export type Note = MdxDocument<typeof noteSchema>;

const noteMdxComponents: MDXComponents = {
  p: ({ children }) => <p>{children}</p>,
  a: ({ href, children }) => <a href={href ?? "#"}>{children}</a>,
  h2: ({ children }) => <h2>{children}</h2>,
  h3: ({ children }) => <h3>{children}</h3>,
  ul: ({ children }) => <ul>{children}</ul>,
  ol: ({ children }) => <ol>{children}</ol>,
  blockquote: ({ children }) => <blockquote>{children}</blockquote>,
  pre: ({ children }) => <pre>{children}</pre>,
  code: ({ children }) => <code>{children}</code>,
  aside: ({ children }) => <aside>{children}</aside>,
};

export function formatListDate(note: Note): string {
  if (note.frontmatter.listDate) {
    return note.frontmatter.listDate;
  }

  return new Date(`${note.frontmatter.date}T00:00:00`).toLocaleDateString(
    "en-US",
    {
      month: "short",
      year: "numeric",
    },
  );
}

export async function getSortedNotes(): Promise<Note[]> {
  const notes = await getMdxCollection({
    dir: "src/app/(main)/recyclopedia/notes",
    schema: noteSchema,
    components: noteMdxComponents,
  });

  const showDrafts = process.env.NODE_ENV === "development";

  return notes
    .filter((note) => !note.frontmatter.isDraft || showDrafts)
    .sort(
      (a, b) =>
        new Date(b.frontmatter.date).getTime() -
        new Date(a.frontmatter.date).getTime(),
    );
}

export async function getNote(slug: string): Promise<Note> {
  return await getMdxDocument({
    dir: "src/app/(main)/recyclopedia/notes",
    schema: noteSchema,
    slug,
    components: noteMdxComponents,
  });
}
