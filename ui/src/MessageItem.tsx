import { useState } from 'react';
import { Bot, User, Copy, Check, ShieldAlert, CheckCircle2, RotateCw } from 'lucide-react';
import { useTranslation } from './i18n';

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
}

export function MessageItem({ message, onInterruptResponse, onRetry }: MessageItemProps) {
  const [copied, setCopied] = useState(false);
  const [inputText, setInputText] = useState('');
  const { t } = useTranslation();

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const isUser = message.role === 'user';
  const agentName = message.agent_name || (isUser ? 'User' : 'Workforce');

  // Simple clean markdown parser for code blocks, headers, lists, and bold text
  const renderFormattedContent = (content: string) => {
    if (!content) return null;

    const lines = content.split('\n');
    const elements: any[] = [];
    let inCodeBlock = false;
    let codeLanguage = '';
    let codeBuffer: string[] = [];

    lines.forEach((line, idx) => {
      if (line.startsWith('```')) {
        if (!inCodeBlock) {
          inCodeBlock = true;
          codeLanguage = line.slice(3).trim() || 'text';
          codeBuffer = [];
        } else {
          inCodeBlock = false;
          const codeText = codeBuffer.join('\n');
          elements.push(
            <div key={`code-${idx}`} style={{
              margin: '12px 0',
              borderRadius: 'var(--radius)',
              overflow: 'hidden',
              border: '1px solid hsl(var(--border))',
              backgroundColor: 'hsl(var(--card))'
            }}>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '6px 12px',
                backgroundColor: 'hsl(var(--muted))',
                fontSize: '11px',
                fontFamily: 'var(--font-mono)',
                color: 'hsl(var(--muted-fg))',
                borderBottom: '1px solid hsl(var(--border))'
              }}>
                <span>{codeLanguage}</span>
                <button
                  className="btn btn-ghost"
                  style={{ padding: '2px 6px', fontSize: '11px' }}
                  onClick={() => navigator.clipboard.writeText(codeText)}
                >
                  <Copy size={12} /> Copy
                </button>
              </div>
              <pre style={{
                padding: '12px',
                margin: 0,
                fontSize: '12.5px',
                fontFamily: 'var(--font-mono)',
                overflowX: 'auto',
                lineHeight: 1.5,
                color: 'hsl(var(--fg))'
              }}>
                <code>{codeText}</code>
              </pre>
            </div>
          );
        }
        return;
      }

      if (inCodeBlock) {
        codeBuffer.push(line);
        return;
      }

      // Headers
      if (line.startsWith('### ')) {
        elements.push(<h4 key={idx} style={{ margin: '14px 0 6px', fontSize: '15px', fontWeight: 600 }}>{line.slice(4)}</h4>);
      } else if (line.startsWith('## ')) {
        elements.push(<h3 key={idx} style={{ margin: '18px 0 8px', fontSize: '17px', fontWeight: 600 }}>{line.slice(3)}</h3>);
      } else if (line.startsWith('# ')) {
        elements.push(<h2 key={idx} style={{ margin: '22px 0 10px', fontSize: '19px', fontWeight: 700 }}>{line.slice(2)}</h2>);
      } else if (line.startsWith('* ') || line.startsWith('- ')) {
        // Bullet list
        elements.push(
          <div key={idx} style={{ display: 'flex', gap: '8px', margin: '4px 0 4px 12px' }}>
            <span style={{ color: 'hsl(var(--primary))' }}>•</span>
            <span style={{ flex: 1 }}>{renderInlineMarkdown(line.slice(2))}</span>
          </div>
        );
      } else if (/^\d+\.\s/.test(line)) {
        // Numbered list
        const match = line.match(/^(\d+)\.\s(.*)/);
        if (match) {
          elements.push(
            <div key={idx} style={{ display: 'flex', gap: '8px', margin: '4px 0 4px 12px' }}>
              <span style={{ fontWeight: 600, color: 'hsl(var(--muted-fg))', minWidth: '18px' }}>{match[1]}.</span>
              <span style={{ flex: 1 }}>{renderInlineMarkdown(match[2])}</span>
            </div>
          );
        }
      } else if (line.startsWith('> ')) {
        // Blockquote
        elements.push(
          <blockquote key={idx} style={{
            borderLeft: '3px solid hsl(var(--primary))',
            paddingLeft: '12px',
            margin: '8px 0',
            color: 'hsl(var(--muted-fg))',
            fontStyle: 'italic'
          }}>
            {renderInlineMarkdown(line.slice(2))}
          </blockquote>
        );
      } else if (line.trim() === '') {
        elements.push(<div key={idx} style={{ height: '8px' }} />);
      } else {
        elements.push(
          <p key={idx} style={{ margin: '4px 0', lineHeight: 1.6 }}>
            {renderInlineMarkdown(line)}
          </p>
        );
      }
    });

    return elements;
  };

  const renderInlineMarkdown = (text: string) => {
    // Process **bold**, *italic*, `code`, and [sources]
    const parts = text.split(/(\*\*.*?\*\*|\*.*?\*|`.*?`)/g);
    return parts.map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={i} style={{ fontWeight: 600 }}>{part.slice(2, -2)}</strong>;
      }
      if (part.startsWith('*') && part.endsWith('*')) {
        return <em key={i}>{part.slice(1, -1)}</em>;
      }
      if (part.startsWith('`') && part.endsWith('`')) {
        return (
          <code key={i} style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '12px',
            padding: '2px 5px',
            borderRadius: '4px',
            backgroundColor: 'hsl(var(--muted))',
            color: 'hsl(var(--primary))'
          }}>
            {part.slice(1, -1)}
          </code>
        );
      }
      return part;
    });
  };

  return (
    <div style={{
      display: 'flex',
      gap: '14px',
      padding: '20px 24px',
      borderBottom: '1px solid hsl(var(--border)/0.5)',
      backgroundColor: isUser ? 'hsl(var(--card)/0.3)' : 'transparent',
      transition: 'background-color 0.15s ease'
    }}>
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
            {message.created_at && (
              <span style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>
                {new Date(message.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
            )}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <button
              className="btn btn-ghost"
              style={{ padding: '4px 8px', fontSize: '12px' }}
              onClick={handleCopy}
              title={t('copyText')}
            >
              {copied ? <Check size={14} className="text-primary" /> : <Copy size={14} />}
              <span style={{ fontSize: '11px' }}>{copied ? t('copied') : t('copyText')}</span>
            </button>
            {isUser && onRetry && (
              <button
                className="btn btn-ghost"
                style={{ padding: '4px 8px', fontSize: '12px' }}
                onClick={() => onRetry(message.content)}
                title={t('retry')}
              >
                <RotateCw size={14} />
              </button>
            )}
          </div>
        </div>

        <div style={{ fontSize: '14px', color: 'hsl(var(--fg))' }}>
          {renderFormattedContent(message.content)}
        </div>

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
                  placeholder="Type your response..."
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
