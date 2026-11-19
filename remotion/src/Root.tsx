import React from "react";
import { Composition, Still } from "remotion";
import { Episode } from "./Episode";
import { FontTest } from "./FontTest";
import { Thumbnail, type ThumbnailProps } from "./Thumbnail";
import { episodeFrames } from "./timing";
import type { EpisodeProps } from "./types";
import { testEpisodeProps, testShortProps } from "./test/testEpisode";

// Episode props come from render.py (--props); the test episode is the default for Studio.
const calculateMetadata = ({ props }: { props: Record<string, unknown> }) => {
  const p = props as unknown as EpisodeProps;
  return {
    durationInFrames: episodeFrames(p),
    fps: p.episode.video.fps,
    width: p.episode.video.width,
    height: p.episode.video.height,
  };
};

// Size and orientation always come from episode.video, so "Episode" renders both
// long (16:9) and short (9:16) episodes. "EpisodeShort" is the same component with
// vertical test props, for previewing in Studio.
export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="Episode"
      component={Episode as unknown as React.FC<Record<string, unknown>>}
      defaultProps={testEpisodeProps as unknown as Record<string, unknown>}
      fps={30}
      width={1920}
      height={1080}
      durationInFrames={1}
      calculateMetadata={calculateMetadata}
    />
    <Composition
      id="EpisodeShort"
      component={Episode as unknown as React.FC<Record<string, unknown>>}
      defaultProps={testShortProps as unknown as Record<string, unknown>}
      fps={30}
      width={1080}
      height={1920}
      durationInFrames={1}
      calculateMetadata={calculateMetadata}
    />
    <Still id="FontTest" component={FontTest} width={1920} height={1080} />
    <Still
      id="Thumbnail"
      component={Thumbnail as unknown as React.FC<Record<string, unknown>>}
      width={1280}
      height={720}
      defaultProps={
        {
          text: "मिट्टी की जांच क्यों ज़रूरी",
          image: "test/images/scene-02.png",
          logo: "brand/logo.png",
          width: 1280,
          height: 720,
        } satisfies ThumbnailProps as unknown as Record<string, unknown>
      }
      calculateMetadata={({ props }) => ({
        width: (props as unknown as ThumbnailProps).width,
        height: (props as unknown as ThumbnailProps).height,
      })}
    />
  </>
);
