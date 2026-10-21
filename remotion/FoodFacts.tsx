import React from 'react';
import {AbsoluteFill, Sequence, useCurrentFrame, useVideoConfig} from 'remotion';
import {Captions} from './Captions';
import {AudioLayer} from './AudioLayer';
import {Effects} from './Effects';
import {Scenes} from './Scenes';
import {Manifest} from './types';

const sceneStartTimes = (manifest: Manifest): number[] => {
  const words = manifest.words ?? [];
  return manifest.script.scenes.map((scene, index) => {
    if (index === 0) return 0;
    const first = scene.caption.split(/\s+/)[0]?.toLowerCase().replace(/[.,!?;:]/g, '');
    return words.find((word) => word.word.toLowerCase().replace(/[.,!?;:]/g, '') === first)?.start
      ?? (manifest.durationSeconds * index) / manifest.script.scenes.length;
  });
};

export const FoodFacts = ({manifest}: {manifest: Manifest}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const starts = manifest.sceneStarts ?? sceneStartTimes(manifest);
  const activeIndex = starts.reduce((active, start, index) => (frame / fps >= start ? index : active), 0);
  const scene = manifest.script.scenes[activeIndex] ?? manifest.script.scenes[0];
  const start = starts[activeIndex] ?? 0;

  return (
    <AbsoluteFill style={{backgroundColor: manifest.colors?.background ?? '#000', color: '#fff', overflow: 'hidden'}}>
      <div style={{position: 'absolute', top: 150, left: 0, right: 0, textAlign: 'center', fontSize: 38, fontWeight: 800, letterSpacing: 5}}>
        {manifest.channelLabel}
      </div>
      <Sequence from={0} durationInFrames={Math.ceil(manifest.durationSeconds * fps)}>
        <Scenes scene={scene} manifest={manifest} start={start} />
        <Effects scene={scene} />
        <Captions scene={scene} manifest={manifest} start={start} />
      </Sequence>
      <AudioLayer manifest={manifest} />
    </AbsoluteFill>
  );
};
