import React from 'react';
import {Audio} from 'remotion';
import {Manifest} from './types';

export const AudioLayer = ({manifest}: {manifest: Manifest}) =>
  manifest.audioPath ? <Audio src={manifest.audioPath} /> : null;
