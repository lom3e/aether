/**
 * AETHER V2 — UNIFIED STATE MACHINE
 * Single source of truth for the living presence of Aether.
 * Coordinates Orb, Audio Synthesis, Dialogue, and UI presence.
 * 
 * Supported Core States:
 * - IDLE
 * - LISTENING
 * - SPEAKING
 * - WORKING
 * - NEEDS_YOU
 * - DONE
 */

export class StateMachine {
  constructor({ orbEngine, audioSim, onStateChange }) {
    this.orbEngine = orbEngine;
    this.audioSim = audioSim;
    this.onStateChange = onStateChange;

    this.currentState = 'idle';

    this.stateMeta = {
      idle: {
        id: 'idle',
        badgeText: 'Disponibile',
        presenceText: 'Aether è presente e in ascolto',
        orbClass: 'orb-state-idle',
        color: '#8c5cf6'
      },
      listening: {
        id: 'listening',
        badgeText: 'In Ascolto',
        presenceText: 'Aether ti sta ascoltando...',
        orbClass: 'orb-state-listening',
        color: '#38bdf8'
      },
      speaking: {
        id: 'speaking',
        badgeText: 'In Risposta',
        presenceText: 'Aether sta rispondendo...',
        orbClass: 'orb-state-speaking',
        color: '#a855f7'
      },
      working: {
        id: 'working',
        badgeText: 'In Attività',
        presenceText: 'Aether sta svolgendo il lavoro...',
        orbClass: 'orb-state-working',
        color: '#818cf8'
      },
      'needs-you': {
        id: 'needs-you',
        badgeText: 'Decisione Richiesta',
        presenceText: 'Aether richiede una tua decisione',
        orbClass: 'orb-state-needs-you',
        color: '#f59e0b'
      },
      done: {
        id: 'done',
        badgeText: 'Completato',
        presenceText: 'Lavoro verificato con successo',
        orbClass: 'orb-state-done',
        color: '#10b981'
      }
    };
  }

  getState() {
    return this.currentState;
  }

  transitionTo(newState) {
    if (!this.stateMeta[newState]) {
      console.warn(`[StateMachine] Unknown state: ${newState}`);
      return;
    }

    this.currentState = newState;
    const meta = this.stateMeta[newState];

    // 1. Update Orb Engine
    if (this.orbEngine) {
      this.orbEngine.setState(newState);
    }

    // 2. Audio Engine reactivity
    if (this.audioSim) {
      if (newState === 'speaking') {
        this.audioSim.setSpeaking(true);
        this.audioSim.setListening(false);
      } else if (newState === 'listening') {
        this.audioSim.setSpeaking(false);
        this.audioSim.setListening(true);
      } else {
        this.audioSim.setSpeaking(false);
        this.audioSim.setListening(false);
      }
    }

    // 3. Update DOM Orb Stage classes
    const stageContainer = document.querySelector('.orb-stage-container');
    if (stageContainer) {
      stageContainer.classList.remove(
        'orb-state-idle',
        'orb-state-listening',
        'orb-state-speaking',
        'orb-state-working',
        'orb-state-needs-you',
        'orb-state-done'
      );
      stageContainer.classList.add(meta.orbClass);
    }

    // 4. Update Header & Badges
    const badgeTextEl = document.querySelector('.orb-state-badge span');
    const badgeDotEl = document.querySelector('.orb-state-dot');
    const presenceTextEl = document.querySelector('.orb-presence-text');
    const headerStatusEl = document.querySelector('.header-status-indicator span');
    const headerDotEl = document.querySelector('.status-pulse-dot');

    if (badgeTextEl) badgeTextEl.textContent = meta.badgeText;
    if (badgeDotEl) {
      badgeDotEl.style.background = meta.color;
      badgeDotEl.style.boxShadow = `0 0 10px ${meta.color}`;
    }
    if (presenceTextEl) presenceTextEl.textContent = meta.presenceText;
    if (headerStatusEl) headerStatusEl.textContent = meta.badgeText;
    if (headerDotEl) {
      headerDotEl.style.background = meta.color;
      headerDotEl.style.boxShadow = `0 0 8px ${meta.color}`;
    }

    // 5. Harmonize subtle atmospheric background aura
    const ambientGradEl = document.querySelector('.ambient-gradient-center');
    if (ambientGradEl) {
      ambientGradEl.style.background = `radial-gradient(circle at center, ${meta.color}12 0%, rgba(20, 24, 40, 0.02) 48%, transparent 72%)`;
    }

    // 5. Sync Top State Buttons
    document.querySelectorAll('.state-btn').forEach(btn => {
      if (btn.dataset.state === newState) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });

    if (this.onStateChange) {
      this.onStateChange(newState, meta);
    }
  }
}
