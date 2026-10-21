import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import {beatPulse, enterSpring} from './animation';
import {CastMember, Manifest, Scene} from './types';
import {Hand} from './Hands';
import {HairAccessories} from './HairAccessories';

const hairColors = ['#FFD000', '#282828', '#784828', '#C86E3C', '#E6E6E6', '#78C8DC', '#DC78C8', '#966EDC'];

const Character = ({
  cast,
  scene,
  manifest,
  x,
  y,
  index,
}: {
  cast: CastMember;
  scene: Scene;
  manifest: Manifest;
  x: number;
  y: number;
  index: number;
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const enter = enterSpring(frame, fps, index * 5);
  const pulse = beatPulse(frame, fps, manifest.beats);
  const face = scene.faces?.[cast.id] ?? 'smile';
  const pose = scene.poses?.[cast.id] ?? 'idle';
  const hair = hairColors[cast.hair_color_idx ?? 0] ?? hairColors[0];
  const tilt = Math.sin((frame + index * 17) / 38) * 2.5;
  const bob = Math.sin((frame + index * 13) / 11) * 4 + pulse * 9;
  const sick = face === 'ew' && pose === 'pinch';
  const scale = 0.94 + enter * 0.06 + pulse * 0.025;

  return (
    <div
      style={{
        position: 'absolute',
        left: x,
        top: y + (1 - enter) * 90 + bob,
        width: 250,
        height: 620,
        transform: `translate(-50%, -50%) rotate(${tilt}deg) scale(${scale})`,
        transformOrigin: '50% 80%',
      }}
    >
      <svg viewBox="0 0 250 620" width="250" height="620" overflow="visible">
        <path
          d="M82 220 C70 270 62 400 40 570 Q125 610 210 570 C188 400 180 270 168 220 Z"
          fill="#000"
          stroke="#fff"
          strokeWidth="15"
          strokeLinejoin="round"
        />
        <HairAccessories style={cast.hair_style} color={hair} accessory={cast.accessory} />
        <circle
          cx="125"
          cy="140"
          r="92"
          fill={sick ? '#78C878' : '#000'}
          stroke={sick ? '#78C878' : '#fff'}
          strokeWidth="15"
        />
        <circle cx="92" cy="132" r="9" fill="#fff" />
        <circle cx="158" cy="132" r="9" fill="#fff" />
        {face === 'open' ? (
          <ellipse cx="125" cy="177" rx="20" ry="27" fill="#fff" />
        ) : face === 'meh' ? (
          <path d="M102 180 L148 180" stroke="#fff" strokeWidth="9" strokeLinecap="round" />
        ) : face === 'ew' ? (
          <>
            <path d="M78 125 L101 145 M101 125 L78 145 M149 125 L172 145 M172 125 L149 145" stroke="#fff" strokeWidth="8" />
            <path d="M98 183 L112 170 L125 184 L138 170 L152 183" fill="none" stroke="#fff" strokeWidth="8" strokeLinejoin="round" />
          </>
        ) : (
          <path d="M91 173 Q125 208 161 170" fill="none" stroke="#fff" strokeWidth="8" strokeLinecap="round" />
        )}
      </svg>
      {sick && (
        <div style={{position: 'absolute', right: -32, top: 88, color: '#78C878', fontSize: 38}}>〰</div>
      )}
      <div style={{position: 'absolute', left: -42, top: 244}}><Hand pose={pose === 'point' ? 'point' : pose === 'pinch' ? 'pinch' : pose} side="left" /></div>
      <div style={{position: 'absolute', right: -42, top: 244}}><Hand pose={pose === 'point' ? 'point' : pose === 'pinch' ? 'pinch' : pose} side="right" /></div>
    </div>
  );
};

export const Characters = ({
  scene,
  manifest,
  cast,
}: {
  scene: Scene;
  manifest: Manifest;
  cast: CastMember[];
}) => {
  const {width, height} = useVideoConfig();
  const visible = (scene.cast_ids ?? cast.map((member) => member.id))
    .map((id) => cast.find((member) => member.id === id))
    .filter((member): member is CastMember => Boolean(member));
  const y = height * 0.58;
  const positions = visible.length === 1
    ? [width / 2]
    : visible.length === 2
      ? [width * 0.34, width * 0.66]
      : [width * 0.22, width * 0.5, width * 0.78];
  return (
    <>
      {visible.map((member, index) => (
        <Character
          key={member.id}
          cast={member}
          scene={scene}
          manifest={manifest}
          x={positions[index]}
          y={y}
          index={index}
        />
      ))}
    </>
  );
};
