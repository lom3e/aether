import { forwardRef, type HTMLAttributes, type ReactNode } from 'react';

export interface SectionProps extends Omit<HTMLAttributes<HTMLElement>, 'title'> {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
}

export const Section = forwardRef<HTMLElement, SectionProps>(
  ({ title, description, actions, className = '', style, children, ...props }, ref) => {
    return (
      <section
        ref={ref}
        className={`ds-section ${className}`}
        style={style}
        {...props}
      >
        {(title || description || actions) && (
          <header className="ds-section-header">
            <div className="ds-section-header-text">
              {typeof title === 'string' ? (
                <h2 className="ds-heading ds-heading--3">{title}</h2>
              ) : (
                title
              )}
              {typeof description === 'string' ? (
                <p className="ds-text ds-text--muted ds-text--sm">{description}</p>
              ) : (
                description
              )}
            </div>
            {actions && <div className="ds-section-actions">{actions}</div>}
          </header>
        )}
        {children}
      </section>
    );
  }
);

Section.displayName = 'Section';
