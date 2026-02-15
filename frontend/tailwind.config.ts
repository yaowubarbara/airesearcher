import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        bg: {
          primary: '#0f172a',
          card: '#1e293b',
          hover: '#334155',
        },
        accent: {
          DEFAULT: '#38bdf8',
          dim: '#0ea5e9',
        },
        text: {
          primary: '#e2e8f0',
          secondary: '#94a3b8',
          muted: '#64748b',
        },
        success: '#6ee7b7',
        error: '#fca5a5',
        warning: '#fcd34d',
      },
    },
  },
  plugins: [],
};

export default config;
