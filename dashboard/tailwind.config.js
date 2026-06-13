/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        display: ['"Orbitron"', '"Syne"', 'system-ui', 'sans-serif'],
        orbitron: ['"Orbitron"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      colors: {
        sentinel: {
          bg: '#020308',
          panel: 'rgba(255,255,255,0.03)',
          cyan: '#22d3ee',
          violet: '#a78bfa',
          rose: '#fb7185',
          amber: '#fbbf24',
        },
      },
      boxShadow: {
        glow: '0 0 50px -8px rgba(34, 211, 238, 0.4)',
        'glow-violet': '0 0 50px -8px rgba(167, 139, 250, 0.4)',
        'glow-rose': '0 0 50px -8px rgba(251, 113, 133, 0.4)',
        'glow-amber': '0 0 50px -8px rgba(251, 191, 36, 0.35)',
      },
      animation: {
        float: 'float 10s ease-in-out infinite',
        shimmer: 'shimmer 5s linear infinite',
      },
    },
  },
  plugins: [],
}
