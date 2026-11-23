// Light or dark theme: the saved choice, otherwise the system setting.
// Loaded in <head>, so the page never flashes in the wrong theme.
function savedTheme() {
  try {
    return localStorage.getItem("theme");
  } catch {
    return null;
  }
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem("theme", theme);
  } catch {
    // Storage blocked (private window): the theme just isn't remembered.
  }
}

const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
document.documentElement.dataset.theme = savedTheme() || (systemDark ? "dark" : "light");

function toggleTheme() {
  setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
}
