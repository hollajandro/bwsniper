/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      colors: {
        // Purple-tinted dark palette (Material 3 dark scheme)
        gray: {
          50:  '#f4f3fa',
          100: '#eae8f5',
          200: '#d2cfea',
          300: '#b3afd4',
          400: '#8e89b0',
          500: '#6b6690',
          600: '#524e72',
          700: '#3a3754',
          750: '#2d2a42',
          800: '#222036',
          850: '#1a1829',
          900: '#12101e',
          950: '#0b0a14',
        },
        bw: {
          blue:   '#7c6ff7',   // indigo/violet primary
          dark:   '#0b0a14',
          green:  '#4ade80',
          red:    '#f87171',
          yellow: '#fbbf24',
        },
      },
    },
  },
  plugins: [],
}
