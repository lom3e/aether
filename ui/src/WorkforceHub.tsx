import { useState, useEffect } from 'react';
import { Users, Brain, GraduationCap, Activity, Puzzle, Bot } from 'lucide-react';
import { Teams } from './Teams';
import { Agents } from './Agents';
import { Memory } from './Memory';
import { Learning } from './Learning';
import { WorkforceHealthView } from './WorkforceHealthView';
import { Skills } from './Skills';

interface WorkforceHubProps {
  initialTab?: string;
  navigate?: (view: string, params?: any) => void;
}

export function WorkforceHub({ initialTab = 'teams', navigate = () => {} }: WorkforceHubProps) {
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
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <Users size={15} /> Team & Topology
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
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <Bot size={15} /> Agents
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
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <Puzzle size={15} /> Skills
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
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <Brain size={15} /> Memory
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
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <GraduationCap size={15} /> Learning & Corrections
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
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <Activity size={15} /> Workforce Health
        </button>
      </div>

      {/* Tab Content */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {currentTab === 'teams' && <Teams />}
        {currentTab === 'agents' && <Agents navigate={navigate} />}
        {currentTab === 'memory' && <Memory />}
        {currentTab === 'learning' && <Learning />}
        {currentTab === 'health' && <WorkforceHealthView />}
        {currentTab === 'skills' && <Skills navigate={navigate} />}
      </div>
    </div>
  );
}
