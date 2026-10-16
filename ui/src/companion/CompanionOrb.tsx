import { useRef } from 'react';
import { AetherOrb } from '../orb/AetherOrb';
import { orbStateFor, STATUS_COLORS, type CompanionStatus } from './status';
import { startNativeDrag } from './windowControl';

interface Props {
  status: CompanionStatus;
  label: string;
  /** Approvals waiting for the user, shown as a count badge. */
  badge?: number;
  onOpen: () => void;
}

const DRAG_THRESHOLD_PX = 5;

/**
 * The compact Companion. A click opens the panel; pressing and moving more than a few pixels starts a native window
 * drag instead, so the same gesture never does both.
 */
export function CompanionOrb({ status, label, badge = 0, onOpen }: Props) {
  const down = useRef<{ x: number; y: number; dragged: boolean } | null>(null);
  const color = STATUS_COLORS[status];

  return (
    <div
      className="cmp-orb"
      data-testid="companion-orb"
      data-status={status}
      role="button"
      tabIndex={0}
      aria-label={label}
      title={label}
      style={{ ['--cmp-ring' as any]: color, ['--cmp-glow' as any]: `${color}66` }}
      onMouseDown={e => {
        if (e.button !== 0) return;
        down.current = { x: e.clientX, y: e.clientY, dragged: false };
      }}
      onMouseMove={e => {
        const d = down.current;
        if (!d || d.dragged || e.buttons !== 1) return;
        if (Math.hypot(e.clientX - d.x, e.clientY - d.y) > DRAG_THRESHOLD_PX) {
          d.dragged = true;
          startNativeDrag();
        }
      }}
      onClick={() => {
        // The browser's own click (press and release on the orb) opens the panel, unless the press turned into a drag.
        // mouseup fires before click, so the drag flag is only cleared here (or by the next mousedown), never on mouseup.
        const wasDrag = down.current?.dragged === true;
        down.current = null;
        if (!wasDrag) onOpen();
      }}
      onKeyDown={e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onOpen();
        }
      }}
    >
      <div className="cmp-orb-core">
        <AetherOrb state={orbStateFor(status)} size={64} quality="medium" interactive={false} compact />
        <span className="cmp-orb-ring" />
        {badge > 0 && <span className="cmp-badge" data-testid="companion-badge">{badge > 9 ? '9+' : badge}</span>}
        {status === 'error' && badge === 0 && <span className="cmp-badge" data-testid="companion-badge">!</span>}
      </div>
    </div>
  );
}
