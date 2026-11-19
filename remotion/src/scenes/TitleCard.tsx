import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { fontFamily, useTheme } from "../theme";
import { GraphicBackground } from "./GraphicBackground";

export type TitleCardProps = { title: string; subtitle?: string };

export const TitleCard: React.FC<TitleCardProps> = ({ title, subtitle }) => {
  const theme = useTheme();
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 200 } });
  const bar = spring({ frame: frame - 8, fps, config: { damping: 200 } });
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
          style={{
            color: theme.colors.text,
            fontSize: g.titleSize,
            fontWeight: 800,
            lineHeight: theme.font.lineHeight,
            opacity: enter,
            transform: `translateY(${interpolate(enter, [0, 1], [40, 0])}px)`,
          }}
        >
          {title}
        </div>
        <div
          style={{
            height: 10,
            width: 360 * bar,
            borderRadius: 5,
            background: theme.colors.primary,
            margin: "28px 0",
          }}
        />
        {subtitle ? (
          <div
            style={{
              color: theme.colors.primaryTint,
              fontSize: g.subtitleSize,
              fontWeight: 500,
              lineHeight: theme.font.lineHeight,
              opacity: bar,
            }}
          >
            {subtitle}
          </div>
        ) : null}
      </AbsoluteFill>
    </GraphicBackground>
  );
};
