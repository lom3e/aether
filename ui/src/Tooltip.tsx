import React, { useState, useRef, useEffect, useCallback, cloneElement } from 'react';
import { createPortal } from 'react-dom';

export interface TooltipProps {
  content: React.ReactNode;
  children: React.ReactElement;
  position?: 'top' | 'bottom' | 'left' | 'right';
  delay?: number;
  disabled?: boolean;
  className?: string;
  style?: React.CSSProperties;
}

export function Tooltip({
  content,
  children,
  position = 'top',
  delay = 200,
  disabled = false,
  className = '',
  style = {},
}: TooltipProps) {
  const [visible, setVisible] = useState(false);
  const [coords, setCoords] = useState<{ top: number; left: number }>({ top: 0, left: 0 });
  const [actualPosition, setActualPosition] = useState<'top' | 'bottom' | 'left' | 'right'>(position);

  const timeoutRef = useRef<any>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  const tooltipRef = useRef<HTMLDivElement | null>(null);

  const updatePosition = useCallback(() => {
    if (!triggerRef.current) return;
    const targetRect = triggerRef.current.getBoundingClientRect();
    const tooltipEl = tooltipRef.current;

    const tooltipWidth = tooltipEl ? tooltipEl.offsetWidth : 120;
    const tooltipHeight = tooltipEl ? tooltipEl.offsetHeight : 28;
    const gap = 6;

    let targetPos = position;
    let top = 0;
    let left = 0;

    // Determine auto-flip based on viewport boundaries
    if (targetPos === 'top' && targetRect.top - tooltipHeight - gap < 8) {
      targetPos = 'bottom';
    } else if (targetPos === 'bottom' && targetRect.bottom + tooltipHeight + gap > window.innerHeight - 8) {
      targetPos = 'top';
    } else if (targetPos === 'left' && targetRect.left - tooltipWidth - gap < 8) {
      targetPos = 'right';
    } else if (targetPos === 'right' && targetRect.right + tooltipWidth + gap > window.innerWidth - 8) {
      targetPos = 'left';
    }

    setActualPosition(targetPos);

    if (targetPos === 'top') {
      top = targetRect.top - tooltipHeight - gap;
      left = targetRect.left + targetRect.width / 2 - tooltipWidth / 2;
    } else if (targetPos === 'bottom') {
      top = targetRect.bottom + gap;
      left = targetRect.left + targetRect.width / 2 - tooltipWidth / 2;
    } else if (targetPos === 'left') {
      top = targetRect.top + targetRect.height / 2 - tooltipHeight / 2;
      left = targetRect.left - tooltipWidth - gap;
    } else if (targetPos === 'right') {
      top = targetRect.top + targetRect.height / 2 - tooltipHeight / 2;
      left = targetRect.right + gap;
    }

    // Viewport clamping
    left = Math.max(8, Math.min(window.innerWidth - tooltipWidth - 8, left));
    top = Math.max(8, Math.min(window.innerHeight - tooltipHeight - 8, top));

    setCoords({ top, left });
  }, [position]);

  const showTooltip = useCallback(() => {
    if (disabled || !content) return;
    clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => {
      setVisible(true);
    }, delay);
  }, [delay, disabled, content]);

  const hideTooltip = useCallback(() => {
    clearTimeout(timeoutRef.current);
    setVisible(false);
  }, []);

  useEffect(() => {
    if (visible) {
      updatePosition();
      const handleScrollOrResize = () => updatePosition();
      window.addEventListener('scroll', handleScrollOrResize, true);
      window.addEventListener('resize', handleScrollOrResize);
      return () => {
        window.removeEventListener('scroll', handleScrollOrResize, true);
        window.removeEventListener('resize', handleScrollOrResize);
      };
    }
  }, [visible, updatePosition]);

  useEffect(() => {
    return () => {
      clearTimeout(timeoutRef.current);
    };
  }, []);

  if (!content) {
    return children;
  }

  // Clone child with enhanced event handlers and ref
  const childProps = (children as any).props || {};
  const clonedChild = (cloneElement as any)(children, {
    ref: (node: HTMLElement | null) => {
      triggerRef.current = node;
      const { ref } = children as any;
      if (typeof ref === 'function') {
        ref(node);
      } else if (ref && typeof ref === 'object') {
        ref.current = node;
      }
    },
    onMouseEnter: (e: React.MouseEvent) => {
      showTooltip();
      childProps.onMouseEnter?.(e);
    },
    onMouseLeave: (e: React.MouseEvent) => {
      hideTooltip();
      childProps.onMouseLeave?.(e);
    },
    onFocus: (e: React.FocusEvent) => {
      showTooltip();
      childProps.onFocus?.(e);
    },
    onBlur: (e: React.FocusEvent) => {
      hideTooltip();
      childProps.onBlur?.(e);
    },
    'aria-label': typeof content === 'string' ? (childProps['aria-label'] || content) : childProps['aria-label'],
    title: typeof content === 'string' ? (childProps.title || content) : childProps.title,
  });

  return (
    <>
      {clonedChild}
      {visible &&
        createPortal(
          <div
            ref={tooltipRef}
            role="tooltip"
            className={`aether-tooltip aether-tooltip-${actualPosition} ${className}`}
            style={{
              position: 'fixed',
              top: `${coords.top}px`,
              left: `${coords.left}px`,
              zIndex: 99999,
              pointerEvents: 'none',
              ...style,
            }}
          >
            {content}
          </div>,
          document.body
        )}
    </>
  );
}
