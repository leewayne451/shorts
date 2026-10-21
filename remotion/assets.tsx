import type {CSSProperties} from 'react';
import {Img, staticFile} from 'remotion';

export const assetUrl = (path: string): string =>
  path.startsWith('http://') || path.startsWith('https://') || path.startsWith('file:') || path.startsWith('data:')
    ? path
    : staticFile(path);

export const SafeImage = ({src, style}: {src: string; style?: CSSProperties}) => (
  <Img src={assetUrl(src)} style={style} />
);
