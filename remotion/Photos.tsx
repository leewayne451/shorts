import React from 'react';
import {Img} from 'remotion';

export const PhotoCard = ({src, size}: {src?: string; size: number}) => (
  <div style={{width: size, height: size, border: '12px solid #fff', borderRadius: 52, overflow: 'hidden', background: '#141414'}}>
    {src ? <Img src={src} style={{width: '100%', height: '100%', objectFit: 'cover'}} /> : null}
  </div>
);
