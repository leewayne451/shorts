import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import {delayed, overshoot} from './animation';
import {Manifest, Scene} from './types';

const tokenise = (value: string): string[] => value.match(/[A-Za-z0-9'’-]+|[^\s]/g) ?? [];

export const Captions = ({
  scene,
  manifest,
  start,
}: {
  scene: Scene;
  manifest: Manifest;
  start: number;
}) => {
  const frame = useCurrentFrame();
  const {fps, height, width} = useVideoConfig();
  const elapsed = frame / fps - start;
  const tokens = tokenise(scene.caption);
  const active = manifest.words.findIndex(
    (word) => word.start <= frame / fps && frame / fps < word.end,
  );
  const emphasis = new Set((scene.emphasis ?? []).map((word) => word.toLowerCase()));

  return (
    <div
      style={{
        position: 'absolute',
        left: width * 0.08,
        right: width * 0.08,
        bottom: height * 0.12,
        display: 'flex',
        justifyContent: 'center',
        flexWrap: 'wrap',
        gap: 12,
        fontFamily: 'Poppins, Arial, sans-serif',
        fontWeight: 800,
        fontSize: 62,
        lineHeight: 1.08,
        textAlign: 'center',
        textShadow: '0 5px 0 rgba(0,0,0,0.85)',
      }}
    >
      {tokens.map((word, index) => {
        const progress = delayed(elapsed, index * 0.035, 0.18);
        const scale = 0.86 + 0.14 * overshoot(progress);
        const normalized = word.toLowerCase().replace(/[^a-z0-9'’-]/g, '');
        const isActive = index === active;
        const color = isActive
          ? manifest.colors?.active ?? '#FFD700'
          : emphasis.has(normalized)
            ? manifest.colors?.emphasis ?? '#FF8C00'
            : manifest.colors?.text ?? '#FFFFFF';
        return (
          <span
            key={`${index}-${word}`}
            style={{
              color,
              display: 'inline-block',
              opacity: progress,
              transform: `scale(${scale}) ${isActive ? 'rotate(-1deg)' : ''}`,
            }}
          >
            {word}
          </span>
        );
      })}
    </div>
  );
};
