import React from "react";
import { AbsoluteFill } from "remotion";
import "./fonts";
import { fontFamily, theme } from "./theme";

// Still for checking Devanagari shaping: conjuncts, nukta, reph, matras, Latin mix.
export const TEST_WORDS = ["क्षेत्र", "श्रमिक", "द्वारा", "कृषि", "ज़्यादा", "प्रधानमंत्री", "ट्रैक्टर"];

export const FontTest: React.FC = () => (
  <AbsoluteFill
    style={{
      background: theme.colors.primaryDeep,
      color: theme.colors.text,
      fontFamily,
      padding: `${theme.safe.y}px ${theme.safe.x}px`,
      gap: 6,
    }}
  >
    <div style={{ fontSize: 40, color: theme.colors.primary, fontWeight: 700 }}>
      Noto Sans Devanagari — font test
    </div>
    {[400, 600, 800].map((w) => (
      <div key={w} style={{ fontSize: 82, fontWeight: w, lineHeight: 1.45, display: "flex", gap: 30, flexWrap: "wrap" }}>
        {TEST_WORDS.map((t) => (
          <span key={t}>{t}</span>
        ))}
      </div>
    ))}
    <div style={{ fontSize: 64, fontWeight: 600, lineHeight: 1.5 }}>
      DAP, NPK, यूरिया, स्प्रे — ₹2,500 · 25% · 10-12 किलो · ०१२३४५६७८९
    </div>
    <div
      style={{
        alignSelf: "center",
        marginTop: "auto",
        fontSize: theme.captions.fontSize,
        fontWeight: theme.captions.fontWeight,
        background: theme.colors.captionBg,
        padding: "10px 28px",
        borderRadius: 14,
        lineHeight: 1.5,
      }}
    >
      कैप्शन: प्रधानमंत्री योजना के तहत ट्रैक्टर से ज़्यादा काम
    </div>
  </AbsoluteFill>
);
