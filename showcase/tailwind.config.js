/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/templates/**/*.html', './src/static/js/**/*.js'],
  theme: {
    extend: {
      colors: {
        ink: { 950: '#090A0F', 900: '#0E1117', 800: '#111827', 700: '#1E293B', 600: '#334155' },
        signal: { DEFAULT: '#3B82F6', soft: '#93C5FD', deep: '#2563EB' },
        verified: { DEFAULT: '#10B981', soft: '#6EE7B7' },
      },
      fontFamily: {
        display: ['"Space Grotesk Variable"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        sans: ['"Plus Jakarta Sans Variable"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      maxWidth: { measure: '62ch' },
      boxShadow: { glass: '0 1px 0 0 rgba(255,255,255,0.04) inset, 0 24px 48px -24px rgba(0,0,0,0.6)' },
    },
  },
  plugins: [require('@tailwindcss/forms'), require('@tailwindcss/typography')],
};
