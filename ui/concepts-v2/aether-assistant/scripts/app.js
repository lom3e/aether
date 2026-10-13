/**
 * AETHER V2 — APPLICATION MASTER COORDINATOR
 * Ties together Orb, Audio, Bubbles, Field, Unified States & Scenario
 */

import { OrbEngine } from './orb-engine.js?v=starry3';
import { AudioSim } from './audio-sim.js';
import { StateMachine } from './state-machine.js';
import { BubblesEngine } from './bubbles-engine.js';
import { FieldEngine } from './field-engine.js';
import { ManualController } from './manual-drawer.js';
import { ScenarioEngine } from './scenario-engine.js';

function bootstrapAether() {
  // 1. DOM Elements
  const orbCanvas = document.getElementById('orb-canvas');
  const bubblesContainer = document.getElementById('thought-bubbles-container');
  const fieldContainer = document.getElementById('aether-field-container');
  const drawerBackdrop = document.getElementById('manual-drawer-backdrop');
  const commandPaletteBackdrop = document.getElementById('command-palette-backdrop');

  if (!orbCanvas) {
    console.warn("[Aether] orb-canvas not found, retrying...");
    return;
  }

  // 2. Core Engines
  const urlParams = new URLSearchParams(window.location.search);
  const paramState = urlParams.get('state') || 'idle';
  const audioSim = new AudioSim();
  const orbEngine = new OrbEngine(orbCanvas, { initialState: paramState });
  
  let fieldEngine;
  let scenarioEngine;

  // Bubbles Engine
  const bubblesEngine = new BubblesEngine(bubblesContainer, () => {
    if (fieldEngine) fieldEngine.showMode('approval');
  });

  // State Machine (Single Source of Truth)
  const stateMachine = new StateMachine({
    orbEngine,
    audioSim,
    onStateChange: (state) => {
      // Keep voice mic button in sync with listening state
      const voiceMicBtn = document.getElementById('voice-mic-btn');
      if (voiceMicBtn) {
        if (state === 'listening') voiceMicBtn.classList.add('active-listening');
        else voiceMicBtn.classList.remove('active-listening');
      }
    }
  });

  // Field Engine with interactive approval callback
  fieldEngine = new FieldEngine(fieldContainer, () => {
    // When user clicks "Approva ed Esegui" on approval surface
    orbEngine.triggerApprovalPulse();
    if (scenarioEngine && scenarioEngine.currentStep === 7) {
      scenarioEngine.goToStep(8);
      scenarioEngine.play();
    } else {
      stateMachine.transitionTo('working');
      fieldEngine.showMode('stream', { step: 6 });
      bubblesEngine.spawn({
        tier: 'micro',
        text: 'Decisione autorizzata • Esecuzione in corso',
        icon: 'check',
        duration: 3500
      });
    }
  });

  // Manual Mode Controller (Drawer & ⌘K)
  const manualController = new ManualController({
    drawerBackdrop,
    commandPaletteBackdrop
  });

  // Scenario Engine
  scenarioEngine = new ScenarioEngine({
    stateMachine,
    bubblesEngine,
    fieldEngine,
    onStepChange: (step, stepDef) => {
      const stepIndicator = document.getElementById('scenario-step-indicator');
      const toastText = document.getElementById('scenario-toast-text');
      const toastStep = document.getElementById('scenario-toast-step');

      if (stepIndicator) stepIndicator.textContent = `${step}/10`;
      if (toastStep) toastStep.textContent = `Step ${step}`;
      if (toastText) toastText.textContent = `${stepDef.title}: ${stepDef.desc}`;
    }
  });

  // 3. Render Loop (60/120 FPS requestAnimationFrame with Telemetry)
  let lastTelemetryTick = 0;
  function renderLoop(currentTime) {
    const audioLevel = audioSim.update(16.6);
    orbEngine.setAudioLevel(audioLevel);
    orbEngine.render(currentTime);

    // Update Telemetry HUD every 400ms
    if (currentTime - lastTelemetryTick > 400) {
      lastTelemetryTick = currentTime;
      const metrics = orbEngine.getMetrics();
      const telemetryText = document.getElementById('telemetry-text');
      if (telemetryText) {
        telemetryText.textContent = `${metrics.fps} FPS • ${metrics.frameTimeMs}ms • ${metrics.particleCount}pts`;
      }
    }

    requestAnimationFrame(renderLoop);
  }
  requestAnimationFrame(renderLoop);

  // Debounced Window Resize
  let resizeTimer = null;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      orbEngine.setupCanvas();
      orbEngine.initParticles();
    }, 120);
  });

  // 4. Quick State Switcher Buttons (Top Bar)
  document.querySelectorAll('.state-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const targetState = btn.dataset.state;
      scenarioEngine.pause();

      if (targetState === 'needs-you') {
        stateMachine.transitionTo('needs-you');
        fieldEngine.showMode('approval');
        bubblesEngine.spawn({
          tier: 'attention',
          text: 'Mi serve una tua decisione sul database',
          icon: 'alert',
          duration: 0
        });
      } else if (targetState === 'done') {
        stateMachine.transitionTo('done');
        fieldEngine.showMode('result');
      } else if (targetState === 'working') {
        stateMachine.transitionTo('working');
        fieldEngine.showMode('stream', { step: 5 });
        bubblesEngine.spawn({
          tier: 'micro',
          text: 'Analisi codice in corso...',
          icon: 'search',
          duration: 3000
        });
      } else {
        stateMachine.transitionTo(targetState);
        fieldEngine.showMode('hidden');
        bubblesEngine.clear();
      }
    });
  });

  // 5. Adaptive Quality Switcher Buttons
  document.querySelectorAll('.quality-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      document.querySelectorAll('.quality-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const quality = btn.dataset.quality;
      orbEngine.setQuality(quality);
    });
  });

  // 6. Reduced Motion Accessibility Toggle
  const motionToggleBtn = document.getElementById('motion-toggle-btn');
  if (motionToggleBtn) {
    motionToggleBtn.addEventListener('click', () => {
      const isCurrentlyReduced = orbEngine.reducedMotion;
      const nextReduced = !isCurrentlyReduced;
      orbEngine.setReducedMotion(nextReduced);
      motionToggleBtn.classList.toggle('active-reduced', nextReduced);
      motionToggleBtn.querySelector('span').textContent = nextReduced ? 'Moto: Ridotto' : 'Moto: Normale';
    });
  }

  // 7. Scenario Playback Controls
  const playBtn = document.getElementById('scenario-play-btn');
  const prevBtn = document.getElementById('scenario-prev-btn');
  const nextBtn = document.getElementById('scenario-next-btn');

  if (playBtn) {
    playBtn.addEventListener('click', (e) => {
      e.preventDefault();
      scenarioEngine.togglePlay();
    });
  }

  if (prevBtn) {
    prevBtn.addEventListener('click', (e) => {
      e.preventDefault();
      scenarioEngine.pause();
      scenarioEngine.prev();
    });
  }

  if (nextBtn) {
    nextBtn.addEventListener('click', (e) => {
      e.preventDefault();
      scenarioEngine.pause();
      scenarioEngine.next();
    });
  }

  // 8. Audio Toggle Pill
  const audioPill = document.getElementById('audio-sim-pill');
  if (audioPill) {
    audioPill.addEventListener('click', () => {
      const isUnmuted = audioSim.toggleSound();
      audioPill.classList.toggle('sound-active', isUnmuted);
      audioPill.querySelector('span').textContent = isUnmuted ? 'Voce: Attiva' : 'Voce: Muto';
    });
  }

  // 7. Manual Drawer & Command Palette Buttons
  const openDrawerBtn = document.getElementById('open-manual-drawer-btn');
  if (openDrawerBtn) {
    openDrawerBtn.addEventListener('click', () => manualController.toggleDrawer());
  }

  const openPaletteBtn = document.getElementById('open-command-palette-btn');
  if (openPaletteBtn) {
    openPaletteBtn.addEventListener('click', () => manualController.toggleCommandPalette());
  }

  // 8. Prompt Input Dock & Voice Mic
  const promptInput = document.getElementById('prompt-input');
  const sendPromptBtn = document.getElementById('send-prompt-btn');
  const voiceMicBtn = document.getElementById('voice-mic-btn');

  function handleSendPrompt() {
    const text = promptInput ? promptInput.value.trim() : '';
    if (!text) return;

    scenarioEngine.pause();
    scenarioEngine.updateDialogue('user', text);
    if (promptInput) promptInput.value = '';

    // Aether reacts
    stateMachine.transitionTo('listening');
    setTimeout(() => {
      stateMachine.transitionTo('speaking');
      scenarioEngine.updateDialogue('aether', `Ricevuto. Procedo con la gestione di "${text}".`);
      setTimeout(() => {
        stateMachine.transitionTo('working');
        bubblesEngine.spawn({
          tier: 'micro',
          text: 'Attività avviata in background...',
          duration: 3200
        });
      }, 2500);
    }, 1200);
  }

  if (sendPromptBtn) {
    sendPromptBtn.addEventListener('click', handleSendPrompt);
  }

  if (promptInput) {
    promptInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        handleSendPrompt();
      }
    });
  }

  if (voiceMicBtn) {
    voiceMicBtn.addEventListener('click', () => {
      const isListening = stateMachine.getState() === 'listening';
      if (isListening) {
        stateMachine.transitionTo('idle');
      } else {
        stateMachine.transitionTo('listening');
      }
    });
  }

  // 9. Prompt Suggestion Chips
  document.querySelectorAll('.prompt-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const text = chip.dataset.prompt || chip.textContent.trim();
      if (text.includes('progetto Alfa') || text.includes('Alfa')) {
        scenarioEngine.goToStep(1);
        scenarioEngine.play();
      } else {
        if (promptInput) promptInput.value = text;
        handleSendPrompt();
      }
    });
  });

  // 10. Click on Orb directly to cycle states
  const orbViewport = document.querySelector('.orb-viewport');
  if (orbViewport) {
    orbViewport.addEventListener('click', () => {
      orbEngine.triggerMicroReaction();
      const cur = stateMachine.getState();
      const cycle = ['idle', 'listening', 'speaking', 'working', 'needs-you', 'done'];
      const nextIdx = (cycle.indexOf(cur) + 1) % cycle.length;
      const targetState = cycle[nextIdx];

      scenarioEngine.pause();
      if (targetState === 'needs-you') {
        stateMachine.transitionTo('needs-you');
        fieldEngine.showMode('approval');
      } else if (targetState === 'done') {
        stateMachine.transitionTo('done');
        fieldEngine.showMode('result');
      } else {
        stateMachine.transitionTo(targetState);
        fieldEngine.showMode('hidden');
      }
    });
  }

  // Expose to window for testing and verification
  window.Aether = {
    stateMachine,
    orbEngine,
    audioSim,
    scenarioEngine,
    fieldEngine,
    bubblesEngine,
    manualController
  };

  // Initial step setup (respecting ?step= or ?state= URL params)
  const paramStep = parseInt(urlParams.get('step') || '0', 10);
  if (paramStep >= 1 && paramStep <= 10) {
    scenarioEngine.goToStep(paramStep);
  } else if (paramState && ['idle', 'listening', 'speaking', 'working', 'needs-you', 'done'].includes(paramState)) {
    stateMachine.transitionTo(paramState);
    if (paramState === 'needs-you') {
      fieldEngine.showMode('approval');
    } else if (paramState === 'done') {
      fieldEngine.showMode('result');
    } else if (paramState === 'working') {
      fieldEngine.showMode('stream', { step: 5 });
    }
  } else {
    scenarioEngine.goToStep(1);
  }

  console.log("[Aether V2] Initialized successfully.");
}

// Robust DOM bootstrap (runs whether DOMContentLoaded has already fired or not)
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootstrapAether);
} else {
  bootstrapAether();
}
