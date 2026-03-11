/**
 * Events page — Ink & Switch article aesthetic
 */

import Link from "next/link";

import { CONTACT_EMAIL_MAILTO } from "@/lib/constants";

const FONT_URL =
  "https://fonts.googleapis.com/css2?family=Merriweather:ital,opsz,wght@0,18..144,300..900;1,18..144,300..900&family=Merriweather+Sans:ital,wght@0,300..800;1,300..800&display=swap";

export const metadata = {
  title: "Softmax — Events",
};

// ─── Icon ──────────────────────────────────────────────────────────────────

function EventsIcon() {
  return (
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
      <path d="M3 6.5C3 5.4 3.9 4.5 5 4.5H19C20.1 4.5 21 5.4 21 6.5V19.5C21 20.6 20.1 21.5 19 21.5H5C3.9 21.5 3 20.6 3 19.5Z" />
      <path d="M3 10H21" />
      <path d="M8.5 4.5V2.5" />
      <path d="M15.5 4.5V2.5" />
    </svg>
  );
}

// ─── Data ──────────────────────────────────────────────────────────────────

const pastAlignmentHours: string[] = ["February 4", "February 25"];

const joinMailto =
  CONTACT_EMAIL_MAILTO +
  "?subject=" +
  encodeURIComponent("Joining the next Alignment Hour") +
  "&body=" +
  encodeURIComponent(
    "Hi there,\n\nI am a [your research/engineering background]\n\nI heard about Softmax by [how you found us]\n\nI would love to join the next Alignment Hour.\n\nBest,\n[Name]",
  );

// ─── Typography ────────────────────────────────────────────────────────────

const H2 = ({ children }: { children: React.ReactNode }) => (
  <h2
    style={{
      font: "700 22px/30px 'Merriweather Sans', sans-serif",
      color: "#0E2758",
      margin: "2.5rem 0 0.75rem",
    }}
  >
    {children}
  </h2>
);

const P = ({ children }: { children: React.ReactNode }) => (
  <p
    style={{
      font: "400 17px/30px 'Merriweather', serif",
      margin: "0 0 1rem",
      maxWidth: "38rem",
    }}
  >
    {children}
  </p>
);

// ─── Page ──────────────────────────────────────────────────────────────────

export default function EventsPage() {
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
        {/* ── HERO IMAGE ───────────────────────────────────────────────────── */}
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
            src="/alignment-hour-text3.png"
            alt=""
            aria-hidden="true"
            style={{
              position: "absolute",
              inset: 0,
              width: "100%",
              height: "100%",
              objectFit: "cover",
              objectPosition: "center 25%",
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
              marginBlock: "2rem 1.5rem",
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
              <EventsIcon />
              <span
                style={{
                  font: "700 30px/38px 'Merriweather Sans', sans-serif",
                  paddingBottom: "0.1em",
                  background:
                    "url('/Assets/ul.svg') no-repeat bottom / 100% 0.5em",
                }}
              >
                Events
              </span>
            </span>
          </header>

          {/* ── CONTENT ──────────────────────────────────────────────────── */}
          <article>
            <H2>Alignment Hours</H2>
            <P>
              We host alignment hours at our SF office every month—informal
              gatherings for researchers and engineers thinking seriously about
              AI alignment.
            </P>
            <P>
              <a href={joinMailto} className="ias-link">
                Join the next one
              </a>
              .
            </P>

            {pastAlignmentHours.length > 0 && (
              <>
                <H2>Past Events</H2>
                <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                  {pastAlignmentHours.map((date) => (
                    <li
                      key={date}
                      style={{
                        borderTop: "1px solid #e8e4dc",
                        padding: "0.65rem 0",
                        font: "400 17px/26px 'Merriweather Sans', sans-serif",
                        color: "#555",
                      }}
                    >
                      Alignment Hour — {date}
                    </li>
                  ))}
                  <li style={{ borderTop: "1px solid #e8e4dc" }} />
                </ul>
              </>
            )}
          </article>
        </div>
      </div>
    </>
  );
}
