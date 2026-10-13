/**
 * AETHER V2 — SCENARIO ENGINE ("Progetto Alfa Walkthrough")
 * Implements the 10-step narrative requested:
 * Step 1: Idle
 * Step 2: Listening
 * Step 3: Speaking
 * Step 4: Working + Bubble
 * Step 5: Field Emerge
 * Step 6: Problemi Trovati
 * Step 7: Needs You / Approval
 * Step 8: Working (Post-Approval)
 * Step 9: Done
 * Step 10: Result
 */

export class ScenarioEngine {
  constructor({ stateMachine, bubblesEngine, fieldEngine, onStepChange }) {
    this.stateMachine = stateMachine;
    this.bubblesEngine = bubblesEngine;
    this.fieldEngine = fieldEngine;
    this.onStepChange = onStepChange;

    this.currentStep = 1;
    this.totalSteps = 10;
    this.isPlaying = false;
    this.playTimer = null;
    this.stepTimers = new Set();
    this.playbackSpeed = 1.0;

    this.initSteps();
  }

  addTimer(fn, delay) {
    const id = setTimeout(() => {
      this.stepTimers.delete(id);
      fn();
    }, delay / this.playbackSpeed);
    this.stepTimers.add(id);
    return id;
  }

  clearStepTimers() {
    this.stepTimers.forEach(id => clearTimeout(id));
    this.stepTimers.clear();
  }

  initSteps() {
    this.steps = [
      // STEP 1: IDLE
      {
        step: 1,
        title: "1. Presenza Iniziale",
        state: "idle",
        desc: "Orb in quiete. Aether è presente e attende la richiesta dell'utente.",
        action: () => {
          this.clearStepTimers();
          this.fieldEngine.showMode('hidden');
          this.bubblesEngine.clear();
          this.stateMachine.transitionTo('idle');
          this.clearDialogue();
        }
      },

      // STEP 2: LISTENING
      {
        step: 2,
        title: "2. Ascolto Concentrato",
        state: "listening",
        desc: "L'utente pronuncia la richiesta. L'Orb contrae il volume e si concentra sull'ascolto.",
        action: () => {
          this.clearStepTimers();
          this.fieldEngine.showMode('hidden');
          this.bubblesEngine.clear();
          this.stateMachine.transitionTo('listening');
        }
      },

      // STEP 3: SPEAKING
      {
        step: 3,
        title: "3. Risposta Vocale",
        state: "speaking",
        desc: "Aether risponde all'utente: l'Orb vibra organicamente in sincronia con le armoniche vocali.",
        action: () => {
          this.clearStepTimers();
          this.fieldEngine.showMode('hidden');
          this.bubblesEngine.clear();
          this.stateMachine.transitionTo('speaking');
          this.updateDialogue("aether", "Ricevuto. Mi collego al repository del progetto Alfa e avvio la diagnosi.");
        }
      },

      // STEP 4: WORKING + BUBBLE
      {
        step: 4,
        title: "4. Avvio Lavoro & Thought Bubble",
        state: "working",
        desc: "Orb passa in Working con flussi orbitali. Emerge la prima micro-bubble attorno all'Orb.",
        action: () => {
          this.clearStepTimers();
          this.fieldEngine.showMode('hidden');
          this.bubblesEngine.clear();
          this.stateMachine.transitionTo('working');

          this.bubblesEngine.spawn({
            tier: 'micro',
            text: 'Controllo il progetto Alfa...',
            icon: 'search',
            duration: 3500
          });

          this.addTimer(() => {
            this.bubblesEngine.spawn({
              tier: 'micro',
              text: 'Ho trovato il repository e i file',
              icon: 'check',
              duration: 3200
            });
          }, 1400);
        }
      },

      // STEP 5: FIELD EMERGE
      {
        step: 5,
        title: "5. Aether Field Prende Forma",
        state: "working",
        desc: "Le Thought Bubbles scivolano e fanno emergere lo spazio di lavoro contestuale senza cambiare pagina.",
        action: () => {
          this.clearStepTimers();
          this.bubblesEngine.morphAllToField();
          this.stateMachine.transitionTo('working');

          this.addTimer(() => {
            this.fieldEngine.showMode('stream', { step: 5 });
          }, 350);
        }
      },

      // STEP 6: PROBLEMI TROVATI & RISOLUZIONE
      {
        step: 6,
        title: "6. Problemi Trovati & Primi Fix",
        state: "working",
        desc: "Aether individua 4 problemi. Corregge autonomamente i primi 3 e aggiorna il Field.",
        action: () => {
          this.clearStepTimers();
          this.stateMachine.transitionTo('working');
          this.fieldEngine.showMode('stream', { step: 6 });

          this.bubblesEngine.spawn({
            tier: 'status',
            text: 'Trovati 4 problemi • 3 corretti subito',
            countBadge: '3 fix',
            icon: 'check',
            duration: 4000
          });
        }
      },

      // STEP 7: NEEDS YOU / APPROVAL
      {
        step: 7,
        title: "7. Decisione Richiesta (Needs You)",
        state: "needs-you",
        desc: "L'Orb rallenta con calore ambra controllato. Il Field diventa Superficie di Approvazione per la migrazione DB.",
        action: () => {
          this.clearStepTimers();
          this.stateMachine.transitionTo('needs-you');
          this.fieldEngine.showMode('approval');

          this.bubblesEngine.spawn({
            tier: 'attention',
            text: 'Mi serve una tua decisione sul database',
            icon: 'alert',
            duration: 0,
            onClick: () => {
              this.fieldEngine.showMode('approval');
            }
          });

          this.updateDialogue("aether", "Ho corretto i primi 3 problemi di codice. Per lo schema del database serve la tua approvazione per applicare la procedura sicura.");
        }
      },

      // STEP 8: WORKING (POST-APPROVAL)
      {
        step: 8,
        title: "8. Approvazione & Convalida",
        state: "working",
        desc: "L'utente approva: l'Orb riprende l'energia di Working; Aether applica la migrazione e lancia i test.",
        action: () => {
          this.clearStepTimers();
          this.bubblesEngine.clear();
          if (this.stateMachine.orbEngine) {
            this.stateMachine.orbEngine.triggerApprovalPulse();
          }
          this.stateMachine.transitionTo('working');
          this.fieldEngine.showMode('stream', { step: 6 });
          this.updateDialogue("user", "Approvato. Procedi pure.");

          this.bubblesEngine.spawn({
            tier: 'micro',
            text: 'Applicazione migrazione e test...',
            icon: 'check',
            duration: 3500
          });
        }
      },

      // STEP 9: DONE
      {
        step: 9,
        title: "9. Lavoro Verificato (Done)",
        state: "done",
        desc: "Tutti i test sono superati. L'Orb rilascia un impulso verde smeraldo e conclude l'attività.",
        action: () => {
          this.clearStepTimers();
          this.bubblesEngine.clear();
          this.stateMachine.transitionTo('done');
          this.updateDialogue("aether", "Tutto verificato con successo. Tutti i test sono passati.");

          this.bubblesEngine.spawn({
            tier: 'status',
            text: 'Tutto verificato (100% test superati)',
            countBadge: 'OK',
            icon: 'check',
            duration: 3500
          });
        }
      },

      // STEP 10: RESULT
      {
        step: 10,
        title: "10. Risultato Finale: Fatto",
        state: "idle",
        desc: "Aether consegna il risultato finale: l'Orb torna calmo e il Field mostra la scheda pronta per la Pull Request.",
        action: () => {
          this.clearStepTimers();
          this.bubblesEngine.clear();
          this.stateMachine.transitionTo('idle');
          this.fieldEngine.showMode('result');
          this.updateDialogue("aether", "Fatto. Il progetto Alfa è a posto e pronto per la Pull Request.");
        }
      }
    ];
  }

  goToStep(stepNumber) {
    if (stepNumber < 1) stepNumber = 1;
    if (stepNumber > this.totalSteps) stepNumber = this.totalSteps;

    this.currentStep = stepNumber;
    const stepDef = this.steps[stepNumber - 1];
    if (stepDef && stepDef.action) {
      stepDef.action();
    }

    if (this.onStepChange) {
      this.onStepChange(this.currentStep, stepDef);
    }
  }

  next() {
    if (this.currentStep < this.totalSteps) {
      this.goToStep(this.currentStep + 1);
    } else {
      this.pause();
    }
  }

  prev() {
    if (this.currentStep > 1) {
      this.goToStep(this.currentStep - 1);
    }
  }

  play() {
    // If at the end, restart from step 1
    if (this.currentStep >= this.totalSteps) {
      this.goToStep(1);
    } else {
      this.goToStep(this.currentStep);
    }

    this.isPlaying = true;
    this.updatePlayButton();
    this.scheduleNext();
  }

  pause() {
    this.isPlaying = false;
    if (this.playTimer) {
      clearTimeout(this.playTimer);
      this.playTimer = null;
    }
    this.updatePlayButton();
  }

  togglePlay() {
    if (this.isPlaying) {
      this.pause();
    } else {
      this.play();
    }
  }

  scheduleNext() {
    if (!this.isPlaying) return;

    // Pause on Step 7 (Needs You) to allow user to make the decision
    if (this.currentStep === 7) {
      this.pause();
      return;
    }

    if (this.currentStep >= this.totalSteps) {
      this.pause();
      return;
    }

    const durations = {
      1: 2800,
      2: 2400,
      3: 3200,
      4: 3400,
      5: 3200,
      6: 3400,
      7: 0,
      8: 3000,
      9: 2800,
      10: 0
    };

    const delay = (durations[this.currentStep] || 3000) / this.playbackSpeed;
    this.playTimer = setTimeout(() => {
      if (this.isPlaying) {
        this.next();
        this.scheduleNext();
      }
    }, delay);
  }

  updatePlayButton() {
    const playBtn = document.getElementById('scenario-play-btn');
    if (!playBtn) return;
    if (this.isPlaying) {
      playBtn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg> Pausa`;
      playBtn.style.background = '#7c3aed';
    } else {
      playBtn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg> Play Scenario`;
      playBtn.style.background = '';
    }
  }

  clearDialogue() {
    const streamContainer = document.querySelector('.dialogue-stream');
    if (streamContainer) {
      streamContainer.innerHTML = '';
    }
  }

  updateDialogue(speaker, text) {
    const streamContainer = document.querySelector('.dialogue-stream');
    if (!streamContainer) return;

    const entry = document.createElement('div');
    entry.className = `dialogue-entry from-${speaker}`;

    if (speaker === 'aether') {
      entry.innerHTML = `
        <svg class="dialogue-aether-sparkle" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/></svg>
        <span>${text}</span>
      `;
    } else {
      entry.textContent = text;
    }

    while (streamContainer.children.length >= 2) {
      streamContainer.removeChild(streamContainer.firstChild);
    }
    streamContainer.appendChild(entry);
  }
}
