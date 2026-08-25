import { useState, useContext } from 'react';
import { Sparkles, RefreshCw } from 'lucide-react';
import { useTranslation } from './i18n';
import { ToastContext } from './toast';
import { apiUrl } from './api';

interface MagicEnhancePromptButtonProps {
  prompt: string;
  role?: string;
  agentName?: string;
  teamName?: string;
  onEnhanced: (enhancedPrompt: string) => void;
  style?: React.CSSProperties;
}

export function MagicEnhancePromptButton({
  prompt,
  role,
  agentName,
  teamName,
  onEnhanced,
  style,
}: MagicEnhancePromptButtonProps) {
  const { t } = useTranslation();
  const showToast = useContext(ToastContext);
  const [isEnhancing, setIsEnhancing] = useState(false);

  const handleEnhance = async () => {
    if (!prompt || !prompt.trim()) {
      showToast(t('enterPromptFirst') || 'Scrivi prima una bozza di istruzioni da ottimizzare', 'info');
      return;
    }

    setIsEnhancing(true);
    try {
      const res = await fetch(apiUrl('/api/architect/enhance-prompt'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt_hint: prompt.trim(),
          role: role || '',
          agent_name: agentName || '',
          team_name: teamName || '',
        }),
      });

      if (!res.ok) {
        throw new Error('Failed to enhance prompt');
      }

      const data = await res.json();
      if (data.enhanced_prompt) {
        onEnhanced(data.enhanced_prompt);
        showToast(t('promptEnhancedSuccess') || 'Prompt ottimizzato con successo!', 'success');
      }
    } catch (err) {
      console.error('Enhance prompt error', err);
      showToast(t('promptEnhanceError') || 'Impossibile ottimizzare il prompt', 'error');
    } finally {
      setIsEnhancing(false);
    }
  };

  return (
    <button
      type="button"
      className="btn btn-ghost"
      onClick={handleEnhance}
      disabled={isEnhancing}
      style={{
        padding: '3px 8px',
        fontSize: '11px',
        color: 'hsl(var(--primary))',
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        cursor: 'pointer',
        ...style,
      }}
    >
      {isEnhancing ? (
        <RefreshCw size={12} className="animate-spin" />
      ) : (
        <Sparkles size={12} />
      )}
      <span>{isEnhancing ? (t('enhancing') || 'Ottimizzazione...') : (t('magicEnhance') || '✨ Migliora con l\'IA')}</span>
    </button>
  );
}
