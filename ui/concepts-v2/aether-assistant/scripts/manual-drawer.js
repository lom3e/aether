/**
 * AETHER V2 — MANUAL MODE CONTROLLER
 * Contextual Drawer & ⌘K Command Palette
 * Clean & secondary access to Jobs, Results, Connectors, Assistants, Automations, Memory & Settings
 */

export class ManualController {
  constructor({ drawerBackdrop, commandPaletteBackdrop }) {
    this.drawerBackdrop = drawerBackdrop;
    this.commandPaletteBackdrop = commandPaletteBackdrop;
    this.isDrawerOpen = false;
    this.isPaletteOpen = false;

    this.bindEvents();
  }

  bindEvents() {
    // Backdrop clicks close
    this.drawerBackdrop.addEventListener('click', (e) => {
      if (e.target === this.drawerBackdrop) {
        this.closeDrawer();
      }
    });

    this.commandPaletteBackdrop.addEventListener('click', (e) => {
      if (e.target === this.commandPaletteBackdrop) {
        this.closeCommandPalette();
      }
    });

    // Close button in drawer
    const closeBtn = this.drawerBackdrop.querySelector('.drawer-close-btn');
    if (closeBtn) {
      closeBtn.addEventListener('click', () => this.closeDrawer());
    }

    // Keyboard shortcuts (Escape & ⌘K / Ctrl+K)
    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        if (this.isPaletteOpen) this.closeCommandPalette();
        if (this.isDrawerOpen) this.closeDrawer();
      }

      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        this.toggleCommandPalette();
      }
    });
  }

  openDrawer() {
    this.drawerBackdrop.classList.add('drawer-open');
    this.isDrawerOpen = true;
  }

  closeDrawer() {
    this.drawerBackdrop.classList.remove('drawer-open');
    this.isDrawerOpen = false;
  }

  toggleDrawer() {
    if (this.isDrawerOpen) this.closeDrawer();
    else this.openDrawer();
  }

  openCommandPalette() {
    this.commandPaletteBackdrop.classList.add('palette-open');
    this.isPaletteOpen = true;
    const input = this.commandPaletteBackdrop.querySelector('.palette-input');
    if (input) {
      setTimeout(() => input.focus(), 60);
    }
  }

  closeCommandPalette() {
    this.commandPaletteBackdrop.classList.remove('palette-open');
    this.isPaletteOpen = false;
  }

  toggleCommandPalette() {
    if (this.isPaletteOpen) this.closeCommandPalette();
    else this.openCommandPalette();
  }
}
