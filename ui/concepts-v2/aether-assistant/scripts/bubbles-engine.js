/**
 * AETHER V2 — THOUGHT BUBBLES ENGINE
 * Lightweight operational updates • Micro / Status / Attention hierarchy • Orbital emergence
 */

export class BubblesEngine {
  constructor(containerElement, onAttentionClick) {
    this.container = containerElement;
    this.onAttentionClick = onAttentionClick;
    this.activeBubbles = new Map();
    this.nextId = 1;
    this.pendingTimers = new Set();

    // Orbital positioning around the 480px Orb (relative to stage center)
    // Orbital positioning around the enlarged Orb (ensuring >=80px clearance from the sphere surface)
    this.orbitalSlots = [
      { id: 'top-right', x: 74, y: 28 },
      { id: 'top-left',  x: 26, y: 28 },
      { id: 'right-mid', x: 78, y: 50 },
      { id: 'left-mid',  x: 22, y: 50 }
    ];
    this.usedSlots = new Set();
  }

  getAvailableSlot() {
    for (const slot of this.orbitalSlots) {
      if (!this.usedSlots.has(slot.id)) {
        this.usedSlots.add(slot.id);
        return slot;
      }
    }
    // Default fallback to top-right
    return this.orbitalSlots[0];
  }

  releaseSlot(slotId) {
    this.usedSlots.delete(slotId);
  }

  /**
   * Spawn a new Thought Bubble
   */
  spawn({ tier = 'micro', text, countBadge, icon = 'sparkle', duration = 3400, onClick }) {
    const id = this.nextId++;
    const slot = this.getAvailableSlot();

    const bubbleEl = document.createElement('div');
    bubbleEl.className = `thought-bubble bubble-${tier}`;
    bubbleEl.id = `thought-bubble-${id}`;
    bubbleEl.style.left = `${slot.x}%`;
    bubbleEl.style.top = `${slot.y}%`;
    bubbleEl.style.transform = `translate(-50%, -50%)`;

    let iconSvg = '';
    if (tier === 'attention' || icon === 'alert') {
      iconSvg = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`;
    } else if (tier === 'status' || icon === 'check') {
      iconSvg = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>`;
    } else if (icon === 'search') {
      iconSvg = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>`;
    } else {
      iconSvg = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/></svg>`;
    }

    let badgeHtml = countBadge ? `<span class="thought-bubble-count">${countBadge}</span>` : '';
    let actionHtml = tier === 'attention' ? `<span class="thought-bubble-action">Decisione</span>` : '';

    bubbleEl.innerHTML = `
      <div class="thought-bubble-icon">${iconSvg}</div>
      <div class="thought-bubble-text">${text}</div>
      ${badgeHtml}
      ${actionHtml}
    `;

    bubbleEl.addEventListener('click', (e) => {
      e.stopPropagation();
      if (tier === 'attention' && this.onAttentionClick) {
        this.onAttentionClick();
      }
      if (onClick) onClick();
      this.dismiss(id);
    });

    this.container.appendChild(bubbleEl);
    this.activeBubbles.set(id, { element: bubbleEl, slotId: slot.id });

    if (duration > 0) {
      const timerId = setTimeout(() => {
        this.pendingTimers.delete(timerId);
        this.dismiss(id);
      }, duration);
      this.pendingTimers.add(timerId);
    }

    return id;
  }

  dismiss(id) {
    const bubbleData = this.activeBubbles.get(id);
    if (!bubbleData) return;

    const el = bubbleData.element;
    el.classList.add('bubble-closing');
    this.releaseSlot(bubbleData.slotId);

    setTimeout(() => {
      if (el.parentNode) {
        el.parentNode.removeChild(el);
      }
      this.activeBubbles.delete(id);
    }, 280);
  }

  morphAllToField() {
    this.activeBubbles.forEach((bubbleData, id) => {
      const el = bubbleData.element;
      el.classList.add('bubble-morphing-to-field');
      this.releaseSlot(bubbleData.slotId);
      setTimeout(() => {
        if (el.parentNode) el.parentNode.removeChild(el);
        this.activeBubbles.delete(id);
      }, 550);
    });
  }

  clear() {
    // Clear all pending timers
    this.pendingTimers.forEach(t => clearTimeout(t));
    this.pendingTimers.clear();

    // Remove elements
    this.activeBubbles.forEach((bubbleData) => {
      if (bubbleData.element.parentNode) {
        bubbleData.element.parentNode.removeChild(bubbleData.element);
      }
    });
    this.activeBubbles.clear();
    this.usedSlots.clear();
  }
}
