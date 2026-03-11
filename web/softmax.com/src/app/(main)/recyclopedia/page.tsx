import { Metadata } from "next";
import Link from "next/link";

import { RecyclopediaHeader } from "./RecyclopediaHeader";
import styles from "./recyclopedia.module.css";
import { formatListDate, getSortedNotes } from "./utils";

export const metadata: Metadata = {
  title: "Softmax — Recyclopedia",
  description:
    "Internal field notes from our experiments with recyclable interfaces, material signals, and human-in-the-loop sorting.",
};

export default async function RecyclopediaPage() {
  const notes = await getSortedNotes();
  const featuredNotes = notes.filter((note) => note.frontmatter.featured);
  const notesToShow =
    featuredNotes.length > 0 ? featuredNotes : notes.slice(0, 8);

  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <RecyclopediaHeader isIndex />

        <dl className={styles.macrodata}>
          <div className={`${styles.macroRow} ${styles.macroTitle}`}>
            <dt>title</dt>
            <dd>Featured Notes</dd>
          </div>
        </dl>

        <h1 className={styles.h1}>Pulling back the curtain</h1>

        <p className={styles.indexIntro}>
          We’ve begun publishing the internal research notes we write within the
          lab. Some of these newly published notes come from our archives of
          past projects, others are being freshly written about our latest work.
          Be aware that these are notes we write for ourselves. Sometimes
          they’ll mention a term or name that you won’t be familiar with. Many
          notes link to other notes that aren’t public (yet?). If you’re
          interested in our quest to build organic alignment, or are working on
          something similar yourself, there’ll be lots to see and learn here.
        </p>

        <section className={styles.section}>
          <h2 id="featured-notes" className={styles.sectionTitle}>
            <a href="#featured-notes" className={styles.plainLink}>
              Featured Notes
            </a>
          </h2>
          <ul className={styles.featuredList}>
            {notesToShow.map((note) => (
              <li key={note.slug}>
                <Link
                  href={`/recyclopedia/${note.slug}`}
                  className={styles.noteLink}
                >
                  <strong>{note.frontmatter.title}</strong>
                </Link>{" "}
                <i className={styles.noteDate}>{formatListDate(note)}</i>
              </li>
            ))}
          </ul>
        </section>
      </main>
    </div>
  );
}
