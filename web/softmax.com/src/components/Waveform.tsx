"use client";
import { ReactNode, useEffect, useId, useMemo, useRef, useState } from "react";

export function Waveform({
  waveCount = 6,
  echoCount = 9,
  baseAmplitude = 55,
  wavelength = 750,
  speed = 0.02,
}: {
  waveCount?: number;
  echoCount?: number;
  baseAmplitude?: number;
  wavelength?: number;
  speed?: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  // Keep a stable ID for gradient/mask per mount
  const rid = useId();
  const ids = useMemo(() => {
    return {
      grad: `fade-gradient-${rid}`,
      mask: `edge-fade-mask-${rid}`,
    };
  }, []);

  // Track container size via ResizeObserver for accurate viewBox and sampling
  const [{ width, height }, setSize] = useState({ width: 0, height: 0 });
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const update = () => {
      const rect = el.getBoundingClientRect();
      setSize({
        width: Math.min(rect.width, window.innerWidth),
        height: rect.height || 100,
      });
    };

    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    window.addEventListener("resize", update);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", update);
    };
  }, []);

  type WaveGroup = {
    centerY: number;
    amplitude: number;
    wavelength: number;
    phase: number;
    speed: number;
    count: number;
  };

  // Create wave groups with randomized parameters (stable for the life of the component)
  const waveGroupsRef = useRef<WaveGroup[]>(null);
  const allPathRefs = useRef<SVGPathElement[]>([]); // Flat list of path refs for quick iteration

  if (!waveGroupsRef.current && height > 0) {
    const centerY = height / 2;
    const groups: WaveGroup[] = [];
    for (let i = 0; i < waveCount; i++) {
      const g: WaveGroup = {
        centerY,
        amplitude: baseAmplitude * (0.1 + Math.random() * 0.8),
        wavelength: wavelength * (0.7 + Math.random() * 0.6),
        phase: Math.random() * Math.PI * 2,
        speed: speed * (0.6 + Math.random() * 0.8),
        count: 1 + echoCount, // main + echoes
      };
      groups.push(g);
    }
    waveGroupsRef.current = groups;
  }

  // Animation loop
  useEffect(() => {
    if (!width || !height || !waveGroupsRef.current) return;

    const calcY = (x: number, t: number, g: WaveGroup) => {
      const freq = 1 / g.wavelength;
      let y = Math.sin(2 * Math.PI * freq * x + g.phase + t * g.speed);
      y +=
        0.2 *
        Math.sin(
          2 * 2 * Math.PI * freq * x + g.phase * 1.5 + t * g.speed * 1.3,
        );
      y +=
        0.1 *
        Math.sin(
          3 * 2 * Math.PI * freq * x + g.phase * 0.8 + t * g.speed * 0.7,
        );
      return y * g.amplitude;
    };

    const step = () => {
      const t = Date.now() / 1000;
      let pathIndex = 0;

      for (const g of waveGroupsRef.current || []) {
        // Sample the main wave first
        const points = [];
        for (let x = 0; x <= width; x += 5) {
          const y = calcY(x, t, g);
          points.push({ x, y: g.centerY + y });
        }

        // Update main path
        const main = allPathRefs.current[pathIndex++];
        if (main) {
          let d = `M ${points[0].x} ${points[0].y}`;
          for (let i = 1; i < points.length; i++)
            d += ` L ${points[i].x} ${points[i].y}`;
          main.setAttribute("d", d);
        }

        // Update echoes
        for (let i = 1; i < g.count; i++) {
          const echo = allPathRefs.current[pathIndex++];
          const compression = (i / g.count) * 0.8; // closer to center line
          if (!echo) continue;

          let d = `M ${points[0].x} ${g.centerY + (points[0].y - g.centerY) * compression}`;
          for (let k = 1; k < points.length; k++) {
            const p = points[k];
            const ny = g.centerY + (p.y - g.centerY) * compression;
            d += ` L ${p.x} ${ny}`;
          }
          echo.setAttribute("d", d);
        }
      }

      raf = requestAnimationFrame(step);
    };

    let raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [width, height]);

  // Reset wave groups if height changed significantly
  useEffect(() => {
    waveGroupsRef.current = null;
  }, [height]);

  // Build the path elements once (based on counts). We'll reuse refs for updates.
  const pathElements = useMemo(() => {
    const paths: ReactNode[] = [];
    allPathRefs.current = [];

    if (!waveGroupsRef.current) return paths;

    waveGroupsRef.current.forEach((g, gi) => {
      // main
      paths.push(
        <path
          key={`g${gi}-main`}
          ref={(el) => {
            el && allPathRefs.current.push(el);
          }}
          fill="none"
          stroke="rgba(0,0,0,0.25)"
          strokeOpacity="1"
          strokeWidth="1.2"
        />,
      );
      // echoes
      for (let j = 0; j < g.count - 1; j++) {
        paths.push(
          <path
            key={`g${gi}-echo${j}`}
            ref={(el) => {
              el && allPathRefs.current.push(el);
            }}
            fill="none"
            stroke="rgba(0,0,0,0.15)"
            strokeOpacity="1"
            strokeWidth="0.7"
          />,
        );
      }
    });

    return paths;
  }, [waveCount, echoCount, baseAmplitude, wavelength, speed, height]);

  return (
    <div
      ref={containerRef}
      className="relative h-[100px] w-screen max-w-screen overflow-visible"
      style={{
        marginLeft: "calc(-50vw + 50%)", // bleed to full screen width even if nested in a container
      }}
    >
      {/* Background SVG */}
      <svg
        ref={svgRef}
        className="absolute inset-0 max-w-screen overflow-visible"
        width="100%"
        height="100%"
        viewBox={`0 0 ${Math.max(1, width)} ${Math.max(1, height)}`}
        preserveAspectRatio="none"
      >
        <defs>
          <linearGradient id={ids.grad} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopOpacity="0" stopColor="#FFFFFF" />
            <stop offset="0.2" stopOpacity="1" stopColor="#FFFFFF" />
            <stop offset="0.5" stopOpacity="1" stopColor="#FFFFFF" />
            <stop offset="0.8" stopOpacity="1" stopColor="#FFFFFF" />
            <stop offset="1" stopOpacity="0" stopColor="#FFFFFF" />
          </linearGradient>
          <mask id={ids.mask}>
            <rect
              x="0"
              y="0"
              width="100%"
              height="100%"
              fill={`url(#${ids.grad})`}
            />
          </mask>
        </defs>

        <g mask={`url(#${ids.mask})`}>{pathElements}</g>
      </svg>
    </div>
  );
}
