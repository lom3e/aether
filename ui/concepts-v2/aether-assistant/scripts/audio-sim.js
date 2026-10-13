/**
 * AETHER V2 — AUDIO SIMULATION & WAVE ENGINE
 * Generates synthetic speech frequencies & audio levels for Orb responsiveness.
 * Designed so that later real Web Audio API / TTS streams can replace this seamlessly.
 */

export class AudioSim {
  constructor() {
    this.audioCtx = null;
    this.oscillator = null;
    this.gainNode = null;
    this.filterNode = null;
    this.isMuted = true; // Default to silent for user comfort
    this.currentLevel = 0; // [0, 1] normalized volume
    this.targetLevel = 0;
    this.speechPhase = 0;
    this.isSpeaking = false;
    this.isListening = false;
  }

  init() {
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (AudioContext) {
        this.audioCtx = new AudioContext();
      }
    } catch (e) {
      console.warn("AudioContext initialization postponed until user interaction", e);
    }
  }

  toggleSound() {
    if (!this.audioCtx) {
      this.init();
    }
    if (this.audioCtx && this.audioCtx.state === 'suspended') {
      this.audioCtx.resume();
    }
    this.isMuted = !this.isMuted;
    if (this.isMuted) {
      this.stopSyntheticVoice();
    }
    return !this.isMuted;
  }

  setSpeaking(speaking) {
    this.isSpeaking = speaking;
    if (speaking && !this.isMuted) {
      this.startSyntheticVoice();
    } else {
      this.stopSyntheticVoice();
    }
  }

  setListening(listening) {
    this.isListening = listening;
  }

  startSyntheticVoice() {
    if (!this.audioCtx || this.isMuted) return;
    try {
      if (this.oscillator) {
        this.oscillator.stop();
        this.oscillator.disconnect();
      }

      // Soft harmonic sound for Aether
      this.oscillator = this.audioCtx.createOscillator();
      this.gainNode = this.audioCtx.createGain();
      this.filterNode = this.audioCtx.createBiquadFilter();

      this.oscillator.type = 'sine';
      this.oscillator.frequency.setValueAtTime(220, this.audioCtx.currentTime); // A3 calm note

      this.filterNode.type = 'lowpass';
      this.filterNode.frequency.setValueAtTime(600, this.audioCtx.currentTime);

      this.gainNode.gain.setValueAtTime(0.001, this.audioCtx.currentTime);
      this.gainNode.gain.exponentialRampToValueAtTime(0.04, this.audioCtx.currentTime + 0.1);

      this.oscillator.connect(this.filterNode);
      this.filterNode.connect(this.gainNode);
      this.gainNode.connect(this.audioCtx.destination);

      this.oscillator.start();
    } catch (e) {
      console.warn("Could not start synthetic sound", e);
    }
  }

  stopSyntheticVoice() {
    if (this.gainNode && this.audioCtx) {
      try {
        this.gainNode.gain.setValueAtTime(this.gainNode.gain.value, this.audioCtx.currentTime);
        this.gainNode.gain.exponentialRampToValueAtTime(0.0001, this.audioCtx.currentTime + 0.08);
        setTimeout(() => {
          if (this.oscillator) {
            try { this.oscillator.stop(); } catch (_) {}
            this.oscillator = null;
          }
        }, 100);
      } catch (e) {
        this.oscillator = null;
      }
    }
  }

  /**
   * Update audio levels every animation frame
   * Returns current intensity [0, 1] to drive Orb particles
   */
  update(deltaMs) {
    if (this.isSpeaking) {
      this.speechPhase += deltaMs * 0.006;
      // Multi-frequency speech cadenza: simulated syllables and natural pauses
      const syllable = Math.sin(this.speechPhase * 3.2);
      const cadence = Math.sin(this.speechPhase * 0.9);
      const breath = Math.sin(this.speechPhase * 0.25);

      // Natural pause simulation
      const pause = cadence > 0.6 ? 0.15 : 1.0;

      let rawLevel = (Math.max(0, syllable) * 0.6 + Math.max(0, cadence) * 0.3 + 0.1) * breath * pause;
      rawLevel = Math.max(0.05, Math.min(1.0, rawLevel));
      this.targetLevel = rawLevel;

      // Modulate oscillator frequency gently if unmuted
      if (this.oscillator && this.audioCtx && !this.isMuted) {
        const targetPitch = 220 + syllable * 45 + cadence * 30;
        this.oscillator.frequency.setTargetAtTime(targetPitch, this.audioCtx.currentTime, 0.04);
        if (this.gainNode) {
          const targetVol = 0.015 + rawLevel * 0.035;
          this.gainNode.gain.setTargetAtTime(targetVol, this.audioCtx.currentTime, 0.04);
        }
      }
    } else if (this.isListening) {
      // Gentle listening acoustic attention wave
      this.speechPhase += deltaMs * 0.003;
      const wave = Math.sin(this.speechPhase * 2.5);
      this.targetLevel = 0.2 + Math.max(0, wave) * 0.25;
    } else {
      this.targetLevel = 0;
    }

    // Smooth interpolation
    this.currentLevel += (this.targetLevel - this.currentLevel) * 0.18;
    return this.currentLevel;
  }
}
