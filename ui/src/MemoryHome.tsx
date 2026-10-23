import { useState } from 'react';
import { useTranslation } from './i18n';
import { TopHeader } from './TopHeader';
import { KnowsList } from './KnowsList';
import { Knowledge } from './Knowledge';
import './privacy.css';

// One personal Memory: what Aether knows about you (add, correct, forget) and the documents it can read.
export function MemoryHome() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<'knows' | 'docs'>('knows');
  return (
    <div className="pv-page" data-testid="memory-home">
      <TopHeader variant="page" title={t('memHomeTitle')} subtitle={t('memHomeSub')} />
      <div className="pv-body">
        <div className="pv-tabs" role="tablist">
          <button role="tab" aria-selected={tab === 'knows'} className={tab === 'knows' ? 'on' : ''} onClick={() => setTab('knows')} data-testid="memory-tab-knows">{t('memTabKnows')}</button>
          <button role="tab" aria-selected={tab === 'docs'} className={tab === 'docs' ? 'on' : ''} onClick={() => setTab('docs')} data-testid="memory-tab-docs">{t('memTabDocs')}</button>
        </div>
        {tab === 'knows' ? <KnowsList allowAdd /> : <div className="mh-docs"><Knowledge /></div>}
      </div>
    </div>
  );
}
