/**
 * Writing listing page — Ink & Switch article aesthetic
 */

import Link from "next/link";

import { getSortedPosts } from "./utils";

const FONT_URL =
  "https://fonts.googleapis.com/css2?family=Merriweather:ital,opsz,wght@0,18..144,300..900;1,18..144,300..900&family=Merriweather+Sans:ital,wght@0,300..800;1,300..800&display=swap";

export const metadata = {
  title: "Softmax — Writing",
  description: "Essays and research from the Softmax lab.",
};

// ─── Icon ──────────────────────────────────────────────────────────────────

function WritingIcon() {
  return (
    // Fountain pen — solid filled silhouette, diagonal bottom-left (nib tip) to top-right (rounded cap)
    // Outline: upper nib tine → section shoulder → long barrel → rounded cap end → barrel bottom → section → lower nib tine
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

export default async function BlogPage() {
  const posts = await getSortedPosts();

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
        {/* ── HERO ──────────────────────────────────────────────────────────────── */}
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
          {/* ── HEADER ───────────────────────────────────────────────────── */}
          <header
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.75rem",
              flexWrap: "wrap",
              marginBlock: "2.5rem 1.5rem",
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

            <span
              style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}
            >
              <WritingIcon />
              <span
                style={{
                  font: "700 30px/38px 'Merriweather Sans', sans-serif",
                  paddingBottom: "0.1em",
                  background:
                    "url('/Assets/ul.svg') no-repeat bottom / 100% 0.5em",
                }}
              >
                Writing
              </span>
            </span>
          </header>

          <p
            style={{
              font: "400 17px/30px 'Merriweather', serif",
              maxWidth: "38rem",
              margin: "0 0 1.5rem",
            }}
          >
            Research and essays about organic alignment and collective
            intelligence. You can also read about our{" "}
            <Link href="/mission" className="ias-link">
              mission
            </Link>{" "}
            or view{" "}
            <Link href="/media" className="ias-link">
              talks and interviews
            </Link>
            .
          </p>

          <hr
            style={{
              border: "none",
              borderTop: "1px solid #e8e4dc",
              margin: "0 0 1.5rem",
            }}
          />

          {/* ── POST LIST ────────────────────────────────────────────────── */}
          <div style={{ display: "flex", flexDirection: "column" }}>
            {posts.map((post, i) => (
              <div
                key={post.slug}
                style={{
                  maxWidth: "38rem",
                  paddingBlock: "2rem",
                  borderTop: i === 0 ? "none" : "1px solid #e8e4dc",
                }}
              >
                <h2
                  style={{
                    font: "600 22px/30px 'Merriweather Sans', sans-serif",
                    margin: "0 0 0.3rem",
                  }}
                >
                  <Link href={`/blog/${post.slug}`} className="ias-link">
                    {post.frontmatter.title}
                    {post.frontmatter.subtitle && (
                      <span
                        className="ias-link-subtle"
                        style={{ fontWeight: 400 }}
                      >
                        {": "}
                        {post.frontmatter.subtitle}
                      </span>
                    )}
                  </Link>
                </h2>

                {post.frontmatter.snippet && (
                  <p
                    style={{
                      font: "400 16px/26px 'Merriweather Sans', sans-serif",
                      margin: "0.4rem 0 0.5rem",
                      color: "#333",
                    }}
                  >
                    {post.frontmatter.snippet}
                  </p>
                )}

                <span
                  style={{
                    font: "500 11px/16px 'Merriweather Sans', sans-serif",
                    letterSpacing: "0.04em",
                    textTransform: "uppercase",
                    color: "#999",
                  }}
                >
                  {post.frontmatter.author}
                  {post.frontmatter.author && (
                    <span style={{ margin: "0 0.4em", color: "#ccc" }}>·</span>
                  )}
                  {new Date(
                    post.frontmatter.date + "T00:00:00",
                  ).toLocaleDateString("en-US", {
                    month: "long",
                    year: "numeric",
                  })}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
