import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { fontFamily, useTheme } from "../theme";
import type { Caption } from "../types";

// Bottom-centered caption chunk for the current time (scene-relative seconds).
export const Captions: React.FC<{ captions: Caption[]; fontSize?: number }> = ({ captions, fontSize }) => {
  const theme = useTheme();
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const active = captions.find((c) => t >= c.start && t < c.end);
  if (!active) return null;
  const c = theme.captions;

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
          {active.text}
        </div>
      </div>
    </AbsoluteFill>
  );
};
