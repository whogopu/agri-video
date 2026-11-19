import React from "react";
import { AbsoluteFill, Easing, Img, interpolate, useCurrentFrame } from "remotion";
import { useTheme } from "../theme";

// Deterministic motion per scene id so re-renders are identical.
const MOVES = [
  { zoomIn: true, panX: 1, panY: 0 },
  { zoomIn: false, panX: -1, panY: 0 },
  { zoomIn: true, panX: -1, panY: 1 },
  { zoomIn: false, panX: 1, panY: -1 },
] as const;

export const KenBurnsImage: React.FC<{ src: string; sceneId: number; durationInFrames: number }> = ({
  src,
  sceneId,
  durationInFrames,
}) => {
  const theme = useTheme();
  const frame = useCurrentFrame();
  const move = MOVES[sceneId % MOVES.length];
  const { minScale, maxScale } = theme.kenBurns;
  const p = interpolate(frame, [0, durationInFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.sin),
  });
  const scale = move.zoomIn ? minScale + (maxScale - minScale) * p : maxScale - (maxScale - minScale) * p;
  // Pan stays inside the zoom margin so image edges never show.
  const room = ((scale - 1) / 2) * 0.9 * 100; // % of frame
  const tx = move.panX * room * (p - 0.5) * 2;
  const ty = move.panY * room * (p - 0.5) * 2;

  return (
    <AbsoluteFill style={{ backgroundColor: theme.colors.background, overflow: "hidden" }}>
      <Img
        src={src}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform: `translate(${tx}%, ${ty}%) scale(${scale})`,
        }}
      />
    </AbsoluteFill>
  );
};
