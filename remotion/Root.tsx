import React from 'react';
import {Composition} from 'remotion';
import {FoodFacts} from './FoodFacts';
import {Manifest} from './types';

const defaultManifest: Manifest = {
  script: {
    title: 'What if?',
    opening_question: 'What if bees vanished?',
    cast: [{id: 'c1', name: 'Ava', hair_style: 'bob', hair_color_idx: 0, bust: true}],
    scenes: [{
      index: 0,
      time_label: 'opening',
      scene_template: 'intro_prop',
      props: [{type: 'icon', name: 'question_mark'}],
      cast_ids: ['c1'],
      caption: 'What if bees vanished?',
    }],
  },
  words: [],
  width: 1080,
  height: 1920,
  fps: 30,
  durationSeconds: 30,
  channelLabel: 'WHAT IF',
};

export const RemotionRoot = () => (
  <Composition
    id="FoodFacts"
    component={FoodFacts}
    durationInFrames={900}
    fps={30}
    width={1080}
    height={1920}
    defaultProps={{manifest: defaultManifest}}
    calculateMetadata={({props}) => {
      const manifest = (props as {manifest: Manifest}).manifest;
      return {
        durationInFrames: Math.round(manifest.durationSeconds * manifest.fps),
        fps: manifest.fps,
        width: manifest.width,
        height: manifest.height,
      };
    }}
  />
);
