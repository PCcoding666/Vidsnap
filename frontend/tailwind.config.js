/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#6366F1',
          50: '#F5F7FF',
          100: '#EEF0FF',
          200: '#E0E4FF',
          300: '#C7CCFF',
          400: '#A5ABFF',
          500: '#6366F1',
          600: '#4F46E5',
          700: '#4338CA',
          800: '#3730A3',
          900: '#312E81',
        },
        accent: {
          green: '#10B981',
          orange: '#F59E0B',
          pink: '#EC4899',
          blue: '#3B82F6',
          purple: '#8B5CF6',
        },
      },
      fontFamily: {
        sans: ['Inter', 'PingFang SC', 'sans-serif'],
        display: ['Poppins', 'PingFang SC', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
