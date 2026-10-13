import React, { useEffect, useRef } from 'react';
import { X } from 'lucide-react';

export interface DrawerProps {
  isOpen: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  description?: React.ReactNode;
  footer?: React.ReactNode;
  closeOnOverlayClick?: boolean;
  closeOnEsc?: boolean;
  width?: string | number;
  children: React.ReactNode;
  className?: string;
}

export function Drawer({
  isOpen,
  onClose,
  title,
  description,
  footer,
  closeOnOverlayClick = true,
  closeOnEsc = true,
  width = '520px',
  children,
  className = '',
}: DrawerProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (closeOnEsc && e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };

    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = originalOverflow;
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, closeOnEsc, onClose]);

  if (!isOpen) return null;

  const panelWidth = typeof width === 'number' ? `${width}px` : width;

  return (
    <div
      className={`ds-drawer-overlay ${className}`}
      onClick={(e) => {
        if (closeOnOverlayClick && e.target === e.currentTarget) {
          onClose();
        }
      }}
      role="presentation"
    >
      <div
        ref={panelRef}
        className="ds-drawer-panel"
        style={{ maxWidth: panelWidth }}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? 'ds-drawer-title' : undefined}
      >
        <div className="ds-drawer-header">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            {typeof title === 'string' ? (
              <h3 id="ds-drawer-title" className="ds-heading ds-heading--3">
                {title}
              </h3>
            ) : (
              <div id="ds-drawer-title">{title}</div>
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
            aria-label="Chiudi pannello"
          >
            <X size={16} />
          </button>
        </div>
        <div className="ds-drawer-body">{children}</div>
        {footer && <div className="ds-drawer-footer">{footer}</div>}
      </div>
    </div>
  );
}
