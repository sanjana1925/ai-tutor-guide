/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  darkMode: "media",
  theme: {
    extend: {
      colors: {
        bg: "#FFFDF5",
        fg: "#1E293B",
        muted: "#F1F5F9",
        "muted-fg": "#64748B",
        violet: "#8B5CF6",
        pink: "#F472B6",
        amber: "#FBBF24",
        emerald: "#34D399",
        border: "#E2E8F0",
        input: "#FFFFFF",
        card: "#FFFFFF",
        focus: "#8B5CF6",
        ink: "#1E293B",
      },
      fontFamily: {
        heading: ["Outfit", "sans-serif"],
        body: ["Plus Jakarta Sans", "sans-serif"],
      },
      borderRadius: {
        sm: "8px",
        md: "16px",
        lg: "24px",
        pill: "9999px",
      },
      boxShadow: {
        std: "4px 4px 0px #1E293B",
        hover: "6px 6px 0px #1E293B",
        active: "2px 2px 0px #1E293B",
        card: "8px 8px 0px #E2E8F0",
        "std-violet": "4px 4px 0px #8B5CF6",
        sm: "2px 2px 0px #1E293B",
      },
      transitionTimingFunction: {
        bouncy: "cubic-bezier(0.34,1.56,0.64,1)",
      },
      maxWidth: {
        shell: "1200px",
      },
    },
  },
  plugins: [],
};
