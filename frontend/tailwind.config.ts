import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        sidebar: {
          bg: '#003D1A',
          hover: '#006129',
          border: '#1A6B3A',
          text: '#D1FAE5',
          muted: '#6EE7B7',
        },
        bg: {
          primary: '#FAFAF7',
          card: '#FFFFFF',
          hover: '#F0F0EB',
        },
        accent: {
          DEFAULT: '#00843D',
          dim: '#007A33',
          light: '#E6F5EC',
        },
        text: {
          primary: '#1A1A1A',
          secondary: '#4A4A4A',
          muted: '#8A8A8A',
          inverse: '#FAFAF7',
        },
        success: '#059669',
        error: '#DC2626',
        warning: '#D97706',
        border: {
          DEFAULT: '#E2E2DD',
          strong: '#C8C8C2',
        },
      },
    },
  },
  plugins: [],
};

export default config;
