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

/**
 * Start frame of each shot of an image scene, relative to the scene start (lead-in included).
 * A shot starting at narration segment j>0 cuts in the middle of the pause before that sentence;
 * without segment timings the shots split the narration evenly.
 * Mirrors pipeline/common.py shot_starts_sec: change both together.
 */
export const shotStartFrames = (scene: Scene, fps: number, leadInSec = 0): number[] => {
  const shots = scene.visual.shots ?? [];
  const segs = scene.audio?.segments ?? [];
  const dur = scene.audio?.duration_sec ?? FALLBACK_SCENE_SEC;
  return shots.map((sh, k) => {
    const j = sh.at_segment;
    let sec = 0;
    if (j === 0) sec = 0;
    else if (segs.length > 0 && j < segs.length) sec = leadInSec + (segs[j - 1].end + segs[j].start) / 2;
    else sec = leadInSec + (dur * k) / shots.length;
    return Math.round(sec * fps);
  });
};
