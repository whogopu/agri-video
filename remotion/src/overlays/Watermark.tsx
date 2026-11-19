import React from "react";
import { AbsoluteFill, Img } from "remotion";
import { useTheme } from "../theme";

// The logo's wordmark is dark green on transparent, so it sits on a white pill
// to stay visible on dark footage.
export const Watermark: React.FC<{ src: string }> = ({ src }) => {
  const theme = useTheme();
  const w = theme.watermark;
  return (
    <AbsoluteFill style={{ padding: `${theme.safe.y}px ${theme.safe.x}px`, alignItems: "flex-end" }}>
      <div
        style={{
          opacity: w.opacity,
          background: "rgba(255,255,255,0.92)",
          borderRadius: 999,
          padding: "8px 22px",
          display: "flex",
        }}
      >
        <Img src={src} style={{ height: w.logoHeight }} />
      </div>
    </AbsoluteFill>
  );
};
