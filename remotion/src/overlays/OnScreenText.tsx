import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { fontFamily, useTheme } from "../theme";

// Short keyword (1–4 words) top-left, styled as a brand-green tag (different from captions).
export const OnScreenText: React.FC<{ text: string }> = ({ text }) => {
  const theme = useTheme();
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - 6, fps, config: { damping: 200 } });
  const o = theme.onScreenText;

  return (
    <AbsoluteFill style={{ padding: `${theme.safe.y}px ${theme.safe.x}px`, alignItems: "flex-start" }}>
      <div
        style={{
          display: "flex",
          alignItems: "stretch",
          borderRadius: o.radius,
          overflow: "hidden",
          boxShadow: "0 6px 24px rgba(0,0,0,0.35)",
          opacity: s,
          transform: `translateX(${interpolate(s, [0, 1], [-80, 0])}px)`,
        }}
      >
        <div style={{ width: 14, background: theme.colors.primaryDark }} />
        <div
          style={{
            background: theme.colors.primary,
            color: theme.colors.text,
            fontFamily,
            fontSize: o.fontSize,
            fontWeight: o.fontWeight,
            lineHeight: theme.font.lineHeight,
            padding: "4px 32px 8px 24px",
            textShadow: "0 2px 6px rgba(0,0,0,0.25)",
          }}
        >
          {text}
        </div>
      </div>
    </AbsoluteFill>
  );
};
