// Load Noto Sans Devanagari from remotion/public/fonts (no network at render time).
// delayRender blocks every frame until the font is ready, so no frame renders with a fallback font.
import { cancelRender, continueRender, delayRender, staticFile } from "remotion";
import { theme } from "./theme";

const FONT_FILE = "fonts/NotoSansDevanagari-Variable.ttf";

let loaded: Promise<void> | null = null;

export const ensureFontLoaded = (): Promise<void> => {
  if (loaded) return loaded;
  const handle = delayRender(`Loading font ${theme.font.family}`);
  const face = new FontFace(theme.font.family, `url('${staticFile(FONT_FILE)}') format('truetype')`, {
    weight: "100 900",
    style: "normal",
  });
  loaded = face
    .load()
    .then(() => {
      document.fonts.add(face);
      // also wait for layout-ready state of all faces
      return document.fonts.ready.then(() => undefined);
    })
    .then(() => continueRender(handle))
    .catch((err) => cancelRender(err));
  return loaded;
};

ensureFontLoaded();
