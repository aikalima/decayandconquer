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
    const get = (name: string) => styles.getPropertyValue(name).trim();
    return {
      theme,
      text: get("--text"),
      muted: get("--text-muted"),
      subtle: get("--muted-2"),
      grid: get("--chart-grid"),
      fill: get("--chart-fill"),
      fillSoft: get("--chart-fill-soft"),
      brand: get("--brand"),
      brandStrong: get("--brand-hover"),
      up: get("--up"),
      down: get("--down"),
      risk: get("--risk"),
      accent: get("--brand"),
      blue: get("--brand"),
      success: get("--up"),
      warning: get("--risk"),
      danger: get("--down"),
      orange: get("--risk"),
      cyan: get("--brand-hover"),
    };
  }, [theme]);
}
