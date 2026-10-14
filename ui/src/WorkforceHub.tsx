import { useState, useEffect } from 'react';
import { Users, Brain, GraduationCap, Activity, Puzzle, Bot, Award } from 'lucide-react';
import { Teams } from './Teams';
import { Agents } from './Agents';
import { Memory } from './Memory';
import { Learning } from './Learning';
import { WorkforceHealthView } from './WorkforceHealthView';
import { Skills } from './Skills';
import { BenchmarkingView } from './BenchmarkingView';
import { useTranslation } from './i18n';



interface WorkforceHubProps {
  initialTab?: string;
  navigate?: (view: string, params?: any) => void;
}

export function WorkforceHub({ initialTab = 'agents', navigate = () => {} }: WorkforceHubProps) {
  const { t } = useTranslation();
  const [currentTab, setCurrentTab] = useState<string>(initialTab);

  useEffect(() => {
    if (initialTab) {
      setCurrentTab(initialTab);
    }
  }, [initialTab]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Sub-header Navigation Tabs */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '4px',
        padding: '12px 24px 0',
        backgroundColor: 'hsl(var(--card))',
        borderBottom: '1px solid hsl(var(--border))',
        overflowX: 'auto',      // seven tabs do not fit a phone: the row scrolls inside itself
        flexShrink: 0,
      }}>
        <button
          className={`btn btn-ghost ${currentTab === 'teams' ? 'active' : ''}`}
          onClick={() => setCurrentTab('teams')}
          style={{
            borderBottom: currentTab === 'teams' ? '2px solid hsl(var(--primary))' : 'none',
            borderRadius: 0,
            padding: '8px 14px',
            fontSize: '13px',
            fontWeight: 600,
            whiteSpace: 'nowrap',
            flexShrink: 0,
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <Users size={15} /> {t('seTeamsRoles')}
        </button>

        <button
          className={`btn btn-ghost ${currentTab === 'agents' ? 'active' : ''}`}
          onClick={() => setCurrentTab('agents')}
          style={{
            borderBottom: currentTab === 'agents' ? '2px solid hsl(var(--primary))' : 'none',
            borderRadius: 0,
            padding: '8px 14px',
            fontSize: '13px',
            fontWeight: 600,
            whiteSpace: 'nowrap',
            flexShrink: 0,
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <Bot size={15} /> {t('seAssistantsAgents')}
        </button>

        <button
          className={`btn btn-ghost ${currentTab === 'skills' ? 'active' : ''}`}
          onClick={() => setCurrentTab('skills')}
          style={{
            borderBottom: currentTab === 'skills' ? '2px solid hsl(var(--primary))' : 'none',
            borderRadius: 0,
            padding: '8px 14px',
            fontSize: '13px',
            fontWeight: 600,
            whiteSpace: 'nowrap',
            flexShrink: 0,
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <Puzzle size={15} /> {t('seSkillsAbilities')}
        </button>

        <button
          data-testid="tab-memory"
          className={`btn btn-ghost ${currentTab === 'memory' ? 'active' : ''}`}
          onClick={() => setCurrentTab('memory')}
          style={{
            borderBottom: currentTab === 'memory' ? '2px solid hsl(var(--primary))' : 'none',
            borderRadius: 0,
            padding: '8px 14px',
            fontSize: '13px',
            fontWeight: 600,
            whiteSpace: 'nowrap',
            flexShrink: 0,
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <Brain size={15} /> {t('seSharedMemory')}
        </button>

        <button
          data-testid="tab-learning"
          className={`btn btn-ghost ${currentTab === 'learning' ? 'active' : ''}`}
          onClick={() => setCurrentTab('learning')}
          style={{
            borderBottom: currentTab === 'learning' ? '2px solid hsl(var(--primary))' : 'none',
            borderRadius: 0,
            padding: '8px 14px',
            fontSize: '13px',
            fontWeight: 600,
            whiteSpace: 'nowrap',
            flexShrink: 0,
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <GraduationCap size={15} /> {t('seLearningFeedback')}
        </button>

        <button
          className={`btn btn-ghost ${currentTab === 'health' ? 'active' : ''}`}
          onClick={() => setCurrentTab('health')}
          style={{
            borderBottom: currentTab === 'health' ? '2px solid hsl(var(--primary))' : 'none',
            borderRadius: 0,
            padding: '8px 14px',
            fontSize: '13px',
            fontWeight: 600,
            whiteSpace: 'nowrap',
            flexShrink: 0,
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <Activity size={15} /> {t('seOperationalStatus')}
        </button>

        <button
          data-testid="tab-benchmarking"
          className={`btn btn-ghost ${currentTab === 'benchmarking' ? 'active' : ''}`}
          onClick={() => setCurrentTab('benchmarking')}
          style={{
            borderBottom: currentTab === 'benchmarking' ? '2px solid hsl(var(--primary))' : 'none',
            borderRadius: 0,
            padding: '8px 14px',
            fontSize: '13px',
            fontWeight: 600,
            whiteSpace: 'nowrap',
            flexShrink: 0,
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <Award size={15} /> {t('sePerformanceEvaluation')}
        </button>
      </div>

      {/* Tab Content */}
      <div style={{ flex: 1, overflowY: 'auto', overscrollBehavior: 'contain' }}>
        {currentTab === 'teams' && <Teams />}
        {currentTab === 'agents' && <Agents navigate={navigate} />}
        {currentTab === 'memory' && <Memory />}
        {currentTab === 'learning' && <Learning />}
        {currentTab === 'health' && <WorkforceHealthView />}
        {currentTab === 'skills' && <Skills navigate={navigate} />}
        {currentTab === 'benchmarking' && <BenchmarkingView />}
      </div>
    </div>
  );
}

