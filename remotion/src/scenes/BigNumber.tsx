import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { fontFamily, useTheme } from "../theme";
import { GraphicBackground } from "./GraphicBackground";

// `number` is a string so ranges like "10-12" or "₹2,500" work as written in the script.
// cue: optional phrase (as in the narration) at which the number pops; resolved in pipeline/cues.py.
export type BigNumberProps = { number: string; unit?: string; label?: string; cue?: string | null };

/** brightness of a cued number before it is spoken (user choice 2026-11-20: faint, never an empty screen) */
export const FAINT_OPACITY = 0.3;

// revealFrame > 0 (a cue): number, unit and label fade in together at the scene start, the number
// faint; when it is spoken it brightens and pops (a short swell above full size and back), so the
// screen is never empty and the label always reads with its number ("3 साल का एक चक्र").
// revealFrame 0 = old behaviour (the number springs in at once, the label after).
export const BigNumber: React.FC<BigNumberProps & { revealFrame?: number }> = ({ number, unit, label, revealFrame = 0 }) => {
  const theme = useTheme();
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const cued = revealFrame > 0;
  const intro = spring({ frame: frame - 4, fps, config: { damping: 200 } });
  const hit = spring({ frame: frame - revealFrame, fps, config: { damping: 12, stiffness: 120 } });
  // cued: scale 1 → ~1.12 → 1 around the cue; brightness FAINT → 1
  const swell = cued ? 1 + 0.12 * Math.sin(Math.PI * Math.min(1, Math.max(0, (frame - revealFrame) / (0.45 * fps)))) : hit;
  const numberOpacity = cued ? intro * interpolate(hit, [0, 1], [FAINT_OPACITY, 1], { extrapolateRight: "clamp" }) : 1;
  const labelIn = cued ? intro : spring({ frame: frame - 10, fps, config: { damping: 200 } });
  const g = theme.graphics;

  return (
    <GraphicBackground>
      <AbsoluteFill
        style={{
          justifyContent: "center",
          alignItems: "center",
          padding: `${theme.safe.y}px ${theme.safe.right}px ${g.contentBottom}px ${theme.safe.x}px`,
          fontFamily,
          textAlign: "center",
        }}
      >
        <div
          style={{ display: "flex", alignItems: "baseline", gap: 28, transform: `scale(${swell})`, opacity: numberOpacity }}
        >
          <span style={{ fontSize: g.bigNumberSize, fontWeight: 800, lineHeight: 1.1, color: theme.colors.primary }}>
            {number}
          </span>
          {unit ? (
            <span style={{ fontSize: g.unitSize, fontWeight: 700, color: theme.colors.text, lineHeight: 1.3 }}>
              {unit}
            </span>
          ) : null}
        </div>
        {label ? (
          <div
            style={{
              marginTop: 12,
              fontSize: g.labelSize,
              fontWeight: 600,
              lineHeight: theme.font.lineHeight,
              color: theme.colors.primaryTint,
              opacity: labelIn,
              transform: `translateY(${interpolate(labelIn, [0, 1], [24, 0])}px)`,
            }}
          >
            {label}
          </div>
        ) : null}
      </AbsoluteFill>
    </GraphicBackground>
  );
};
