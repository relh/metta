"use client";

import { useEffect, useId, useRef, useState } from "react";

type Screenshot = {
  title: string;
  imageSrc: string;
  description: string;
  imageScale?: number;
  imageTransformOrigin?: string;
};

type Point = {
  x: number;
  y: number;
};

type CardRect = {
  left: number;
  top: number;
  width: number;
  height: number;
  centerX: number;
  centerY: number;
};

const HORIZONTAL_PAD = 40;
const VERTICAL_PAD = 28;
const ROW_TOLERANCE = 20;
const TURN_OUTSET = 16;
const WIGGLES = [8, -7, 6, -8, 5, -6];
const GRID_GAP_PX = 13.6;
const MIN_CARD_WIDTH_PX = 176;

function inferColumnCount(containerWidth: number): number {
  if (containerWidth <= 0) {
    return 1;
  }

  return Math.max(
    1,
    Math.min(
      4,
      Math.floor(
        (containerWidth + GRID_GAP_PX) / (MIN_CARD_WIDTH_PX + GRID_GAP_PX),
      ),
    ),
  );
}

function pathFromPoints(points: Point[]): string {
  if (points.length === 0) {
    return "";
  }

  if (points.length === 1) {
    return `M ${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)}`;
  }

  if (points.length === 2) {
    return `M ${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)} L ${points[1].x.toFixed(1)} ${points[1].y.toFixed(1)}`;
  }

  let path = `M ${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)}`;
  for (let i = 1; i < points.length - 1; i += 1) {
    const point = points[i];
    const nextPoint = points[i + 1];
    const midX = (point.x + nextPoint.x) / 2;
    const midY = (point.y + nextPoint.y) / 2;
    path += ` Q ${point.x.toFixed(1)} ${point.y.toFixed(1)} ${midX.toFixed(1)} ${midY.toFixed(1)}`;
  }

  const penultimatePoint = points[points.length - 2];
  const lastPoint = points[points.length - 1];
  path += ` Q ${penultimatePoint.x.toFixed(1)} ${penultimatePoint.y.toFixed(1)} ${lastPoint.x.toFixed(1)} ${lastPoint.y.toFixed(1)}`;
  return path;
}

function buildSnakePath(cards: CardRect[], containerWidth: number): string {
  if (cards.length === 0) {
    return "";
  }

  const rows: CardRect[][] = [];
  const sortedCards = [...cards].sort(
    (a, b) => a.top - b.top || a.left - b.left,
  );

  for (const card of sortedCards) {
    const lastRow = rows.at(-1);
    if (!lastRow || Math.abs(card.top - lastRow[0].top) > ROW_TOLERANCE) {
      rows.push([card]);
      continue;
    }

    lastRow.push(card);
  }

  for (const row of rows) {
    row.sort((a, b) => a.left - b.left);
  }

  const points: Point[] = [];
  let wiggleIndex = 0;

  const pushPoint = (point: Point) => {
    const previous = points.at(-1);
    if (
      previous &&
      Math.abs(previous.x - point.x) < 0.5 &&
      Math.abs(previous.y - point.y) < 0.5
    ) {
      return;
    }

    points.push(point);
  };

  const cardCenter = (card: CardRect): Point => ({
    x: card.centerX + HORIZONTAL_PAD,
    y: card.centerY + VERTICAL_PAD,
  });

  for (let rowIndex = 0; rowIndex < rows.length; rowIndex += 1) {
    const row = rows[rowIndex];
    const orderedRow = rowIndex % 2 === 0 ? row : [...row].reverse();

    for (let cardIndex = 0; cardIndex < orderedRow.length; cardIndex += 1) {
      const point = cardCenter(orderedRow[cardIndex]);

      if (points.length > 0) {
        const previous = points[points.length - 1];
        if (Math.abs(previous.y - point.y) <= 1) {
          pushPoint({
            x: (previous.x + point.x) / 2,
            y: previous.y + WIGGLES[wiggleIndex % WIGGLES.length],
          });
          wiggleIndex += 1;
        }
      }

      pushPoint(point);
    }

    if (rowIndex === rows.length - 1) {
      continue;
    }

    const rowEnd = cardCenter(orderedRow[orderedRow.length - 1]);
    const nextRow = rows[rowIndex + 1];
    const nextOrderedRow =
      (rowIndex + 1) % 2 === 0 ? nextRow : [...nextRow].reverse();
    const nextStart = cardCenter(nextOrderedRow[0]);
    const direction = rowIndex % 2 === 0 ? 1 : -1;
    const edgeX =
      direction > 0
        ? containerWidth + HORIZONTAL_PAD + TURN_OUTSET
        : HORIZONTAL_PAD - TURN_OUTSET;
    const bendY = (rowEnd.y + nextStart.y) / 2;
    const rowGap = Math.max(42, Math.abs(nextStart.y - rowEnd.y));

    pushPoint({
      x: rowEnd.x + direction * 18,
      y: rowEnd.y + WIGGLES[wiggleIndex % WIGGLES.length] * 0.4,
    });
    wiggleIndex += 1;

    pushPoint({
      x: edgeX - direction * 16,
      y: rowEnd.y + rowGap * 0.14,
    });
    wiggleIndex += 1;

    pushPoint({
      x: edgeX + direction * 18,
      y: bendY - rowGap * 0.22 + WIGGLES[wiggleIndex % WIGGLES.length] * 0.45,
    });
    wiggleIndex += 1;

    pushPoint({
      x: edgeX - direction * 24,
      y: bendY + rowGap * 0.26 + WIGGLES[wiggleIndex % WIGGLES.length] * 0.45,
    });
    wiggleIndex += 1;

    pushPoint({
      x: edgeX + direction * 12,
      y: nextStart.y - rowGap * 0.12,
    });
    wiggleIndex += 1;

    pushPoint({
      x: nextStart.x - direction * 20,
      y: nextStart.y + WIGGLES[wiggleIndex % WIGGLES.length] * 0.4,
    });
    wiggleIndex += 1;

    pushPoint(nextStart);
  }

  const lastRow = rows[rows.length - 1];
  const lastOrderedRow =
    (rows.length - 1) % 2 === 0 ? lastRow : [...lastRow].reverse();
  const lastPoint = cardCenter(lastOrderedRow[lastOrderedRow.length - 1]);
  const finalDirection = (rows.length - 1) % 2 === 0 ? 1 : -1;

  pushPoint({
    x: lastPoint.x + finalDirection * 16,
    y: lastPoint.y + WIGGLES[wiggleIndex % WIGGLES.length] * 0.45,
  });
  wiggleIndex += 1;

  pushPoint({
    x: lastPoint.x + finalDirection * 34,
    y: lastPoint.y + WIGGLES[wiggleIndex % WIGGLES.length] * 0.22,
  });

  return pathFromPoints(points);
}

function ScreenshotCard({
  stepNumber,
  title,
  imageSrc,
  description,
  imageScale,
  imageTransformOrigin,
  isTouchMode,
  isOpen,
  onToggle,
  refCallback,
}: Screenshot & {
  stepNumber: number;
  isTouchMode: boolean;
  isOpen: boolean;
  onToggle: () => void;
  refCallback: (node: HTMLElement | null) => void;
}) {
  return (
    <article
      ref={refCallback}
      className="cogsguard-shot"
      data-touch={isTouchMode ? "true" : "false"}
      data-open={isOpen ? "true" : "false"}
      role={isTouchMode ? "button" : undefined}
      aria-pressed={isTouchMode ? isOpen : undefined}
      tabIndex={0}
      onClick={isTouchMode ? onToggle : undefined}
      onKeyDown={
        isTouchMode
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onToggle();
              }
            }
          : undefined
      }
      style={{
        position: "relative",
        zIndex: 1,
        border: "1px solid #e4dac8",
        background: "#fffaf0",
        padding: "0.45rem",
        cursor: isTouchMode ? "pointer" : "default",
      }}
    >
      <div
        className="cogsguard-shot-frame"
        style={{
          position: "relative",
          overflow: "hidden",
          aspectRatio: "1 / 1",
          border: "1px solid #ddd1bd",
          background: "#f6f1e7",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <img
          src={imageSrc}
          alt={title}
          style={{
            display: "block",
            width: "100%",
            height: "100%",
            objectFit: "cover",
            transform: `scale(${imageScale ?? 1})`,
            transformOrigin: imageTransformOrigin ?? "50% 50%",
          }}
        />
        <div className="cogsguard-shot-overlay">
          <div style={{ textAlign: "center" }}>
            <div
              style={{
                font: "600 28px/1 'Merriweather Sans', sans-serif",
                color: "rgba(255, 253, 244, 0.96)",
                marginBottom: "0.4rem",
              }}
            >
              {stepNumber}
            </div>
            <h3
              style={{
                font: "600 14px/20px 'Merriweather Sans', sans-serif",
                color: "#fffdf4",
                margin: 0,
              }}
            >
              {title}
            </h3>
            <p
              style={{
                font: "400 12px/18px 'Merriweather Sans', sans-serif",
                color: "rgba(255, 253, 244, 0.92)",
                margin: "0.35rem 0 0",
              }}
            >
              {description}
            </p>
          </div>
        </div>
      </div>
    </article>
  );
}

export function CogsguardScreenshotGallery({
  screenshots,
}: {
  screenshots: Screenshot[];
}) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const cardRefs = useRef<(HTMLElement | null)[]>([]);
  const markerId = useId();
  const [containerWidth, setContainerWidth] = useState(0);
  const [isTouchMode, setIsTouchMode] = useState(false);
  const [showArrow, setShowArrow] = useState(true);
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const [pathState, setPathState] = useState({
    width: 1,
    height: 1,
    path: "",
  });
  const columnCount = inferColumnCount(containerWidth);

  useEffect(() => {
    const touchMedia = window.matchMedia("(hover: none), (pointer: coarse)");
    const arrowMedia = window.matchMedia("(min-width: 768px)");

    const updateInteractionMode = () => {
      setIsTouchMode(touchMedia.matches);
      setShowArrow(arrowMedia.matches);
    };

    updateInteractionMode();
    touchMedia.addEventListener("change", updateInteractionMode);
    arrowMedia.addEventListener("change", updateInteractionMode);

    return () => {
      touchMedia.removeEventListener("change", updateInteractionMode);
      arrowMedia.removeEventListener("change", updateInteractionMode);
    };
  }, []);

  useEffect(() => {
    if (!isTouchMode) {
      setOpenIndex(null);
    }
  }, [isTouchMode]);

  useEffect(() => {
    let frameId = 0;

    const updateWidth = () => {
      cancelAnimationFrame(frameId);
      frameId = window.requestAnimationFrame(() => {
        const wrapper = wrapperRef.current;
        if (!wrapper) {
          return;
        }

        setContainerWidth(
          Math.min(wrapper.getBoundingClientRect().width, window.innerWidth),
        );
      });
    };

    updateWidth();

    const observer = new ResizeObserver(updateWidth);
    const wrapper = wrapperRef.current;
    if (wrapper) {
      observer.observe(wrapper);
    }
    window.addEventListener("resize", updateWidth);

    return () => {
      cancelAnimationFrame(frameId);
      observer.disconnect();
      window.removeEventListener("resize", updateWidth);
    };
  }, []);

  useEffect(() => {
    let frameId = 0;

    const updatePath = () => {
      cancelAnimationFrame(frameId);
      frameId = window.requestAnimationFrame(() => {
        const wrapper = wrapperRef.current;
        if (!wrapper || !showArrow) {
          setPathState({
            width: 1,
            height: 1,
            path: "",
          });
          return;
        }

        const wrapperRect = wrapper.getBoundingClientRect();
        const cards = cardRefs.current.filter(
          (card): card is HTMLElement => card !== null,
        );

        const measuredCards = cards.map((card) => {
          const rect = card.getBoundingClientRect();
          return {
            left: rect.left - wrapperRect.left,
            top: rect.top - wrapperRect.top,
            width: rect.width,
            height: rect.height,
            centerX: rect.left - wrapperRect.left + rect.width / 2,
            centerY: rect.top - wrapperRect.top + rect.height / 2,
          };
        });

        setPathState({
          width: Math.max(1, wrapperRect.width + HORIZONTAL_PAD * 2),
          height: Math.max(1, wrapperRect.height + VERTICAL_PAD * 2),
          path: buildSnakePath(measuredCards, wrapperRect.width),
        });
      });
    };

    updatePath();

    const observer = new ResizeObserver(updatePath);
    const wrapper = wrapperRef.current;
    if (wrapper) {
      observer.observe(wrapper);
    }

    for (const card of cardRefs.current) {
      if (card) {
        observer.observe(card);
      }
    }

    window.addEventListener("resize", updatePath);

    return () => {
      cancelAnimationFrame(frameId);
      observer.disconnect();
      window.removeEventListener("resize", updatePath);
    };
  }, [columnCount, screenshots.length, showArrow]);

  return (
    <div
      ref={wrapperRef}
      style={{
        position: "relative",
        width: "100%",
        maxWidth: "100%",
        overflowX: showArrow ? "visible" : "hidden",
      }}
    >
      {showArrow ? (
        <svg
          aria-hidden="true"
          viewBox={`0 0 ${pathState.width} ${pathState.height}`}
          style={{
            position: "absolute",
            inset: `-${VERTICAL_PAD}px -${HORIZONTAL_PAD}px`,
            width: `calc(100% + ${HORIZONTAL_PAD * 2}px)`,
            height: `calc(100% + ${VERTICAL_PAD * 2}px)`,
            pointerEvents: "none",
            overflow: "visible",
            zIndex: 0,
          }}
        >
          <defs>
            <marker
              id={markerId}
              markerWidth="9"
              markerHeight="9"
              refX="8"
              refY="4.5"
              orient="auto"
            >
              <path d="M 0 0 L 9 4.5 L 0 9 Q 3 4.5 0 0" fill="#63779e" />
            </marker>
          </defs>
          {pathState.path ? (
            <>
              <path
                d={pathState.path}
                fill="none"
                stroke="rgba(255, 253, 244, 0.92)"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="10.5"
              />
              <path
                d={pathState.path}
                fill="none"
                stroke="rgba(70, 88, 129, 0.58)"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="4.2"
                markerEnd={`url(#${markerId})`}
              />
            </>
          ) : null}
        </svg>
      ) : null}

      <div
        style={{
          position: "relative",
          zIndex: 1,
          display: "grid",
          gridTemplateColumns: `repeat(${Math.max(1, columnCount)}, minmax(0, 1fr))`,
          gap: "0.85rem",
        }}
      >
        {screenshots.map((screenshot, index) => {
          return (
            <ScreenshotCard
              key={screenshot.title}
              stepNumber={index + 1}
              isTouchMode={isTouchMode}
              isOpen={openIndex === index}
              onToggle={() => {
                setOpenIndex((currentIndex) =>
                  currentIndex === index ? null : index,
                );
              }}
              {...screenshot}
              refCallback={(node) => {
                cardRefs.current[index] = node;
              }}
            />
          );
        })}
      </div>
    </div>
  );
}
