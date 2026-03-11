/**
 * Media page — Ink & Switch article aesthetic
 */

import Link from "next/link";

const FONT_URL =
  "https://fonts.googleapis.com/css2?family=Merriweather:ital,opsz,wght@0,18..144,300..900;1,18..144,300..900&family=Merriweather+Sans:ital,wght@0,300..800;1,300..800&display=swap";

export const metadata = {
  title: "Softmax — Media",
  description:
    "Talks and interviews on organic alignment and the future of AGI as cooperative beings.",
};

const videos = [
  {
    title: "Scaling Up Organic Alignment",
    date: "July 28, 2025",
    source: "Softmax Introduction",
    description:
      "Technical overview of how Softmax uses multi-agent reinforcement learning to evolve cooperation.",
    youtubeId: "UgKx0jNOnr8",
  },
  {
    title: "Why Nature Holds the Answer to Alignment",
    date: "September 29, 2025",
    source: "Win-Win Podcast",
    description:
      "Exploring how biological systems achieve alignment through collective identities and why we should mimic this in AI.",
    youtubeId: "Nkhp-mb6FRc",
  },
  {
    title: "Building AI That Actually Cares",
    date: "November 17, 2025",
    source: "a16z Podcast",
    description:
      "Emmett challenges the steering-control paradigm and explains why AGI must be treated as a teammate rather than a tool.",
    youtubeId: "Ua8nPJ1_yk8",
  },
  {
    title: "Controlling Tools or Aligning Creatures?",
    date: "December 27, 2025",
    source: "The Cognitive Revolution",
    description:
      "A deep dive into multi-agent simulations, theory of mind, and the moral status of advanced systems.",
    youtubeId: "-4G5zFYT2M8",
  },
  {
    title: "Explaining AI to the Humanities",
    date: "January 31, 2026",
    source: "The Hope Axis",
    description:
      "A philosophical exploration of AI, discussing interiority, art, and why alignment is a shared direction, not a restriction.",
    youtubeId: "5qRgjypTfUs",
  },
];

// ─── Icon ──────────────────────────────────────────────────────────────────

function MediaIcon() {
  return (
    // Audio waveform — organic irregular wave, caught mid-squiggle, dots at peak + trough
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{
        width: "2.2em",
        height: "2.2em",
        flexShrink: 0,
        display: "block",
      }}
      aria-hidden="true"
    >
      {/* asymmetric: crest shallower, trough deeper, trails off */}
      <path d="M1 12 C3 5, 6 3, 9 12 C12 21, 15 20, 17 12 C19 5, 21 6, 23 10" />
      {/* peak and trough amplitude markers */}
      <circle cx="4.6" cy="6" r="1.8" fill="currentColor" stroke="none" />
      <circle cx="13.4" cy="18.5" r="1.8" fill="currentColor" stroke="none" />
    </svg>
  );
}

// ─── Page ──────────────────────────────────────────────────────────────────

export default function MediaPage() {
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
            src="/media-cropped.png"
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
              <MediaIcon />
              <span
                style={{
                  font: "700 30px/38px 'Merriweather Sans', sans-serif",
                  paddingBottom: "0.1em",
                  background:
                    "url('/Assets/ul.svg') no-repeat bottom / 100% 0.5em",
                }}
              >
                Media
              </span>
            </span>
          </header>

          {/* ── INTRO ────────────────────────────────────────────────────── */}
          <p
            style={{
              font: "400 17px/30px 'Merriweather', serif",
              maxWidth: "38rem",
              margin: "0",
            }}
          >
            Talks and interviews on organic alignment and the future of AGI as
            cooperative beings. For essays and research, see our{" "}
            <Link href="/blog" className="ias-link">
              writing
            </Link>
            .
          </p>

          <hr
            style={{
              border: "none",
              borderTop: "1px solid #e8e4dc",
              margin: "1.5rem 0",
            }}
          />

          {/* ── VIDEO LIST ───────────────────────────────────────────────── */}
          <div style={{ display: "flex", flexDirection: "column" }}>
            {videos.map((v, i) => (
              <div
                key={v.youtubeId}
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
                    color: "#0E2758",
                  }}
                >
                  <span
                    style={{
                      paddingBottom: "0.1em",
                      background:
                        "url('/Assets/ul.svg') no-repeat bottom / 100% 0.5em",
                    }}
                  >
                    {v.title}
                  </span>
                </h2>
                <p
                  style={{
                    font: "400 16px/26px 'Merriweather Sans', sans-serif",
                    margin: "0.4rem 0 0.3rem",
                    color: "#333",
                  }}
                >
                  {v.description}
                </p>
                <span
                  style={{
                    font: "500 11px/16px 'Merriweather Sans', sans-serif",
                    letterSpacing: "0.04em",
                    textTransform: "uppercase",
                    color: "#999",
                    display: "block",
                    marginBottom: "1rem",
                  }}
                >
                  {v.source}
                  <span style={{ margin: "0 0.4em", color: "#ccc" }}>·</span>
                  {v.date}
                </span>
                <div
                  style={{
                    position: "relative",
                    height: 0,
                    overflow: "hidden",
                    borderRadius: "4px",
                    paddingBottom: "56.25%",
                  }}
                >
                  <iframe
                    style={{
                      position: "absolute",
                      top: 0,
                      left: 0,
                      width: "100%",
                      height: "100%",
                    }}
                    src={`https://www.youtube.com/embed/${v.youtubeId}`}
                    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                    allowFullScreen
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
