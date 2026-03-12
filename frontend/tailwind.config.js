/** @type {import('tailwindcss').Config} */
export default {
content: [
    "./index.html",
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'bg-primary': '#0a0a0a',
        'bg-secondary': '#1a1a1a',
        'bg-tertiary': '#2a2a2a',
        'accent-green': '#00d26a',
        'accent-red': '#ff4757',
        'accent-blue': '#4a90d9',
        'accent-yellow': '#ffd93d',
      },
    },
  },
  plugins: [],
}
