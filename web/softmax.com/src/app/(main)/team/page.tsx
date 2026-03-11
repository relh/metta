/**
 * Team page — Ink & Switch article aesthetic
 */

import Link from "next/link";

// import { Waveform } from "@/components/Waveform";

const FONT_URL =
  "https://fonts.googleapis.com/css2?family=Merriweather:ital,opsz,wght@0,18..144,300..900;1,18..144,300..900&family=Merriweather+Sans:ital,wght@0,300..800;1,300..800&display=swap";

const S3_IMAGE_BASE =
  "https://softmax-public.s3.amazonaws.com/softmax-com/images";

export const metadata = {
  title: "Softmax — Team",
};

// ─── Icon ──────────────────────────────────────────────────────────────────

function TeamIcon() {
  return (
    // Three overlapping organic blobs — community as intersection
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
      <path d="M12.3 2.8C14.8 2.6 16.5 4.4 16 6.9C15.6 9.1 13.6 10.2 11.8 9.7C9.8 9.2 8.6 7.5 9.2 5.7C9.7 4.1 10.8 2.9 12.3 2.8Z" />
      <path d="M7.2 12.8C9.5 12.2 11.3 13.8 11 16.3C10.7 18.5 9 19.6 7.1 19C5.2 18.5 4.1 16.8 4.6 15C5 13.4 6 12.9 7.2 12.8Z" />
      <path d="M17.1 12.6C18.3 12.9 19.7 14.2 19.6 15.8C19.5 17.5 18.1 18.9 16.6 19.1C15 19.3 13.4 18.2 13.2 16.4C12.9 14.4 14.6 12.5 17.1 12.6Z" />
    </svg>
  );
}

// ─── Typography ────────────────────────────────────────────────────────────

const SectionH2 = ({ children }: { children: React.ReactNode }) => (
  <h2
    style={{
      font: "700 22px/30px 'Merriweather Sans', sans-serif",
      color: "#0E2758",
      margin: "2.5rem 0 1rem",
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

// ─── Collaborators ─────────────────────────────────────────────────────────

// const collaborators = [
//   {
//     name: "Michael Levin",
//     href: "https://as.tufts.edu/biology/people/faculty/michael-levin",
//   },
//   { name: "Ken Wilber", href: "https://kenwilber.com/" },
//   { name: "Chris Fields", href: "https://chrisfieldsresearch.com/" },
//   { name: "Ken Stanley", href: "https://www.kenstanley.net/" },
//   { name: "Denis Noble", href: "https://www.denisnoble.com/" },
//   { name: "Andrew Briggs", href: "https://andrewbriggs.org/" },
//   { name: "Jeff Clune", href: "http://jeffclune.com/" },
//   { name: "Erik Hoel", href: "https://substack.com/@erikhoel" },
//   {
//     name: "Ryan Smith",
//     href: "https://www.laureateinstitute.org/ryan-smith.html",
//   },
//   {
//     name: "Center for the Study of Apparent Selves",
//     href: "https://apparentselves.org/",
//   },
//   { name: "Dalton Sakthivadivel", href: "https://darsakthi.github.io/" },
//   { name: "Perry Marshall", href: "https://perrymarshall.info/evolution-2-0/" },
// ];

// ─── Page ──────────────────────────────────────────────────────────────────

export default function TeamPage() {
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
            src={`${S3_IMAGE_BASE}/cellularity.png`}
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
              <TeamIcon />
              <span
                style={{
                  font: "700 30px/38px 'Merriweather Sans', sans-serif",
                  paddingBottom: "0.1em",
                  background:
                    "url('/Assets/ul.svg') no-repeat bottom / 100% 0.5em",
                }}
              >
                Team
              </span>
            </span>
          </header>

          {/* ── CONTENT ──────────────────────────────────────────────────── */}
          <article>
            <SectionH2>Our Founders</SectionH2>

            <P>
              Emmett Shear is a 20 year entrepreneur, most notably as the
              founder and CEO of Twitch. More recently, he&apos;s been a YC
              partner, extremely interim CEO of OpenAI, and an independent
              researcher in alignment and agency before co-founding Softmax.
            </P>

            <P>
              David Bloomin is a seasoned software engineer, AI researcher, and
              entrepreneur with over two decades of experience building
              large-scale infrastructure at Google, Facebook, and Asana. As a
              co-founder of the Plurality Institute, he has led research
              initiatives exploring novel governance models and multi-agent AI
              frameworks. His work has been featured in NeurIPS and other
              leading research forums.
            </P>

            {/* <div style={{ margin: "2rem 0" }}>
              <Waveform />
            </div> */}

            {/* <SectionH2>Our Research Collaborators</SectionH2>

            <P>
              We work with researchers across disciplines to understand the
              state of the art. Some of the individuals and groups we
              collaborate with include:
            </P>

            <ul style={{ listStyle: "none", margin: "0", padding: "0" }}>
              {collaborators.map((c) => (
                <li
                  key={c.name}
                  style={{
                    borderTop: "1px solid #e8e4dc",
                    padding: "0.65rem 0",
                    font: "400 17px/26px 'Merriweather Sans', sans-serif",
                  }}
                >
                  <a
                    href={c.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="ias-link"
                  >
                    {c.name}
                  </a>
                </li>
              ))}
              <li style={{ borderTop: "1px solid #e8e4dc" }} />
            </ul> */}
          </article>
        </div>
      </div>
    </>
  );
}
