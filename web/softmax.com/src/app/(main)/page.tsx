/**
 * Softmax homepage — Ink & Switch aesthetic
 *
 * Design reference: https://www.inkandswitch.com
 * Fonts: Merriweather (serif body) + Merriweather Sans (sans UI/headings)
 * Colors: #fffdf4 bg, black text, #999 faded, #859EBE hover red
 * Layout: max-width 62rem, centered, negative-margin logo hangs left
 */

import { CogsguardScreenshotGallery } from "@/components/CogsguardScreenshotGallery";
import { HomepageAgentPrompt } from "@/components/HomepageAgentPrompt";
import { HomepageHeroVideo } from "@/components/HomepageHeroVideo";
import { MissionMurmurationBirds } from "@/components/MissionMurmurationBirds";
import Link from "next/link";

const FONT_URL =
  "https://fonts.googleapis.com/css2?family=Merriweather:ital,opsz,wght@0,18..144,300..900;1,18..144,300..900&family=Merriweather+Sans:ital,wght@0,300..800;1,300..800&display=swap";

// ─── Data ────────────────────────────────────────────────────────────────────

type PlayCogamesIconName = "play" | "train" | "mod";

const featuredWork = [
  {
    title: "The Frame-Dependent Mind",
    href: "/blog/the-frame-dependent-mind",
    description:
      "On Reality's Stubborn Refusal To Be One Thing — the recognition that everything we know of reality is frame-dependent.",
    author: "Emmett Shear",
    date: "Jan 2025",
  },
  {
    title: "Research That Inspires Us",
    href: "/blog/inspiration",
    description:
      "A curated selection of papers, essays, and ideas that shaped our thinking about organic alignment and open-ended learning.",
    author: "Softmax Team",
    date: "Mar 2025",
  },
];

const topCogsguardScreenshots = [
  {
    title: "Territory control",
    imageSrc: "/cogames/cogsguard-screenshots/full%20map.png",
    description:
      "Teams compete to control junctions and expand their friendly territory.",
  },
  {
    title: "Gear station",
    imageSrc: "/cogames/cogsguard-screenshots/gear%20miner%20close.png",
    description:
      "Gear stations let cogs switch between four roles: miner, aligner, scrambler, and scout.",
  },
  {
    title: "Miner selected",
    imageSrc: "/cogames/cogsguard-screenshots/miner%20closeup%20unselected.png",
    description:
      "Miners collect resources and craft them into hearts for aligners to spend.",
  },
];

// ─── Sub-components ───────────────────────────────────────────────────────────

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h1
      style={{
        font: "300 24px/36px 'Merriweather Sans', sans-serif",
        margin: "0 0 0.4rem",
      }}
    >
      {children}
    </h1>
  );
}

function SectionIntro({
  children,
  style,
}: {
  children: React.ReactNode;
  style?: React.CSSProperties;
}) {
  return (
    <p
      style={{
        font: "400 17px/26px 'Merriweather', serif",
        maxWidth: "43rem",
        margin: "0 0 1.6rem",
        ...style,
      }}
    >
      {children}
    </p>
  );
}

function PlayCogamesIcon({ icon }: { icon: PlayCogamesIconName }) {
  switch (icon) {
    case "play":
      return <CogamesPlayIcon />;
    case "train":
      return <CogamesTrainIcon />;
    case "mod":
      return <CogamesModIcon />;
  }
}

function CogamesOverviewItem({
  icon,
  title,
  description,
  children,
}: {
  icon: PlayCogamesIconName;
  title: string;
  description: string;
  children?: React.ReactNode;
}) {
  return (
    <div
      style={{
        display: "grid",
        gap: children ? "0.5rem" : 0,
        minWidth: 0,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          gap: "0.85rem",
          maxWidth: "43rem",
          minWidth: 0,
        }}
      >
        <div
          style={{
            flexShrink: 0,
            width: "2rem",
            height: "2rem",
            color: "black",
          }}
        >
          <PlayCogamesIcon icon={icon} />
        </div>
        <div style={{ minWidth: 0 }}>
          <div
            style={{
              font: "600 14px/21px 'Merriweather Sans', sans-serif",
              textTransform: "uppercase",
              letterSpacing: "0.02em",
              color: "black",
              marginBottom: "0.25rem",
            }}
          >
            {title}
          </div>
          <p
            style={{
              font: "400 16px/24px 'Merriweather Sans', sans-serif",
              margin: 0,
              color: "black",
            }}
          >
            {description}
          </p>
        </div>
      </div>
      {children ? (
        <div
          style={{
            display: "grid",
            gap: "0.45rem",
            paddingLeft: "2.85rem",
            minWidth: 0,
            maxWidth: "100%",
            boxSizing: "border-box",
          }}
        >
          {children}
        </div>
      ) : null}
    </div>
  );
}

function HomepageVideoPanel({ style }: { style?: React.CSSProperties }) {
  return (
    <div
      style={{
        maxWidth: "34rem",
        overflow: "hidden",
        borderRadius: "14px",
        background: "#2f3747",
        boxShadow: "0 12px 26px rgba(14, 39, 88, 0.14)",
        ...style,
      }}
    >
      <HomepageHeroVideo />
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export const metadata = {
  title: "Softmax — Scaling Alignment",
  description:
    "An independent research lab building the science of organic alignment through multi-agent reinforcement learning.",
};

export default function Home() {
  return (
    <>
      {/* Google Fonts + hover styles (no JS event handlers needed) */}
      <style>{`
        @import url('${FONT_URL}');

        /* Hand-drawn SVG underline — matches inkandswitch.com exactly */
        .ias-link {
          color: black;
          text-decoration: none;
          line-height: 1.5;
          padding-bottom: .1em;
          background: url('/Assets/ul.svg') no-repeat bottom / 100% .5em;
          transition: color 0.1s;
        }
        .ias-link:hover {
          color: #859EBE;
          background-size: 100% 100px;
        }

        /* Connect section items */
        .connect-item {
          display: flex;
          align-items: flex-start;
          gap: 0.85rem;
          text-decoration: none;
          color: inherit;
        }
        .connect-icon {
          color: black;
          transition: color 0.1s;
        }
        .connect-title {
          display: inline;
          color: black;
          text-decoration: none;
          line-height: 1.5;
          padding-bottom: .1em;
          background: url('/Assets/ul.svg') no-repeat bottom / 100% .5em;
          transition: color 0.1s;
        }
        .connect-description {
          color: black;
          transition: color 0.1s;
        }
        .connect-item:hover .connect-title {
          color: #859EBE;
          background-size: 100% 100px;
        }
        .connect-item:hover .connect-icon { color: #859EBE; }

        .writing-item {
          display: block;
          text-decoration: none;
          color: inherit;
        }
        .writing-title {
          display: inline;
          color: black;
          text-decoration: none;
          line-height: 1.5;
          padding-bottom: .1em;
          background: url('/Assets/ul.svg') no-repeat bottom / 100% .5em;
          transition: color 0.1s;
        }
        .writing-item:hover .writing-title {
          color: #859EBE;
          background-size: 100% 100px;
        }

        .cogsguard-shot {
          outline: none;
        }
        .cogsguard-shot-frame {
          isolation: isolate;
        }
        .cogsguard-shot-overlay {
          position: absolute;
          inset: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 0.9rem;
          text-align: center;
          background: rgba(18, 24, 31, 0.74);
          opacity: 0;
          transition: opacity 0.14s ease;
        }
        .cogsguard-shot:hover .cogsguard-shot-overlay,
        .cogsguard-shot:focus-visible .cogsguard-shot-overlay {
          opacity: 1;
        }
        .cogsguard-shot[data-open="true"] .cogsguard-shot-overlay {
          opacity: 1;
        }
        .cogsguard-shot:focus-visible {
          box-shadow: 0 0 0 2px #859EBE;
        }
        @media (hover: none) {
          .cogsguard-shot[data-touch="true"] .cogsguard-shot-overlay {
            opacity: 0;
            background: linear-gradient(180deg, rgba(18, 24, 31, 0.08) 0%, rgba(18, 24, 31, 0.76) 100%);
          }
          .cogsguard-shot[data-touch="true"][data-open="true"] .cogsguard-shot-overlay,
          .cogsguard-shot[data-touch="true"]:focus-visible .cogsguard-shot-overlay {
            opacity: 1;
          }
        }
      `}</style>

      <div
        style={{
          fontFamily: "'Merriweather', serif",
          fontSize: "16px",
          lineHeight: "24px",
          color: "black",
          background: "#fffdf4",
          minHeight: "100vh",
          width: "100%",
        }}
      >
        <div
          style={{
            maxWidth: "62rem",
            margin: "0 auto",
            paddingLeft: "2rem",
            paddingRight: "2rem",
            paddingBottom: "4rem",
          }}
        >
          {/* ── HEADER / Logo ──────────────────────────────────────────────────── */}
          <header
            style={{
              display: "flex",
              flexFlow: "wrap",
              alignItems: "center",
              gap: "0.25rem",
              marginBlock: "2.5rem 1.5rem",
              lineHeight: 1,
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
              }}
            >
              <img
                src="/Assets/Softmax brand mark.svg"
                alt=""
                aria-hidden="true"
                style={{ height: "48px", width: "auto" }}
              />
              <img
                src="/Assets/softmax_wordmark.png"
                alt="Softmax"
                style={{ height: "28px", width: "auto" }}
              />
            </Link>
          </header>

          {/* ── INTRO ──────────────────────────────────────────────────────────── */}
          <section id="intro" style={{ marginTop: "2rem" }}>
            <h1
              style={{
                fontFamily: "'Merriweather', serif",
                fontWeight: 300,
                fontSize: "clamp(21px, 3.2vw, 32px)",
                lineHeight: 1.5,
                letterSpacing: "0.01em",
                textWrap: "balance" as React.CSSProperties["textWrap"],
                margin: "0 0 1rem",
                marginTop: "-0.17em",
              }}
            >
              An independent research lab building a massively multiplayer
              benchmark for social intelligence.
            </h1>
            <SectionIntro style={{ marginBottom: "1.5rem" }}>
              Social intelligence is the ability to skillfully interact with
              other agents with their own needs, capacities, and goals. We think
              social intelligence is critical for scaling alignment, and we're
              releasing a public benchmark to measure it.
            </SectionIntro>
          </section>

          {/* ── PLAY COGAMES ───────────────────────────────────────────────────── */}
          <section id="production" style={{ marginTop: "1.35rem" }}>
            <HomepageVideoPanel style={{ marginBottom: "2.5rem" }} />
            <SectionHeading>Play, Train, and Build with Cogames</SectionHeading>
            <SectionIntro>
              <IasLink href="https://github.com/Metta-AI/cogames">
                Cogames
              </IasLink>{" "}
              is an open source package and live benchmark for making social
              intelligence games and training against them.
            </SectionIntro>

            <div
              style={{
                display: "grid",
                gap: "1.4rem",
                marginBottom: "2rem",
              }}
            >
              <CogamesOverviewItem
                icon="play"
                title="Play Our First Cogame: Cogs vs Clips"
                description="In Cogs vs Clips, teams of loyal Cogs capture and defend territory."
              >
                <p
                  style={{
                    font: "400 16px/24px 'Merriweather Sans', sans-serif",
                    margin: 0,
                    color: "black",
                  }}
                >
                  Tell your agent:
                </p>
                <div>
                  <HomepageAgentPrompt />
                </div>
              </CogamesOverviewItem>

              <CogamesOverviewItem
                icon="train"
                title="Train your agent"
                description="Training for cogames is a great way to level up social intelligence. Cogames offers agent skill files, an optional integrated PufferLib-based RL PPO trainer, high quality experience logs, and a diagnostic eval suite."
              />

              <CogamesOverviewItem
                icon="mod"
                title="Mod a game, or make your own"
                description="Cogames are built using libraries of composable game rules called variants. Variants have the power to change almost anything about the game, from adding or removing mechanics to adding new victory conditions. You can use Cogs vs Clips as a base, or start from scratch."
              />
            </div>

            <div style={{ marginTop: "1.85rem" }}>
              <CogsguardScreenshotGallery
                screenshots={topCogsguardScreenshots}
              />
            </div>
          </section>

          {/* ── FEATURED WRITING ───────────────────────────────────────────────── */}
          <section id="writing" style={{ marginTop: "3rem" }}>
            <SectionHeading>Writing</SectionHeading>
            <SectionIntro style={{ marginBottom: "0.85rem" }}>
              Below is a selection of featured essays. For more, see{" "}
              <IasLink href="/blog">all our writing</IasLink> and{" "}
              <IasLink href="/media">all our media</IasLink>.
            </SectionIntro>

            {featuredWork.map((item, i) => (
              <Link
                key={item.title}
                href={item.href}
                className="writing-item"
                style={{
                  maxWidth: "33rem",
                  marginTop: i === 0 ? "1.25rem" : "1.2rem",
                }}
              >
                <h3
                  style={{
                    font: "350 16px/24px 'Merriweather Sans', sans-serif",
                    margin: "0 0 0.3rem",
                  }}
                >
                  <span className="writing-title">{item.title}</span>
                </h3>
                <p
                  style={{
                    font: "400 14px/22px 'Merriweather Sans', sans-serif",
                    margin: "0 0 0.3rem",
                    color: "black",
                  }}
                >
                  {item.description}
                </p>
                <span
                  style={{
                    font: "500 10px/15px 'Merriweather Sans', sans-serif",
                    letterSpacing: "0.03em",
                    textTransform: "uppercase",
                    color: "#999",
                  }}
                >
                  {item.author}
                  <span style={{ margin: "0 0.4em", color: "#ccc" }}>·</span>
                  {item.date}
                </span>
              </Link>
            ))}
          </section>

          <section id="mission" style={{ marginTop: "3rem" }}>
            <SectionHeading>Mission</SectionHeading>
            <SectionIntro style={{ marginBottom: "1rem" }}>
              Organic alignment is the process by which individuals learn to
              form flourishing wholes at ever greater scales. It's the way cells
              form organisms, animals form packs, and people form societies. We
              use multi-agent machine learning at scale to study how agents
              learn when and how to share goals, develop specialized roles, and
              generate collectively intelligent systems. Everything we do
              pursues this <IasLink href="/mission">mission.</IasLink>
            </SectionIntro>
            <div style={{ maxWidth: "43rem", marginTop: "2rem" }}>
              <MissionMurmurationBirds />
            </div>
          </section>

          {/* ── CONNECT ────────────────────────────────────────────────────────── */}
          <section style={{ marginTop: "3rem" }}>
            <SectionHeading>Connect with us</SectionHeading>
            <SectionIntro>
              Softmax is an independent research lab led by Emmett Shear. Our
              work is supported by a small group of individuals and
              organizations who share our goal: to help humanity navigate the
              transition to a world with powerful AI through genuine scientific
              understanding.
            </SectionIntro>

            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "1.4rem",
                marginTop: "1.5rem",
                maxWidth: "33rem",
              }}
            >
              <ConnectItem
                href="/team"
                icon={<TeamIcon />}
                title="Team"
                description="Meet the researchers and engineers building the science of organic alignment."
              />
              <ConnectItem
                href="/jobs"
                icon={<JobsIcon />}
                title="Jobs"
                description="We're hiring researchers and engineers who want to work on the hardest problem in AI."
              />
              <ConnectItem
                href="/events"
                icon={<EventsIcon />}
                title="Events"
                description="Talks, workshops, and appearances from members of the Softmax lab."
              />
            </div>
          </section>
        </div>
      </div>
    </>
  );
}

// ─── Connect section ──────────────────────────────────────────────────────────

function ConnectItem({
  href,
  icon,
  title,
  description,
}: {
  href: string;
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <Link href={href} className="connect-item">
      <div
        className="connect-icon"
        style={{
          flexShrink: 0,
          width: "2rem",
          height: "2rem",
        }}
      >
        {icon}
      </div>
      <div>
        <div style={{ marginBottom: "0.25rem" }}>
          <span
            className="connect-title"
            style={{
              font: "600 14px/21px 'Merriweather Sans', sans-serif",
              textTransform: "uppercase",
              letterSpacing: "0.02em",
            }}
          >
            {title}
          </span>
        </div>
        <p
          className="connect-description"
          style={{
            font: "400 16px/24px 'Merriweather Sans', sans-serif",
            margin: 0,
          }}
        >
          {description}
        </p>
      </div>
    </Link>
  );
}

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
      aria-hidden="true"
    >
      {/* top blob */}
      <path d="M12.3 2.8C14.8 2.6 16.5 4.4 16 6.9C15.6 9.1 13.6 10.2 11.8 9.7C9.8 9.2 8.6 7.5 9.2 5.7C9.7 4.1 10.8 2.9 12.3 2.8Z" />
      {/* bottom-left blob */}
      <path d="M7.2 12.8C9.5 12.2 11.3 13.8 11 16.3C10.7 18.5 9 19.6 7.1 19C5.2 18.5 4.1 16.8 4.6 15C5 13.4 6 12.9 7.2 12.8Z" />
      {/* bottom-right blob */}
      <path d="M17.1 12.6C18.3 12.9 19.7 14.2 19.6 15.8C19.5 17.5 18.1 18.9 16.6 19.1C15 19.3 13.4 18.2 13.2 16.4C12.9 14.4 14.6 12.5 17.1 12.6Z" />
    </svg>
  );
}

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

function EventsIcon() {
  return (
    // A calendar
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {/* body — wide enough to feel square (3→21 = 18 units wide, 4.5→21.5 = 17 units tall) */}
      <path d="M3 6.5C3 5.4 3.9 4.5 5 4.5H19C20.1 4.5 21 5.4 21 6.5V19.5C21 20.6 20.1 21.5 19 21.5H5C3.9 21.5 3 20.6 3 19.5Z" />
      {/* header divider */}
      <path d="M3 10H21" />
      {/* tab pegs */}
      <path d="M8.5 4.5V2.5" />
      <path d="M15.5 4.5V2.5" />
    </svg>
  );
}

function AlbIcon() {
  return (
    // Bullseye — benchmark, hitting the target, alignment
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {/* outer ring — slightly organic */}
      <path d="M12 2.5C17.5 2.3 21.8 6.8 21.5 12.2C21.2 17.4 16.8 21.8 12 21.5C6.8 21.3 2.3 17.2 2.5 12C2.7 6.8 6.8 2.7 12 2.5Z" />
      {/* middle ring */}
      <path d="M12 6.5C15.3 6.3 17.8 9 17.5 12.2C17.2 15.2 14.8 17.5 12 17.5C9 17.4 6.3 15.2 6.5 12C6.7 9 9.2 6.7 12 6.5Z" />
      {/* center dot — filled */}
      <path
        d="M12.1 9.5C13.5 9.4 14.6 10.7 14.5 12.1C14.4 13.4 13.3 14.5 12 14.5C10.6 14.4 9.4 13.3 9.5 12C9.6 10.7 10.8 9.6 12.1 9.5Z"
        fill="currentColor"
        stroke="none"
      />
    </svg>
  );
}

function CogamesPlayIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M5.1 20.4C8.2 19.9 15.8 19.9 18.9 20.4" />
      <path d="M9.4 4.4C11 4.2 12.3 5.4 12.1 7C11.9 8.6 10.6 9.6 9.2 9.4C7.8 9.2 6.8 8 7 6.5C7.1 5.3 8.2 4.5 9.4 4.4Z" />
      <path d="M10 9.8C10.1 11.7 10 13.6 10 15.5" />
      <path d="M10.2 11.4C8.8 12 7.8 13 7.2 14.1" />
      <path d="M10.2 11.4C11.5 11.8 12.5 12.7 13.2 13.5" />
      <path d="M10 15.5C8.9 16.5 8 17.8 7.3 19.1" />
      <path d="M10.2 15.2C11.9 15.5 13.2 16.6 14.8 17.8" />
      <path d="M17.6 16.2C18.5 16.1 19.3 16.8 19.2 17.7C19.1 18.6 18.4 19.3 17.5 19.2C16.7 19.1 16 18.4 16.1 17.5C16.2 16.7 16.8 16.2 17.6 16.2Z" />
      <path d="M16.8 17.7L15.8 17.7" />
      <path d="M18.7 17.7L19.7 17.7" />
      <path d="M17.7 16.8L17.7 15.8" />
      <path d="M17.7 18.7L17.7 19.7" />
    </svg>
  );
}

function CogamesTrainIcon() {
  return <AlbIcon />;
}

function CogamesModIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M8.5 1H15.5V8H8.5Z" fill="currentColor" stroke="none" />
      <path d="M16 8.5H23V15.5H16Z" fill="currentColor" stroke="none" />
      <path d="M1 16H8V23H1Z" fill="currentColor" stroke="none" />
      <path d="M8.5 16H15.5V23H8.5Z" fill="currentColor" stroke="none" />
      <path d="M16 16H23V23H16Z" fill="currentColor" stroke="none" />
      <path d="M1 1H8V8H1Z" />
      <path d="M16 1H23V8H16Z" />
      <path d="M1 8.5H8V15.5H1Z" />
      <path d="M8.5 8.5H15.5V15.5H8.5Z" />
    </svg>
  );
}

// ─── Link components — hover via CSS classes defined in <style> above ─────────

function IasLink({
  href,
  openInNewTab = false,
  children,
}: {
  href: string;
  openInNewTab?: boolean;
  children: React.ReactNode;
}) {
  const isExternal = href.startsWith("http");
  const props =
    isExternal || openInNewTab
      ? { target: "_blank", rel: "noopener noreferrer" }
      : {};
  return (
    <Link href={href} {...props} className="ias-link">
      {children}
    </Link>
  );
}
