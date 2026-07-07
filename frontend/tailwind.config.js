export default {
  content: ['./index.html', './src/**/*.{vue,ts}'],
  theme: {
    extend: {
      colors: {
        ink: '#1a1a1a', paper: '#faf9f6', card: '#ffffff',
        line: '#e6e3dc', accent: '#2d4a7c', accent2: '#7c2d3a'
      },
      fontFamily: {
        sans: ['Inter', 'Source Han Sans SC', 'system-ui', 'sans-serif'],
        serif: ['Source Serif Pro', 'Source Han Serif SC', 'Georgia', 'serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace']
      }
    }
  },
  plugins: []
}
