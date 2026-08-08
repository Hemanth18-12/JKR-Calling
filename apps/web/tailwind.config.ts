import sharedPreset from "@jkr/config/tailwind-preset";
import type { Config } from "tailwindcss";

const config: Config = {
  presets: [sharedPreset as Partial<Config>],
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "../../packages/ui/src/**/*.{ts,tsx}",
  ],
};

export default config;
