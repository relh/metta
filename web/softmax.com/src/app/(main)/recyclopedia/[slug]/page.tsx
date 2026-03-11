import { Metadata } from "next";

import { RecyclopediaHeader } from "../RecyclopediaHeader";
import styles from "../recyclopedia.module.css";
import { getNote, getSortedNotes } from "../utils";

export const dynamicParams = false;

function formatPeriod(date: string): string {
  return new Date(`${date}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    year: "numeric",
  });
}

export default async function RecyclopediaNotePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const note = await getNote(slug);
  const period = note.frontmatter.period ?? formatPeriod(note.frontmatter.date);
  const related = note.frontmatter.related ?? [];

  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <RecyclopediaHeader />

        <dl className={styles.macrodata}>
          <div className={`${styles.macroRow} ${styles.macroTitle}`}>
            <dt>title</dt>
            <dd>{note.frontmatter.title}</dd>
          </div>
          <div className={styles.macroRow}>
            <dt>dated</dt>
            <dd>{period}</dd>
          </div>
          <div className={styles.macroRow}>
            <dt>author</dt>
            <dd>{note.frontmatter.author}</dd>
          </div>
          {related.length > 0 && (
            <div className={styles.macroRow}>
              <dt>related</dt>
              <dd className={styles.macroLinks}>
                {related.map((entry, index) => (
                  <span key={entry.href}>
                    <a href={entry.href} className={styles.noteLink}>
                      {entry.label}
                    </a>
                    {index < related.length - 1 && (
                      <span className={styles.dot}> · </span>
                    )}
                  </span>
                ))}
              </dd>
            </div>
          )}
        </dl>

        {note.frontmatter.excerpt && (
          <p className={styles.lede}>
            <em>{note.frontmatter.excerpt}</em>
          </p>
        )}

        <article className={styles.noteBody}>{note.content}</article>
      </main>
    </div>
  );
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const note = await getNote(slug);
  return {
    title: `Softmax - ${note.frontmatter.title}`,
    description: note.frontmatter.snippet,
  };
}

export async function generateStaticParams() {
  const notes = await getSortedNotes();
  return notes.map((note) => ({ slug: note.slug }));
}
