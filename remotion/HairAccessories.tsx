import React from 'react';

export const HairAccessories = ({style, color, accessory}: {style?: string; color: string; accessory?: string}) => (
  <>
    <path
      d={style === 'ponytail' ? 'M48 112 Q4 80 15 18 Q55 0 112 20 Q205 15 190 130 L159 118 L154 55 Q110 28 54 55Z' : style === 'short' ? 'M48 112 Q24 40 61 15 Q135 -10 190 38 L173 80 Q138 47 55 65Z' : style === 'bun' ? 'M48 112 Q22 32 74 16 Q112 2 164 25 L190 4 Q215 15 190 55 L160 116 L154 55 Q108 28 54 55Z' : 'M48 112 Q28 24 101 12 Q205 22 190 130 L159 118 L154 55 Q110 28 54 55Z'}
      fill={color}
      stroke={color}
      strokeWidth="10"
      strokeLinejoin="round"
    />
    {accessory === 'glasses' && (
      <path d="M62 130 H100 M150 130 H188 M100 130 Q125 115 150 130" stroke="#fff" strokeWidth="7" fill="none" />
    )}
    {accessory === 'beanie' && <path d="M45 66 Q125 0 200 66 L195 84 H48Z" fill="#3C8CFF" stroke="#fff" strokeWidth="7" />}
    {accessory === 'bow_tie' && <path d="M104 240 L78 226 L78 254 L104 242 M146 240 L172 226 L172 254 L146 242Z" fill="#FF3C3C" stroke="#fff" strokeWidth="5" />}
    {accessory === 'chef_hat' && <path d="M54 40 Q45 5 82 15 Q108 -8 128 15 Q164 0 171 40 L160 62 H62Z" fill="#fff" stroke="#fff" strokeWidth="7" />}
  </>
);
