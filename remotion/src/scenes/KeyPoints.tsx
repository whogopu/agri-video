import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { fontFamily, useTheme } from "../theme";
import { GraphicBackground } from "./GraphicBackground";

/** cues: optional phrase per point (as in the narration) that makes it appear; resolved in pipeline/cues.py */
export type KeyPointsProps = { title?: string; points: string[]; cues?: (string | null)[] };

/** Frame each point appears: its cue frame (when the narrator starts on it), else the old even
 * schedule over the first 60% of the scene; never earlier than the point before. */
export const pointRevealFrames = (n: number, durationInFrames: number, cueFrames: (number | null)[] = []): number[] => {
  const step = n > 1 ? (durationInFrames * 0.6) / n : 0;
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const f = cueFrames[i] ?? Math.round(i * step);
    out.push(i > 0 ? Math.max(f, out[i - 1]) : f);
  }
  return out;
};

// The title shows at once; each point slides in when the narration reaches it.
export const KeyPoints: React.FC<KeyPointsProps & { durationInFrames: number; revealFrames?: (number | null)[] }> = ({
  title,
  points,
  durationInFrames,
  revealFrames,
}) => {
  const theme = useTheme();
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const g = theme.graphics;
  const inset = theme.orientation === "portrait" ? 0 : 80;
  const at = pointRevealFrames(points.length, durationInFrames, revealFrames);

  return (
    <GraphicBackground>
      <AbsoluteFill
        style={{
          justifyContent: "center",
          padding: `${theme.safe.y + 40}px ${theme.safe.right + inset}px ${g.contentBottom}px ${theme.safe.x + inset}px`,
          fontFamily,
          color: theme.colors.text,
        }}
      >
        {title ? (
          <div
            style={{
              fontSize: g.pointSize + 16,
              fontWeight: 800,
              lineHeight: theme.font.lineHeight,
              color: theme.colors.text,
              marginBottom: 24,
              paddingLeft: 28,
              borderLeft: `12px solid ${theme.colors.primary}`,
            }}
          >
            {title}
          </div>
        ) : null}
        {points.map((pt, i) => {
          const s = spring({ frame: frame - at[i], fps, config: { damping: 200 } });
          return (
            <div
              key={i}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 32,
                margin: "14px 0",
                opacity: s,
                transform: `translateX(${interpolate(s, [0, 1], [-60, 0])}px)`,
              }}
            >
              <div
                style={{
                  flex: "0 0 auto",
                  width: 64,
                  height: 64,
                  borderRadius: 32,
                  background: theme.colors.primary,
                  color: theme.colors.primaryDeep,
                  fontSize: 40,
                  fontWeight: 800,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                {i + 1}
              </div>
              <div style={{ fontSize: g.pointSize, fontWeight: 600, lineHeight: theme.font.lineHeight }}>{pt}</div>
            </div>
          );
        })}
      </AbsoluteFill>
    </GraphicBackground>
  );
};
