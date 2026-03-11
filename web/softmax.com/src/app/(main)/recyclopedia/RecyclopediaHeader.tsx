import Link from "next/link";

import styles from "./recyclopedia.module.css";

export function RecyclopediaHeader({ isIndex = false }: { isIndex?: boolean }) {
  const labNotesHref = "/recyclopedia/recyclopedia";

  return (
    <header className={styles.header}>
      <Link href="/" className={styles.logoLink}>
        <img
          src="/Assets/Softmax brand mark.svg"
          alt=""
          aria-hidden="true"
          className={styles.logoMark}
        />
        <img
          src="/Assets/softmax_wordmark.png"
          alt="Softmax"
          className={styles.logoWordmark}
        />
      </Link>

      <span className={styles.slash} aria-hidden="true">
        /
      </span>

      <span className={styles.wrap}>
        <span className={styles.trackTitleWrap}>
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={styles.trackIcon}
            aria-hidden="true"
          >
            {/* hand-drawn spiral — 1.5 turns CCW, slightly organic control points */}
            <path d="M12 12 C11 9, 8 8, 8 12 C8 16, 11 17, 12 16 C14 16, 16 14, 16 12 C16 7, 13 5, 12 5 C10 5, 5 7, 4 12 C3 17, 7 21, 12 21" />
            {/* arrowhead pointing right at outer tail */}
            <path
              d="M14 21 L12 19.5 L12 22.5 Z"
              fill="currentColor"
              stroke="none"
            />
          </svg>
          {isIndex ? (
            <span className={styles.trackTitle}>Recyclopedia</span>
          ) : (
            <Link href="/recyclopedia" className={styles.trackTitle}>
              Recyclopedia
            </Link>
          )}
        </span>
        <Link href={labNotesHref} className={styles.stamp}>
          Lab Notes
        </Link>
      </span>
    </header>
  );
}
