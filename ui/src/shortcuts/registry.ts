import type { ShortcutDefinition, ShortcutCategory } from './types';

export const isMac =
  typeof navigator !== 'undefined'
    ? /Mac|iPod|iPhone|iPad/.test(navigator.platform || '') ||
      /Macintosh/.test(navigator.userAgent || '')
    : true;

export function isInputActive(target: EventTarget | null): boolean {
  if (!target || !(target instanceof HTMLElement)) return false;
  const tagName = target.tagName.toUpperCase();
  if (tagName === 'INPUT' || tagName === 'TEXTAREA' || tagName === 'SELECT') {
    return true;
  }
  return target.isContentEditable || target.getAttribute('contenteditable') === 'true';
}

export function formatShortcutKeys(shortcut: ShortcutDefinition, mac: boolean = isMac): string[] {
  const parts: string[] = [];

  if (shortcut.meta) {
    parts.push(mac ? '⌘' : 'Ctrl');
  }
  if (shortcut.ctrl && mac) {
    parts.push('⌃');
  } else if (shortcut.ctrl && !shortcut.meta) {
    parts.push('Ctrl');
  }
  if (shortcut.alt) {
    parts.push(mac ? '⌥' : 'Alt');
  }
  if (shortcut.shift) {
    parts.push(mac ? '⇧' : 'Shift');
  }

  // Key normalization
  const k = shortcut.key.toUpperCase();
  if (k === 'ESCAPE') parts.push('Esc');
  else if (k === 'ENTER') parts.push('↵');
  else if (k === 'ARROWUP') parts.push('↑');
  else if (k === 'ARROWDOWN') parts.push('↓');
  else if (k === 'SLASH' || k === '/') parts.push('/');
  else if (k === 'COMMA' || k === ',') parts.push(',');
  else parts.push(k);

  return parts;
}

export const DEFAULT_SHORTCUTS: ShortcutDefinition[] = [
  {
    id: 'command_palette',
    key: 'k',
    meta: true,
    labelKey: 'shortcutCmdPalette',
    category: 'general',
    allowInInput: true,
  },
  {
    id: 'shortcuts_help',
    key: '/',
    meta: true,
    labelKey: 'shortcutHelp',
    category: 'general',
    allowInInput: true,
  },
  {
    id: 'new_task',
    key: 'n',
    meta: true,
    labelKey: 'shortcutNewTask',
    category: 'general',
    allowInInput: false,
  },
  {
    id: 'toggle_sidebar',
    key: 'b',
    meta: true,
    labelKey: 'shortcutToggleSidebar',
    category: 'general',
    allowInInput: false,
  },
  {
    id: 'manage_workspace',
    key: 'w',
    meta: true,
    shift: true,
    labelKey: 'shortcutManageWorkspace',
    category: 'workspace',
    allowInInput: false,
  },
  {
    id: 'nav_home',
    key: '1',
    meta: true,
    labelKey: 'shortcutNavHome',
    category: 'navigation',
    allowInInput: false,
  },
  {
    id: 'nav_chat',
    key: '2',
    meta: true,
    labelKey: 'shortcutNavChat',
    category: 'navigation',
    allowInInput: false,
  },
  {
    id: 'nav_agents',
    key: '3',
    meta: true,
    labelKey: 'shortcutNavAgents',
    category: 'navigation',
    allowInInput: false,
  },
  {
    id: 'nav_teams',
    key: '4',
    meta: true,
    labelKey: 'shortcutNavTeams',
    category: 'navigation',
    allowInInput: false,
  },
  {
    id: 'nav_knowledge',
    key: '5',
    meta: true,
    labelKey: 'shortcutNavKnowledge',
    category: 'navigation',
    allowInInput: false,
  },
  {
    id: 'nav_automations',
    key: '6',
    meta: true,
    labelKey: 'shortcutNavAutomations',
    category: 'navigation',
    allowInInput: false,
  },
  {
    id: 'nav_settings',
    key: ',',
    meta: true,
    labelKey: 'shortcutNavSettings',
    category: 'navigation',
    allowInInput: false,
  },
  {
    id: 'close_modal',
    key: 'Escape',
    labelKey: 'shortcutCloseModal',
    category: 'dialogs',
    allowInInput: true,
  },
];

export const CATEGORY_ORDER: Array<{ category: ShortcutCategory; labelKey: string }> = [
  { category: 'general', labelKey: 'shortcutsCategoryGeneral' },
  { category: 'navigation', labelKey: 'shortcutsCategoryNavigation' },
  { category: 'workspace', labelKey: 'shortcutsCategoryWorkspace' },
  { category: 'dialogs', labelKey: 'shortcutsCategoryDialogs' },
];
