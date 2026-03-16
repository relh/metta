'use client'

import { useEffect, useMemo, useState } from 'react'

import { fetchPantheonStories, type PantheonStory } from '../lib/api'

const PANTHEON_HALLS = ['fame', 'same', 'lame'] as const
const PANTHEON_HALL_LABELS: Record<(typeof PANTHEON_HALLS)[number], string> = {
  fame: 'Hall of Fame',
  same: 'Hall of Same',
  lame: 'Hall of Lame',
}

function pantheonStoriesByHall(stories: PantheonStory[]): Record<(typeof PANTHEON_HALLS)[number], PantheonStory[]> {
  return PANTHEON_HALLS.reduce(
    (groups, hall) => {
      groups[hall] = stories.filter((story) => story.hall === hall)
      return groups
    },
    {
      fame: [] as PantheonStory[],
      same: [] as PantheonStory[],
      lame: [] as PantheonStory[],
    }
  )
}

export default function PantheonPage() {
  const [stories, setStories] = useState<PantheonStory[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    void fetchPantheonStories()
      .then((response) => {
        if (cancelled) return
        setStories(response.stories)
        setError(null)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setStories([])
        setError(err instanceof Error ? err.message : String(err))
      })
      .finally(() => {
        if (cancelled) return
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const storiesByHall = useMemo(() => pantheonStoriesByHall(stories), [stories])

  return (
    <main className="grid" style={{ gap: 16 }}>
      <section className="card grid" style={{ gap: 8 }}>
        <h1 style={{ margin: 0 }}>Pantheon</h1>
        <p style={{ margin: 0 }}>
          Replay motif stories grouped as fame/lame/same. This is the supervised seed set for future behavior learning.
        </p>
      </section>

      {loading ? (
        <section className="card">
          <p style={{ margin: 0 }}>Loading Pantheon motifs...</p>
        </section>
      ) : error ? (
        <section className="card">
          <p className="pantheon-error" style={{ margin: 0 }}>
            <strong>Error:</strong> {error}
          </p>
        </section>
      ) : stories.length === 0 ? (
        <section className="card">
          <p style={{ margin: 0 }}>No Pantheon stories found yet.</p>
        </section>
      ) : (
        <section className="pantheon-hall-grid">
          {PANTHEON_HALLS.map((hall) => (
            <article key={hall} className={`card pantheon-hall-card pantheon-hall-${hall}`}>
              <div className="pantheon-hall-head">
                <h2 style={{ margin: 0 }}>{PANTHEON_HALL_LABELS[hall]}</h2>
                <span>{storiesByHall[hall].length}</span>
              </div>
              <div className="grid" style={{ gap: 8 }}>
                {storiesByHall[hall].map((story) => (
                  <article key={story.story_id} className="pantheon-story-card">
                    <div className="pantheon-story-head">
                      <strong>{story.title}</strong>
                      <span>{story.source ?? 'unknown'}</span>
                    </div>
                    <p style={{ margin: 0 }}>{story.motif}</p>
                    <p className="pantheon-story-summary" style={{ margin: 0 }}>
                      {story.summary}
                    </p>
                    <p className="pantheon-story-meta">
                      policy <code>{story.policy}</code>
                      {story.run_id ? (
                        <>
                          {' '}
                          · run <code>{story.run_id}</code>
                        </>
                      ) : null}
                      {story.episode_id ? (
                        <>
                          {' '}
                          · episode <code>{story.episode_id}</code>
                        </>
                      ) : null}
                    </p>
                    {Array.isArray(story.tags) && story.tags.length > 0 ? (
                      <p className="pantheon-story-tags">
                        tags: <code>{story.tags.join(', ')}</code>
                      </p>
                    ) : null}
                    {story.replay_url ? (
                      <a href={story.replay_url} target="_blank" rel="noreferrer">
                        Open replay
                      </a>
                    ) : null}
                  </article>
                ))}
              </div>
            </article>
          ))}
        </section>
      )}
    </main>
  )
}
