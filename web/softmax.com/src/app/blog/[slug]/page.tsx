import { Metadata } from "next";

import { Container } from "@/components/Container";
import { DraftBadge } from "@/components/DraftBadge";
import { StyledLink } from "@/components/StyledLink";

import { BlogPostMeta } from "../BlogPostMeta";
import { getPost, getSortedPosts } from "../utils";

export default async function BlogPostPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const post = await getPost(slug);

  return (
    <Container>
      <article className="mt-24">
        <header className="mb-12">
          <h1 className="mt-12 mb-2 text-[2.4em]/12 font-bold text-[#0E2758] md:text-[3em]/14">
            {post.frontmatter.title}
            {post.frontmatter.subtitle && `: ${post.frontmatter.subtitle}`}
            {post.frontmatter.isDraft && <DraftBadge />}
          </h1>
          <BlogPostMeta post={post} boldAuthor />
        </header>

        <div>{post.content}</div>
      </article>

      <div className="mt-12 mb-40">
        <div className="flex justify-center font-mono">
          <StyledLink href="/blog">← Back to all posts</StyledLink>
        </div>
      </div>
    </Container>
  );
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const post = await getPost(slug);
  return {
    title: post.frontmatter.title,
  };
}

export async function generateStaticParams() {
  const posts = await getSortedPosts();
  return posts.map((post) => ({ slug: post.slug }));
}
