import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import {enterSpring} from './animation';
import {assetUrl} from './assets';
import {Manifest, Prop, Scene} from './types';

const Icon = ({name}: {name: string}) => (
  <div style={{fontSize: 150, color: name === 'no_sign' ? '#E62828' : '#FFD700', fontWeight: 900}}>
    {name === 'clock' ? '◷' : name === 'arrow' ? '➜' : name === 'sparkle' ? '✦' : name === 'no_sign' ? '⊘' : '?'}
  </div>
);

export const Props = ({scene, manifest}: {scene: Scene; manifest: Manifest}) => {
  const frame = useCurrentFrame();
  const {fps, width} = useVideoConfig();
  const progress = enterSpring(frame, fps, 4);
  const props = scene.props ?? [];
  return (
    <div style={{position: 'absolute', left: 0, right: 0, top: 300, display: 'flex', justifyContent: 'center', gap: 36}}>
      {props.slice(0, 2).map((prop: Prop, index) => {
        const photo = prop.query ? manifest.photos?.[prop.query] : undefined;
        return (
          <div
            key={`${prop.type}-${index}`}
            style={{
              width: props.length > 1 ? width * 0.34 : width * 0.5,
              aspectRatio: '1',
              border: '12px solid #fff',
              borderRadius: 52,
              overflow: 'hidden',
              background: '#141414',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transform: `scale(${0.82 + progress * 0.18}) rotate(${(1 - progress) * (index ? 5 : -5)}deg)`,
              opacity: progress,
            }}
          >
            {photo ? <img src={assetUrl(photo)} style={{width: '100%', height: '100%', objectFit: 'cover'}} /> : <Icon name={prop.name ?? 'question_mark'} />}
          </div>
        );
      })}
    </div>
  );
};
