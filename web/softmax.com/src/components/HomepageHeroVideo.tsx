"use client";

import { useEffect, useRef } from "react";

export function HomepageHeroVideo({ autoPlay = true }: { autoPlay?: boolean }) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    if (!autoPlay) {
      return;
    }

    const playVideo = () => void video.play().catch(() => undefined);

    playVideo();

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && entry.intersectionRatio >= 0.35) {
          playVideo();
          return;
        }

        video.pause();
      },
      {
        threshold: [0, 0.35, 1],
      },
    );

    observer.observe(video);

    return () => {
      observer.disconnect();
    };
  }, [autoPlay]);

  return (
    <video
      ref={videoRef}
      aria-label="Alignment League gameplay trailer"
      style={{
        display: "block",
        width: "100%",
        aspectRatio: "16 / 9",
        objectFit: "cover",
      }}
      autoPlay={autoPlay}
      controls
      loop
      muted
      playsInline
      preload="metadata"
      poster="/CogsClips_TrailerV5_trimmed_v1_poster.jpg"
    >
      <source
        src="https://softmax-public.s3.amazonaws.com/softmax-com/images/CogsClips_TrailerV5_trimmed_v1.mp4"
        type="video/mp4"
      />
    </video>
  );
}
