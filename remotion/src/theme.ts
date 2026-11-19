// One place for colors, sizes and margins. Two layouts:
//   landscape — px at 1920×1080 (long-format videos)
//   portrait  — px at 1080×1920 (YouTube Shorts). Shorts overlays its own UI at the
//               bottom (~25%: channel, title) and down the right side (like/comment
//               buttons), so captions and graphics sit higher and leave a right gutter.
// Draft renders use --scale, so values stay proportional.
// Brand colors are sampled from assets/brand/logo.png (see assets/brand/brand.json).
import { useVideoConfig } from "remotion";

const colors = {
  primary: "#3fb660", // logo "a" mark green
  primaryDark: "#0a6132", // logo wordmark green
  primaryDeep: "#063d1f", // darker shade for graphic backgrounds
  primaryTint: "#e9f7ee", // very light tint for text accents on dark backgrounds
  text: "#ffffff",
  textMuted: "rgba(255,255,255,0.82)",
  captionBg: "rgba(0,0,0,0.62)",
  background: "#000000",
};

const font = {
  family: "Noto Sans Devanagari",
  lineHeight: 1.5, // Devanagari needs room for matras above and below
};

export const TRANSITION_FRAMES = 10;

export const landscapeTheme = {
  orientation: "landscape" as "landscape" | "portrait",
  colors,
  font,
  // title-safe margins; `right` adds room on the right edge
  safe: { x: 96, y: 64, right: 96 },
  captions: { fontSize: 56, fontWeight: 600, maxWidth: 1500, bottom: 72, padX: 28, padY: 10, radius: 14 },
  onScreenText: { fontSize: 60, fontWeight: 800, radius: 16 },
  watermark: { logoHeight: 56, opacity: 0.75 },
  kenBurns: { minScale: 1.02, maxScale: 1.12 },
  graphics: {
    titleSize: 112,
    subtitleSize: 56,
    pointSize: 64,
    bigNumberSize: 300,
    unitSize: 110,
    labelSize: 64,
    // keep graphic content above the caption band
    contentBottom: 220,
  },
  transitionFrames: TRANSITION_FRAMES,
};

export type Theme = typeof landscapeTheme;

export const portraitTheme: Theme = {
  ...landscapeTheme,
  orientation: "portrait",
  safe: { x: 64, y: 200, right: 170 },
  captions: { fontSize: 64, fontWeight: 700, maxWidth: 860, bottom: 500, padX: 24, padY: 10, radius: 16 },
  onScreenText: { fontSize: 60, fontWeight: 800, radius: 16 },
  watermark: { logoHeight: 52, opacity: 0.75 },
  graphics: {
    titleSize: 100,
    subtitleSize: 54,
    pointSize: 56,
    bigNumberSize: 280,
    unitSize: 100,
    labelSize: 60,
    contentBottom: 680,
  },
};

export const themeFor = (width: number, height: number): Theme =>
  height > width ? portraitTheme : landscapeTheme;

/** Theme for the current composition's orientation. */
export const useTheme = (): Theme => {
  const { width, height } = useVideoConfig();
  return themeFor(width, height);
};

/** Orientation-independent values (colors, font) for code outside a composition. */
export const theme = landscapeTheme;

export const fontFamily = `"${font.family}", sans-serif`;
