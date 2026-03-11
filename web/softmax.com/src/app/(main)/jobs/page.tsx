/**
 * Jobs page — Ink & Switch article aesthetic
 * Both open positions listed on one page, cogames-style section dividers.
 */

import Link from "next/link";

const FONT_URL =
  "https://fonts.googleapis.com/css2?family=Merriweather:ital,opsz,wght@0,18..144,300..900;1,18..144,300..900&family=Merriweather+Sans:ital,wght@0,300..800;1,300..800&display=swap";

const APPLY_URL =
  "https://form.asana.com/?k=Bud764ZSBAtkdcbfkI-fHQ&d=1209016784099267";

export const metadata = {
  title: "Softmax — Jobs",
  description:
    "Open positions at Softmax — join us in building the science of organic alignment.",
};

// ─── Typography ────────────────────────────────────────────────────────────

const H2 = ({
  children,
  id,
  sectionMark,
}: {
  children: React.ReactNode;
  id?: string;
  sectionMark?: string;
}) => (
  <h2
    id={id}
    style={{
      font: "700 30px/38px 'Merriweather Sans', sans-serif",
      margin: "0 0 0.4rem",
      color: "black",
      scrollMarginTop: "2rem",
      display: "flex",
      alignItems: "baseline",
      gap: "0.7rem",
    }}
  >
    {sectionMark ? (
      <span
        style={{
          font: "300 46px/0.8 'Merriweather', serif",
          color: "#c8bfaf",
          flexShrink: 0,
          transform: "translateY(0.08em)",
        }}
      >
        {sectionMark}
      </span>
    ) : null}
    <span style={{ minWidth: 0 }}>{children}</span>
  </h2>
);

const H3 = ({ children }: { children: React.ReactNode }) => (
  <h3
    style={{
      font: "600 18px/27px 'Merriweather Sans', sans-serif",
      margin: "2rem 0 0.3rem",
      color: "black",
    }}
  >
    {children}
  </h3>
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

const UL = ({ children }: { children: React.ReactNode }) => (
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
);

const Meta = ({ children }: { children: React.ReactNode }) => (
  <p
    style={{
      font: "500 11px/16px 'Merriweather Sans', sans-serif",
      letterSpacing: "0.04em",
      textTransform: "uppercase",
      color: "#999",
      margin: "0 0 1.5rem",
    }}
  >
    {children}
  </p>
);

const Divider = ({ margin = "3rem 0" }: { margin?: string }) => (
  <hr style={{ border: "none", borderTop: "1px solid #e8e4dc", margin }} />
);

const RolesIndex = () => (
  <nav
    aria-label="Open roles"
    style={{
      maxWidth: "42rem",
      margin: "1.5rem 0 2.1rem",
      borderTop: "1px solid #ddd7cc",
      borderBottom: "1px solid #ddd7cc",
      padding: "0.45rem 0",
    }}
  >
    <div
      style={{
        display: "flex",
        alignItems: "baseline",
        justifyContent: "space-between",
        gap: "1rem",
        margin: "0 0 0.35rem",
      }}
    >
      <p
        style={{
          font: "600 11px/16px 'Merriweather Sans', sans-serif",
          letterSpacing: "0.05em",
          textTransform: "uppercase",
          color: "#8a8172",
          margin: 0,
        }}
      >
        Contents
      </p>
      <p
        style={{
          font: "400 12px/18px 'Merriweather Sans', sans-serif",
          color: "#8a8172",
          margin: 0,
        }}
      >
        2 roles
      </p>
    </div>
    <ol
      style={{
        listStyle: "none",
        margin: 0,
        padding: 0,
      }}
    >
      <li className="contents-row">
        <a href="#software-engineer" className="contents-entry">
          <span className="contents-index">I</span>
          <div>
            <span className="contents-link">Software Engineer</span>
            <p className="contents-meta">San Francisco, CA · Full-time</p>
          </div>
        </a>
      </li>
      <li className="contents-row">
        <a href="#software-engineer-contractor" className="contents-entry">
          <span className="contents-index">II</span>
          <div>
            <span className="contents-link">
              Software Engineer — Contractor
            </span>
            <p className="contents-meta">Remote · Global · From $60/hr</p>
          </div>
        </a>
      </li>
    </ol>
  </nav>
);

const ApplyButton = () => (
  <a
    href={APPLY_URL}
    target="_blank"
    rel="noopener noreferrer"
    className="apply-btn"
    style={{
      display: "inline-block",
      marginTop: "0.7rem",
      padding: "0.68em 1.28em",
      font: "600 17px/1 'Merriweather Sans', sans-serif",
      color: "#fffdf4",
      background: "linear-gradient(150deg, #1a3875 0%, #0e2758 100%)",
      border: "1.5px solid #859ebe",
      borderRadius: "4px",
      textDecoration: "none",
      letterSpacing: "0.02em",
      boxShadow: "0 2px 8px rgba(14, 39, 88, 0.18)",
    }}
  >
    Apply
  </a>
);

// ─── Icon ──────────────────────────────────────────────────────────────────

function JobsIcon() {
  return (
    // A seedling — growth, potential, new beginnings
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
      {/* stem — slight S-curve */}
      <path d="M12.2 21.5C12 18.5 11.5 15 12.8 10.2" />
      {/* left leaf — sweeps out and back */}
      <path d="M12.2 16.5C10.8 14.8 7.8 14 6.8 11.2C8.4 10.7 11.5 13 12.4 15.8" />
      {/* right leaf — higher, other side */}
      <path d="M12.8 12.8C14 10.8 17.2 9.2 18.2 6.5C16.5 5.8 13.2 8.5 12.2 11.8" />
      {/* soil line */}
      <path d="M7.8 21.8C9.8 21.2 14.5 21.2 16.5 21.8" />
    </svg>
  );
}

// ─── Page ──────────────────────────────────────────────────────────────────

export default function JobsPage() {
  return (
    <>
      <style>{`
        @import url('${FONT_URL}');
        .apply-btn {
          transition: transform 0.15s ease, box-shadow 0.15s ease;
        }
        .apply-btn:hover {
          transform: translateY(-1px);
          background: #859ebe !important;
          border-color: #859ebe !important;
          box-shadow: 0 8px 20px rgba(14, 39, 88, 0.3);
        }
        .apply-btn:active {
          transform: translateY(0);
          box-shadow: 0 3px 8px rgba(14, 39, 88, 0.2);
        }
        .contents-row {
          padding: 0.9rem 0;
          border-top: 1px solid #ebe5d8;
        }
        .contents-entry {
          display: grid;
          grid-template-columns: 2.5rem minmax(0, 1fr);
          gap: 0.9rem;
          text-decoration: none;
          color: inherit;
        }
        .contents-index {
          font: 300 26px/0.9 'Merriweather', serif;
          color: #8a8172;
          padding-top: 0.05rem;
          transition: color 0.15s ease;
        }
        .contents-link {
          font: 400 20px/1.4 'Merriweather', serif;
          color: black;
          padding-bottom: 0.1em;
          background: url('/Assets/ul.svg') no-repeat bottom / 100% 0.5em;
          transition: color 0.1s ease;
        }
        .contents-entry:hover .contents-link,
        .contents-entry:hover .contents-index,
        .contents-entry:focus-visible .contents-link,
        .contents-entry:focus-visible .contents-index {
          color: #859ebe;
        }
        .contents-entry:hover .contents-link,
        .contents-entry:focus-visible .contents-link {
          background-size: 100% 100px;
        }
        .contents-meta {
          font: 500 11px/16px 'Merriweather Sans', sans-serif;
          letter-spacing: 0.04em;
          text-transform: uppercase;
          color: #8a8172;
          margin: 0.18rem 0 0;
        }
      `}</style>

      <div
        style={{
          fontFamily: "'Merriweather', serif",
          color: "black",
          background: "#fffdf4",
          minHeight: "100vh",
          width: "100%",
        }}
      >
        {/* ── HERO ────────────────────────────────────────────────────────────── */}
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
            src="/murmuration.jpg"
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
          {/* ── HEADER ──────────────────────────────────────────────────────── */}
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
              <JobsIcon />
              <span
                style={{
                  font: "700 30px/38px 'Merriweather Sans', sans-serif",
                  paddingBottom: "0.1em",
                  background:
                    "url('/Assets/ul.svg') no-repeat bottom / 100% 0.5em",
                }}
              >
                Jobs
              </span>
            </span>
          </header>

          {/* ── INTRO ───────────────────────────────────────────────────────── */}
          <P>
            We&apos;re a small, ambitious team building the science of organic
            alignment. We hire for depth, ownership, and the drive to work on
            the hardest problems in AI. If that&apos;s you, we&apos;d love to
            hear from you.
          </P>

          <RolesIndex />

          {/* ── JOB 1: SOFTWARE ENGINEER ────────────────────────────────────── */}
          <H2 id="software-engineer" sectionMark="I">
            Software Engineer
          </H2>
          <Meta>San Francisco, CA · Full-time</Meta>

          <H3>The Role</H3>
          <P>
            We&apos;re looking for a Software Engineer who thinks like a
            scientist and operates like a founder. You&apos;ll own entire
            systems end-to-end: from identifying what to build, to designing and
            implementing solutions, to measuring impact and iterating. This
            isn&apos;t a role where you wait for specs — you generate clarity
            from ambiguity and ship with conviction.
          </P>
          <P>
            You&apos;re also fluent in modern AI tools and use them to multiply
            your output. We expect engineers here to be exceptionally productive
            and to leverage that productivity toward bigger problems, not just
            faster typing.
          </P>

          <H3>What You&apos;ll Do</H3>
          <UL>
            <li>
              <strong>Own products end-to-end.</strong> Define what to build
              based on user needs and business goals. Design the technical
              approach. Build it. Ship it. Measure it. Improve it.
            </li>
            <li>
              <strong>Apply analytic rigor to feature decisions.</strong> Design
              experiments properly. Understand what your data can and can&apos;t
              tell you.
            </li>
            <li>
              <strong>Move fast with quality.</strong> We ship frequently and
              learn from real usage. Balance speed with craft.
            </li>
            <li>
              <strong>Leverage AI tools aggressively.</strong> We expect you to
              operate at 2–5x the productivity of a traditional engineer.
            </li>
            <li>
              <strong>Collaborate with a small, excellent team.</strong> Low
              process, high ownership, direct feedback.
            </li>
          </UL>

          <H3>What We&apos;re Looking For</H3>
          <UL>
            <li>
              <strong>Deep analytical background.</strong> Graduate work in a
              quantitative field (CS, physics, etc.), research experience, or
              equivalent depth from industry.
            </li>
            <li>
              <strong>
                Full-stack capability with multi-language strength.
              </strong>{" "}
              Comfortable across the stack — backend services, data pipelines,
              frontend when needed. Python and C++.
            </li>
            <li>
              <strong>Strong customer instincts.</strong> You understand why
              something should be built, not just how.
            </li>
            <li>
              <strong>AI-native workflow.</strong> You already use AI tools
              daily and have opinions about how to use them effectively.
            </li>
            <li>
              <strong>Ownership mentality.</strong> You see problems, propose
              solutions, and drive them to completion.
            </li>
          </UL>

          <H3>Compensation</H3>
          <P>
            We hire based on impact, not years of experience. Compensation
            reflects your expected contribution. This covers a range of
            experience levels including what would be considered staff and
            principal engineer at larger organizations.
          </P>

          <ApplyButton />

          <Divider margin="2.45rem 0" />

          {/* ── JOB 2: CONTRACTOR ───────────────────────────────────────────── */}
          <H2 id="software-engineer-contractor" sectionMark="II">
            Software Engineer — Contractor
          </H2>
          <Meta>Remote · Global · From $60/hr</Meta>

          <H3>The Role</H3>
          <P>
            We&apos;re seeking a remote contract software engineer to build
            high-quality systems and tools. You&apos;ll work independently on
            diverse engineering challenges that support our research and product
            development, focusing on scalability, performance, and clean
            architecture. Ideal for self-directed engineers who thrive with
            autonomy.
          </P>

          <H3>Key Responsibilities</H3>
          <UL>
            <li>Design and implement robust, scalable software systems</li>
            <li>
              Build tools and infrastructure to support research and development
              workflows
            </li>
            <li>Optimize system performance</li>
            <li>
              Collaborate asynchronously with team members to translate
              requirements into technical solutions
            </li>
            <li>
              Write clean, maintainable code with appropriate testing and
              documentation
            </li>
          </UL>

          <H3>Requirements</H3>
          <UL>
            <li>
              Strong software engineering background with demonstrated
              experience building complex systems independently
            </li>
            <li>
              Ability to work autonomously and manage projects from conception
              to delivery
            </li>
            <li>
              Strong written communication skills for remote collaboration
            </li>
            <li>
              Comfortable working across time zones and managing asynchronous
              workflows
            </li>
          </UL>

          <H3>Nice to Have</H3>
          <UL>
            <li>
              Experience with machine learning, data science, or AI systems
            </li>
            <li>Familiarity with distributed computing</li>
            <li>Background in data visualization or analytics tools</li>
          </UL>

          <ApplyButton />

          <Divider margin="2.45rem 0" />

          <p
            style={{
              font: "400 14px/22px 'Merriweather Sans', sans-serif",
              color: "#999",
              maxWidth: "38rem",
            }}
          >
            Softmax is an equal opportunity employer. We welcome applicants of
            all backgrounds, identities, and experience levels.
          </p>
        </div>
      </div>
    </>
  );
}
