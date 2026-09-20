export type StudioItem = {
  id: string;
  key: string;
  label: string;
  preview: string;
  chars: number;
  value?: string;
};

export type AiStudioResponse = {
  personas: StudioItem[];
  configs: StudioItem[];
  platforms: StudioItem[];
};
