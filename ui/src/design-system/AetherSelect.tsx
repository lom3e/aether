import { forwardRef } from 'react';
import { Select, type SelectProps } from './Select';

export type AetherSelectProps = SelectProps;

export const AetherSelect = forwardRef<HTMLSelectElement, AetherSelectProps>(
  (props, ref) => {
    return <Select ref={ref} {...props} />;
  }
);

AetherSelect.displayName = 'AetherSelect';
