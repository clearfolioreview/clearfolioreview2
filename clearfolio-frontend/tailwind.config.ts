import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        heading: ["var(--font-space-grotesk)", "sans-serif"],
        body:    ["var(--font-inter)", "sans-serif"],
        mono:    ["var(--font-ibm-plex-mono)", "monospace"],
      },
      colors: {
        parchment: {
          50:  "#FAFAF7",
          100: "#F4F3EE",
          200: "#E8E7DF",
          300: "#D4D2C7",
        },
        ink: {
          DEFAULT: "#1A1917",
          muted:   "#6B6963",
          faint:   "#9E9B95",
        },
        risk: {
          critical: "#C8392B",
          high:     "#C05621",
          medium:   "#92680A",
          low:      "#1D5A8E",
          none:     "#3A7D44",
        },
        grade: {
          a: "#2E7D32",
          b: "#0277BD",
          c: "#F57F17",
          d: "#E65100",
          f: "#B71C1C",
        },
      },
      animation: {
        "fade-up":    "fadeUp 0.5s ease forwards",
        "fade-in":    "fadeIn 0.4s ease forwards",
        "score-fill": "scoreFill 1.2s ease-out forwards",
        "shimmer":    "shimmer 1.6s infinite linear",
      },
      keyframes: {
        fadeUp: {
          "0%":   { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        fadeIn: {
          "0%":   { opacity: "0" },
          "100%": { opacity: "1" },
        },
        scoreFill: {
          "0%":   { strokeDashoffset: "220" },
          "100%": { strokeDashoffset: "var(--score-offset)" },
        },
        shimmer: {
          "0%":   { backgroundPosition: "-400px 0" },
          "100%": { backgroundPosition: "400px 0" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
