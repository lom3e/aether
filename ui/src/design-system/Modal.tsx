import React, { useEffect, useRef } from 'react';
import { X } from 'lucide-react';

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  description?: React.ReactNode;
  footer?: React.ReactNode;
  size?: 'sm' | 'md' | 'lg' | 'xl';
  closeOnOverlayClick?: boolean;
  closeOnEsc?: boolean;
  children: React.ReactNode;
  className?: string;
  containerClassName?: string;
}

export function Modal({
  isOpen,
  onClose,
  title,
  description,
  footer,
  size = 'md',
  closeOnOverlayClick = true,
  closeOnEsc = true,
  children,
  className = '',
  containerClassName = '',
}: ModalProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (closeOnEsc && e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };

    // Lock body scroll while open
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = originalOverflow;
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, closeOnEsc, onClose]);

  if (!isOpen) return null;

  return (
    <div
      className={`ds-modal-overlay ${className}`}
      onClick={(e) => {
        if (closeOnOverlayClick && e.target === e.currentTarget) {
          onClose();
        }
      }}
      role="presentation"
    >
      <div
        ref={containerRef}
        className={`ds-modal-container ds-modal-container--${size} ${containerClassName}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? 'ds-modal-title' : undefined}
      >
        {(title || description) && (
          <div className="ds-modal-header">
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              {typeof title === 'string' ? (
                <h3 id="ds-modal-title" className="ds-heading ds-heading--3">
                  {title}
                </h3>
              ) : (
                <div id="ds-modal-title">{title}</div>
              )}
              {typeof description === 'string' ? (
                <p className="ds-text ds-text--muted ds-text--sm">{description}</p>
              ) : (
                description
              )}
            </div>
            <button
              type="button"
              className="ds-icon-btn ds-icon-btn--sm"
              onClick={onClose}
              aria-label="Chiudi finestra"
            >
              <X size={16} />
            </button>
          </div>
        )}
        <div className="ds-modal-body">{children}</div>
        {footer && <div className="ds-modal-footer">{footer}</div>}
      </div>
    </div>
  );
}
