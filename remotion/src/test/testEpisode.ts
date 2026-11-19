// Phase 2 test composition: ~20 s, every scene and overlay component, placeholder assets
// from scripts/make-test-assets.sh, dummy tone audio. Text includes the Devanagari test words.
import type { EpisodeProps } from "../types";

export const testEpisodeProps: EpisodeProps = {
  assetBase: "test",
  brollBase: "test/broll",
  brollFiles: { "test-clip": "test-clip.mp4" },
  paddingSec: 0.35,
  logo: "brand/logo.png",
  episode: {
    id: "test-components",
    title_hi: "कंपोनेंट टेस्ट",
    format: "long",
    video: { width: 1920, height: 1080, fps: 30 },
    scenes: [
      {
        id: 1,
        purpose: "hook",
        narration_display: "मिट्टी की जांच क्यों ज़रूरी है?",
        visual: {
          type: "graphic",
          template: "TitleCard",
          props: { title: "मिट्टी की जांच क्यों ज़रूरी है", subtitle: "कृषि सलाहकार की सलाह" },
        },
        audio: { file: "audio/scene-01.wav", duration_sec: 3.2 },
        captions: [{ text: "मिट्टी की जांच क्यों ज़रूरी है?", start: 0, end: 3.2 }],
      },
      {
        id: 2,
        purpose: "explain",
        narration_display: "इस क्षेत्र के श्रमिक द्वारा कृषि में ज़्यादा मेहनत होती है।",
        on_screen_text: "क्षेत्र और श्रमिक",
        visual: { type: "image", image_prompt: "placeholder", seed: 1 },
        image_file: "images/scene-02.png",
        audio: { file: "audio/scene-02.wav", duration_sec: 4.5 },
        captions: [
          { text: "इस क्षेत्र के श्रमिक द्वारा", start: 0, end: 2.2 },
          // deliberately long chunk to test the 2-line limit
          {
            text: "कृषि में ज़्यादा मेहनत होती है, इसलिए हर कदम सोच-समझकर उठाएं और अपने खेत की मिट्टी की जांच ज़रूर कराएं, ताकि खाद सही मात्रा में पड़े",
            start: 2.2,
            end: 4.5,
          },
        ],
      },
      {
        id: 3,
        purpose: "step",
        narration_display: "प्रधानमंत्री योजना के तहत ट्रैक्टर से DAP और यूरिया डालें।",
        on_screen_text: "ट्रैक्टर",
        visual: { type: "broll", broll_id: "test-clip", in_sec: 1.0, out_sec: 6.0 },
        audio: { file: "audio/scene-03.wav", duration_sec: 4.3 },
        captions: [
          { text: "प्रधानमंत्री योजना के तहत", start: 0, end: 2.0 },
          { text: "ट्रैक्टर से DAP और यूरिया डालें।", start: 2.0, end: 4.3 },
        ],
      },
      {
        id: 4,
        purpose: "mistake",
        narration_display: "ये तीन बातें ध्यान रखें।",
        visual: {
          type: "graphic",
          template: "KeyPoints",
          props: {
            title: "ध्यान रखें",
            points: ["खेत की कई जगहों से नमूना लें", "DAP डालने से पहले जांच कराएं", "दवा का लेबल ज़रूर पढ़ें"],
          },
        },
        audio: { file: "audio/scene-04.wav", duration_sec: 4.5 },
        captions: [{ text: "ये तीन बातें ध्यान रखें।", start: 0, end: 4.5 }],
      },
      {
        id: 5,
        purpose: "step",
        narration_display: "नमूना 15 सेंटीमीटर गहराई से लें।",
        visual: {
          type: "graphic",
          template: "BigNumber",
          props: { number: "15", unit: "सेमी", label: "नमूने की गहराई" },
        },
        audio: { file: "audio/scene-05.wav", duration_sec: 3.5 },
        captions: [{ text: "नमूना 15 सेंटीमीटर गहराई से लें।", start: 0, end: 3.5 }],
      },
    ],
  },
};

// Same scenes as a vertical YouTube Short (1080×1920) with a portrait placeholder image.
export const testShortProps: EpisodeProps = {
  ...testEpisodeProps,
  episode: {
    ...testEpisodeProps.episode,
    id: "test-components-short",
    format: "short",
    video: { width: 1080, height: 1920, fps: 30 },
    scenes: testEpisodeProps.episode.scenes.map((s) =>
      s.image_file ? { ...s, image_file: "images/scene-02-portrait.png" } : s,
    ),
  },
};
