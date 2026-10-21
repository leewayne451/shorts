import React from 'react';
import {Audio, staticFile} from 'remotion';
import {Manifest} from './types';

const audioSrc = (path: string): string => {
  if (path.startsWith('data:') || path.startsWith('http://') || path.startsWith('https://')) {
    return path;
  }
  return staticFile(path.replace(/^\/+/, ''));
};

export const AudioLayer = ({manifest}: {manifest: Manifest}) =>
  manifest.audioPath ? <Audio src={audioSrc(manifest.audioPath)} /> : null;
