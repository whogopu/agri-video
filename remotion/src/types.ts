// Mirrors pipeline/schema.py (episode.json). Keep the two in sync.

export type CaptionWord = { text: string; start: number; end: number };

/** words: when each word is spoken (scene seconds); empty = no word timing, no highlight */
export type Caption = { text: string; start: number; end: number; words?: CaptionWord[] };

export type AudioWord = { text: string; start: number; end: number; segment: number; timed: boolean };

export type GraphicTemplate = "TitleCard" | "KeyPoints" | "BigNumber";

export type Shot = {
  /** the shot starts with this narration segment (0 = scene start) */
  at_segment: number;
  image_prompt?: string | null;
  characters?: string[];
  seed?: number | null;
  attempts?: number;
  image_file?: string | null;
  reference_sha1?: Record<string, string>;
  inspection?: { file_sha1: string; passed: boolean; notes?: string; inspected_at?: string } | null;
  notes?: string | null;
};

export type Visual = {
  type: "image" | "broll" | "graphic" | null;
  shots?: Shot[];
  broll_id?: string | null;
  in_sec?: number | null;
  out_sec?: number | null;
  template?: GraphicTemplate | null;
  props?: Record<string, unknown> | null;
  notes?: string | null;
};

export type Scene = {
  id: number;
  purpose: string;
  narration_display: string;
  narration_spoken?: string;
  on_screen_text?: string | null;
  visual: Visual;
  sources?: string[];
  audio?: {
    file: string;
    duration_sec: number;
    segments?: { text: string; start: number; end: number; style: string }[];
    /** when each displayed word is spoken (pipeline/word_align.py); empty until word timing has run */
    words?: AudioWord[];
  } | null;
  captions: Caption[];
};

export type Episode = {
  schema_version?: number;
  id: string;
  title_hi: string;
  status?: string;
  cast?: string[];
  format?: "long" | "short";
  video: { width: number; height: number; fps: number };
  voice?: Record<string, unknown>;
  scenes: Scene[];
  package?: Record<string, unknown>;
};

// Input props for the Episode composition. render.py builds these.
export type EpisodeProps = {
  episode: Episode;
  /** folder under remotion/public holding this episode's assets, e.g. "episodes/<id>" */
  assetBase: string;
  /** folder under remotion/public holding B-roll clips */
  brollBase: string;
  /** broll_id → file name inside brollBase (from assets/broll/index.json) */
  brollFiles: Record<string, string>;
  /** config.yaml video.scene_padding_sec: silence after a scene's narration (the crossfade sits in it) */
  paddingSec: number;
  /** config.yaml video.scene_lead_in_sec: the new picture shows this long before the narration starts */
  leadInSec?: number;
  /** looped room-tone file under the whole video (episode audio/room-tone.wav), or null */
  roomTone?: string | null;
  /** logo path under remotion/public, or null to hide the watermark */
  logo: string | null;
  /** caption font size in px at full resolution (config.yaml captions.font_size_px); theme default if absent */
  captionFontSize?: number;
  /** config.yaml captions.highlight_words: the word being spoken turns brand green */
  captionHighlight?: boolean;
  /** config.yaml captions.highlight_hold_sec: a word stays lit at most this long after it ends */
  captionHoldSec?: number;
};
