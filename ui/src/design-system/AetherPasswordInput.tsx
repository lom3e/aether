import { forwardRef, useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';
import { AetherInput, type AetherInputProps } from './AetherInput';

export interface AetherPasswordInputProps extends Omit<AetherInputProps, 'type' | 'rightElement'> {
  showToggle?: boolean;
}

export const AetherPasswordInput = forwardRef<HTMLInputElement, AetherPasswordInputProps>(
  ({ showToggle = true, ...props }, ref) => {
    const [visible, setVisible] = useState(false);

    const toggleButton = showToggle ? (
      <button
        type="button"
        tabIndex={-1}
        onClick={() => setVisible(!visible)}
        aria-label={visible ? 'Nascondi password' : 'Mostra password'}
        style={{
          background: 'none',
          border: 'none',
          padding: 0,
          cursor: 'pointer',
          color: 'hsl(var(--muted-fg))',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {visible ? <EyeOff size={16} /> : <Eye size={16} />}
      </button>
    ) : null;

    return (
      <AetherInput
        ref={ref}
        type={visible ? 'text' : 'password'}
        rightElement={toggleButton}
        {...props}
      />
    );
  }
);

AetherPasswordInput.displayName = 'AetherPasswordInput';
