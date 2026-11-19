import React from "react";
import { AbsoluteFill, Audio, Sequence, interpolate, staticFile, useVideoConfig } from "remotion";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import "./fonts";
import { theme } from "./theme";
import { sceneFrames } from "./timing";
import type { EpisodeProps, Scene } from "./types";
import { KenBurnsImage } from "./scenes/KenBurnsImage";
import { BrollClip } from "./scenes/BrollClip";
import { TitleCard, type TitleCardProps } from "./scenes/TitleCard";
import { KeyPoints, type KeyPointsProps } from "./scenes/KeyPoints";
import { BigNumber, type BigNumberProps } from "./scenes/BigNumber";
import { Captions } from "./overlays/Captions";
import { OnScreenText } from "./overlays/OnScreenText";
import { Watermark } from "./overlays/Watermark";

const asset = (base: string, rel: string) => staticFile(`${base}/${rel}`);

const SceneVisual: React.FC<{ scene: Scene; props: EpisodeProps; durationInFrames: number }> = ({
  scene,
  props,
  durationInFrames,
}) => {
  const v = scene.visual;
  if (v.type === "image" && scene.image_file) {
    return <KenBurnsImage src={asset(props.assetBase, scene.image_file)} sceneId={scene.id} durationInFrames={durationInFrames} />;
  }
  if (v.type === "broll" && v.broll_id && props.brollFiles[v.broll_id] && v.in_sec != null && v.out_sec != null) {
    return (
      <BrollClip
        src={asset(props.brollBase, props.brollFiles[v.broll_id])}
        inSec={v.in_sec}
        outSec={v.out_sec}
        durationInFrames={durationInFrames}
      />
    );
  }
  if (v.type === "graphic" && v.template && v.props) {
    switch (v.template) {
      case "TitleCard":
        return <TitleCard {...(v.props as TitleCardProps)} />;
      case "KeyPoints":
        return <KeyPoints {...(v.props as KeyPointsProps)} durationInFrames={durationInFrames} />;
      case "BigNumber":
        return <BigNumber {...(v.props as BigNumberProps)} />;
    }
  }
  // Visual not ready yet: plain brand card with the scene number, so previews still work.
  return <TitleCard title={`दृश्य ${scene.id}`} subtitle={`(${v.type ?? "visual pending"})`} />;
};

export const Episode: React.FC<EpisodeProps> = (props) => {
  const { episode, paddingSec } = props;
  const fps = episode.video.fps;
  const leadIn = Math.round((props.leadInSec ?? 0) * fps);
  const { durationInFrames } = useVideoConfig();
  const toneFade = Math.min(fps, Math.floor(durationInFrames / 3));
  // continuous room tone under everything: fades in/out with the video, never steps at scene changes
  const roomToneVolume = (f: number) =>
    interpolate(f, [0, toneFade, durationInFrames - toneFade, durationInFrames], [0, 1, 1, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });

  return (
    <AbsoluteFill style={{ backgroundColor: theme.colors.background }}>
      <TransitionSeries>
        {episode.scenes.map((scene, i) => {
          const dur = sceneFrames(scene, fps, paddingSec, props.leadInSec ?? 0);
          return (
            <React.Fragment key={scene.id}>
              <TransitionSeries.Sequence durationInFrames={dur} name={`scene ${scene.id} (${scene.purpose})`}>
                <SceneVisual scene={scene} props={props} durationInFrames={dur} />
                {scene.on_screen_text ? <OnScreenText text={scene.on_screen_text} /> : null}
                {/* narration and its captions start after the lead-in, so the new picture lands first */}
                <Sequence from={leadIn} layout="none" name="narration">
                  <Captions captions={scene.captions} fontSize={props.captionFontSize} />
                  {scene.audio ? <Audio src={asset(props.assetBase, scene.audio.file)} /> : null}
                </Sequence>
              </TransitionSeries.Sequence>
              {i < episode.scenes.length - 1 ? (
                <TransitionSeries.Transition
                  presentation={fade()}
                  timing={linearTiming({ durationInFrames: theme.transitionFrames })}
                />
              ) : null}
            </React.Fragment>
          );
        })}
      </TransitionSeries>
      {props.roomTone ? <Audio src={staticFile(props.roomTone)} loop volume={roomToneVolume} /> : null}
      {props.logo ? <Watermark src={staticFile(props.logo)} /> : null}
    </AbsoluteFill>
  );
};
