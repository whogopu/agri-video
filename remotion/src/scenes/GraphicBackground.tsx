import React from "react";
import { AbsoluteFill } from "remotion";
import { theme } from "../theme";

// Shared brand-green background for graphic scenes.
export const GraphicBackground: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <AbsoluteFill
    style={{
      background: `radial-gradient(ellipse at 30% 20%, ${theme.colors.primaryDark} 0%, ${theme.colors.primaryDeep} 70%)`,
    }}
  >
    {children}
  </AbsoluteFill>
);
