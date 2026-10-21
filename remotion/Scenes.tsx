import React from 'react';
import {Scene, Manifest} from './types';
import {Characters} from './Characters';
import {Props} from './Props';

export const Scenes = ({scene, manifest, start}: {scene: Scene; manifest: Manifest; start: number}) => (
  <>
    <Props scene={scene} manifest={manifest} />
    <Characters scene={scene} manifest={manifest} cast={manifest.script.cast} />
    <div style={{position: 'absolute', top: 245, left: 0, right: 0, textAlign: 'center', fontSize: 42, fontWeight: 800, color: '#fff', letterSpacing: 3}}>
      {scene.time_label === 'opening' ? '' : scene.time_label}
    </div>
  </>
);
