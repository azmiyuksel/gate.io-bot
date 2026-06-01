import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "#f7f7f4",
        foreground: "#171717",
        border: "#deded8",
        primary: "#146c5d",
        danger: "#b42318",
        muted: "#6b7280",
      },
    },
  },
  plugins: [],
};

export default config;
