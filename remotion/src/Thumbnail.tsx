import React from "react";
import { AbsoluteFill, Img, staticFile, useVideoConfig } from "remotion";
import "./fonts";
import { fontFamily, theme } from "./theme";

// YouTube thumbnail: a strong episode image, a big 3–5 word Hindi title, the brand.
// Long videos: 1280×720. Shorts: 1080×1920 (cover frame). Size comes from props (calculateMetadata).
export type ThumbnailProps = {
  text: string;
  image: string | null; // path under remotion/public
  logo: string | null;
  width: number;
  height: number;
};

export const Thumbnail: React.FC<ThumbnailProps> = ({ text, image, logo }) => {
  const { width, height } = useVideoConfig();
  const portrait = height > width;
  const u = Math.min(width, height) / 720; // scale unit (1 at 1280×720)
  const pad = 44 * u;

  return (
    <AbsoluteFill style={{ backgroundColor: theme.colors.primaryDeep, fontFamily }}>
      {image ? (
        <Img src={staticFile(image)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      ) : null}
      {/* darken the text side so the title reads on any image */}
      <AbsoluteFill
        style={{
          background: portrait
            ? "linear-gradient(to top, rgba(4,30,16,0.92) 0%, rgba(4,30,16,0.75) 35%, rgba(0,0,0,0) 65%)"
            : "linear-gradient(to right, rgba(4,30,16,0.92) 0%, rgba(4,30,16,0.7) 45%, rgba(0,0,0,0) 75%)",
        }}
      />
      <AbsoluteFill
        style={{
          padding: pad,
          justifyContent: portrait ? "flex-end" : "center",
          paddingBottom: portrait ? 420 * (width / 1080) : pad,
        }}
      >
        <div style={{ width: portrait ? "100%" : "46%" }}>
          <div
            style={{
              width: 120 * u,
              height: 14 * u,
              borderRadius: 7 * u,
              background: theme.colors.primary,
              marginBottom: 22 * u,
            }}
          />
          <div
            style={{
              color: theme.colors.text,
              fontSize: (portrait ? 118 : 96) * u,
              fontWeight: 900,
              lineHeight: 1.32,
              // no text-stroke: the variable font's overlapping contours show stroke lines inside glyphs
              textShadow: `0 ${3 * u}px ${6 * u}px rgba(0,0,0,0.5), 0 ${6 * u}px ${24 * u}px rgba(0,0,0,0.45)`,
            }}
          >
            {text}
          </div>
        </div>
      </AbsoluteFill>
      {logo ? (
        <AbsoluteFill style={{ padding: pad, alignItems: "flex-end" }}>
          <div
            style={{
              background: "rgba(255,255,255,0.95)",
              borderRadius: 999,
              padding: `${8 * u}px ${22 * u}px`,
              display: "flex",
            }}
          >
            <Img src={staticFile(logo)} style={{ height: 56 * u }} />
          </div>
        </AbsoluteFill>
      ) : null}
    </AbsoluteFill>
  );
};
