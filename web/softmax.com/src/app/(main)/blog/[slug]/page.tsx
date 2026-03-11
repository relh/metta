import { Metadata } from "next";
import Link from "next/link";

import { getPost, getSortedPosts } from "../utils";

const FONT_URL =
  "https://fonts.googleapis.com/css2?family=Merriweather:ital,opsz,wght@0,18..144,300..900;1,18..144,300..900&family=Merriweather+Sans:ital,wght@0,300..800;1,300..800&display=swap";

// ─── Icon ──────────────────────────────────────────────────────────────────

function WritingIcon() {
  return (
    // Fountain pen — solid filled silhouette, diagonal bottom-left (nib tip) to top-right (rounded cap)
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="none"
      style={{
        width: "2.2em",
        height: "2.2em",
        flexShrink: 0,
        display: "block",
      }}
      aria-hidden="true"
    >
      <path
        d="M2 22 C0 19, 3 15, 6 12 C7 11, 8 10, 9 9 L17 5 C19 4, 21 2, 22 3 C23 4, 22 6, 21 7 L12 13 C11 14, 10 15, 8 16 C6 18, 4 20, 2 22 Z"
        fill="currentColor"
      />
    </svg>
  );
}

// ─── Page ──────────────────────────────────────────────────────────────────

export default async function BlogPostPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const post = await getPost(slug);

  return (
    <>
      <style>{`@import url('${FONT_URL}');`}</style>

      <div
        style={{
          fontFamily: "'Merriweather', serif",
          color: "black",
          background: "#fffdf4",
          minHeight: "100vh",
          width: "100%",
        }}
      >
        {/* ── HERO IMAGE ─────────────────────────────────────────────────── */}
        <div
          style={{
            position: "relative",
            width: "100%",
            height: "clamp(220px, 42vh, 500px)",
            overflow: "hidden",
          }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/writing.png"
            alt=""
            aria-hidden="true"
            style={{
              position: "absolute",
              inset: 0,
              width: "100%",
              height: "100%",
              objectFit: "cover",
              objectPosition: "center 45%",
            }}
          />
          <div
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              right: 0,
              height: "28%",
              background:
                "linear-gradient(to bottom, #fffdf4 0%, transparent 100%)",
            }}
          />
          <div
            style={{
              position: "absolute",
              bottom: 0,
              left: 0,
              right: 0,
              height: "38%",
              background:
                "linear-gradient(to bottom, transparent 0%, rgba(255,253,244,0.6) 55%, #fffdf4 100%)",
            }}
          />
        </div>

        <div
          style={{
            maxWidth: "62rem",
            margin: "0 auto",
            paddingLeft: "2rem",
            paddingRight: "2rem",
            paddingBottom: "6rem",
          }}
        >
          {/* ── HEADER ─────────────────────────────────────────────────── */}
          <header
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.75rem",
              flexWrap: "wrap",
              marginBlock: "2rem 2.25rem",
            }}
          >
            <Link
              href="/"
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.75rem",
                textDecoration: "none",
                color: "inherit",
                flexShrink: 0,
              }}
            >
              <img
                src="/Assets/Softmax brand mark.svg"
                alt=""
                aria-hidden="true"
                style={{ height: "42px", width: "auto" }}
              />
              <img
                src="/Assets/softmax_wordmark.png"
                alt="Softmax"
                style={{ height: "24px", width: "auto" }}
              />
            </Link>

            <span
              style={{
                color: "#ccc",
                fontSize: "36px",
                fontWeight: 300,
                lineHeight: 1,
                userSelect: "none",
              }}
            >
              /
            </span>

            <Link
              href="/blog"
              className="ias-link-with-icon"
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.4rem",
                textDecoration: "none",
                flexShrink: 0,
              }}
            >
              <WritingIcon />
              <span
                className="ias-link"
                style={{
                  font: "700 30px/38px 'Merriweather Sans', sans-serif",
                }}
              >
                Writing
              </span>
            </Link>
          </header>

          {/* ── ARTICLE ────────────────────────────────────────────────── */}
          <article>
            <h1
              style={{
                font: "700 clamp(2rem, 3.2vw, 2.6rem)/1.12 'Merriweather Sans', sans-serif",
                margin: "0 0 0.75rem",
                maxWidth: "38rem",
              }}
            >
              {post.frontmatter.title}
            </h1>

            {post.frontmatter.subtitle && (
              <p
                style={{
                  font: "300 22px/32px 'Merriweather Sans', sans-serif",
                  color: "#555",
                  margin: "0 0 0.75rem",
                  maxWidth: "38rem",
                }}
              >
                {post.frontmatter.subtitle}
              </p>
            )}

            <p
              style={{
                font: "500 11px/16px 'Merriweather Sans', sans-serif",
                letterSpacing: "0.04em",
                textTransform: "uppercase",
                color: "#999",
                margin: "0 0 2rem",
              }}
            >
              {post.frontmatter.author}
              {post.frontmatter.author && (
                <span style={{ margin: "0 0.4em", color: "#ccc" }}>·</span>
              )}
              {new Date(post.frontmatter.date + "T00:00:00").toLocaleDateString(
                "en-US",
                {
                  month: "long",
                  year: "numeric",
                },
              )}
            </p>

            <div>{post.content}</div>
          </article>
        </div>
      </div>
    </>
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
    title: `Softmax — ${post.frontmatter.title}`,
  };
}

export async function generateStaticParams() {
  const posts = await getSortedPosts();
  return posts.map((post) => ({ slug: post.slug }));
}
