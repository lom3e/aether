import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import type { ShortcutDefinition } from './types';
import { DEFAULT_SHORTCUTS, isInputActive, formatShortcutKeys, isMac } from './registry';

interface ShortcutsContextType {
  shortcuts: ShortcutDefinition[];
  registerShortcut: (shortcut: ShortcutDefinition) => () => void;
  openShortcutsModal: () => void;
  closeShortcutsModal: () => void;
  isShortcutsModalOpen: boolean;
  formatShortcut: (shortcut: ShortcutDefinition) => string[];
  isMac: boolean;
}

export const ShortcutsContext = createContext<ShortcutsContextType>({
  shortcuts: DEFAULT_SHORTCUTS,
  registerShortcut: () => () => {},
  openShortcutsModal: () => {},
  closeShortcutsModal: () => {},
  isShortcutsModalOpen: false,
  formatShortcut: (s) => formatShortcutKeys(s, true),
  isMac: true,
});

export function ShortcutsProvider({
  children,
  initialActions = {},
}: {
  children: ReactNode;
  initialActions?: Record<string, () => void>;
}) {
  const [shortcuts, setShortcuts] = useState<ShortcutDefinition[]>(() =>
    DEFAULT_SHORTCUTS.map((s) => ({
      ...s,
      action: initialActions[s.id] || s.action,
    }))
  );
  const [isShortcutsModalOpen, setIsShortcutsModalOpen] = useState(false);

  const openShortcutsModal = useCallback(() => setIsShortcutsModalOpen(true), []);
  const closeShortcutsModal = useCallback(() => setIsShortcutsModalOpen(false), []);

  const registerShortcut = useCallback((newShortcut: ShortcutDefinition) => {
    setShortcuts((prev) => {
      const filtered = prev.filter((s) => s.id !== newShortcut.id);
      return [...filtered, newShortcut];
    });

    return () => {
      setShortcuts((prev) => prev.filter((s) => s.id !== newShortcut.id));
    };
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // 1. Open shortcuts help modal via Cmd+/ (or Ctrl+/)
      const isMetaOrCtrl = e.metaKey || (!isMac && e.ctrlKey);
      if (isMetaOrCtrl && (e.key === '/' || e.key === '?')) {
        e.preventDefault();
        setIsShortcutsModalOpen((prev) => !prev);
        return;
      }

      // 2. Escape closes open shortcuts modal
      if (e.key === 'Escape' && isShortcutsModalOpen) {
        e.preventDefault();
        setIsShortcutsModalOpen(false);
        return;
      }

      const inputFocused = isInputActive(e.target);

      for (const shortcut of shortcuts) {
        if (shortcut.disabled || !shortcut.action) continue;

        // Skip if input is focused and shortcut does not allow it
        if (inputFocused && !shortcut.allowInInput) continue;

        // Check key match
        const keyMatch =
          e.key.toLowerCase() === shortcut.key.toLowerCase() ||
          (shortcut.key === 'Escape' && e.key === 'Escape');

        if (!keyMatch) continue;

        // Check modifiers
        const expectedMeta = Boolean(shortcut.meta);
        const expectedCtrl = Boolean(shortcut.ctrl);
        const expectedShift = Boolean(shortcut.shift);
        const expectedAlt = Boolean(shortcut.alt);

        const actualMeta = isMac ? e.metaKey : e.ctrlKey || e.metaKey;
        const actualCtrl = isMac ? e.ctrlKey : false;
        const actualShift = e.shiftKey;
        const actualAlt = e.altKey;

        if (
          expectedMeta === actualMeta &&
          expectedCtrl === actualCtrl &&
          expectedShift === actualShift &&
          expectedAlt === actualAlt
        ) {
          e.preventDefault();
          shortcut.action();
          return;
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [shortcuts, isShortcutsModalOpen]);

  const formatShortcut = useCallback(
    (s: ShortcutDefinition) => formatShortcutKeys(s, isMac),
    []
  );

  return (
    <ShortcutsContext.Provider
      value={{
        shortcuts,
        registerShortcut,
        openShortcutsModal,
        closeShortcutsModal,
        isShortcutsModalOpen,
        formatShortcut,
        isMac,
      }}
    >
      {children}
    </ShortcutsContext.Provider>
  );
}

export function useKeyboardShortcuts() {
  return useContext(ShortcutsContext);
}
