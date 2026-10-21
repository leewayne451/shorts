import React from 'react';

export const Hand = ({pose, side}: {pose: string; side: 'left' | 'right'}) => {
  if (pose === 'idle') return null;
  const flip = side === 'left' ? -1 : 1;
  const rotation = pose === 'point' ? (side === 'left' ? 18 : -18) : side === 'left' ? -8 : 8;
  return (
    <svg
      viewBox="0 0 100 130"
      width="100"
      height="130"
      style={{transform: `scaleX(${flip}) rotate(${rotation}deg)`, transformOrigin: '50% 50%'}}
    >
      {pose === 'point' ? (
        <path d="M45 111 C32 90 38 70 48 51 L50 9 Q54 0 62 8 L63 57 L73 35 Q79 29 85 35 L72 74 Q68 99 60 113Z" fill="#FFCC4D" stroke="#CD8219" strokeWidth="6" strokeLinejoin="round" />
      ) : pose === 'pinch' ? (
        <path d="M24 91 Q17 62 35 42 L50 22 Q58 16 65 24 L53 50 L69 39 Q79 37 82 46 L60 66 Q68 88 60 108Z" fill="#FFCC4D" stroke="#CD8219" strokeWidth="6" strokeLinejoin="round" />
      ) : (
        <path d="M23 106 Q12 77 26 56 L27 18 Q29 10 36 12 L42 54 L45 11 Q47 4 54 7 L57 54 L62 15 Q65 8 71 12 L68 58 L76 30 Q80 24 86 30 L75 78 Q69 105 57 114Z" fill="#FFCC4D" stroke="#CD8219" strokeWidth="6" strokeLinejoin="round" />
      )}
      <path d="M35 88 Q48 79 61 88" fill="none" stroke="#FFECB3" strokeWidth="5" strokeLinecap="round" />
    </svg>
  );
};
