import type { EpisodeProps, Scene } from "./types";
import { TRANSITION_FRAMES } from "./theme";

/** Used only when a scene has no audio yet (e.g. previewing an un-narrated script). */
const FALLBACK_SCENE_SEC = 4;

/** Scene = lead-in (new picture before the voice) + narration + padding (silence after it). */
export const sceneFrames = (scene: Scene, fps: number, paddingSec: number, leadInSec = 0): number => {
  const sec = leadInSec + (scene.audio?.duration_sec ?? FALLBACK_SCENE_SEC) + paddingSec;
  // each scene must be longer than the two crossfades that overlap it
  return Math.max(Math.round(sec * fps), TRANSITION_FRAMES * 2 + 1);
};

/** Total = sum of scene lengths minus the crossfade overlaps. */
export const episodeFrames = (props: EpisodeProps): number => {
  const { scenes, video } = props.episode;
  const sum = scenes.reduce((acc, s) => acc + sceneFrames(s, video.fps, props.paddingSec, props.leadInSec ?? 0), 0);
  return Math.max(1, sum - TRANSITION_FRAMES * Math.max(0, scenes.length - 1));
};
