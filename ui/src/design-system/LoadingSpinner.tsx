export interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg' | number;
  color?: string;
  className?: string;
}

const sizeMap = {
  sm: 14,
  md: 18,
  lg: 24,
};

export function LoadingSpinner({
  size = 'md',
  color = 'currentColor',
  className = '',
}: LoadingSpinnerProps) {
  const pixelSize = typeof size === 'number' ? size : sizeMap[size];

  return (
    <svg
      className={`ds-loading-spinner ${className}`}
      width={pixelSize}
      height={pixelSize}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{
        animation: 'dsSpin 0.75s linear infinite',
      }}
      aria-hidden="true"
    >
      <style>{`
        @keyframes dsSpin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
      <path d="M21 12a9 9 0 1 1-6.219-8.56" />
    </svg>
  );
}
