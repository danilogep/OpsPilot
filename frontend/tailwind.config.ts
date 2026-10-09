import type { Config } from "tailwindcss";

/**
 * Paleta do OpsPilot: azul-petróleo como cor institucional, cinzas neutros e
 * cores de estado com contraste suficiente para texto pequeno (WCAG AA).
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef6ff",
          100: "#d9ebff",
          200: "#bcdcff",
          300: "#8ec6ff",
          400: "#59a6ff",
          500: "#2f85f7",
          600: "#1a66e0",
          700: "#1551b4",
          800: "#154690",
          900: "#163c76",
        },
        ink: {
          50: "#f6f7f9",
          100: "#eceef2",
          200: "#d5dae3",
          300: "#b0b9c9",
          400: "#8593aa",
          500: "#66758f",
          600: "#515e76",
          700: "#424c60",
          800: "#394151",
          900: "#1f2430",
        },
        success: {
          50: "#ecfdf3",
          100: "#d1fadf",
          600: "#039855",
          700: "#027a48",
        },
        warning: {
          50: "#fffaeb",
          100: "#fef0c7",
          600: "#dc6803",
          700: "#b54708",
        },
        danger: {
          50: "#fef3f2",
          100: "#fee4e2",
          600: "#d92d20",
          700: "#b42318",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(16 24 40 / 0.06), 0 1px 3px 0 rgb(16 24 40 / 0.1)",
        panel: "0 4px 16px -4px rgb(16 24 40 / 0.12)",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-in": "fade-in 180ms ease-out",
      },
    },
  },
  plugins: [],
} satisfies Config;
