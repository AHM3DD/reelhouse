/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./*/templates/**/*.html",
    "./core/templatetags/*.py",
    "./*/forms.py",
    "./static/js/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#07070b",
          900: "#0c0c12",
          850: "#111119",
          800: "#161620",
          700: "#1f1f2c",
          600: "#2b2b3a",
          500: "#3b3b4e",
        },
        accent: {
          DEFAULT: "#f5b544",
          200: "#fbe3b3",
          300: "#f8cd7a",
          400: "#f6c05c",
          500: "#f5b544",
          600: "#e09a1f",
        },
        ember: {
          DEFAULT: "#ff5d6c",
          400: "#ff7a87",
          500: "#ff5d6c",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        display: ['"Instrument Serif"', "ui-serif", "Georgia", "serif"],
      },
      boxShadow: {
        poster: "0 30px 60px -20px rgba(0,0,0,.75), 0 0 0 1px rgba(255,255,255,.06)",
      },
      keyframes: {
        "toast-in": {
          "0%": { opacity: "0", transform: "translateY(8px) scale(.98)" },
          "100%": { opacity: "1", transform: "translateY(0) scale(1)" },
        },
        progress: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(250%)" },
        },
      },
      animation: {
        "toast-in": "toast-in .25s ease-out",
        progress: "progress 1.1s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
