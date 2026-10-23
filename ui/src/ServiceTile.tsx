import type { ComponentType } from 'react';

/** The icon of a service in Collegamenti, softly tinted, with its state as a small dot on the corner. */
export function ServiceTile({ icon: Icon, hue, state }: { icon: ComponentType<{ size?: number }>; hue: number; state: 'on' | 'warn' | 'off' }) {
  return (
    <span className="cn-icon" style={{ ['--hue' as string]: hue }} aria-hidden>
      <Icon size={18} />
      <i className={`cn-dot ${state === 'off' ? '' : state}`} />
    </span>
  );
}
