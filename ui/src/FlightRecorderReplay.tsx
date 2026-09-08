import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import {
  Play, Pause, SkipBack, SkipForward, Rewind, FastForward,
  Clock, Target, Bot, Wrench, FileText, AlertTriangle,
  Award, ShieldCheck, UserCheck, RefreshCw, Activity
} from 'lucide-react';
import { useTranslation } from './i18n';
import { Tooltip } from './Tooltip';
import { apiUrl } from './api';

export interface ReplayEvent {
  id: string;
  seq: number;
  timestamp: string;
  event_type: string;
  title: string;
  description: string;
  status: 'info' | 'success' | 'warning' | 'error';
  stage_name?: string | null;
  milestone_id?: string | null;
  agent?: string | null;
  task_id?: string | null;
  tool_name?: string | null;
  deliverable_id?: string | null;
  graph_node_id?: string | null;
  duration_ms?: number | null;
  details?: Record<string, any>;
}

export interface ReplayTimelineData {
  mission_id: string;
  mission_title: string;
  execution_id: string;
  run_number: number;
  status: string;
  started_at?: string | null;
  completed_at?: string | null;
  duration_seconds: number;
  total_events: number;
  events: ReplayEvent[];
}

interface FlightRecorderReplayProps {
  missionId: string;
  executionId?: string | null;
  runNumber?: number | null;
  onFocusCanvasNode?: (nodeId: string) => void;
}

export const FlightRecorderReplay: React.FC<FlightRecorderReplayProps> = ({
  missionId,
  executionId,
  runNumber,
  onFocusCanvasNode,
}) => {
  const { t } = useTranslation();
  const [timeline, setTimeline] = useState<ReplayTimelineData | null>(null);
  const [loading, setLoading] = useState(false);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1.0);
  const [selectedEvent, setSelectedEvent] = useState<ReplayEvent | null>(null);

  const timerRef = useRef<any>(null);
  const streamEndRef = useRef<HTMLDivElement | null>(null);

  // Fetch Timeline Data from REST API
  const fetchTimeline = useCallback(async () => {
    try {
      setLoading(true);
      const q = executionId ? `?execution_id=${encodeURIComponent(executionId)}` : '';
      const res = await fetch(apiUrl(`/api/missions/${missionId}/replay${q}`));
      if (!res.ok) throw new Error('Failed to load replay timeline');
      const data: ReplayTimelineData = await res.json();
      setTimeline(data);
      if (data.events && data.events.length > 0) {
        setCurrentIndex(0);
        setSelectedEvent(data.events[0]);
      } else {
        setCurrentIndex(0);
        setSelectedEvent(null);
      }
    } catch (err) {
      console.error(err);
      setTimeline(null);
    } finally {
      setLoading(false);
    }
  }, [missionId, executionId]);

  useEffect(() => {
    setIsPlaying(false);
    fetchTimeline();
  }, [fetchTimeline]);

  const events = useMemo(() => timeline?.events || [], [timeline]);
  const currentEvent = events[currentIndex] || null;

  useEffect(() => {
    if (currentEvent) {
      setSelectedEvent(currentEvent);
    }
  }, [currentEvent]);

  // Playback Interval Controller
  useEffect(() => {
    if (isPlaying) {
      const intervalMs = Math.max(250, Math.floor(1200 / playbackSpeed));
      timerRef.current = setInterval(() => {
        setCurrentIndex((prev) => {
          if (prev < events.length - 1) {
            return prev + 1;
          } else {
            setIsPlaying(false);
            return prev;
          }
        });
      }, intervalMs);
    } else if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isPlaying, playbackSpeed, events.length]);

  // Controls Handlers
  const handlePlayPause = () => {
    if (events.length === 0) return;
    if (currentIndex >= events.length - 1 && !isPlaying) {
      setCurrentIndex(0);
    }
    setIsPlaying(!isPlaying);
  };

  const handleStepBack = () => {
    setIsPlaying(false);
    setCurrentIndex((prev) => Math.max(0, prev - 1));
  };

  const handleStepForward = () => {
    setIsPlaying(false);
    setCurrentIndex((prev) => Math.min(events.length - 1, prev + 1));
  };

  const handleJumpStart = () => {
    setIsPlaying(false);
    setCurrentIndex(0);
  };

  const handleJumpEnd = () => {
    setIsPlaying(false);
    setCurrentIndex(Math.max(0, events.length - 1));
  };

  const handleSpeedCycle = () => {
    const speeds = [0.5, 1.0, 2.0, 4.0];
    const nextIdx = (speeds.indexOf(playbackSpeed) + 1) % speeds.length;
    setPlaybackSpeed(speeds[nextIdx]);
  };

  const handleSeek = (index: number) => {
    setIsPlaying(false);
    setCurrentIndex(Math.min(Math.max(0, index), Math.max(0, events.length - 1)));
  };

  // Helper Icon Resolver
  const getEventIcon = (eventType: string, status: string) => {
    if (status === 'error') return <AlertTriangle size={15} color="#ef4444" />;
    if (eventType.includes('milestone')) return <Target size={15} color="hsl(var(--primary))" />;
    if (eventType.includes('tool')) return <Wrench size={15} color="#0284c7" />;
    if (eventType.includes('quality_gate')) return <ShieldCheck size={15} color="#10b981" />;
    if (eventType.includes('deliverable')) return <FileText size={15} color="#8b5cf6" />;
    if (eventType.includes('approval')) return <UserCheck size={15} color="#f59e0b" />;
    if (eventType.includes('rework')) return <AlertTriangle size={15} color="#f97316" />;
    if (eventType.includes('completed')) return <Award size={15} color="#10b981" />;
    return <Bot size={15} color="hsl(var(--primary))" />;
  };

  const formatTimestamp = (ts?: string | null) => {
    if (!ts) return '--:--';
    try {
      const d = new Date(ts);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
      return ts;
    }
  };

  if (loading) {
    return (
      <div style={{ padding: '48px', textAlign: 'center', color: 'hsl(var(--muted-fg))' }}>
        <RefreshCw size={24} className="animate-spin" style={{ margin: '0 auto 12px' }} />
        <div style={{ fontSize: '13px' }}>Loading flight recorder timeline...</div>
      </div>
    );
  }

  if (!timeline || events.length === 0) {
    return (
      <div
        data-testid="replay-empty-state"
        style={{
          padding: '48px 24px',
          borderRadius: '12px',
          border: '1px dashed hsl(var(--border))',
          backgroundColor: 'hsl(var(--card) / 0.5)',
          textAlign: 'center',
          maxWidth: '540px',
          margin: '32px auto',
        }}
      >
        <Clock size={32} style={{ margin: '0 auto 12px', opacity: 0.35, color: 'hsl(var(--primary))' }} />
        <div style={{ fontSize: '15px', fontWeight: 600, color: 'hsl(var(--foreground))' }}>
          {t('replayEmptyTitle')}
        </div>
        <div style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))', marginTop: '6px', lineHeight: 1.5 }}>
          {t('replayEmptyDesc')}
        </div>
      </div>
    );
  }

  const progressPct = events.length > 1 ? (currentIndex / (events.length - 1)) * 100 : 100;

  return (
    <div
      className="flight-recorder-replay-container flight-recorder-replay"
      data-testid="flight-recorder-replay"
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        minHeight: '560px',
        gap: '14px',
      }}
    >
      {/* 1. Header & Scrubber Toolbar */}
      <div
        style={{
          padding: '16px 20px',
          borderRadius: '12px',
          backgroundColor: 'hsl(var(--card))',
          border: '1px solid hsl(var(--border))',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
          boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
        }}
      >
        {/* Top line: Mission Title, Run badge, Time indicators */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ fontSize: '14px', fontWeight: 700, color: 'hsl(var(--foreground))' }}>
              {t('replayTitle')}
            </span>
            <span
              style={{
                fontSize: '11px',
                fontWeight: 600,
                padding: '2px 8px',
                borderRadius: '12px',
                backgroundColor: 'hsl(var(--primary) / 0.1)',
                color: 'hsl(var(--primary))',
              }}
            >
              Run #{runNumber || timeline.run_number}
            </span>
            <span
              style={{
                fontSize: '11px',
                padding: '2px 8px',
                borderRadius: '12px',
                backgroundColor: timeline.status === 'completed' ? '#10b98120' : 'hsl(var(--muted))',
                color: timeline.status === 'completed' ? '#10b981' : 'hsl(var(--muted-fg))',
                fontWeight: 600,
                textTransform: 'uppercase',
              }}
            >
              {timeline.status}
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
            <span>
              Event <strong style={{ color: 'hsl(var(--foreground))' }}>{currentIndex + 1}</strong> of {events.length}
            </span>
            <span>•</span>
            <span style={{ fontFamily: 'monospace', fontWeight: 600, color: 'hsl(var(--foreground))' }}>
              {formatTimestamp(currentEvent?.timestamp)}
            </span>
          </div>
        </div>

        {/* Interactive Scrubber Bar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{ fontSize: '11px', fontFamily: 'monospace', color: 'hsl(var(--muted-fg))', minWidth: '55px' }}>
            {formatTimestamp(events[0]?.timestamp)}
          </span>

          <div
            onClick={(e) => {
              const rect = e.currentTarget.getBoundingClientRect();
              const clickX = e.clientX - rect.left;
              const pct = Math.max(0, Math.min(1, clickX / rect.width));
              const targetIdx = Math.round(pct * (events.length - 1));
              handleSeek(targetIdx);
            }}
            style={{
              flex: 1,
              height: '8px',
              backgroundColor: 'hsl(var(--muted))',
              borderRadius: '4px',
              position: 'relative',
              cursor: 'pointer',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: `${progressPct}%`,
                height: '100%',
                backgroundColor: 'hsl(var(--primary))',
                transition: isPlaying ? 'width 0.1s linear' : 'width 0.2s ease',
              }}
            />
          </div>

          <span style={{ fontSize: '11px', fontFamily: 'monospace', color: 'hsl(var(--muted-fg))', minWidth: '55px', textAlign: 'right' }}>
            {formatTimestamp(events[events.length - 1]?.timestamp)}
          </span>
        </div>

        {/* Player Controls Bar */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: '4px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Tooltip content={t('jumpToStart')} position="top">
              <button
                data-testid="replay-jump-start-btn"
                className="btn btn-ghost"
                onClick={handleJumpStart}
                style={{ padding: '6px', borderRadius: '6px' }}
                aria-label={t('jumpToStart')}
              >
                <SkipBack size={15} />
              </button>
            </Tooltip>

            <Tooltip content={t('stepBack')} position="top">
              <button
                data-testid="replay-step-back-btn"
                className="btn btn-ghost"
                onClick={handleStepBack}
                disabled={currentIndex <= 0}
                style={{ padding: '6px', borderRadius: '6px' }}
                aria-label={t('stepBack')}
              >
                <Rewind size={15} />
              </button>
            </Tooltip>

            <button
              data-testid="replay-play-pause-btn"
              className="btn btn-primary"
              onClick={handlePlayPause}
              style={{
                padding: '6px 16px',
                borderRadius: '8px',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                fontSize: '12px',
                fontWeight: 600,
              }}
              aria-label={isPlaying ? t('pause') : t('play')}
            >
              {isPlaying ? <Pause size={14} /> : <Play size={14} />}
              <span>{isPlaying ? t('pause') : t('play')}</span>
            </button>

            <Tooltip content={t('stepForward')} position="top">
              <button
                data-testid="replay-step-forward-btn"
                className="btn btn-ghost"
                onClick={handleStepForward}
                disabled={currentIndex >= events.length - 1}
                style={{ padding: '6px', borderRadius: '6px' }}
                aria-label={t('stepForward')}
              >
                <FastForward size={15} />
              </button>
            </Tooltip>

            <Tooltip content={t('jumpToEnd')} position="top">
              <button
                data-testid="replay-jump-end-btn"
                className="btn btn-ghost"
                onClick={handleJumpEnd}
                style={{ padding: '6px', borderRadius: '6px' }}
                aria-label={t('jumpToEnd')}
              >
                <SkipForward size={15} />
              </button>
            </Tooltip>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <button
              data-testid="replay-speed-btn"
              className="btn btn-ghost"
              onClick={handleSpeedCycle}
              style={{
                padding: '4px 10px',
                fontSize: '11px',
                fontWeight: 600,
                borderRadius: '6px',
                border: '1px solid hsl(var(--border))',
                backgroundColor: 'hsl(var(--card))',
              }}
            >
              {playbackSpeed}x
            </button>
          </div>
        </div>
      </div>

      {/* 2. Main Content Split View: Event Stream (Left) & Event Detail Inspector (Right) */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: '14px', flex: 1, minHeight: 0 }}>
        {/* Left Column: Chronological Event Stream */}
        <div
          data-testid="replay-event-stream"
          style={{
            overflowY: 'auto',
            borderRadius: '12px',
            border: '1px solid hsl(var(--border))',
            backgroundColor: 'hsl(var(--card))',
            padding: '12px',
            display: 'flex',
            flexDirection: 'column',
            gap: '8px',
          }}
        >
          {events.map((ev, idx) => {
            const isCurrent = idx === currentIndex;
            const isSelected = selectedEvent?.id === ev.id;
            const isPassed = idx < currentIndex;

            return (
              <div
                key={ev.id}
                data-testid={`replay-event-item-${idx}`}
                onClick={() => {
                  setCurrentIndex(idx);
                  setSelectedEvent(ev);
                  setIsPlaying(false);
                }}
                style={{
                  padding: '10px 14px',
                  borderRadius: '8px',
                  border: isCurrent
                    ? '1.5px solid hsl(var(--primary))'
                    : isSelected
                    ? '1px solid hsl(var(--primary) / 0.4)'
                    : '1px solid hsl(var(--border))',
                  backgroundColor: isCurrent
                    ? 'hsl(var(--primary) / 0.08)'
                    : isSelected
                    ? 'hsl(var(--card))'
                    : isPassed
                    ? 'hsl(var(--muted) / 0.25)'
                    : 'hsl(var(--card))',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '12px',
                  transition: 'all 0.15s ease',
                  opacity: isPassed || isCurrent ? 1 : 0.65,
                }}
              >
                {/* Event Icon */}
                <div
                  style={{
                    padding: '6px',
                    borderRadius: '6px',
                    backgroundColor: isCurrent ? 'hsl(var(--primary) / 0.15)' : 'hsl(var(--muted))',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    marginTop: '2px',
                  }}
                >
                  {getEventIcon(ev.event_type, ev.status)}
                </div>

                {/* Event Summary */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px', marginBottom: '3px' }}>
                    <span style={{ fontSize: '13px', fontWeight: 600, color: 'hsl(var(--foreground))' }}>
                      {ev.title}
                    </span>
                    <span style={{ fontSize: '11px', fontFamily: 'monospace', color: 'hsl(var(--muted-fg))', flexShrink: 0 }}>
                      {formatTimestamp(ev.timestamp)}
                    </span>
                  </div>

                  <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', lineHeight: 1.4 }}>
                    {ev.description}
                  </div>

                  {/* Pills row */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '6px', flexWrap: 'wrap' }}>
                    {ev.stage_name && (
                      <span
                        style={{
                          fontSize: '10px',
                          fontWeight: 500,
                          padding: '1px 6px',
                          borderRadius: '4px',
                          backgroundColor: 'hsl(var(--muted))',
                          color: 'hsl(var(--muted-fg))',
                        }}
                      >
                        {ev.stage_name}
                      </span>
                    )}
                    {ev.agent && (
                      <span
                        style={{
                          fontSize: '10px',
                          fontWeight: 600,
                          padding: '1px 6px',
                          borderRadius: '4px',
                          backgroundColor: 'hsl(var(--primary) / 0.1)',
                          color: 'hsl(var(--primary))',
                        }}
                      >
                        @{ev.agent}
                      </span>
                    )}
                    {ev.tool_name && (
                      <span
                        style={{
                          fontSize: '10px',
                          fontFamily: 'monospace',
                          padding: '1px 6px',
                          borderRadius: '4px',
                          backgroundColor: '#0284c715',
                          color: '#0284c7',
                        }}
                      >
                        {ev.tool_name}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
          <div ref={streamEndRef} />
        </div>

        {/* Right Column: Selected Event Detail Panel */}
        <div
          data-testid="replay-event-detail"
          style={{
            borderRadius: '12px',
            border: '1px solid hsl(var(--border))',
            backgroundColor: 'hsl(var(--card))',
            padding: '16px',
            display: 'flex',
            flexDirection: 'column',
            gap: '14px',
            overflowY: 'auto',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '13px', fontWeight: 700, color: 'hsl(var(--foreground))' }}>
              {t('eventDetailTitle')}
            </span>
            {selectedEvent && (
              <span
                style={{
                  fontSize: '10px',
                  fontWeight: 600,
                  padding: '2px 8px',
                  borderRadius: '10px',
                  textTransform: 'uppercase',
                  backgroundColor:
                    selectedEvent.status === 'success'
                      ? '#10b98120'
                      : selectedEvent.status === 'error'
                      ? '#ef444420'
                      : selectedEvent.status === 'warning'
                      ? '#f59e0b20'
                      : 'hsl(var(--muted))',
                  color:
                    selectedEvent.status === 'success'
                      ? '#10b981'
                      : selectedEvent.status === 'error'
                      ? '#ef4444'
                      : selectedEvent.status === 'warning'
                      ? '#f59e0b'
                      : 'hsl(var(--muted-fg))',
                }}
              >
                {selectedEvent.status}
              </span>
            )}
          </div>

          {selectedEvent ? (
            <div data-testid="replay-event-inspector" style={{ display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '12px' }}>
              <div>
                <div style={{ fontSize: '14px', fontWeight: 600, color: 'hsl(var(--foreground))', marginBottom: '4px' }}>
                  {selectedEvent.title}
                </div>
                <div style={{ color: 'hsl(var(--muted-fg))', lineHeight: 1.45 }}>
                  {selectedEvent.description}
                </div>
              </div>

              {/* Correlation Action: Focus in Graph */}
              {selectedEvent.graph_node_id && onFocusCanvasNode && (
                <button
                  data-testid="focus-graph-node-btn"
                  className="btn btn-outline"
                  onClick={() => onFocusCanvasNode(selectedEvent.graph_node_id!)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '6px',
                    padding: '8px 12px',
                    borderRadius: '8px',
                    fontSize: '12px',
                    fontWeight: 600,
                    width: '100%',
                    border: '1px solid hsl(var(--primary) / 0.5)',
                    color: 'hsl(var(--primary))',
                  }}
                >
                  <Activity size={14} />
                  <span>{t('focusCanvas')}</span>
                </button>
              )}

              {/* Metadata Key-Values */}
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px',
                  padding: '12px',
                  borderRadius: '8px',
                  backgroundColor: 'hsl(var(--muted) / 0.3)',
                  border: '1px solid hsl(var(--border))',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'hsl(var(--muted-fg))' }}>Timestamp</span>
                  <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>{selectedEvent.timestamp}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'hsl(var(--muted-fg))' }}>Event Type</span>
                  <span style={{ fontFamily: 'monospace' }}>{selectedEvent.event_type}</span>
                </div>
                {selectedEvent.stage_name && (
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'hsl(var(--muted-fg))' }}>Stage</span>
                    <span style={{ fontWeight: 500 }}>{selectedEvent.stage_name}</span>
                  </div>
                )}
                {selectedEvent.agent && (
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'hsl(var(--muted-fg))' }}>Agent</span>
                    <span style={{ fontWeight: 600, color: 'hsl(var(--primary))' }}>@{selectedEvent.agent}</span>
                  </div>
                )}
                {selectedEvent.tool_name && (
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'hsl(var(--muted-fg))' }}>Tool</span>
                    <span style={{ fontFamily: 'monospace', color: '#0284c7' }}>{selectedEvent.tool_name}</span>
                  </div>
                )}
                {selectedEvent.duration_ms != null && (
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'hsl(var(--muted-fg))' }}>Duration</span>
                    <span>{selectedEvent.duration_ms.toFixed(1)} ms</span>
                  </div>
                )}
                {selectedEvent.graph_node_id && (
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'hsl(var(--muted-fg))' }}>Graph Node ID</span>
                    <span style={{ fontFamily: 'monospace', fontSize: '11px' }}>{selectedEvent.graph_node_id}</span>
                  </div>
                )}
              </div>

              {/* Sanitized Details JSON Viewer */}
              {selectedEvent.details && Object.keys(selectedEvent.details).length > 0 && (
                <div>
                  <div style={{ fontSize: '11px', fontWeight: 600, color: 'hsl(var(--muted-fg))', marginBottom: '6px', textTransform: 'uppercase' }}>
                    Observable Parameters
                  </div>
                  <pre
                    style={{
                      margin: 0,
                      padding: '10px',
                      borderRadius: '8px',
                      backgroundColor: 'hsl(var(--background))',
                      border: '1px solid hsl(var(--border))',
                      fontSize: '11px',
                      fontFamily: 'monospace',
                      maxHeight: '180px',
                      overflowY: 'auto',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                    }}
                  >
                    {JSON.stringify(selectedEvent.details, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          ) : (
            <div style={{ color: 'hsl(var(--muted-fg))', fontSize: '12px', textAlign: 'center', padding: '32px 0' }}>
              Select an event from the timeline stream to inspect observable facts.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
