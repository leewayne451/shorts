export type WordTiming = {
  word: string;
  start: number;
  end: number;
};

export type CastMember = {
  id: string;
  name: string;
  hair_style?: string;
  hair_color_idx?: number;
  accessory?: string;
  accessory_color_idx?: number;
  bust?: boolean;
};

export type Prop = {
  type: 'photo' | 'icon';
  query?: string;
  name?: string;
};

export type Scene = {
  index: number;
  time_label: string;
  scene_template: string;
  props?: Prop[];
  cast_ids?: string[];
  poses?: Record<string, string>;
  faces?: Record<string, string>;
  emphasis?: string[];
  caption: string;
  shake?: boolean;
  claims?: string[];
  visual_action?: string;
  camera_move?: string;
  character_animation?: string;
  prop_animation?: string;
  effects?: string[];
};

export type Script = {
  title: string;
  opening_question: string;
  cast: CastMember[];
  scenes: Scene[];
};

export type Manifest = {
  script: Script;
  words: WordTiming[];
  audioPath?: string;
  width: number;
  height: number;
  fps: number;
  durationSeconds: number;
  channelLabel: string;
  beats?: number[];
  colors?: {
    background?: string;
    outline?: string;
    active?: string;
    emphasis?: string;
    text?: string;
  };
  photos?: Record<string, string>;
  sceneStarts?: number[];
};
