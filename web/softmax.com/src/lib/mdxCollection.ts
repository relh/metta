import "server-only";

import fs from "fs/promises";
import { MDXComponents } from "mdx/types";
import { compileMDX } from "next-mdx-remote/rsc";
import path from "path";
import { ReactNode } from "react";
import remarkSmartypants from "remark-smartypants";
import z from "zod";

import { commonMdxComponents } from "@/mdx-components";

export type MdxDocument<T extends z.ZodSchema> = {
  frontmatter: z.infer<T>;
  slug: string;
  content: ReactNode;
};

export async function getMdxCollection<T extends z.ZodSchema>({
  dir,
  schema,
  components,
}: {
  dir: string;
  schema: T;
  components?: MDXComponents;
}): Promise<MdxDocument<T>[]> {
  const files = (await fs.readdir(dir)).filter((file) => file.endsWith(".mdx"));
  const items = await Promise.all(
    files.map(async (file) => {
      const slug = file.replace(".mdx", "");
      return await getMdxDocument({ dir, slug, schema, components });
    }),
  );
  return items;
}

export async function getMdxDocument<T extends z.ZodSchema>({
  dir,
  slug,
  schema,
  components,
}: {
  dir: string;
  slug: string;
  schema: T;
  components?: MDXComponents;
}): Promise<MdxDocument<T>> {
  const itemFile = await fs.readFile(path.join(dir, `${slug}.mdx`), "utf-8");
  const { frontmatter, content } = await compileMDX({
    source: itemFile,
    components: {
      ...commonMdxComponents,
      ...components,
    },
    options: {
      parseFrontmatter: true,
      mdxOptions: { remarkPlugins: [remarkSmartypants] },
    },
  });
  const typedFrontmatter = schema.parse(frontmatter);
  return { frontmatter: typedFrontmatter, slug, content };
}
