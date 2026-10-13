/**
 * AETHER V2 — AETHER FIELD ENGINE
 * Fluid Contextual Workspace • Progressive Disclosure • Simplified & Human-Centered
 */

export class FieldEngine {
  constructor(fieldContainerElement, onApprovalSubmit) {
    this.container = fieldContainerElement;
    this.onApprovalSubmit = onApprovalSubmit;
    this.currentMode = 'hidden';
  }

  showMode(mode, options = {}) {
    this.currentMode = mode;
    this.container.classList.remove('field-hidden', 'field-visible');
    
    const stageContainer = document.querySelector('.main-stage');
    if (stageContainer) {
      stageContainer.classList.remove('stage-with-field', 'stage-with-approval', 'stage-with-result');
    }
    document.body.classList.remove('stage-with-field', 'stage-with-approval', 'stage-with-result');

    if (mode === 'hidden') {
      this.container.classList.add('field-hidden');
      return;
    }

    this.container.classList.add('field-visible');

    if (mode === 'stream') {
      if (stageContainer) stageContainer.classList.add('stage-with-field');
      document.body.classList.add('stage-with-field');
      this.renderStreamView(options);
    } else if (mode === 'approval') {
      if (stageContainer) stageContainer.classList.add('stage-with-approval');
      document.body.classList.add('stage-with-approval');
      this.renderApprovalView();
    } else if (mode === 'result') {
      if (stageContainer) stageContainer.classList.add('stage-with-result');
      document.body.classList.add('stage-with-result');
      this.renderResultView();
    }
  }

  /**
   * 1. ACTIVE WORK STREAM (Steps 4 - 6)
   */
  renderStreamView({ step = 5 } = {}) {
    const isStep6 = step >= 6;

    this.container.innerHTML = `
      <div class="field-card">
        <div class="field-header">
          <div class="field-context-title">
            <div class="field-context-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/></svg>
            </div>
            <div class="field-context-text">
              <h3>Progetto Alfa</h3>
              <p>Diagnosi e risoluzione autonoma in corso</p>
            </div>
          </div>
          <div class="field-status-badge working">
            <div class="status-pulse-dot" style="background:#818cf8;box-shadow:0 0 8px #818cf8"></div>
            <span>${isStep6 ? 'Risoluzione automatica' : 'Analisi in corso'}</span>
          </div>
        </div>

        <div class="field-body">
          <div class="field-work-stream">
            <div class="work-milestones">
              <div class="milestone-item complete">
                <div class="milestone-check">✓</div>
                <span>Repository trovato</span>
              </div>
              <div class="milestone-item complete">
                <div class="milestone-check">✓</div>
                <span>Contesto raccolto</span>
              </div>
              <div class="milestone-item ${isStep6 ? 'complete' : 'active'}">
                ${isStep6 ? '<div class="milestone-check">✓</div>' : '<div class="milestone-pulse"></div>'}
                <span>${isStep6 ? '4 problemi individuati' : 'Verifica test e codice'}</span>
              </div>
            </div>

            <div class="issues-container">
              <div class="issues-container-title">Cosa ha trovato Aether</div>
              <div class="issues-grid">
                
                <div class="issue-row">
                  <div class="issue-left">
                    <span class="issue-badge-tag tag-minor">Codice</span>
                    <span class="issue-title-text">Errore potenziale nel controllo credenziali</span>
                  </div>
                  <div class="issue-status-pill ${isStep6 ? 'resolved' : ''}">
                    ${isStep6 ? '✓ Corretto da Aether' : '● In lavorazione'}
                  </div>
                </div>

                <div class="issue-row">
                  <div class="issue-left">
                    <span class="issue-badge-tag tag-warn">Flusso</span>
                    <span class="issue-title-text">Buffer di memoria non limitato</span>
                  </div>
                  <div class="issue-status-pill ${isStep6 ? 'resolved' : ''}">
                    ${isStep6 ? '✓ Corretto da Aether' : '● In lavorazione'}
                  </div>
                </div>

                <div class="issue-row">
                  <div class="issue-left">
                    <span class="issue-badge-tag tag-minor">Sicurezza</span>
                    <span class="issue-title-text">Libreria esterna da aggiornare</span>
                  </div>
                  <div class="issue-status-pill ${isStep6 ? 'resolved' : ''}">
                    ${isStep6 ? '✓ Aggiornata da Aether' : '● In lavorazione'}
                  </div>
                </div>

                <div class="issue-row" style="background: rgba(245, 158, 11, 0.05); border-color: rgba(245, 158, 11, 0.25);">
                  <div class="issue-left">
                    <span class="issue-badge-tag tag-critical">Database</span>
                    <span class="issue-title-text">Disallineamento schema utenti</span>
                  </div>
                  <div class="issue-status-pill pending-approval">
                    <span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:#fbbf24;"></span>
                    <span>Richiede la tua decisione</span>
                  </div>
                </div>

              </div>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  /**
   * 2. APPROVAL SURFACE (Steps 7 & 8)
   */
  renderApprovalView() {
    this.container.innerHTML = `
      <div class="field-card" style="border-color: rgba(245, 158, 11, 0.35); box-shadow: 0 20px 50px -10px rgba(0, 0, 0, 0.85), 0 0 30px rgba(245, 158, 11, 0.12);">
        <div class="field-header" style="background: rgba(245, 158, 11, 0.04);">
          <div class="field-context-title">
            <div class="field-context-icon" style="background: rgba(245, 158, 11, 0.15); border-color: rgba(245, 158, 11, 0.4); color: #fbbf24;">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
            </div>
            <div class="field-context-text">
              <h3>Confermi l'aggiornamento del database?</h3>
              <p>I primi 3 problemi di codice sono stati già risolti da Aether</p>
            </div>
          </div>
          <div class="field-status-badge needs-decision">
            <span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:#f59e0b;box-shadow:0 0 8px #f59e0b;"></span>
            <span>In attesa di tua decisione</span>
          </div>
        </div>

        <div class="field-body">
          <div class="field-approval-surface">
            
            <div class="approval-callout-card">
              <div class="approval-callout-header">
                <span class="approval-callout-badge">Aether ha preparato la soluzione</span>
                <span class="approval-callout-title">Migrazione sicura a zero interruzioni</span>
              </div>
              <p class="approval-callout-desc">
                Ho predisposto una procedura in due fasi per allineare lo schema utenti senza bloccare l'applicazione e con ripristino automatico garantito.
              </p>

              <div class="approval-impact-box">
                <div class="impact-metric">
                  <span class="impact-metric-label">Impatto servizio</span>
                  <span class="impact-metric-value" style="color: #34d399;">Nessuna interruzione</span>
                </div>
                <div class="impact-metric">
                  <span class="impact-metric-label">Sicurezza dati</span>
                  <span class="impact-metric-value" style="color: #34d399;">Retrocompatibile</span>
                </div>
                <div class="impact-metric">
                  <span class="impact-metric-label">Rollback</span>
                  <span class="impact-metric-value" style="color: #34d399;">Automatico e testato</span>
                </div>
              </div>
            </div>

            <div class="approval-actions-dock">
              <button class="btn-amber" id="approval-btn-confirm" style="cursor:pointer;">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                Approva ed Esegui
              </button>
            </div>

          </div>
        </div>
      </div>
    `;

    const confirmBtn = document.getElementById('approval-btn-confirm');
    if (confirmBtn) {
      confirmBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (this.onApprovalSubmit) {
          this.onApprovalSubmit();
        }
      });
    }
  }

  /**
   * 3. FINAL RESULTS DELIVERABLE (Steps 9 - 10)
   */
  renderResultView() {
    this.container.innerHTML = `
      <div class="field-card" style="border-color: rgba(16, 185, 129, 0.35); box-shadow: 0 20px 50px -10px rgba(0, 0, 0, 0.85), 0 0 30px rgba(16, 185, 129, 0.12);">
        <div class="field-header" style="background: rgba(16, 185, 129, 0.05);">
          <div class="field-context-title">
            <div class="field-context-icon" style="background: rgba(16, 185, 129, 0.15); border-color: rgba(16, 185, 129, 0.4); color: #34d399;">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
            </div>
            <div class="field-context-text">
              <h3>Progetto Alfa — Completato</h3>
              <p>Tutti i problemi sono stati risolti e verificati</p>
            </div>
          </div>
          <div class="field-status-badge done">
            <span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:#10b981;box-shadow:0 0 8px #10b981;"></span>
            <span>Verificato</span>
          </div>
        </div>

        <div class="field-body">
          <div class="field-result-surface">
            
            <div class="result-summary-banner">
              <div class="result-banner-left">
                <div class="result-check-shield">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                </div>
                <div class="result-banner-text">
                  <h4>Fatto. Il progetto Alfa è integro e pronto.</h4>
                  <p>3 correzioni applicate • Migrazione database eseguita con successo</p>
                </div>
              </div>
            </div>

            <div class="result-metrics-grid">
              <div class="result-metric-card">
                <span class="result-metric-num" style="color: #34d399;">4 su 4</span>
                <span class="result-metric-title">Problemi risolti</span>
              </div>
              <div class="result-metric-card">
                <span class="result-metric-num" style="color: #60a5fa;">100%</span>
                <span class="result-metric-title">Test superati</span>
              </div>
              <div class="result-metric-card">
                <span class="result-metric-num" style="color: #a78bfa;">4 file</span>
                <span class="result-metric-title">Modifiche pronte</span>
              </div>
              <div class="result-metric-card">
                <span class="result-metric-num" style="color: #34d399;">0s</span>
                <span class="result-metric-title">Interruzioni</span>
              </div>
            </div>

            <div class="result-footer-actions">
              <button class="btn-secondary" id="btn-close-field" style="cursor:pointer;">
                Chiudi Scheda
              </button>
              <button class="btn-primary" id="btn-create-pr" style="cursor:pointer;">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M13 6h3a2 2 0 0 1 2 2v7"/><line x1="6" y1="9" x2="6" y2="21"/></svg>
                Crea Pull Request
              </button>
            </div>

          </div>
        </div>
      </div>
    `;

    const closeBtn = document.getElementById('btn-close-field');
    if (closeBtn) {
      closeBtn.addEventListener('click', (e) => {
        e.preventDefault();
        this.showMode('hidden');
      });
    }

    const prBtn = document.getElementById('btn-create-pr');
    if (prBtn) {
      prBtn.addEventListener('click', (e) => {
        e.preventDefault();
        prBtn.textContent = 'Pull Request Creata ✓';
        prBtn.style.background = '#10b981';
      });
    }
  }
}
