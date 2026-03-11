"use client";

import { useLayoutEffect, useRef } from "react";

type Boid = {
  x: number;
  y: number;
  vx: number;
  vy: number;
  seed: number;
  tone: number;
};

type FoodDrop = {
  x: number;
  y: number;
  placedAt: number;
  remaining: number;
  seed: number;
};

const MAX_SPEED = 1.75;
const MIN_SPEED = 0.34;
const NEIGHBOR_RADIUS = 62;
const SEPARATION_RADIUS = 20;
const CONNECTION_RADIUS = 68;
const POINTER_INFLUENCE_RADIUS = 165;
const FOOD_INFLUENCE_RADIUS = 165;
const FOOD_EAT_RADIUS = 18;
const FOOD_POP_IN_MS = 180;
const FOOD_CONSUMPTION_RATE = 0.00014;
const FOOD_DROPS_ENABLED = true;
const BOID_STROKES = ["#8f5b3f", "#b36e4e", "#6e8050", "#9a6a8a"];
const BIRD_SCALE = 1.28;

function clampSpeed(vx: number, vy: number): [number, number] {
  const speed = Math.hypot(vx, vy) || 1;
  if (speed > MAX_SPEED) {
    const ratio = MAX_SPEED / speed;
    return [vx * ratio, vy * ratio];
  }
  if (speed < MIN_SPEED) {
    const ratio = MIN_SPEED / speed;
    return [vx * ratio, vy * ratio];
  }
  return [vx, vy];
}

function wrapPosition(value: number, max: number): number {
  if (value < 0) return value + max;
  if (value > max) return value - max;
  return value;
}

export function MissionMurmurationBirds() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useLayoutEffect(() => {
    const container = containerRef.current;
    const canvas = canvasRef.current;
    if (!container || !canvas) {
      return;
    }

    const ctx = canvas.getContext("2d");
    if (!ctx) {
      return;
    }

    let width = 0;
    let height = 0;
    let dpr = 1;
    let rafId = 0;
    let isInViewport = true;
    let isDocumentVisible = document.visibilityState === "visible";
    let isTouchMode = false;
    const pointer = {
      x: 0,
      y: 0,
      active: false,
    };

    const boids: Boid[] = [];
    let foodDrop: FoodDrop | null = null;
    let lastFrameAt = 0;
    const touchMedia = window.matchMedia("(hover: none), (pointer: coarse)");

    const resize = () => {
      dpr = window.devicePixelRatio || 1;
      width = Math.max(1, canvas.clientWidth);
      height = Math.max(1, canvas.clientHeight);

      canvas.width = Math.max(1, Math.floor(width * dpr));
      canvas.height = Math.max(1, Math.floor(height * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const seedBoids = () => {
      const count = Math.max(
        42,
        Math.min(88, Math.floor((width * height) / 10800)),
      );
      boids.length = 0;
      for (let i = 0; i < count; i += 1) {
        const angle = Math.random() * Math.PI * 2;
        const speed = MIN_SPEED + Math.random() * (MAX_SPEED - MIN_SPEED);
        boids.push({
          x: Math.random() * width,
          y: Math.random() * height,
          vx: Math.cos(angle) * speed,
          vy: Math.sin(angle) * speed,
          seed: Math.random() * 1000,
          tone: Math.floor(Math.random() * BOID_STROKES.length),
        });
      }
    };

    const updateInteractionMode = () => {
      isTouchMode = touchMedia.matches;
      if (isTouchMode) {
        foodDrop = null;
      }
    };

    const getPoint = (event: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      return {
        x: (event.clientX - rect.left) * (width / rect.width),
        y: (event.clientY - rect.top) * (height / rect.height),
      };
    };

    const updatePointer = (event: PointerEvent) => {
      const point = getPoint(event);
      pointer.x = point.x;
      pointer.y = point.y;
      pointer.active = true;
    };

    const placeFoodDrop = (event: PointerEvent) => {
      if (!FOOD_DROPS_ENABLED || isTouchMode || event.button !== 0) {
        return;
      }

      const point = getPoint(event);
      const placedAt = performance.now();
      foodDrop = {
        x: point.x,
        y: point.y,
        placedAt,
        remaining: 1,
        seed: Math.random() * 1000,
      };
    };

    const handlePointerDown = (event: PointerEvent) => {
      updatePointer(event);
      placeFoodDrop(event);
    };

    const handlePointerEnd = () => {
      if (isTouchMode) {
        clearPointer();
      }
    };

    const clearPointer = () => {
      pointer.active = false;
    };

    const drawFoodDrop = (drop: FoodDrop, now: number) => {
      const popIn = Math.min(1, (now - drop.placedAt) / FOOD_POP_IN_MS);
      const scale = (0.72 + drop.remaining * 0.48) * (0.84 + popIn * 0.16);
      const pulse = 0.95 + Math.sin(now * 0.012 + drop.seed) * 0.06;
      const wobble = Math.sin(now * 0.009 + drop.seed * 1.7) * 0.22;

      ctx.save();
      ctx.translate(drop.x, drop.y);
      ctx.rotate(drop.seed * 0.012);
      ctx.scale(scale * pulse, scale * (1.02 + wobble * 0.08));

      ctx.fillStyle = `rgba(191, 118, 74, ${(0.1 + drop.remaining * 0.1).toFixed(3)})`;
      ctx.beginPath();
      ctx.arc(0, 0, 14, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = `rgba(146, 82, 48, ${(0.55 + drop.remaining * 0.25).toFixed(3)})`;
      ctx.strokeStyle = `rgba(120, 67, 40, ${(0.34 + drop.remaining * 0.18).toFixed(3)})`;
      ctx.lineWidth = 0.9;
      ctx.beginPath();
      ctx.moveTo(-5.2, -0.9 + wobble);
      ctx.quadraticCurveTo(-5.1, -4.7, -1.2, -4.1 + wobble * 0.35);
      ctx.quadraticCurveTo(3.5, -4.2 - wobble * 0.3, 5.4, -0.8);
      ctx.quadraticCurveTo(6.0, 2.6 + wobble * 0.5, 1.8, 4.4 - wobble * 0.25);
      ctx.quadraticCurveTo(-2.8, 5.2 + wobble * 0.4, -5.2, -0.9 + wobble);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = `rgba(249, 231, 193, ${(0.2 + drop.remaining * 0.18).toFixed(3)})`;
      ctx.beginPath();
      ctx.ellipse(-1.3, -1.8, 1.6, 1.05, -0.3, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = `rgba(162, 91, 54, ${(0.48 + drop.remaining * 0.16).toFixed(3)})`;
      ctx.beginPath();
      ctx.arc(6.1, 1.7, 1.05, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = `rgba(238, 216, 176, ${(0.18 + drop.remaining * 0.16).toFixed(3)})`;
      ctx.beginPath();
      ctx.arc(5.8, 1.4, 0.42, 0, Math.PI * 2);
      ctx.fill();

      ctx.restore();
    };

    const drawBoid = (boid: Boid, now: number) => {
      const angle = Math.atan2(boid.vy, boid.vx);
      const wobble = Math.sin(now * 0.005 + boid.seed) * 1.05;
      const stroke = BOID_STROKES[boid.tone];

      ctx.save();
      ctx.translate(boid.x, boid.y);
      ctx.rotate(angle);
      ctx.scale(BIRD_SCALE, BIRD_SCALE);
      ctx.strokeStyle = stroke;
      ctx.fillStyle = stroke;
      ctx.lineWidth = 1.55;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";

      // upper squiggle
      ctx.beginPath();
      ctx.moveTo(-4.6, -1.15 + wobble * 0.2);
      ctx.quadraticCurveTo(
        -2.2,
        -2.7 + wobble * 0.7,
        0.3,
        -0.55 + wobble * 0.2,
      );
      ctx.quadraticCurveTo(2.45, 1.0 - wobble * 0.2, 4.35, 0.3 + wobble * 0.1);
      ctx.stroke();

      // lower squiggle
      ctx.beginPath();
      ctx.moveTo(-4.1, 1.35 - wobble * 0.2);
      ctx.quadraticCurveTo(
        -1.7,
        2.8 - wobble * 0.45,
        0.95,
        1.2 - wobble * 0.12,
      );
      ctx.quadraticCurveTo(2.75, 0.3 + wobble * 0.2, 4.0, 0.82 + wobble * 0.12);
      ctx.stroke();

      ctx.beginPath();
      ctx.arc(4.55, 0.4, 0.53, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    };

    const stopAnimation = () => {
      if (rafId !== 0) {
        window.cancelAnimationFrame(rafId);
        rafId = 0;
      }
      lastFrameAt = 0;
    };

    const syncAnimationState = () => {
      if (!isInViewport || !isDocumentVisible) {
        stopAnimation();
        return;
      }

      if (rafId === 0) {
        rafId = window.requestAnimationFrame(step);
      }
    };

    const step = (now: number) => {
      if (!isInViewport || !isDocumentVisible) {
        rafId = 0;
        return;
      }

      const deltaMs = lastFrameAt === 0 ? 16 : Math.min(40, now - lastFrameAt);
      lastFrameAt = now;

      ctx.fillStyle = "rgba(245, 233, 214, 0.17)";
      ctx.fillRect(0, 0, width, height);

      if (foodDrop && foodDrop.remaining <= 0) {
        foodDrop = null;
      }

      const neighborRadiusSq = NEIGHBOR_RADIUS * NEIGHBOR_RADIUS;
      const separationRadiusSq = SEPARATION_RADIUS * SEPARATION_RADIUS;
      const pointerRadiusSq =
        POINTER_INFLUENCE_RADIUS * POINTER_INFLUENCE_RADIUS;
      const foodRadiusSq = FOOD_INFLUENCE_RADIUS * FOOD_INFLUENCE_RADIUS;
      const foodEatRadiusSq = FOOD_EAT_RADIUS * FOOD_EAT_RADIUS;
      let foodVisitors = 0;

      if (foodDrop) {
        drawFoodDrop(foodDrop, now);
      }

      for (let i = 0; i < boids.length; i += 1) {
        const boid = boids[i];

        let alignmentX = 0;
        let alignmentY = 0;
        let cohesionX = 0;
        let cohesionY = 0;
        let neighborCount = 0;

        let separationX = 0;
        let separationY = 0;

        for (let j = 0; j < boids.length; j += 1) {
          if (i === j) continue;
          const other = boids[j];

          const dx = other.x - boid.x;
          const dy = other.y - boid.y;
          const distanceSq = dx * dx + dy * dy;

          if (distanceSq < neighborRadiusSq) {
            alignmentX += other.vx;
            alignmentY += other.vy;
            cohesionX += other.x;
            cohesionY += other.y;
            neighborCount += 1;
          }

          if (distanceSq > 0 && distanceSq < separationRadiusSq) {
            const inverse = 1 / distanceSq;
            separationX -= dx * inverse;
            separationY -= dy * inverse;
          }
        }

        if (neighborCount > 0) {
          alignmentX = (alignmentX / neighborCount - boid.vx) * 0.04;
          alignmentY = (alignmentY / neighborCount - boid.vy) * 0.04;
          cohesionX = (cohesionX / neighborCount - boid.x) * 0.0012;
          cohesionY = (cohesionY / neighborCount - boid.y) * 0.0012;

          boid.vx += alignmentX + cohesionX;
          boid.vy += alignmentY + cohesionY;
        }

        boid.vx += separationX * 0.094;
        boid.vy += separationY * 0.094;

        if (pointer.active) {
          const pdx = boid.x - pointer.x;
          const pdy = boid.y - pointer.y;
          const pointerDistSq = pdx * pdx + pdy * pdy;
          if (pointerDistSq > 0 && pointerDistSq < pointerRadiusSq) {
            const pointerDist = Math.sqrt(pointerDistSq);
            const influence =
              ((POINTER_INFLUENCE_RADIUS - pointerDist) /
                POINTER_INFLUENCE_RADIUS) *
              0.085;
            boid.vx += (pdx / pointerDist) * influence;
            boid.vy += (pdy / pointerDist) * influence;
          }
        }

        if (foodDrop) {
          const fdx = foodDrop.x - boid.x;
          const fdy = foodDrop.y - boid.y;
          const foodDistSq = fdx * fdx + fdy * fdy;
          if (foodDistSq > 0 && foodDistSq < foodRadiusSq) {
            const foodDist = Math.sqrt(foodDistSq);
            const foodFalloff =
              (FOOD_INFLUENCE_RADIUS - foodDist) / FOOD_INFLUENCE_RADIUS;
            const influence =
              foodFalloff * foodFalloff * (0.035 + foodDrop.remaining * 0.11);
            boid.vx += (fdx / foodDist) * influence;
            boid.vy += (fdy / foodDist) * influence;
          }
        }

        boid.vx += (Math.random() - 0.5) * 0.013;
        boid.vy += (Math.random() - 0.5) * 0.013;

        [boid.vx, boid.vy] = clampSpeed(boid.vx, boid.vy);
        boid.x = wrapPosition(boid.x + boid.vx, width);
        boid.y = wrapPosition(boid.y + boid.vy, height);

        if (foodDrop) {
          const biteDx = boid.x - foodDrop.x;
          const biteDy = boid.y - foodDrop.y;
          const biteDistSq = biteDx * biteDx + biteDy * biteDy;
          if (biteDistSq < foodEatRadiusSq) {
            foodVisitors += 1;
          }
        }
      }

      if (foodDrop) {
        foodDrop.remaining = Math.max(
          0,
          foodDrop.remaining - foodVisitors * FOOD_CONSUMPTION_RATE * deltaMs,
        );
      }

      const connectionRadiusSq = CONNECTION_RADIUS * CONNECTION_RADIUS;
      for (let i = 0; i < boids.length; i += 1) {
        const boidA = boids[i];
        for (let j = i + 1; j < boids.length; j += 1) {
          const boidB = boids[j];
          const dx = boidB.x - boidA.x;
          const dy = boidB.y - boidA.y;
          const distanceSq = dx * dx + dy * dy;
          if (distanceSq >= connectionRadiusSq) continue;

          const distance = Math.sqrt(distanceSq);
          const alpha =
            ((CONNECTION_RADIUS - distance) / CONNECTION_RADIUS) * 0.22;
          const mx =
            (boidA.x + boidB.x) / 2 +
            Math.sin(now * 0.0016 + boidA.seed * 0.01 + boidB.seed * 0.01) *
              1.6;
          const my =
            (boidA.y + boidB.y) / 2 +
            Math.cos(now * 0.0013 + boidA.seed * 0.02 + boidB.seed * 0.02) *
              1.6;

          ctx.strokeStyle = `rgba(152, 116, 79, ${alpha.toFixed(3)})`;
          ctx.lineWidth = 0.9;
          ctx.beginPath();
          ctx.moveTo(boidA.x, boidA.y);
          ctx.quadraticCurveTo(mx, my, boidB.x, boidB.y);
          ctx.stroke();
        }
      }

      for (const boid of boids) {
        drawBoid(boid, now);
      }

      rafId = window.requestAnimationFrame(step);
    };

    const observer = new IntersectionObserver(
      ([entry]) => {
        isInViewport = entry?.isIntersecting ?? true;
        syncAnimationState();
      },
      { threshold: 0.1 },
    );
    const handleVisibilityChange = () => {
      isDocumentVisible = document.visibilityState === "visible";
      syncAnimationState();
    };
    const resizeObserver = new ResizeObserver(() => {
      resize();
    });

    resize();
    updateInteractionMode();
    seedBoids();
    ctx.fillStyle = "#f5e8d4";
    ctx.fillRect(0, 0, width, height);
    syncAnimationState();

    observer.observe(container);
    resizeObserver.observe(canvas);
    container.addEventListener("pointermove", updatePointer);
    container.addEventListener("pointerdown", handlePointerDown);
    container.addEventListener("pointerup", handlePointerEnd);
    container.addEventListener("pointercancel", handlePointerEnd);
    container.addEventListener("pointerleave", clearPointer);
    touchMedia.addEventListener("change", updateInteractionMode);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("resize", resize);

    return () => {
      observer.disconnect();
      resizeObserver.disconnect();
      container.removeEventListener("pointermove", updatePointer);
      container.removeEventListener("pointerdown", handlePointerDown);
      container.removeEventListener("pointerup", handlePointerEnd);
      container.removeEventListener("pointercancel", handlePointerEnd);
      container.removeEventListener("pointerleave", clearPointer);
      touchMedia.removeEventListener("change", updateInteractionMode);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("resize", resize);
      stopAnimation();
    };
  }, []);

  return (
    <div
      ref={containerRef}
      className="rounded-[18px] border border-[#d8c2a1] bg-[#efe0ca] p-3 shadow-[0_16px_30px_-26px_rgba(96,63,35,0.55)]"
    >
      <div className="relative overflow-hidden rounded-[14px] border border-[#ceb593] bg-[#f5e9d4]">
        <canvas
          ref={canvasRef}
          className="h-[250px] w-full md:h-[330px]"
          aria-label="Murmuration simulation"
        />
        <div className="pointer-events-none absolute inset-0 shadow-[inset_0_0_52px_rgba(88,58,33,0.2),inset_0_6px_14px_rgba(112,76,45,0.22),inset_0_-8px_16px_rgba(83,56,34,0.16)]" />
      </div>
    </div>
  );
}
