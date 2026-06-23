import { createContext, useContext, useMemo } from "react";

export type Theme = "dark" | "light";

export interface ThemeContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

export const ThemeContext = createContext<ThemeContextValue | null>(null);

export function useTheme() {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useTheme must be used inside ThemeProvider");
  return value;
}

export function useChartTheme() {
  const { theme } = useTheme();
  return useMemo(() => {
    const styles = getComputedStyle(document.documentElement);
    const get = (name: string, fallback: string) => styles.getPropertyValue(name).trim() || fallback;
    return {
      theme,
      text: get("--text", theme === "dark" ? "#edf2f8" : "#182234"),
      muted: get("--muted", theme === "dark" ? "#9aa8ba" : "#64748b"),
      subtle: get("--muted-2", theme === "dark" ? "#748195" : "#7b8797"),
      grid: get("--chart-grid", theme === "dark" ? "rgba(148,163,184,0.14)" : "rgba(100,116,139,0.18)"),
      fill: get("--chart-fill", "rgba(109, 93, 252, 0.18)"),
      fillSoft: get("--chart-fill-soft", "rgba(109, 93, 252, 0.08)"),
      accent: get("--accent", "#6d5dfc"),
      blue: get("--blue", "#3a9df5"),
      success: get("--success", "#2ecc71"),
      warning: get("--warning", "#f1c40f"),
      danger: get("--danger", "#e85d57"),
      orange: get("--orange", "#f59e42"),
      cyan: get("--cyan", "#24c8db"),
    };
  }, [theme]);
}
