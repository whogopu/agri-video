import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { fontFamily, useTheme } from "../theme";
import { GraphicBackground } from "./GraphicBackground";

// `number` is a string so ranges like "10-12" or "₹2,500" work as written in the script.
export type BigNumberProps = { number: string; unit?: string; label?: string };

export const BigNumber: React.FC<BigNumberProps> = ({ number, unit, label }) => {
  const theme = useTheme();
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 12, stiffness: 120 } });
  const labelIn = spring({ frame: frame - 10, fps, config: { damping: 200 } });
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
        <div style={{ display: "flex", alignItems: "baseline", gap: 28, transform: `scale(${pop})` }}>
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
