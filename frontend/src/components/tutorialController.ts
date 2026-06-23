const STORAGE_KEY = "decay_tutorial_seen";

let triggerTutorial: (() => void) | null = null;

export function setTutorialTrigger(trigger: (() => void) | null) {
  triggerTutorial = trigger;
}

export function startTutorial() {
  triggerTutorial?.();
}

export function resetTutorial() {
  localStorage.removeItem(STORAGE_KEY);
}

export { STORAGE_KEY };
