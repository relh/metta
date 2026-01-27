import Link from "next/link";

import { DraftBadge } from "@/components/DraftBadge";
import { HeroLayout } from "@/components/HeroLayout";
import { StyledLink } from "@/components/StyledLink";
import { S3_IMAGE_BASE } from "@/lib/constants";

import { BlogPostMeta } from "./BlogPostMeta";
import { getSortedPosts } from "./utils";

export default async function BlogPage() {
  const sortedPosts = await getSortedPosts();

  return (
    <HeroLayout image={`${S3_IMAGE_BASE}/writing.png`}>
      <div className="space-y-12">
        {sortedPosts.map((post) => (
          <div key={post.slug} className="blog-post-card">
            <h2 className="mb-2.5 text-[2em]/10 font-bold">
              <Link
                href={`/blog/${post.slug}`}
                className="text-[#0E2758] hover:underline"
              >
                {post.frontmatter.title}
              </Link>
              {post.frontmatter.isDraft && <DraftBadge />}
            </h2>
            <BlogPostMeta post={post} />
            <div className="font-mono text-[0.9em]">
              <StyledLink href={`/blog/${post.slug}`}>Read more →</StyledLink>
            </div>
          </div>
        ))}
      </div>
    </HeroLayout>
  );
}
