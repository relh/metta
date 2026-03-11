"use client";

import { useEffect, useState } from "react";

const AGENT_PROMPT = "Let's follow softmax.com/play.md";
const AGENT_PROMPT_LABEL = "Let's follow softmax.com/play.md";
const MONO_FONT = "ui-monospace, 'Cascadia Code', Menlo, Consolas, monospace";

export function HomepageAgentPrompt() {
  const [copied, setCopied] = useState(false);
  const [isHovered, setIsHovered] = useState(false);

  const handleCopy = () => {
    void navigator.clipboard.writeText(AGENT_PROMPT).then(() => {
      setCopied(true);
    });
  };

  useEffect(() => {
    if (!copied) {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      setCopied(false);
    }, 1800);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [copied]);

  return (
    <div
      style={{
        position: "relative",
        display: "grid",
        gridTemplateColumns: "minmax(0, 1fr) auto",
        alignItems: "center",
        gap: "clamp(0.45rem, 1.8vw, 0.7rem)",
        width: "100%",
        maxWidth: "22rem",
        minWidth: 0,
        padding:
          "clamp(0.4rem, 1.8vw, 0.5rem) clamp(0.4rem, 1.8vw, 0.5rem) clamp(0.4rem, 1.8vw, 0.5rem) clamp(0.62rem, 2.6vw, 0.85rem)",
        boxSizing: "border-box",
        borderRadius: "4px",
        overflow: "hidden",
        background:
          "linear-gradient(135deg, #262f27 0%, #1e261f 58%, #181d19 100%)",
        boxShadow:
          "inset 0 1px 0 rgba(255,255,255,0.035), inset 0 11px 18px rgba(255,255,255,0.02), 0 8px 14px rgba(12,19,12,0.08)",
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "radial-gradient(circle at 18% 16%, rgba(255,255,255,0.045), transparent 26%), radial-gradient(circle at 74% 22%, rgba(255,255,255,0.03), transparent 22%)",
          pointerEvents: "none",
        }}
      />
      <div
        style={{
          position: "relative",
          zIndex: 1,
          minWidth: 0,
          overflow: "hidden",
        }}
      >
        <code
          style={{
            display: "block",
            margin: 0,
            minWidth: 0,
            fontFamily: MONO_FONT,
            fontSize: "clamp(0.68rem, 2.45vw, 0.8rem)",
            fontWeight: 500,
            lineHeight: 1.35,
            letterSpacing: "0.01em",
            whiteSpace: "normal",
            overflowWrap: "anywhere",
            color: "#f5f7f2",
          }}
        >
          {AGENT_PROMPT_LABEL}
        </code>
      </div>
      <button
        type="button"
        onClick={handleCopy}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        onFocus={() => setIsHovered(true)}
        onBlur={() => setIsHovered(false)}
        aria-label={copied ? "Copied prompt" : "Copy prompt"}
        title={copied ? "Copied" : "Copy"}
        style={{
          position: "relative",
          zIndex: 1,
          flexShrink: 0,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          width: "clamp(1.65rem, 6vw, 1.9rem)",
          height: "clamp(1.65rem, 6vw, 1.9rem)",
          border: copied
            ? "1px solid rgba(245,247,242,0.14)"
            : isHovered
              ? "1px solid rgba(133, 158, 190, 0.55)"
              : "1px solid rgba(245,247,242,0.14)",
          borderRadius: "4px",
          background: copied
            ? "#f5f7f2"
            : isHovered
              ? "rgba(133, 158, 190, 0.14)"
              : "rgba(24, 29, 25, 0.96)",
          color: copied ? "#171c18" : isHovered ? "#859EBE" : "#f5f7f2",
          cursor: "pointer",
          transition:
            "background 0.12s ease, color 0.12s ease, border-color 0.12s ease",
        }}
      >
        {copied ? <CheckIcon /> : <CopyIcon />}
      </button>
    </div>
  );
}

function CopyIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      aria-hidden="true"
      style={{
        width: "1rem",
        height: "1rem",
        fill: "none",
        stroke: "currentColor",
        strokeWidth: 1.85,
      }}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="7" y="4" width="9" height="11" rx="2" />
      <path d="M5.5 12.5H5A2 2 0 0 1 3 10.5v-6A2 2 0 0 1 5 2.5h6A2 2 0 0 1 13 4.5V5" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      aria-hidden="true"
      style={{
        width: "1rem",
        height: "1rem",
        fill: "none",
        stroke: "currentColor",
        strokeWidth: 1.9,
      }}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="m5.5 10 3 3 6-6" />
    </svg>
  );
}
