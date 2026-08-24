export type ShortcutCategory = 'general' | 'navigation' | 'workspace' | 'dialogs';

export interface ShortcutDefinition {
  id: string;
  key: string;
  meta?: boolean;         // Meta key (Cmd on macOS, Windows key) or Ctrl on Windows/Linux
  ctrl?: boolean;         // Explicit Ctrl
  shift?: boolean;        // Shift key
  alt?: boolean;          // Alt / Option key
  labelKey: string;       // Translation key in i18n
  category: ShortcutCategory;
  allowInInput?: boolean; // If true, triggers even when input/textarea is focused (e.g. Cmd+K, Escape)
  action?: () => void;
  disabled?: boolean;
}

export interface ShortcutGroup {
  category: ShortcutCategory;
  categoryLabelKey: string;
  items: ShortcutDefinition[];
}
