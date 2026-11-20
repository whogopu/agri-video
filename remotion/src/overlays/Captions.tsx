import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { fontFamily, useTheme } from "../theme";
import type { Caption, CaptionWord } from "../types";

/** Index of the word being spoken at time t, or -1. A word is lit from its start until the next
 * word starts, but at most `holdSec` past its own end, so a comma pause or the pause after a
 * sentence shows no highlight. */
export const activeWordIndex = (words: CaptionWord[], t: number, holdSec: number): number => {
  for (let i = words.length - 1; i >= 0; i--) {
    const w = words[i];
    if (t >= w.start) {
      const next = i + 1 < words.length ? words[i + 1].start : Infinity;
      return t < Math.min(next, w.end + holdSec) ? i : -1;
    }
  }
  return -1;
};

// Bottom-centered caption chunk for the current time (scene-relative seconds).
// With word timings, the word being spoken is drawn in the brand green. Only the colour
// changes (no weight or size change), so the line never reflows while it is read.
export const Captions: React.FC<{
  captions: Caption[];
  fontSize?: number;
  highlight?: boolean;
  holdSec?: number;
}> = ({ captions, fontSize, highlight = true, holdSec = 0.25 }) => {
  const theme = useTheme();
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const active = captions.find((c) => t >= c.start && t < c.end);
  if (!active) return null;
  const c = theme.captions;
  const words = highlight ? active.words ?? [] : [];
  const lit = words.length ? activeWordIndex(words, t, holdSec) : -1;

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom: c.bottom,
        paddingLeft: theme.safe.x,
        paddingRight: theme.safe.right,
      }}
    >
      <div
        style={{
          maxWidth: c.maxWidth,
          padding: `${c.padY}px ${c.padX}px`,
          borderRadius: c.radius,
          background: theme.colors.captionBg,
        }}
      >
        <div
          style={{
            color: theme.colors.text,
            fontFamily,
            fontSize: fontSize ?? c.fontSize,
            fontWeight: c.fontWeight,
            lineHeight: theme.font.lineHeight,
            textAlign: "center",
            // never more than 2 lines (captions.py should keep chunks short; this is a safety net)
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
            maxHeight: `${2 * theme.font.lineHeight}em`,
          }}
        >
          {words.length
            ? words.map((w, i) => (
                <React.Fragment key={i}>
                  {i > 0 ? " " : null}
                  <span style={i === lit ? { color: theme.colors.captionHighlight } : undefined}>{w.text}</span>
                </React.Fragment>
              ))
            : active.text}
        </div>
      </div>
    </AbsoluteFill>
  );
};
