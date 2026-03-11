/**
 * Mission page — Ink & Switch article aesthetic
 * Header: Softmax logo / Mission (like inkandswitch.com/local-first-software/)
 */

import Link from "next/link";
import Mission from "@/mdx/mission.mdx";
import { Waveform } from "@/components/Waveform";
import { S3_IMAGE_BASE } from "@/lib/constants";

const FONT_URL =
  "https://fonts.googleapis.com/css2?family=Merriweather:ital,opsz,wght@0,18..144,300..900;1,18..144,300..900&family=Merriweather+Sans:ital,wght@0,300..800;1,300..800&display=swap";

export const metadata = {
  title: "Softmax — Mission",
  description:
    "Our mission is to understand organic alignment as an empirical science, and to use that understanding to enable organic alignment among all people, both human and digital.",
};

// ─── MDX component overrides ──────────────────────────────────────────────────

const mdxComponents = {
  h2: ({ children }: { children: React.ReactNode }) => (
    <h2
      style={{
        font: "700 30px/38px 'Merriweather Sans', sans-serif",
        color: "#0E2758",
        margin: "2.5rem 0 0.6rem",
      }}
    >
      {children}
    </h2>
  ),
  p: ({ children }: { children: React.ReactNode }) => (
    <p
      style={{
        font: "400 17px/30px 'Merriweather', serif",
        margin: "0 0 1rem",
        maxWidth: "38rem",
      }}
    >
      {children}
    </p>
  ),
  a: ({ href, children }: { href?: string; children: React.ReactNode }) => (
    <Link href={href ?? "#"} className="ias-link">
      {children}
    </Link>
  ),
  ul: ({ children }: { children: React.ReactNode }) => (
    <ul
      style={{
        font: "400 17px/30px 'Merriweather', serif",
        margin: "0 0 1rem",
        paddingLeft: "1.4rem",
        maxWidth: "38rem",
      }}
    >
      {children}
    </ul>
  ),
  Waveform,
};

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function MissionPage() {
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
            src={`${S3_IMAGE_BASE}/oscillon.png`}
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
          {/* top fade */}
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
          {/* bottom fade */}
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
          {/* sentence */}
          <div
            style={{
              position: "absolute",
              inset: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <span
              style={{
                color: "#fffdf4",
                fontFamily: "'Merriweather Sans', sans-serif",
                fontWeight: 700,
                fontSize: "clamp(2rem, 5vw, 4.5rem)",
                letterSpacing: "-0.03em",
                lineHeight: 1.1,
                textShadow: "0 2px 24px rgba(0,0,0,0.25)",
              }}
            >
              scaling alignment
            </span>
          </div>
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
          {/* ── HEADER ───────────────────────────────────────────────────────── */}
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
              style={{ display: "flex", alignItems: "center", gap: "0.5em" }}
            >
              <MissionIcon />
              <span
                style={{
                  font: "700 30px/38px 'Merriweather Sans', sans-serif",
                  paddingBottom: "0.1em",
                  background:
                    "url('/Assets/ul.svg') no-repeat bottom / 100% 0.5em",
                }}
              >
                Mission
              </span>
            </span>
          </header>

          {/* ── CONTENT ──────────────────────────────────────────────────────── */}
          <article>
            <Mission components={mdxComponents} />
          </article>
        </div>
      </div>
    </>
  );
}

// ─── Mission icon ──────────────────────────────────────────────────────────────

function MissionIcon() {
  // Murmuration — 9 dots in an S-curve, bottom-left to top-right
  // Size gradient: small at tail + head, large at core
  // Each dot = one agent; together they read as a collective in motion
  return (
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      style={{
        width: "2.2em",
        height: "2.2em",
        flexShrink: 0,
        display: "block",
      }}
      aria-hidden="true"
    >
      {/* tail — sparse, small */}
      <circle cx="3" cy="19.5" r="0.85" />
      <circle cx="5.5" cy="17" r="1.0" />
      {/* mid-trailing */}
      <circle cx="6" cy="14" r="1.15" />
      <circle cx="9.5" cy="14.5" r="1.25" />
      {/* core — densest */}
      <circle cx="9" cy="11" r="1.45" />
      <circle cx="12.5" cy="11.5" r="1.3" />
      {/* mid-leading */}
      <circle cx="13" cy="8" r="1.1" />
      <circle cx="16.5" cy="7.5" r="1.0" />
      {/* head — sparse, small */}
      <circle cx="19.5" cy="5" r="0.85" />
    </svg>
  );
}
