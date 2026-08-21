import { useState } from 'react';
import { Bot, User, Copy, Check, ShieldAlert, CheckCircle2, RotateCw, Edit2, Trash2 } from 'lucide-react';
import { useTranslation } from './i18n';
import { MarkdownRenderer } from './MarkdownRenderer';
import { ChatErrorCard } from './ChatErrorCard';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  agent_name?: string;
  created_at?: string;
  metadata?: any;
  interrupt?: {
    type: 'approval' | 'input';
    message: string;
    interrupt_id?: string;
  };
}

interface MessageItemProps {
  message: ChatMessage;
  onInterruptResponse?: (response: string) => void;
  onRetry?: (content: string) => void;
  onEditMessage?: (messageId: string, newContent: string) => void;
  onDeleteMessage?: (messageId: string) => void;
  onRetryResponse?: (messageId: string) => void;
}

export function MessageItem({
  message,
  onInterruptResponse,
  onRetry,
  onEditMessage,
  onDeleteMessage,
  onRetryResponse
}: MessageItemProps) {
  const [copied, setCopied] = useState(false);
  const [inputText, setInputText] = useState('');
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(message.content);
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);

  const { t } = useTranslation();

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSaveEdit = () => {
    if (!editContent.trim()) return;
    setIsEditing(false);
    if (onEditMessage) {
      onEditMessage(message.id, editContent.trim());
    }
  };

  const isUser = message.role === 'user';
  const agentName = message.agent_name || (isUser ? 'User' : 'Workforce');

  return (
    <div style={{
      display: 'flex',
      gap: '14px',
      padding: '16px 24px',
      borderBottom: '1px solid hsl(var(--border)/0.4)',
      backgroundColor: isUser ? 'hsl(var(--bg))' : 'hsl(var(--card))',
      position: 'relative'
    }}>
      {/* Avatar */}
      <div style={{
        width: '32px',
        height: '32px',
        borderRadius: '8px',
        backgroundColor: isUser ? 'hsl(var(--primary)/0.15)' : 'hsl(var(--muted))',
        color: isUser ? 'hsl(var(--primary))' : 'hsl(var(--fg))',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
        fontWeight: 600,
        fontSize: '13px'
      }}>
        {isUser ? <User size={18} /> : <Bot size={18} />}
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        {/* Header with Title and Actions */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontWeight: 600, fontSize: '13px', color: 'hsl(var(--fg))' }}>
              {agentName}
            </span>
            {!isUser && (
              <span className="badge" style={{ fontSize: '10px', background: 'hsl(var(--primary)/0.1)', color: 'hsl(var(--primary))' }}>
                AI Workforce
              </span>
            )}
            {!isUser && message.metadata?.model && (
              message.metadata.requested_model && message.metadata.requested_model !== message.metadata.model ? (
                <span
                  data-testid="model-fallback-badge"
                  className="badge"
                  style={{
                    fontSize: '10.5px',
                    background: 'hsl(var(--warning-bg))',
                    color: 'hsl(var(--warning))',
                    border: '1px solid hsl(var(--warning)/0.4)',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '3px',
                  }}
                  title={`Requested: ${message.metadata.requested_model} → Executed: ${message.metadata.model}`}
                >
                  ⚡ {message.metadata.model}
                </span>
              ) : (
                <span
                  data-testid="model-badge"
                  className="badge"
                  style={{
                    fontSize: '10.5px',
                    background: 'hsl(var(--muted)/0.6)',
                    color: 'hsl(var(--muted-fg))',
                    border: '1px solid hsl(var(--border)/0.5)',
                  }}
                  title={`Provider: ${message.metadata?.provider || 'default'} | Model: ${message.metadata.model}`}
                >
                  {message.metadata.model}
                </span>
              )
            )}
            {message.created_at && (
              <span style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>
                {new Date(message.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
            )}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            {/* Copy button */}
            <button
              className="btn btn-ghost"
              style={{ padding: '3px 6px', fontSize: '11px' }}
              onClick={handleCopy}
              title={t('copyText')}
            >
              {copied ? <Check size={13} className="text-primary" /> : <Copy size={13} />}
              <span>{copied ? t('copied') : ''}</span>
            </button>

            {/* User Message Actions: Edit & Delete */}
            {isUser && !isEditing && (
              <>
                <button
                  className="btn btn-ghost"
                  style={{ padding: '3px 6px', fontSize: '11px' }}
                  onClick={() => {
                    setIsEditing(true);
                    setEditContent(message.content);
                  }}
                  title={t('editPrompt')}
                >
                  <Edit2 size={13} />
                </button>

                <button
                  className="btn btn-ghost"
                  style={{ padding: '3px 6px', fontSize: '11px' }}
                  onClick={() => {
                    if (onRetry) onRetry(message.content);
                  }}
                  title={t('retry')}
                >
                  <RotateCw size={13} />
                </button>

                <button
                  className="btn btn-ghost"
                  style={{ padding: '3px 6px', fontSize: '11px', color: 'hsl(var(--destructive))' }}
                  onClick={() => setIsConfirmingDelete(true)}
                  title={t('deleteMessage')}
                >
                  <Trash2 size={13} />
                </button>
              </>
            )}

            {/* Assistant Actions: Retry response */}
            {!isUser && onRetryResponse && (
              <button
                className="btn btn-ghost"
                style={{ padding: '3px 6px', fontSize: '11px' }}
                onClick={() => onRetryResponse(message.id)}
                title={t('retryResponse')}
              >
                <RotateCw size={13} />
              </button>
            )}
          </div>
        </div>

        {/* Inline Delete Confirmation */}
        {isConfirmingDelete ? (
          <div style={{
            padding: '10px 14px',
            margin: '8px 0',
            backgroundColor: 'hsl(var(--destructive)/0.08)',
            border: '1px solid hsl(var(--destructive)/0.3)',
            borderRadius: '6px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px'
          }}>
            <span style={{ fontSize: '12.5px', color: 'hsl(var(--destructive))' }}>
              {t('confirmDeleteMessage')}
            </span>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                className="btn btn-secondary"
                style={{ padding: '4px 10px', fontSize: '12px' }}
                onClick={() => setIsConfirmingDelete(false)}
              >
                {t('cancel')}
              </button>
              <button
                className="btn btn-destructive"
                style={{ padding: '4px 10px', fontSize: '12px' }}
                onClick={() => {
                  setIsConfirmingDelete(false);
                  if (onDeleteMessage) onDeleteMessage(message.id);
                }}
              >
                {t('delete')}
              </button>
            </div>
          </div>
        ) : isEditing ? (
          /* Inline Editor */
          <div style={{ margin: '8px 0', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <textarea
              data-testid="inline-edit-textarea"
              className="form-textarea"
              style={{ minHeight: '80px', fontSize: '13.5px', padding: '10px 12px' }}
              value={editContent}
              onChange={e => setEditContent(e.target.value)}
              autoFocus
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button
                className="btn btn-secondary"
                style={{ padding: '4px 12px', fontSize: '12px' }}
                onClick={() => setIsEditing(false)}
              >
                {t('cancel')}
              </button>
              <button
                className="btn btn-primary"
                style={{ padding: '4px 12px', fontSize: '12px' }}
                onClick={handleSaveEdit}
              >
                {t('saveAndResend')}
              </button>
            </div>
          </div>
        ) : message.metadata?.is_error || message.metadata?.error ? (
          <ChatErrorCard
            error={message.metadata.error}
            onRetry={onRetryResponse ? () => onRetryResponse(message.id) : undefined}
          />
        ) : (
          <div style={{ fontSize: '14px', color: 'hsl(var(--fg))' }}>
            <MarkdownRenderer content={message.content} />
          </div>
        )}

        {/* HITL Interactive Card */}
        {message.interrupt && onInterruptResponse && (
          <div style={{
            margin: '16px 0 8px',
            padding: '16px',
            backgroundColor: 'hsl(var(--warning-bg))',
            border: '1px solid hsl(var(--warning)/0.4)',
            borderRadius: 'var(--radius)'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px', color: 'hsl(var(--warning))', fontWeight: 600, fontSize: '13px' }}>
              <ShieldAlert size={16} />
              <span>{message.interrupt.type === 'approval' ? t('approvalRequired') : t('inputRequired')}</span>
            </div>
            <p style={{ fontSize: '13px', marginBottom: '14px', color: 'hsl(var(--fg))' }}>
              {message.interrupt.message}
            </p>

            {message.interrupt.type === 'approval' ? (
              <div style={{ display: 'flex', gap: '10px' }}>
                <button
                  className="btn btn-primary"
                  onClick={() => onInterruptResponse('yes')}
                >
                  <CheckCircle2 size={15} /> {t('approve')}
                </button>
                <button
                  className="btn btn-secondary"
                  onClick={() => onInterruptResponse('no')}
                >
                  {t('reject')}
                </button>
              </div>
            ) : (
              <div style={{ display: 'flex', gap: '10px' }}>
                <input
                  type="text"
                  className="form-input"
                  placeholder={t('typeYourResponse')}
                  value={inputText}
                  onChange={e => setInputText(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter' && inputText.trim()) {
                      onInterruptResponse(inputText.trim());
                      setInputText('');
                    }
                  }}
                />
                <button
                  className="btn btn-primary"
                  onClick={() => {
                    if (inputText.trim()) {
                      onInterruptResponse(inputText.trim());
                      setInputText('');
                    }
                  }}
                >
                  {t('submit')}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
