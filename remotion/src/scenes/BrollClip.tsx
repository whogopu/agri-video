import React from "react";
import { AbsoluteFill, OffthreadVideo, useVideoConfig } from "remotion";
import { useTheme } from "../theme";

// Muted clip trimmed to [inSec, outSec]. If the segment is shorter than the scene,
// it is slowed down (not below 0.5×) to cover it; the visuals stage should pick
// segments long enough that this rarely happens.
export const BrollClip: React.FC<{ src: string; inSec: number; outSec: number; durationInFrames: number }> = ({
  src,
  inSec,
  outSec,
  durationInFrames,
}) => {
  const theme = useTheme();
  const { fps } = useVideoConfig();
  const segFrames = Math.max(1, Math.round((outSec - inSec) * fps));
  const playbackRate = segFrames >= durationInFrames ? 1 : Math.max(0.5, segFrames / durationInFrames);

  return (
    <AbsoluteFill style={{ backgroundColor: theme.colors.background }}>
      <OffthreadVideo
        src={src}
        muted
        trimBefore={Math.round(inSec * fps)}
        trimAfter={Math.round(outSec * fps)}
        playbackRate={playbackRate}
        style={{ width: "100%", height: "100%", objectFit: "cover" }}
      />
    </AbsoluteFill>
  );
};
