import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--color-bg)",
        foreground: "var(--color-text)",
        bg: "var(--color-bg)",
        surface: "var(--color-surface)",
        ink: "var(--color-text)",
        divider: "var(--color-divider)",
        accent: {
          DEFAULT: "var(--color-accent)",
          100: "var(--color-accent-100)",
          200: "var(--color-accent-200)",
          300: "var(--color-accent-300)",
          400: "var(--color-accent-400)",
          500: "var(--color-accent-500)",
          600: "var(--color-accent-600)",
          700: "var(--color-accent-700)",
          800: "var(--color-accent-800)",
          900: "var(--color-accent-900)",
        },
        "accent-2": {
          DEFAULT: "var(--color-accent-2)",
          100: "var(--color-accent-2-100)",
          200: "var(--color-accent-2-200)",
          300: "var(--color-accent-2-300)",
          400: "var(--color-accent-2-400)",
          500: "var(--color-accent-2-500)",
          600: "var(--color-accent-2-600)",
          700: "var(--color-accent-2-700)",
          800: "var(--color-accent-2-800)",
          900: "var(--color-accent-2-900)",
        },
        neutral: {
          100: "var(--color-neutral-100)",
          200: "var(--color-neutral-200)",
          300: "var(--color-neutral-300)",
          400: "var(--color-neutral-400)",
          500: "var(--color-neutral-500)",
          600: "var(--color-neutral-600)",
          700: "var(--color-neutral-700)",
          800: "var(--color-neutral-800)",
          900: "var(--color-neutral-900)",
        },
      },
      fontFamily: {
        heading: ["var(--font-heading)", "system-ui", "sans-serif"],
        body: ["var(--font-body)", "system-ui", "sans-serif"],
      },
      borderRadius: {
        sm: "8px",
        md: "16px",
        lg: "32px",
      },
      boxShadow: {
        sm: "0 1px 2px color-mix(in srgb, #18181b 8%, transparent)",
        md: "0 3px 10px color-mix(in srgb, #18181b 10%, transparent)",
        lg: "0 12px 32px color-mix(in srgb, #18181b 16%, transparent)",
      },
    },
  },
  plugins: [],
};
export default config;
