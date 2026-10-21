import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import {Scene} from './types';

export const Effects = ({scene}: {scene: Scene}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const shake = scene.shake ? Math.sin(frame * 1.8) * 5 : 0;
  return (
    <div style={{position: 'absolute', inset: 0, transform: `translate(${shake}px, ${Math.cos(frame * 1.5) * (scene.shake ? 3 : 0)}px)`, pointerEvents: 'none'}}>
      {(scene.effects ?? []).includes('dust') && (
        <div style={{position: 'absolute', left: width * 0.18, top: height * 0.43, fontSize: 72, opacity: 0.5}}>· ｡ ·</div>
      )}
    </div>
  );
};
