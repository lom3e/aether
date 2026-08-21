import { useState } from 'react';
import { AlertTriangle, RotateCw, ChevronDown, ChevronUp, Settings } from 'lucide-react';
import { useTranslation } from './i18n';

export interface StructuredError {
  code?: string;
  message?: string;
  provider?: string;
  model?: string;
  retryable?: boolean;
  technical_details?: string;
}

interface ChatErrorCardProps {
  error?: StructuredError | string;
  onRetry?: () => void;
  onOpenSettings?: () => void;
}

export function ChatErrorCard({ error, onRetry, onOpenSettings }: ChatErrorCardProps) {
  const [showDetails, setShowDetails] = useState(false);
  const { t } = useTranslation();

  const structured: StructuredError = typeof error === 'string'
    ? { message: error, retryable: true, code: 'TASK_FAILED' }
    : (error || { message: 'Task encountered an error.', retryable: true, code: 'TASK_FAILED' });

  const title = t('taskFailedTitle');
  const userMessage = structured.message || 'The request could not be completed.';
  const isRetryable = structured.retryable !== false;
  const techDetails = structured.technical_details;

  const isSettingsRelated =
    structured.code === 'AUTHENTICATION_ERROR' ||
    structured.code === 'PROVIDER_UNAVAILABLE' ||
    structured.code === 'MODEL_UNAVAILABLE' ||
    structured.code === 'PROVIDER_NOT_FOUND';

  return (
    <div
      data-testid="chat-error-card"
      style={{
        margin: '12px 0',
        padding: '16px',
        borderRadius: '10px',
        border: '1px solid hsl(var(--destructive)/0.35)',
        backgroundColor: 'hsl(var(--destructive)/0.06)',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div
            style={{
              width: '28px',
              height: '28px',
              borderRadius: '6px',
              backgroundColor: 'hsl(var(--destructive)/0.15)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'hsl(var(--destructive))',
              flexShrink: 0,
            }}
          >
            <AlertTriangle size={16} />
          </div>
          <div>
            <div style={{ fontWeight: 600, fontSize: '13.5px', color: 'hsl(var(--destructive))' }}>
              {title}
            </div>
            {(structured.provider || structured.model) && (
              <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '1px' }}>
                {structured.provider && <span style={{ textTransform: 'capitalize' }}>{structured.provider}</span>}
                {structured.provider && structured.model && <span> · </span>}
                {structured.model && <span style={{ fontFamily: 'var(--font-mono)' }}>{structured.model}</span>}
              </div>
            )}
          </div>
        </div>

        {structured.code && (
          <span
            className="badge"
            style={{
              fontSize: '10px',
              backgroundColor: 'hsl(var(--destructive)/0.12)',
              color: 'hsl(var(--destructive))',
              fontFamily: 'var(--font-mono)',
              padding: '2px 6px',
            }}
          >
            {structured.code}
          </span>
        )}
      </div>

      {/* Human Friendly Message */}
      <div style={{ fontSize: '13.5px', color: 'hsl(var(--fg))', lineHeight: 1.5 }}>
        {userMessage}
      </div>

      {/* Action Buttons */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px', paddingTop: '4px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {isRetryable && onRetry && (
            <button
              type="button"
              className="btn btn-secondary"
              style={{
                fontSize: '12px',
                padding: '5px 12px',
                gap: '6px',
                borderColor: 'hsl(var(--destructive)/0.3)',
              }}
              onClick={onRetry}
            >
              <RotateCw size={13} />
              <span>{t('retry')}</span>
            </button>
          )}

          {isSettingsRelated && onOpenSettings && (
            <button
              type="button"
              className="btn btn-ghost"
              style={{
                fontSize: '12px',
                padding: '5px 10px',
                gap: '6px',
                color: 'hsl(var(--primary))',
              }}
              onClick={onOpenSettings}
            >
              <Settings size={13} />
              <span>{t('openSettings')}</span>
            </button>
          )}
        </div>

        {techDetails && (
          <button
            type="button"
            className="btn btn-ghost"
            style={{
              fontSize: '11.5px',
              padding: '4px 8px',
              gap: '4px',
              color: 'hsl(var(--muted-fg))',
            }}
            onClick={() => setShowDetails(!showDetails)}
          >
            <span>{showDetails ? t('hideDetails') : t('errorDetails')}</span>
            {showDetails ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          </button>
        )}
      </div>

      {/* Technical Details Collapsible */}
      {showDetails && techDetails && (
        <div
          style={{
            marginTop: '4px',
            padding: '10px 12px',
            borderRadius: '6px',
            backgroundColor: 'hsl(var(--muted)/0.5)',
            border: '1px solid hsl(var(--border))',
            fontSize: '11.5px',
            fontFamily: 'var(--font-mono)',
            color: 'hsl(var(--muted-fg))',
            maxHeight: '180px',
            overflowX: 'auto',
            overflowY: 'auto',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          {techDetails}
        </div>
      )}
    </div>
  );
}
