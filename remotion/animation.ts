import {interpolate, spring} from 'remotion';

export const clamp01 = (value: number): number => Math.max(0, Math.min(1, value));

export const smoothstep = (value: number): number => {
  const t = clamp01(value);
  return t * t * (3 - 2 * t);
};

export const easeOut = (value: number): number => 1 - Math.pow(1 - clamp01(value), 3);

export const easeInOut = (value: number): number => {
  const t = clamp01(value);
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
};

export const delayed = (progress: number, delay: number, duration: number): number =>
  smoothstep((progress - delay) / Math.max(0.001, duration));

export const overshoot = (progress: number, amount = 0.12): number => {
  const t = easeOut(progress);
  return interpolate(t, [0, 0.72, 1], [0, 1 + amount, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
};

export const beatPulse = (frame: number, fps: number, beats: number[] = []): number => {
  let pulse = 0;
  for (const beat of beats) {
    const elapsed = frame / fps - beat;
    if (elapsed >= 0 && elapsed < 0.28) {
      pulse = Math.max(pulse, Math.exp(-elapsed * 14));
    }
  }
  return pulse;
};

export const enterSpring = (frame: number, fps: number, delayFrames = 0): number =>
  spring({
    frame: Math.max(0, frame - delayFrames),
    fps,
    config: {damping: 11, stiffness: 150, mass: 0.65},
  });
