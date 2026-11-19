import type { EpisodeProps, Scene } from "./types";
import { TRANSITION_FRAMES } from "./theme";

/** Used only when a scene has no audio yet (e.g. previewing an un-narrated script). */
const FALLBACK_SCENE_SEC = 4;

export const sceneFrames = (scene: Scene, fps: number, paddingSec: number): number => {
  const sec = (scene.audio?.duration_sec ?? FALLBACK_SCENE_SEC) + paddingSec;
  // each scene must be longer than the two crossfades that overlap it
  return Math.max(Math.round(sec * fps), TRANSITION_FRAMES * 2 + 1);
};

/** Total = sum of scene lengths minus the crossfade overlaps. */
export const episodeFrames = (props: EpisodeProps): number => {
  const { scenes, video } = props.episode;
  const sum = scenes.reduce((acc, s) => acc + sceneFrames(s, video.fps, props.paddingSec), 0);
  return Math.max(1, sum - TRANSITION_FRAMES * Math.max(0, scenes.length - 1));
};
