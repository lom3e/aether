/**
 * AETHER ORB V4 — LIVING 3D POINT SPHERE PRODUCTION ENGINE
 *
 * Visual Reference: "Create Point sphere animation in WebGL, THREE JS & GSAP"
 * Architecture: Optimized for React + TypeScript + Vite + Tauri v2
 *
 * Core Capabilities:
 * - Dominant, immersive presence (expanded 640px viewport, ~450px diameter on desktop)
 * - Zero-GC rendering loop with TypedArrays & 32-band pre-calculated depth color LUT
 * - Adaptive Quality profiles (Auto / High 1080pts / Med 720pts / Low 450pts)
 * - Quintic zero-jerk continuous easing across all kinetics, geometry, and color states
 * - Fluid WORKING <-> NEEDS-YOU <-> APPROVED transitions with interactive acceptance pulses
 * - Native prefers-reduced-motion accessibility & Page Visibility battery savings
 * - Live telemetry reporting (FPS, frame time ms, particle count, DPR)
 */

export class OrbEngine {
  constructor(canvasElement, options = {}) {
    this.canvas = canvasElement;
    this.ctx = this.canvas.getContext('2d', { alpha: true });

    // Quality profiles
    this.qualityProfiles = {
      high: {
        particleCount: 1080,
        dprCap: 2.0,
        harmonics: 2,
        coreGlow: true,
        frontCore: false,
        label: 'High'
      },
      medium: {
        particleCount: 720,
        dprCap: 2.0,
        harmonics: 1,
        coreGlow: false,
        frontCore: false,
        label: 'Med'
      },
      low: {
        particleCount: 450,
        dprCap: 1.0,
        harmonics: 1,
        coreGlow: false,
        frontCore: false,
        label: 'Low'
      }
    };

    // Quality mode: 'auto' | 'high' | 'medium' | 'low'
    this.qualityMode = options.quality || 'auto';
    this.activeProfileKey = this.resolveInitialQuality();
    this.profile = this.qualityProfiles[this.activeProfileKey];
    this.particleCount = this.profile.particleCount;

    // Viewport & Scale
    this.width = 640;
    this.height = 640;
    this.fov = 540; // Proportional perspective depth
    this.radius = 225; // Impressive dominant presence (~450px diameter)

    // Motion Accessibility (prefers-reduced-motion)
    this.reducedMotion = options.reducedMotion !== undefined 
      ? options.reducedMotion 
      : (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    this.initReducedMotionWatcher();

    // Canvas & DPR setup
    this.setupCanvas();

    // Pre-allocated TypedArray buffers (Zero allocations in render loop)
    this.maxParticles = 1200;
    this.posData = new Float32Array(this.maxParticles * 6);   // ux, uy, uz, tx, ty, tz
    this.paramData = new Float32Array(this.maxParticles * 4); // phi, theta, phase, freqMult
    this.sizeOffsetData = new Float32Array(this.maxParticles);
    this.projX = new Float32Array(this.maxParticles);
    this.projY = new Float32Array(this.maxParticles);
    this.projZ = new Float32Array(this.maxParticles);
    this.projScale = new Float32Array(this.maxParticles);
    this.projDepth = new Float32Array(this.maxParticles);
    this.projSize = new Float32Array(this.maxParticles);
    this.projIndices = new Int32Array(this.maxParticles);

    // 32-band Depth Color LUT (eliminates 1000+ string concatenations per frame)
    this.depthColorLut = new Array(32);
    for (let i = 0; i < 32; i++) this.depthColorLut[i] = 'rgba(215,175,255,1.0)';

    // Generate particle geometry
    this.initParticles();

    // Motion Clocks & Physical Orientations
    this.rotY = 0.52;
    this.tiltX = -0.42; // Tilted toward viewer
    this.tiltZ = -0.48; // Swirl anchor in lower-left
    this.time = 0;
    this.lastTime = performance.now();
    this.audioLevel = 0;
    this.approvalPulse = 0;
    this.donePulseProgress = 0;
    this.clickMicroReaction = 0;

    // Interactive Pointer Parallax
    this.mouseOffset = { x: 0, y: 0, targetX: 0, targetY: 0 };
    this.initMouseListener();

    // State Configurations
    this.stateConfig = {
      idle: {
        duration: 650,
        speedY: 0.0032,
        speedX: 0.0006,
        radiusScale: 1.0,
        breathAmp: 0.024,
        breathFreq: 0.0015,
        driftAmp: 2.2,
        waveAmp: 0.024,
        waveFreq: 0.0016,
        frontColor: [215, 175, 255], // Luminous radiant Aether Violet
        backColor:  [120, 70, 190],  // Clearly visible deep violet
        pointSizeFront: 3.4,
        pointSizeBack: 1.4,
        alphaFront: 0.95,
        alphaBack: 0.38,
        atmosphereGlow: 0.12
      },
      listening: {
        duration: 650,
        speedY: 0.0052,
        speedX: 0.0010,
        radiusScale: 0.94,          // Gentle attentive contraction (-6%)
        breathAmp: 0.028,
        breathFreq: 0.0026,
        driftAmp: 3.2,
        waveAmp: 0.035,
        waveFreq: 0.0026,
        frontColor: [70, 220, 255],  // Ethereal celestial cyan (NOT neon)
        backColor:  [40, 115, 185],  // Deep oceanic graphite
        pointSizeFront: 3.2,
        pointSizeBack: 1.3,
        alphaFront: 0.92,
        alphaBack: 0.35,
        atmosphereGlow: 0.18
      },
      speaking: {
        duration: 550,
        speedY: 0.0072,
        speedX: 0.0014,
        radiusScale: 1.05,          // Expressive vocal expansion (+5%)
        breathAmp: 0.038,
        breathFreq: 0.0034,
        driftAmp: 4.5,
        waveAmp: 0.060,             // Voice harmonic surface ripple
        waveFreq: 0.0040,
        frontColor: [235, 135, 255], // Vibrant electric violet / magenta
        backColor:  [140, 60, 200],  // Royal amethyst
        pointSizeFront: 3.6,
        pointSizeBack: 1.5,
        alphaFront: 0.98,
        alphaBack: 0.40,
        atmosphereGlow: 0.22
      },
      working: {
        duration: 800,
        speedY: 0.0102,
        speedX: 0.0020,
        radiusScale: 1.0,
        breathAmp: 0.030,
        breathFreq: 0.0028,
        driftAmp: 5.2,
        waveAmp: 0.072,             // Dynamic traveling wave flow
        waveFreq: 0.0036,
        frontColor: [145, 160, 255], // High-energy cobalt / indigo-violet
        backColor:  [70, 85, 190],   // Deep cobalt navy
        pointSizeFront: 3.4,
        pointSizeBack: 1.4,
        alphaFront: 0.95,
        alphaBack: 0.36,
        atmosphereGlow: 0.16
      },
      'needs-you': {
        duration: 850,              // Solemn, respectful deceleration
        speedY: 0.0014,             // Calm stability
        speedX: 0.0003,
        radiusScale: 0.97,
        breathAmp: 0.016,
        breathFreq: 0.0012,
        driftAmp: 1.8,
        waveAmp: 0.016,             // Surface settles
        waveFreq: 0.0012,
        frontColor: [255, 190, 80],  // Warm controlled solar amber / gold
        backColor:  [165, 110, 45],  // Soft bronze
        pointSizeFront: 3.6,
        pointSizeBack: 1.4,
        alphaFront: 0.96,
        alphaBack: 0.38,
        atmosphereGlow: 0.20
      },
      done: {
        duration: 800,
        speedY: 0.0038,
        speedX: 0.0008,
        radiusScale: 1.0,
        breathAmp: 0.024,
        breathFreq: 0.0018,
        driftAmp: 2.5,
        waveAmp: 0.025,
        waveFreq: 0.0018,
        frontColor: [85, 235, 170],  // Soft jade / emerald mint
        backColor:  [45, 135, 95],   // Deep emerald graphite
        pointSizeFront: 3.4,
        pointSizeBack: 1.4,
        alphaFront: 0.95,
        alphaBack: 0.36,
        atmosphereGlow: 0.16
      }
    };

    // State Transition Management
    const startState = options.initialState || 'idle';
    this.currentState = startState;
    this.targetState = startState;
    this.transitionT = 1.0;
    this.transitionDuration = 650;
    this.currentAttrs = { ...(this.stateConfig[startState] || this.stateConfig.idle) };
    this.prevAttrs = { ...(this.stateConfig[startState] || this.stateConfig.idle) };

    // Telemetry Benchmarking
    this.telemetry = {
      fps: 60,
      frameTimeMs: 1.0,
      lastFpsUpdate: performance.now(),
      framesCounted: 0,
      accumTime: 0
    };

    // Page Visibility Watcher (zero CPU when tab is hidden)
    this.isPageVisible = !document.hidden;
    this.initVisibilityWatcher();
  }

  resolveInitialQuality() {
    if (this.qualityMode !== 'auto') return this.qualityMode;
    const isMobile = window.innerWidth < 768;
    const cores = navigator.hardwareConcurrency || 4;
    if (isMobile) return cores >= 8 ? 'medium' : 'low';
    return cores >= 6 ? 'high' : 'medium';
  }

  setQuality(newQuality) {
    if (newQuality === this.qualityMode && this.activeProfileKey === this.resolveInitialQuality()) return;
    this.qualityMode = newQuality;
    this.activeProfileKey = this.resolveInitialQuality();
    this.profile = this.qualityProfiles[this.activeProfileKey];
    this.particleCount = this.profile.particleCount;
    this.setupCanvas();
    this.initParticles();
  }

  setReducedMotion(enabled) {
    this.reducedMotion = !!enabled;
  }

  setupCanvas() {
    const rect = this.canvas.getBoundingClientRect();
    const displayWidth = rect.width > 0 ? rect.width : 640;
    const displayHeight = rect.height > 0 ? rect.height : 640;

    this.width = displayWidth;
    this.height = displayHeight;

    // Apply strict DPR cap based on active profile (never waste GPU fill rate on 3x/4x)
    const rawDpr = window.devicePixelRatio || 1;
    this.dpr = Math.min(rawDpr, this.profile.dprCap);

    this.canvas.width = Math.round(this.width * this.dpr);
    this.canvas.height = Math.round(this.height * this.dpr);

    this.ctx.resetTransform?.();
    this.ctx.scale(this.dpr, this.dpr);

    // Responsive Sphere Radius: commanding presence that scales harmoniously on mobile
    this.radius = Math.min(230, Math.max(130, this.width * 0.355));
    this.fov = this.radius * 2.35;
  }

  initVisibilityWatcher() {
    document.addEventListener('visibilitychange', () => {
      this.isPageVisible = !document.hidden;
      if (this.isPageVisible) {
        this.lastTime = performance.now();
      }
    });
  }

  initReducedMotionWatcher() {
    if (!window.matchMedia) return;
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    media.addEventListener('change', (e) => {
      this.reducedMotion = e.matches;
    });
  }

  initMouseListener() {
    const handlePointer = (e) => {
      if (this.reducedMotion) return;
      const rect = this.canvas.getBoundingClientRect();
      const clientX = e.clientX ?? (e.touches && e.touches[0] ? e.touches[0].clientX : null);
      const clientY = e.clientY ?? (e.touches && e.touches[0] ? e.touches[0].clientY : null);
      if (clientX === null || clientY === null) return;

      const normX = ((clientX - rect.left) / rect.width) * 2 - 1;
      const normY = ((clientY - rect.top) / rect.height) * 2 - 1;

      // Subtle parallax tilt with bounded limits
      this.mouseOffset.targetX = Math.max(-0.25, Math.min(0.25, normX * 0.22));
      this.mouseOffset.targetY = Math.max(-0.25, Math.min(0.25, normY * 0.18));
    };

    window.addEventListener('pointermove', handlePointer, { passive: true });
    window.addEventListener('pointerleave', () => {
      this.mouseOffset.targetX = 0;
      this.mouseOffset.targetY = 0;
    });
  }

  /**
   * Generates spherical coordinates using Mulberry32 PRNG and blended polar bias.
   * Directly writes into pre-allocated TypedArrays for instant allocation-free startup.
   */
  initParticles() {
    const mulberry32 = (seed) => {
      let s = seed >>> 0;
      return () => {
        s = (s + 0x6D2B79F5) >>> 0;
        let t = Math.imul(s ^ (s >>> 15), 1 | s);
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
      };
    };

    const rng = mulberry32(19940428);
    const count = this.particleCount;

    for (let i = 0; i < count; i++) {
      const u1 = rng();
      const u2 = rng();

      // Blended polar sampling: area-preserving + linear bias for polar swirl
      const phiArea = Math.acos(Math.max(-1, Math.min(1, 1 - 2 * u1)));
      const phiLinear = u1 * Math.PI;
      const phi = phiArea * 0.45 + phiLinear * 0.55;

      const theta = u2 * Math.PI * 2;
      const sinPhi = Math.sin(phi);
      const cosPhi = Math.cos(phi);

      const ux = Math.sin(theta) * sinPhi;
      const uy = cosPhi;
      const uz = Math.cos(theta) * sinPhi;

      // Tangent vector along ring for micro-drift
      const tx = Math.cos(theta);
      const ty = 0;
      const tz = -Math.sin(theta);

      const pIdx = i * 6;
      this.posData[pIdx]     = ux;
      this.posData[pIdx + 1] = uy;
      this.posData[pIdx + 2] = uz;
      this.posData[pIdx + 3] = tx;
      this.posData[pIdx + 4] = ty;
      this.posData[pIdx + 5] = tz;

      const paramIdx = i * 4;
      this.paramData[paramIdx]     = phi;
      this.paramData[paramIdx + 1] = theta;
      this.paramData[paramIdx + 2] = (i * 0.413) % (Math.PI * 2);
      this.paramData[paramIdx + 3] = 0.85 + rng() * 0.35;

      this.sizeOffsetData[i] = (rng() - 0.5) * 0.45;
      this.projIndices[i] = i;
    }
  }

  /**
   * Set new target state with customized transition duration and quintic easing
   */
  setState(newState) {
    if (this.currentState === newState && this.transitionT >= 1.0) return;

    const targetDef = this.stateConfig[newState] || this.stateConfig.idle;
    this.targetState = newState;

    // Snapshot current interpolated values as origin of transition
    this.prevAttrs = {
      ...this.currentAttrs,
      frontColor: [...this.currentAttrs.frontColor],
      backColor: [...this.currentAttrs.backColor]
    };

    // Dynamic transition duration based on origin -> destination
    if (
      (this.currentState === 'working' && newState === 'needs-you') ||
      (this.currentState === 'needs-you' && newState === 'working')
    ) {
      this.transitionDuration = 850; // Deep deliberate emotional transition
    } else {
      this.transitionDuration = targetDef.duration || 650;
    }

    this.transitionT = 0.0;
    this.currentState = newState;

    if (newState === 'done') {
      this.donePulseProgress = 1.0;
    }
  }

  /**
   * Trigger the interactive acceptance ripple when user approves an action
   * (Reference Transition: NEEDS YOU -> APPROVED -> WORKING)
   */
  triggerApprovalPulse() {
    this.approvalPulse = 1.0;
  }

  triggerMicroReaction() {
    this.clickMicroReaction = 1.0;
  }

  setAudioLevel(level) {
    this.audioLevel = Math.max(0, Math.min(1, level));
  }

  /**
   * Main render loop called at 60/120 FPS
   */
  render(currentTime) {
    // If browser tab is hidden, suspend frame processing to save 100% battery/CPU
    if (!this.isPageVisible) {
      this.lastTime = currentTime;
      return;
    }

    const frameStart = performance.now();
    const deltaMs = Math.min(32, currentTime - this.lastTime);
    this.lastTime = currentTime;
    this.time += deltaMs;

    // Smooth state transition interpolation (Quintic zero-jerk easing)
    if (this.transitionT < 1.0) {
      this.transitionT += deltaMs / this.transitionDuration;
      if (this.transitionT > 1.0) this.transitionT = 1.0;
    }

    const t = this.quinticEase(this.transitionT);
    const target = this.stateConfig[this.currentState] || this.stateConfig.idle;

    // Interpolate continuous attributes
    this.currentAttrs.speedY = this.lerp(this.prevAttrs.speedY, target.speedY, t);
    this.currentAttrs.speedX = this.lerp(this.prevAttrs.speedX, target.speedX, t);
    this.currentAttrs.radiusScale = this.lerp(this.prevAttrs.radiusScale, target.radiusScale, t);
    this.currentAttrs.breathAmp = this.lerp(this.prevAttrs.breathAmp, target.breathAmp, t);
    this.currentAttrs.breathFreq = this.lerp(this.prevAttrs.breathFreq, target.breathFreq, t);
    this.currentAttrs.driftAmp = this.lerp(this.prevAttrs.driftAmp, target.driftAmp, t);
    this.currentAttrs.waveAmp = this.lerp(this.prevAttrs.waveAmp, target.waveAmp, t);
    this.currentAttrs.waveFreq = this.lerp(this.prevAttrs.waveFreq, target.waveFreq, t);
    this.currentAttrs.pointSizeFront = this.lerp(this.prevAttrs.pointSizeFront, target.pointSizeFront, t);
    this.currentAttrs.pointSizeBack = this.lerp(this.prevAttrs.pointSizeBack, target.pointSizeBack, t);
    this.currentAttrs.alphaFront = this.lerp(this.prevAttrs.alphaFront, target.alphaFront, t);
    this.currentAttrs.alphaBack = this.lerp(this.prevAttrs.alphaBack, target.alphaBack, t);
    this.currentAttrs.atmosphereGlow = this.lerp(this.prevAttrs.atmosphereGlow, target.atmosphereGlow, t);

    // Continuous RGB Color Vector Lerp
    let frontColor = this.lerpVec3(this.prevAttrs.frontColor, target.frontColor, t);
    let backColor = this.lerpVec3(this.prevAttrs.backColor, target.backColor, t);

    // In SPEAKING state, voice phonemes add radiant vocal harmonic shifts
    if (this.currentState === 'speaking' && this.audioLevel > 0.04) {
      const voiceShift = Math.sin(this.time * 0.007) * 0.5 + 0.5;
      const blueTint = [160, 205, 255];
      frontColor = this.lerpVec3(frontColor, blueTint, this.audioLevel * 0.35 * voiceShift);
    }

    this.currentAttrs.frontColor = frontColor;
    this.currentAttrs.backColor = backColor;

    // Update 32-band Depth Color LUT (Zero string allocations inside point loop)
    const frontR = frontColor[0], frontG = frontColor[1], frontB = frontColor[2];
    const backR  = backColor[0],  backG  = backColor[1],  backB  = backColor[2];
    const aFront = this.currentAttrs.alphaFront;
    const aBack  = this.currentAttrs.alphaBack;

    for (let b = 0; b < 32; b++) {
      const depthRatio = b / 31;
      let r = Math.round(backR + (frontR - backR) * depthRatio);
      let g = Math.round(backG + (frontG - backG) * depthRatio);
      let bl = Math.round(backB + (frontB - backB) * depthRatio);
      let alpha = aBack + (aFront - aBack) * depthRatio;

      // Natural luminous highlight for front-most 18% of particles
      if (depthRatio > 0.82) {
        const shine = (depthRatio - 0.82) / 0.18;
        r = Math.min(255, Math.round(r + (255 - r) * shine * 0.5));
        g = Math.min(255, Math.round(g + (255 - g) * shine * 0.5));
        bl = Math.min(255, Math.round(bl + (255 - bl) * shine * 0.5));
        alpha = Math.min(1.0, alpha + shine * 0.06);
      }

      this.depthColorLut[b] = `rgba(${r},${g},${bl},${alpha.toFixed(2)})`;
    }

    // Motion Scaling based on Accessibility
    const motionScale = this.reducedMotion ? 0.22 : 1.0;
    const waveScale   = this.reducedMotion ? 0.15 : 1.0;

    // Pointer parallax inertia damping
    if (!this.reducedMotion) {
      this.mouseOffset.x += (this.mouseOffset.targetX - this.mouseOffset.x) * 0.05;
      this.mouseOffset.y += (this.mouseOffset.targetY - this.mouseOffset.y) * 0.05;
    } else {
      this.mouseOffset.x = 0;
      this.mouseOffset.y = 0;
    }

    // Global rotation clocks
    this.rotY += this.currentAttrs.speedY * (deltaMs / 16.6) * motionScale;

    // Tilted polar orientation
    const currentTiltX = this.tiltX + this.mouseOffset.y + (this.reducedMotion ? 0 : Math.sin(this.time * 0.0006) * 0.02);
    const currentTiltZ = this.tiltZ + this.mouseOffset.x + (this.reducedMotion ? 0 : Math.cos(this.time * 0.0005) * 0.02);

    // Global breathing
    const globalBreath = Math.sin(this.time * this.currentAttrs.breathFreq) * this.currentAttrs.breathAmp * motionScale;

    // Voice acoustic expansion (subtle and dignified, not an equalizer)
    const voiceExpansion = this.audioLevel * 0.06 * motionScale;

    // Micro Reaction Decay (on pointer click)
    let clickExpansion = 0;
    if (this.clickMicroReaction > 0) {
      this.clickMicroReaction -= deltaMs * 0.0025; // decays smoothly in ~400ms
      if (this.clickMicroReaction < 0) this.clickMicroReaction = 0;
      // Critically damped curve: zero overshoot, gentle 1.5% soft breath
      clickExpansion = this.clickMicroReaction * 0.015;
    }

    // Approval Acceptance Soft Pulse (gentle dignified acknowledgment, zero bounce)
    let approvalWave = 0;
    if (this.approvalPulse > 0) {
      this.approvalPulse -= deltaMs * 0.0018; // smooth decay in ~550ms
      if (this.approvalPulse < 0) this.approvalPulse = 0;
      approvalWave = this.approvalPulse * 0.022; // max +2.2%, smooth monotonic return
    }

    // DONE state soft settling (monotonic relaxation, zero bounce)
    let doneWave = 0;
    if (this.donePulseProgress > 0) {
      this.donePulseProgress -= deltaMs * 0.0016;
      if (this.donePulseProgress < 0) this.donePulseProgress = 0;
      doneWave = this.donePulseProgress * 0.018; // max +1.8%, monotonic return
    }

    const effectiveBaseRadius = this.radius * (
      this.currentAttrs.radiusScale + 
      globalBreath + 
      voiceExpansion + 
      approvalWave + 
      doneWave +
      clickExpansion
    );

    // Clear Canvas
    this.ctx.clearRect(0, 0, this.width, this.height);

    const centerX = this.width / 2;
    const centerY = this.height / 2;

    // Optional controlled atmospheric aura directly behind the Orb
    if (this.profile.coreGlow && this.currentAttrs.atmosphereGlow > 0.02) {
      const auraRadius = effectiveBaseRadius * 0.85;
      const auraGrad = this.ctx.createRadialGradient(centerX, centerY, 0, centerX, centerY, auraRadius);
      auraGrad.addColorStop(0, `rgba(${frontR},${frontG},${frontB},${this.currentAttrs.atmosphereGlow * 0.12})`);
      auraGrad.addColorStop(0.5, `rgba(${frontR},${frontG},${frontB},${this.currentAttrs.atmosphereGlow * 0.04})`);
      auraGrad.addColorStop(1, 'rgba(0,0,0,0)');
      this.ctx.fillStyle = auraGrad;
      this.ctx.beginPath();
      this.ctx.arc(centerX, centerY, auraRadius, 0, Math.PI * 2);
      this.ctx.fill();
    }

    // Pre-calculate Rotation Matrices
    const cosY = Math.cos(this.rotY), sinY = Math.sin(this.rotY);
    const cosX = Math.cos(currentTiltX), sinX = Math.sin(currentTiltX);
    const cosZ = Math.cos(currentTiltZ), sinZ = Math.sin(currentTiltZ);

    const count = this.particleCount;
    const wFreq = this.currentAttrs.waveFreq;
    const wAmp  = this.currentAttrs.waveAmp * waveScale;
    const dAmp  = this.currentAttrs.driftAmp * motionScale;
    const ptFrontBase = this.currentAttrs.pointSizeFront;
    const ptBackBase  = this.currentAttrs.pointSizeBack;

    // Transform and project all particles (TypedArray batch processing)
    for (let i = 0; i < count; i++) {
      const pIdx = i * 6;
      const ux = this.posData[pIdx];
      const uy = this.posData[pIdx + 1];
      const uz = this.posData[pIdx + 2];
      const tx = this.posData[pIdx + 3];
      const tz = this.posData[pIdx + 5];

      const paramIdx = i * 4;
      const phi      = this.paramData[paramIdx];
      const theta    = this.paramData[paramIdx + 1];
      const phase    = this.paramData[paramIdx + 2];
      const freqMult = this.paramData[paramIdx + 3];

      // Multi-harmonic surface traveling wave
      let surfaceWave = 0;
      if (wAmp > 0.001) {
        const wave1 = Math.sin(theta * 3.0 + this.time * wFreq) *
                      Math.cos(phi * 4.0 + this.time * wFreq * 0.85);
        let wave2 = 0;
        if (this.profile.harmonics > 1) {
          wave2 = Math.sin(ux * 2.8 + uy * 2.4 + this.time * wFreq * 1.3) * 0.35;
        }
        surfaceWave = (wave1 + wave2) * wAmp;
      }

      // Voice acoustic wave during speech
      let voiceWave = 0;
      if (this.audioLevel > 0.02 && !this.reducedMotion) {
        voiceWave = Math.sin(phi * 6.0 + this.time * 0.014) * (this.audioLevel * 0.05);
      }

      // Micro tangential drift
      let driftX = 0, driftZ = 0;
      if (dAmp > 0.01) {
        const drift = Math.sin(this.time * 0.0018 * freqMult + phase) * dAmp;
        driftX = tx * drift;
        driftZ = tz * drift;
      }

      const r = effectiveBaseRadius * (1.0 + surfaceWave + voiceWave);

      // 3D position
      const px = ux * r + driftX;
      const py = uy * r;
      const pz = uz * r + driftZ;

      // 1. Spin around polar axis Y
      const x1 = px * cosY - pz * sinY;
      const y1 = py;
      const z1 = px * sinY + pz * cosY;

      // 2. Tilt around X
      const x2 = x1;
      const y2 = y1 * cosX - z1 * sinX;
      const z2 = y1 * sinX + z1 * cosX;

      // 3. Tilt around Z
      const x3 = x2 * cosZ - y2 * sinZ;
      const y3 = x2 * sinZ + y2 * cosZ;
      const z3 = z2;

      // Perspective Projection
      const camDist = this.fov - z3;
      const scale = this.fov / Math.max(120, camDist);

      this.projX[i] = centerX + x3 * scale;
      this.projY[i] = centerY - y3 * scale; // Inverted for canvas coordinates
      this.projZ[i] = z3;
      this.projScale[i] = scale;

      // Depth ratio in [0, 1]
      const d = (z3 + effectiveBaseRadius) / (effectiveBaseRadius * 2);
      const clampedD = Math.max(0.0, Math.min(1.0, d));
      this.projDepth[i] = clampedD;

      // Pre-calculate point size with size attenuation (fine, starry, volumetric)
      const sizeOffset = this.sizeOffsetData[i];
      if (clampedD > 0.45) {
        this.projSize[i] = Math.max(1.2, (ptFrontBase * 0.4 + clampedD * 0.6 + sizeOffset * 0.3) * scale);
      } else {
        this.projSize[i] = Math.max(0.7, (ptBackBase * 0.5 + clampedD * 0.3) * scale);
      }
    }

    // Depth Sorting (Back particles rendered first, front on top)
    this.projIndices.subarray(0, count).sort((a, b) => this.projZ[a] - this.projZ[b]);

    // Render loop using 32-band LUT & perfectly round circular points (Zero GC)
    for (let i = 0; i < count; i++) {
      const idx = this.projIndices[i];
      const x = this.projX[idx];
      const y = this.projY[idx];
      const d = this.projDepth[idx];
      const size = this.projSize[idx];
      const radius = size * 0.5;

      // Fetch pre-computed color string from 32-band LUT
      const lutIndex = Math.min(31, Math.max(0, (d * 31) | 0));
      this.ctx.fillStyle = this.depthColorLut[lutIndex];
      this.ctx.beginPath();
      this.ctx.arc(x, y, radius, 0, Math.PI * 2);
      this.ctx.fill();
    }

    // Telemetry tracking
    const frameElapsed = performance.now() - frameStart;
    this.telemetry.accumTime += frameElapsed;
    this.telemetry.framesCounted++;

    if (currentTime - this.telemetry.lastFpsUpdate >= 500) {
      this.telemetry.fps = Math.round((this.telemetry.framesCounted * 1000) / (currentTime - this.telemetry.lastFpsUpdate));
      this.telemetry.frameTimeMs = (this.telemetry.accumTime / this.telemetry.framesCounted).toFixed(2);
      this.telemetry.lastFpsUpdate = currentTime;
      this.telemetry.framesCounted = 0;
      this.telemetry.accumTime = 0;

      // Auto Quality Adjustment
      if (this.qualityMode === 'auto' && parseFloat(this.telemetry.frameTimeMs) > 17.0) {
        if (this.activeProfileKey === 'high') {
          this.setQuality('medium');
        } else if (this.activeProfileKey === 'medium') {
          this.setQuality('low');
        }
      }
    }
  }

  getMetrics() {
    return {
      fps: this.telemetry.fps,
      frameTimeMs: this.telemetry.frameTimeMs,
      particleCount: this.particleCount,
      dpr: this.dpr.toFixed(2),
      quality: this.activeProfileKey,
      qualityLabel: this.profile.label,
      reducedMotion: this.reducedMotion
    };
  }

  // Mathematics: Quintic Zero-Jerk Easing
  quinticEase(t) {
    return t * t * t * (t * (t * 6 - 15) + 10);
  }

  lerp(a, b, t) {
    return a + (b - a) * t;
  }

  lerpVec3(v1, v2, t) {
    return [
      this.lerp(v1[0], v2[0], t),
      this.lerp(v1[1], v2[1], t),
      this.lerp(v1[2], v2[2], t)
    ];
  }
}
