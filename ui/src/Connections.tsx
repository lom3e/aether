import React, { useState, useEffect, useContext, useMemo } from 'react';
import {
  Calendar, Mail, GitBranch, MessageSquare, FileText,
  RefreshCw, Clock, Zap, Globe, Send,
  Shield, Trash2, Copy, Check,
  Plus, CheckCircle2, ArrowRight, Layers
} from 'lucide-react';
import { apiUrl } from './api';
import { ToastContext } from './toast';
import { submitApprovalDecision, approvalToastKind } from './canonicalNotification';
import { openExternalUrl } from './desktop';
import { useTranslation } from './i18n';
import type { TranslationKey } from './i18n';

// Design System Core Imports
import {
  PageContainer,
  Section,
  Stack,
  Grid,
  Panel,
  Modal,
  Drawer,
  Heading,
  Text,
  Button,
  IconButton,
  Switch,
  SegmentedControl,
  StatusBadge,
  AlertBanner,
  EmptyState,
  LoadingSpinner,
  AetherForm,
  AetherField,
  AetherInput,
  AetherPasswordInput,
  AetherSelect,
  AetherFormActions,
} from './design-system';

type Translate = (key: TranslationKey) => string;

// Renders the light inline markup used by long translated sentences: **bold**, *italic*, `code`.
function renderRich(text: string): React.ReactNode {
  return text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/).map((part, i) => {
    if (part.startsWith('**')) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith('`')) return <code key={i}>{part.slice(1, -1)}</code>;
    if (part.startsWith('*') && part.length > 2) return <em key={i}>{part.slice(1, -1)}</em>;
    return <React.Fragment key={i}>{part}</React.Fragment>;
  });
}

interface OAuthProviderInfo {
  provider: string;
  name: string;
  supports_oauth: boolean;
  ready_for_user_connect: boolean;
  requires_developer_setup: boolean;
  redirect_uri: string;
  setup_url: string;
  has_client_id: boolean;
  has_client_secret: boolean;
  client_id_preview?: string;
}

interface ConnectionItem {
  id: string;
  provider: string;
  account_name: string;
  status: string;
  scopes: string[];
  capabilities: string[];
  auth_metadata?: Record<string, any>;
  last_synced_at?: string;
  last_verified_at?: string;
  last_verification_error?: string;
  last_successful_operation?: string;
  verification_method?: string;
  updated_at?: string;
}

interface CalendarEventItem {
  id: string;
  title: string;
  start_time: string;
  end_time?: string;
  description?: string;
  location?: string;
  is_all_day?: boolean;
  start_date?: string;
  end_date?: string;
  time_zone?: string;
  html_link?: string;
}

const NO_DATE_KEY = '__no_date__';

function getEventDateKey(evt: CalendarEventItem): string {
  if (evt.start_date) {
    return evt.start_date;
  }
  if (evt.start_time) {
    if (/^\d{4}-\d{2}-\d{2}$/.test(evt.start_time.trim())) {
      return evt.start_time.trim();
    }
    const d = new Date(evt.start_time);
    if (!isNaN(d.getTime())) {
      const year = d.getFullYear();
      const month = String(d.getMonth() + 1).padStart(2, '0');
      const day = String(d.getDate()).padStart(2, '0');
      return `${year}-${month}-${day}`;
    }
  }
  return NO_DATE_KEY;
}

function formatDayLabel(dateKey: string, t: Translate, locale: string): { label: string; isToday: boolean } {
  if (dateKey === NO_DATE_KEY) {
    return { label: t('connUiNoDate'), isToday: false };
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dateKey)) {
    return { label: dateKey, isToday: false };
  }
  const [y, m, d] = dateKey.split('-').map(Number);
  const eventDate = new Date(y, m - 1, d);
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const targetDateOnly = new Date(y, m - 1, d);
  targetDateOnly.setHours(0, 0, 0, 0);

  const diffDays = Math.round((targetDateOnly.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));

  const formattedDate = eventDate.toLocaleDateString(locale, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });
  const capDate = formattedDate.charAt(0).toUpperCase() + formattedDate.slice(1);

  if (diffDays === 0) {
    return { label: `${t('connUiToday')} — ${capDate}`, isToday: true };
  }
  if (diffDays === 1) {
    return { label: `${t('connUiTomorrow')} — ${capDate}`, isToday: false };
  }
  if (diffDays === -1) {
    return { label: `${t('connUiYesterday')} — ${capDate}`, isToday: false };
  }
  return { label: capDate, isToday: false };
}

function formatEventTime(evt: CalendarEventItem, t: Translate, locale: string): string {
  const isAllDay = evt.is_all_day || /^\d{4}-\d{2}-\d{2}$/.test(evt.start_time?.trim() || '');
  if (isAllDay) {
    return t('connUiAllDay');
  }
  try {
    const start = new Date(evt.start_time);
    if (isNaN(start.getTime())) return '';
    const startStr = start.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
    if (evt.end_time) {
      const end = new Date(evt.end_time);
      if (!isNaN(end.getTime())) {
        const endStr = end.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
        return `${startStr} – ${endStr}`;
      }
    }
    return startStr;
  } catch {
    return '';
  }
}


interface ActionExecutionItem {
  id: string;
  action_id: string;
  status: string;
  input_data: any;
  output_data: any;
  created_at: string;
  error_message?: string;
}

interface ConnectionsProps {
  navigate?: (view: string, params?: any) => void;
  initialExecutionId?: string | null;
  initialTab?: 'apps' | 'calendar' | 'actions';
}

type CategoryType = 'all' | 'productivity' | 'dev' | 'communication';

interface ProviderDefinition {
  id: string;
  name: string;
  icon: React.ComponentType<{ size?: number; color?: string; className?: string }>;
  category: 'productivity' | 'dev' | 'communication';
  description: string;
  capabilitiesText: string;
  capabilitiesList: string[];
  color: string;
  builtIn: boolean;
  isOAuth: boolean;
}

const buildProviders = (t: Translate): ProviderDefinition[] => [
  {
    id: 'calendar',
    name: t('connUiAetherCalendarLocal'),
    icon: Calendar,
    category: 'productivity',
    description: t('connUiScheduleAndAppointmentArchiveBuiltInto'),
    capabilitiesText: t('connUiViewAppointmentsAndStoreMeetingsIn'),
    capabilitiesList: [
      t('connUiViewCommitmentsAndMeetings'),
      t('connUiSecureStorageInALocalDatabase'),
      t('connUiWorksWithoutCloudDependencies'),
      t('connUiAutomaticIndexingForTheWorkforce'),
    ],
    color: '#06b6d4',
    builtIn: true,
    isOAuth: false,
  },
  {
    id: 'google_calendar',
    name: 'Google Calendar',
    icon: Calendar,
    category: 'productivity',
    description: t('connUiOfficialGoogleIntegrationToCoordinatePersonal'),
    capabilitiesText: t('connUiReadGoogleCalendarsAndScheduleMeetings'),
    capabilitiesList: [
      t('connUiReadPersonalAndTeamCalendars'),
      t('connUiAutomaticMeetingScheduling'),
      t('connUiSupervisedUpdatingOfCommitments'),
      t('connUiContinuousSynchronizationWithTheWorkspace'),
    ],
    color: '#4285F4',
    builtIn: false,
    isOAuth: true,
  },
  {
    id: 'notion',
    name: 'Notion',
    icon: FileText,
    category: 'productivity',
    description: t('connUiSyncProjectPagesCompanyDocumentationAnd'),
    capabilitiesText: t('connUiAccessNotionDatabasesAndPagesTo'),
    capabilitiesList: [
      t('connUiSearchAndIndexingOfProjectNotes'),
      t('connUiReadingDatabaseTablesAndProperties'),
      t('connUiPublishingVerifiedDeliverables'),
      t('connUiTwoWaySynchronizationWithMemory'),
    ],
    color: '#000000',
    builtIn: false,
    isOAuth: true,
  },
  {
    id: 'github',
    name: 'GitHub',
    icon: GitBranch,
    category: 'dev',
    description: t('connUiAccessRepositoriesDevelopmentBranchesIssuesAnd'),
    capabilitiesText: t('connUiInspectSourceCodeOpenIssuesAnd'),
    capabilitiesList: [
      t('connUiCodeTreeAndFileInspection'),
      t('connUiMonitoringOfBranchesAndRecentCommits'),
      t('connUiCreationOfIssuesAndTechnicalNotes'),
      t('connUiPreparationOfVerifiedPullRequests'),
    ],
    color: '#2dba4e',
    builtIn: false,
    isOAuth: true,
  },
  {
    id: 'openapi',
    name: t('connUiOpenAPI3XSpecification'),
    icon: Zap,
    category: 'dev',
    description: t('connUiConnectAnyCompanyRESTAPIThrough'),
    capabilitiesText: t('connUiDynamicallyDiscoverEndpointsAndValidateCalls'),
    capabilitiesList: [
      t('connUiAutomaticScanOfTheAvailableEndpoints'),
      t('connUiStrictInputValidation'),
      t('connUiSupportForTokensAndAPIKeys'),
      t('connUiControlledExecutionOfRESTCalls'),
    ],
    color: '#8B5CF6',
    builtIn: false,
    isOAuth: false,
  },
  {
    id: 'http',
    name: t('connUiWebhookGenericHTTPAPI'),
    icon: Globe,
    category: 'dev',
    description: t('connUiInteractWithGenericWebServicesAnd'),
    capabilitiesText: t('connUiRunHTTPCallsGETPOSTPUT'),
    capabilitiesList: [
      t('connUiHTTPCallsWithCustomHeaders'),
      t('connUiBearerTokenAPIKeyAndBasic'),
      t('connUiSSRFProtectionAndAccessControl'),
      t('connUiSupervisionOfModifyingActions'),
    ],
    color: '#6366f1',
    builtIn: false,
    isOAuth: false,
  },
  {
    id: 'slack',
    name: 'Slack',
    icon: MessageSquare,
    category: 'communication',
    description: t('connUiSendOperationalBriefsNotifyTeamChannels'),
    capabilitiesText: t('connUiPostStatusUpdatesAndAlertsTo'),
    capabilitiesList: [
      t('connUiSendingProgressReportsToChannels'),
      t('connUiRealTimeOperationalNotifications'),
      t('connUiBotTokenOrIncomingWebhookSupport'),
      t('connUiConfigurableDefaultDestinationChannel'),
    ],
    color: '#4A154B',
    builtIn: false,
    isOAuth: true,
  },
  {
    id: 'email',
    name: t('connUiCompanyEmailSMTP'),
    icon: Mail,
    category: 'communication',
    description: t('connUiPrepareSummaryDraftsWriteCommunicationsAnd'),
    capabilitiesText: t('connUiPrepareAndSendEmailsOverSMTP'),
    capabilitiesList: [
      t('connUiGuidedCompositionOfStructuredEmails'),
      t('connUiNativeSTARTTLSAndSSLTLSEncryption'),
      t('connUiCustomizableSenderAddressAndAliases'),
      t('connUiControlledSendingWithApprovalGating'),
    ],
    color: '#EA4335',
    builtIn: false,
    isOAuth: false,
  },
  {
    id: 'telegram',
    name: 'Telegram Companion Bot',
    icon: Send,
    category: 'communication',
    description: t('connUiTalkToAetherFromYourSmartphone'),
    capabilitiesText: t('connUiReceiveCommandsFromYourSmartphoneAnd'),
    capabilitiesList: [
      t('connUiInstantPushNotificationsOnTelegram'),
      t('connUiQuickTaskApprovalWithInlineButtons'),
      t('connUiProtectionThroughAListOfAuthorized'),
      t('connUiRemoteExecutionOfTasksForThe'),
    ],
    color: '#229ED9',
    builtIn: false,
    isOAuth: false,
  },
];

export function Connections({ initialExecutionId, initialTab }: ConnectionsProps) {
  const showToast = useContext(ToastContext);
  const { t, language } = useTranslation();
  const locale = language === 'it' ? 'it-IT' : 'en-US';
  const AVAILABLE_PROVIDERS = useMemo(() => buildProviders(t), [language]);

  const [activeTab, setActiveTab] = useState<'apps' | 'calendar' | 'actions'>(
    initialTab || (initialExecutionId ? 'actions' : 'apps')
  );
  const [categoryFilter, setCategoryFilter] = useState<CategoryType>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [actionStatusFilter, setActionStatusFilter] = useState<string>('all');

  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [connections, setConnections] = useState<ConnectionItem[]>([]);
  const [calendarEvents, setCalendarEvents] = useState<CalendarEventItem[]>([]);
  const [executions, setExecutions] = useState<ActionExecutionItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [verifyingProvider, setVerifyingProvider] = useState<string | null>(null);
  const [syncingAll, setSyncingAll] = useState(false);

  // Manage Connection Drawer
  const [manageProvider, setManageProvider] = useState<ProviderDefinition | null>(null);
  const [showTechDetails, setShowTechDetails] = useState(false);

  // Disconnect Confirmation Modal
  const [disconnectTarget, setDisconnectTarget] = useState<{ id: string; name: string } | null>(null);
  const [disconnecting, setDisconnecting] = useState(false);

  // Google Calendar States
  const [googleCalendarEvents, setGoogleCalendarEvents] = useState<CalendarEventItem[]>([]);
  const [selectedScheduleSource, setSelectedScheduleSource] = useState<'local' | 'google'>('local');
  const [isGoogleModalOpen, setIsGoogleModalOpen] = useState(false);
  const [googleClientId, setGoogleClientId] = useState('');
  const [googleClientSecret, setGoogleClientSecret] = useState('');
  const [googleAuthPending, setGoogleAuthPending] = useState(false);
  const [googleManualCode, setGoogleManualCode] = useState('');
  const [googleState, setGoogleState] = useState('');
  const [googleAdvOpen, setGoogleAdvOpen] = useState(false);
  const [isCalendarPickerOpen, setIsCalendarPickerOpen] = useState(false);
  const [googleCalendars, setGoogleCalendars] = useState<{ id: string; summary: string; primary: boolean; description?: string }[]>([]);

  // OAuth Management States
  const [oauthProviders, setOauthProviders] = useState<Record<string, OAuthProviderInfo>>({});
  const [oauthPendingProvider, setOauthPendingProvider] = useState<string | null>(null);

  // Dedicated Developer App Setup Modal (GitHub, Slack, Notion)
  const [devSetupModalProvider, setDevSetupModalProvider] = useState<ProviderDefinition | null>(null);
  const [devClientId, setDevClientId] = useState('');
  const [devClientSecret, setDevClientSecret] = useState('');
  const [savingDevConfig, setSavingDevConfig] = useState(false);
  const [copiedField, setCopiedField] = useState<string | null>(null);

  // Dedicated Guided Telegram Modal
  const [isTelegramModalOpen, setIsTelegramModalOpen] = useState(false);
  const [telegramAdvOpen, setTelegramAdvOpen] = useState(false);
  const [verifyingTelegram, setVerifyingTelegram] = useState(false);

  // New Event Form State
  const [isEventModalOpen, setIsEventModalOpen] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newStartTime, setNewStartTime] = useState('');
  const [newLocation, setNewLocation] = useState('');
  const [creatingEvent, setCreatingEvent] = useState(false);

  // Config Modal State (Generic Credentials)
  const [configModalProvider, setConfigModalProvider] = useState<ProviderDefinition | null>(null);
  const [credAccountName, setCredAccountName] = useState('');
  const [githubToken, setGithubToken] = useState('');
  const [slackToken, setSlackToken] = useState('');
  const [slackWebhook, setSlackWebhook] = useState('');
  const [slackDefaultChannel, setSlackDefaultChannel] = useState('');
  const [emailUser, setEmailUser] = useState('');
  const [emailPass, setEmailPass] = useState('');
  const [emailHost, setEmailHost] = useState('smtp.gmail.com');
  const [emailPort, setEmailPort] = useState('587');
  const [emailUseTls, setEmailUseTls] = useState(true);
  const [emailUseSsl, setEmailUseSsl] = useState(false);
  const [emailSenderAddr, setEmailSenderAddr] = useState('');
  const [emailTestRecipient, setEmailTestRecipient] = useState('');
  const [httpBaseUrl, setHttpBaseUrl] = useState('');
  const [httpAuthType, setHttpAuthType] = useState('none');
  const [httpToken, setHttpToken] = useState('');
  const [notionToken, setNotionToken] = useState('');
  const [notionDbId, setNotionDbId] = useState('');
  const [telegramBotToken, setTelegramBotToken] = useState('');
  const [telegramDefaultChatId, setTelegramDefaultChatId] = useState('');
  const [telegramAllowedChats, setTelegramAllowedChats] = useState('');
  const [openapiSpecUrl, setOpenapiSpecUrl] = useState('');
  const [openapiSpecPath, setOpenapiSpecPath] = useState('');
  const [openapiBaseUrl, setOpenapiBaseUrl] = useState('');
  const [openapiAuthType, setOpenapiAuthType] = useState('none');
  const [openapiToken, setOpenapiToken] = useState('');
  const [testingCreds, setTestingCreds] = useState(false);
  const [savingCreds, setSavingCreds] = useState(false);
  const [testResult, setTestResult] = useState<{ valid: boolean; message: string } | null>(null);

  const fetchAll = () => {
    setLoading(true);
    // Google Calendar events are requested only when a Google Calendar connection exists: asking without one is a
    // guaranteed 404 (and a red line in the console) for something that is simply not set up.
    const connectionsPromise = fetch(apiUrl('/api/connections')).then((r) => r.json());
    const googleEventsPromise = connectionsPromise
      .then((conns) =>
        Array.isArray(conns) && conns.some((c: any) => c.provider === 'google_calendar')
          ? fetch(apiUrl('/api/connections/google_calendar/events')).then((r) => (r.ok ? r.json() : []))
          : [],
      )
      .catch(() => []);
    Promise.all([
      connectionsPromise,
      fetch(apiUrl('/api/connections/calendar/events')).then((r) => r.json()),
      googleEventsPromise,
      fetch(apiUrl('/api/actions/executions')).then((r) => r.json()),
      fetch(apiUrl('/api/connections/oauth/providers')).then((r) => (r.ok ? r.json() : {})).catch(() => ({})),
    ])
      .then(([conns, evts, gEvts, execs, oauths]) => {
        if (Array.isArray(conns)) setConnections(conns);
        if (Array.isArray(evts)) setCalendarEvents(evts);
        if (Array.isArray(gEvts)) setGoogleCalendarEvents(gEvts);
        if (Array.isArray(execs)) setExecutions(execs);
        if (oauths && typeof oauths === 'object') {
          setOauthProviders(oauths as Record<string, OAuthProviderInfo>);
        }
      })
      .catch((err) => {
        console.error('Error loading connections data', err);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchAll();
  }, []);

  useEffect(() => {
    if (initialTab) {
      setActiveTab(initialTab);
    } else if (initialExecutionId) {
      setActiveTab('actions');
    }
  }, [initialTab, initialExecutionId]);

  const handleApproveAction = async (executionId: string) => {
    if (actionLoadingId === executionId) return;
    setActionLoadingId(executionId);
    try {
      const res = await submitApprovalDecision({
        target_type: 'action_execution',
        target_id: executionId,
        decision: 'approve',
        approver: 'user',
      });
      if (res.success) {
        showToast(res.message || t('connUiApprovalRecorded'), approvalToastKind(res, 'approve'));
        fetchAll();
      } else {
        showToast(res.message || t('connUiUnableToApproveTheOperation'), 'error');
      }
    } catch (err: any) {
      showToast(err.message || t('connUiErrorDuringApproval'), 'error');
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleRejectAction = async (executionId: string) => {
    if (actionLoadingId === executionId) return;
    setActionLoadingId(executionId);
    try {
      const res = await submitApprovalDecision({
        target_type: 'action_execution',
        target_id: executionId,
        decision: 'reject',
        reason: 'Rifiutato dall\'utente',
      });
      if (res.success) {
        showToast(res.message || t('connUiOperationDeclined'), 'info');
        fetchAll();
      } else {
        showToast(res.message || t('connUiUnableToDeclineTheOperation'), 'error');
      }
    } catch (err: any) {
      showToast(err.message || t('connUiErrorWhileDeclining'), 'error');
    } finally {
      setActionLoadingId(null);
    }
  };

  const openConfigModal = (provider: ProviderDefinition, existingConn?: ConnectionItem) => {
    setConfigModalProvider(provider);
    setCredAccountName(existingConn?.account_name || t('connUiAccountName').replace('{name}', provider.name));
    setTestResult(null);
    setGithubToken('');
    setSlackToken('');
    setSlackWebhook('');
    setSlackDefaultChannel('');
    setEmailUser('');
    setEmailPass('');
    setEmailHost('smtp.gmail.com');
    setEmailPort('587');
    setEmailUseTls(true);
    setEmailUseSsl(false);
    setEmailSenderAddr('');
    setEmailTestRecipient('');
    setHttpBaseUrl('');
    setHttpAuthType('none');
    setHttpToken('');
    setNotionToken('');
    setNotionDbId('');
    setTelegramBotToken('');
    setTelegramDefaultChatId('');
    setTelegramAllowedChats('');
    setOpenapiSpecUrl('');
    setOpenapiSpecPath('');
    setOpenapiBaseUrl('');
    setOpenapiAuthType('none');
    setOpenapiToken('');

    if (existingConn?.auth_metadata) {
      const meta = existingConn.auth_metadata;
      if (provider.id === 'email') {
        if (meta.username) setEmailUser(meta.username);
        if (meta.smtp_host) setEmailHost(meta.smtp_host);
        if (meta.smtp_port) setEmailPort(String(meta.smtp_port));
        if (meta.use_tls !== undefined) setEmailUseTls(Boolean(meta.use_tls));
        if (meta.use_ssl !== undefined) setEmailUseSsl(Boolean(meta.use_ssl));
        if (meta.sender_address) setEmailSenderAddr(meta.sender_address);
        if (meta.test_recipient) setEmailTestRecipient(meta.test_recipient);
      }
      if (provider.id === 'slack' && meta.default_channel) {
        setSlackDefaultChannel(meta.default_channel);
      }
      if (provider.id === 'http') {
        if (meta.base_url) setHttpBaseUrl(meta.base_url);
        if (meta.auth_type) setHttpAuthType(meta.auth_type);
      }
      if (provider.id === 'notion' && meta.default_database_id) {
        setNotionDbId(meta.default_database_id);
      }
      if (provider.id === 'openapi') {
        if (meta.spec_url) setOpenapiSpecUrl(meta.spec_url);
        if (meta.spec_path) setOpenapiSpecPath(meta.spec_path);
        if (meta.base_url) setOpenapiBaseUrl(meta.base_url);
        if (meta.auth_type) setOpenapiAuthType(meta.auth_type);
      }
      if (provider.id === 'telegram') {
        if (meta.default_chat_id) setTelegramDefaultChatId(String(meta.default_chat_id));
        if (meta.allowed_chat_ids) {
          setTelegramAllowedChats(
            Array.isArray(meta.allowed_chat_ids)
              ? meta.allowed_chat_ids.join(', ')
              : String(meta.allowed_chat_ids)
          );
        }
      }
    }
  };

  const handleVerifyConnection = async (providerId: string) => {
    try {
      setVerifyingProvider(providerId);
      const res = await fetch(apiUrl(`/api/connections/${providerId}/verify`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ live_check: true }),
      });
      const data = await res.json();
      if (data.valid) {
        showToast(t('connUiVerificationCompletedTheServiceIsActive'), 'success');
      } else {
        showToast(data.message || t('connUiVerificationFoundAnAuthenticationProblem'), 'error');
      }
      await fetchAll();
    } catch (err: any) {
      showToast(err.message || t('connUiVerificationRequestFailed'), 'error');
    } finally {
      setVerifyingProvider(null);
    }
  };

  const buildAuthMetadata = (providerId: string) => {
    const meta: Record<string, any> = {};
    if (providerId === 'github') meta.token = githubToken.trim();
    if (providerId === 'slack') {
      if (slackToken.trim()) meta.token = slackToken.trim();
      if (slackWebhook.trim()) meta.webhook_url = slackWebhook.trim();
      if (slackDefaultChannel.trim()) meta.default_channel = slackDefaultChannel.trim();
    }
    if (providerId === 'email') {
      meta.username = emailUser.trim();
      meta.password = emailPass;
      meta.smtp_host = emailHost.trim();
      meta.smtp_port = parseInt(emailPort, 10) || 587;
      meta.use_tls = emailUseTls;
      meta.use_ssl = emailUseSsl;
      if (emailSenderAddr.trim()) meta.sender_address = emailSenderAddr.trim();
      if (emailTestRecipient.trim()) meta.test_recipient = emailTestRecipient.trim();
    }
    if (providerId === 'http') {
      meta.base_url = httpBaseUrl.trim();
      meta.auth_type = httpAuthType;
      if (httpToken.trim()) meta.token = httpToken.trim();
    }
    if (providerId === 'notion') {
      meta.token = notionToken.trim();
      if (notionDbId.trim()) meta.default_database_id = notionDbId.trim();
    }
    if (providerId === 'telegram') {
      meta.bot_token = telegramBotToken.trim();
      if (telegramDefaultChatId.trim()) meta.default_chat_id = telegramDefaultChatId.trim();
      if (telegramAllowedChats.trim()) {
        meta.allowed_chat_ids = telegramAllowedChats.split(',').map((s) => s.trim()).filter(Boolean);
      }
    }
    if (providerId === 'openapi') {
      if (openapiSpecUrl.trim()) meta.spec_url = openapiSpecUrl.trim();
      if (openapiSpecPath.trim()) meta.spec_path = openapiSpecPath.trim();
      if (openapiBaseUrl.trim()) meta.base_url = openapiBaseUrl.trim();
      if (openapiAuthType.trim()) meta.auth_type = openapiAuthType.trim();
      if (openapiToken.trim()) meta.token = openapiToken.trim();
    }
    return meta;
  };

  const handleTestCreds = async () => {
    if (!configModalProvider) return;
    setTestingCreds(true);
    setTestResult(null);
    try {
      const authMeta = buildAuthMetadata(configModalProvider.id);
      const res = await fetch(apiUrl(`/api/connections/${configModalProvider.id}/verify`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          auth_metadata: authMeta,
          live_check: true,
        }),
      });
      const data = await res.json();
      setTestResult({
        valid: Boolean(data.valid),
        message: data.message || (data.valid ? t('connUiCredentialsVerifiedSuccessfully') : t('connUiVerificationFailed')),
      });
    } catch {
      setTestResult({
        valid: false,
        message: t('connUiUnableToReachTheLocalServer'),
      });
    } finally {
      setTestingCreds(false);
    }
  };

  const handleSaveAndConnect = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!configModalProvider) return;

    const authMeta = buildAuthMetadata(configModalProvider.id);
    setSavingCreds(true);
    try {
      const res = await fetch(apiUrl('/api/connections'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: configModalProvider.id,
          account_name: credAccountName.trim() || t('connUiAccountName').replace('{name}', configModalProvider.name),
          auth_metadata: authMeta,
          live_check: false,
        }),
      });
      if (res.ok) {
        showToast(t('connUiServiceConnected').replace('{name}', configModalProvider.name), 'success');
        setConfigModalProvider(null);
        fetchAll();
      } else {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || t('connUiUnableToSaveTheConnection'), 'error');
      }
    } catch {
      showToast(t('connUiErrorWhileSavingTheService'), 'error');
    } finally {
      setSavingCreds(false);
    }
  };

  const handleConnectCalendar = async () => {
    try {
      const res = await fetch(apiUrl('/api/connections'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: 'calendar',
          account_name: t('connUiAetherCalendarLocal'),
          auth_metadata: { type: 'sqlite_built_in' },
        }),
      });
      if (res.ok) {
        showToast(t('connUiLocalCalendarReadyAndActive'), 'success');
        fetchAll();
      }
    } catch {
      showToast(t('connUiUnableToInitializeTheLocalCalendar'), 'error');
    }
  };

  const confirmDisconnect = async () => {
    if (!disconnectTarget) return;
    setDisconnecting(true);
    try {
      const res = await fetch(apiUrl(`/api/connections/${disconnectTarget.id}/disconnect`), {
        method: 'POST',
      });
      if (res.ok) {
        showToast(t('connUiServiceDisconnected').replace('{name}', disconnectTarget.name), 'info');
        setDisconnectTarget(null);
        setManageProvider(null);
        fetchAll();
      } else {
        showToast(t('connUiUnableToDisconnectTheService'), 'error');
      }
    } catch {
      showToast(t('connUiCommunicationErrorWhileDisconnecting'), 'error');
    } finally {
      setDisconnecting(false);
    }
  };

  const handleSyncAll = async () => {
    setSyncingAll(true);
    try {
      const res = await fetch(apiUrl('/api/connections/sync_all'), { method: 'POST' });
      const data = await res.json();
      const total = data.total_items_ingested || 0;
      if (total === 0) {
        showToast(t('connUiSyncCompletedNoNewItemsFound'), 'info');
      } else {
        showToast(t('connUiSyncedItems').replace('{count}', String(total)), 'success');
      }
      await fetchAll();
    } catch (err: any) {
      showToast(err.message || t('connUiUnableToSyncTheServices'), 'error');
    } finally {
      setSyncingAll(false);
    }
  };

  const handleStartGoogleOAuth = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const gInfo = oauthProviders['google_calendar'];
    const trimmedId = googleClientId.trim();
    const trimmedSecret = googleClientSecret.trim();

    if (!gInfo?.has_client_id && !trimmedId) {
      showToast(t('connUiSetUpYourGoogleClientID'), 'error');
      return;
    }

    setGoogleAuthPending(true);
    try {
      // If user provided or changed client ID or secret in modal, save config first
      if (trimmedId || trimmedSecret) {
        await fetch(apiUrl('/api/connections/google_calendar/oauth/config'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            client_id: trimmedId || undefined,
            client_secret: trimmedSecret || undefined,
          }),
        });
      }

      const res = await fetch(apiUrl('/api/connections/google_calendar/oauth/start'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: trimmedId || undefined,
          client_secret: trimmedSecret || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || t('connUiUnableToStartGoogleAuthorization'));
      }
      setGoogleState(data.state || '');

      // Open in host/system browser directly
      await openExternalUrl(data.auth_url);

      const messageHandler = (event: MessageEvent) => {
        if (event.data?.type === 'aether_oauth_success' && event.data?.provider === 'google_calendar') {
          window.removeEventListener('message', messageHandler);
          clearInterval(pollTimer);
          showToast(t('connUiGoogleCalendarConnectedSuccessfully'), 'success');
          setIsGoogleModalOpen(false);
          setGoogleAuthPending(false);
          fetchAll();
        } else if (event.data?.type === 'aether_oauth_error' && event.data?.provider === 'google_calendar') {
          window.removeEventListener('message', messageHandler);
          clearInterval(pollTimer);
          showToast(t('connUiGoogleAuthFailed').replace('{error}', event.data.error || t('connUiErrorWord')), 'error');
          setGoogleAuthPending(false);
          fetchAll();
        }
      };
      window.addEventListener('message', messageHandler);

      let attempts = 0;
      const pollTimer = setInterval(async () => {
        attempts++;
        if (attempts > 80) {
          clearInterval(pollTimer);
          window.removeEventListener('message', messageHandler);
          setGoogleAuthPending(false);
          return;
        }
        try {
          const checkRes = await fetch(apiUrl('/api/connections'));
          if (checkRes.ok) {
            const conns = await checkRes.json();
            if (Array.isArray(conns)) {
              const gc = conns.find((c: any) => c.provider === 'google_calendar');
              if (gc && (gc.status === 'verified' || gc.status === 'connected')) {
                clearInterval(pollTimer);
                window.removeEventListener('message', messageHandler);
                showToast(t('connUiGoogleCalendarConnectedAndVerified'), 'success');
                setIsGoogleModalOpen(false);
                setGoogleAuthPending(false);
                fetchAll();
              }
            }
          }
        } catch {}
      }, 1500);
    } catch (err: any) {
      showToast(err.message || t('connUiErrorWhileStartingGoogleOAuth'), 'error');
      setGoogleAuthPending(false);
    }
  };

  const copyToClipboard = (text: string, fieldKey: string) => {
    navigator.clipboard.writeText(text);
    setCopiedField(fieldKey);
    setTimeout(() => setCopiedField(null), 2000);
    showToast(t('connUiCopiedToClipboard'), 'info');
  };

  const handleStartOAuth = async (provider: string) => {
    setOauthPendingProvider(provider);
    try {
      const res = await fetch(apiUrl(`/api/connections/${provider}/oauth/start`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || t('connUiAuthStartFailed').replace('{provider}', provider));
      }
      if (data.auth_url) {
        await openExternalUrl(data.auth_url);
        const nameMap: Record<string, string> = {
          google_calendar: 'Google Calendar',
          github: 'GitHub',
          slack: 'Slack',
          notion: 'Notion',
        };
        const pName = nameMap[provider] || provider;
        showToast(t('connUiOpeningAuth').replace('{name}', pName), 'info');

        let attempts = 0;
        const pollTimer = setInterval(async () => {
          attempts++;
          if (attempts > 80) {
            clearInterval(pollTimer);
            setOauthPendingProvider(null);
            return;
          }
          try {
            const checkRes = await fetch(apiUrl('/api/connections'));
            if (checkRes.ok) {
              const conns = await checkRes.json();
              if (Array.isArray(conns)) {
                const conn = conns.find((c: any) => c.provider === provider);
                if (conn && (conn.status === 'verified' || conn.status === 'connected')) {
                  clearInterval(pollTimer);
                  setOauthPendingProvider(null);
                  showToast(t('connUiConnectedActive').replace('{name}', pName), 'success');
                  fetchAll();
                }
              }
            }
          } catch {}
        }, 1500);
      }
    } catch (err: any) {
      showToast(err.message || t('connUiErrorWhileStartingTheAuthorization'), 'error');
      setOauthPendingProvider(null);
    }
  };

  const openDevSetupModal = (p: ProviderDefinition) => {
    setDevSetupModalProvider(p);
    const existing = connections.find((c) => c.provider === p.id);
    if (existing?.auth_metadata?.client_id) {
      setDevClientId(existing.auth_metadata.client_id);
    } else {
      setDevClientId('');
    }
    setDevClientSecret('');
    setTestResult(null);
  };

  const handleSaveDevOAuthConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!devSetupModalProvider) return;
    if (!devClientId.trim() || !devClientSecret.trim()) {
      showToast(t('connUiClientIDAndClientSecretAre'), 'error');
      return;
    }
    setSavingDevConfig(true);
    try {
      const res = await fetch(apiUrl(`/api/connections/${devSetupModalProvider.id}/oauth/config`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: devClientId.trim(),
          client_secret: devClientSecret.trim(),
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || t('connUiUnableToSaveTheDeveloperConfiguration'));
      }
      showToast(t('connUiApplicationCredentialsSavedSuccessfully'), 'success');
      await fetchAll();
      const targetProv = devSetupModalProvider.id;
      setDevSetupModalProvider(null);
      await handleStartOAuth(targetProv);
    } catch (err: any) {
      showToast(err.message || t('connUiErrorSavingCredentials'), 'error');
    } finally {
      setSavingDevConfig(false);
    }
  };

  const openTelegramModal = (conn?: ConnectionItem) => {
    if (conn && conn.auth_metadata) {
      setTelegramBotToken(conn.auth_metadata.bot_token || '');
      setTelegramDefaultChatId(conn.auth_metadata.default_chat_id || '');
      setTelegramAllowedChats(conn.auth_metadata.allowed_chat_ids || '');
    } else {
      setTelegramBotToken('');
      setTelegramDefaultChatId('');
      setTelegramAllowedChats('');
    }
    setTestResult(null);
    setIsTelegramModalOpen(true);
  };

  const handleConnectTelegramGuided = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!telegramBotToken.trim()) {
      showToast(t('connUiTheBotTokenIsRequiredFor'), 'error');
      return;
    }
    setVerifyingTelegram(true);
    setTestResult(null);
    try {
      const authMeta: Record<string, any> = {
        bot_token: telegramBotToken.trim(),
        live_check: true,
      };
      if (telegramDefaultChatId.trim()) authMeta.default_chat_id = telegramDefaultChatId.trim();
      if (telegramAllowedChats.trim()) authMeta.allowed_chat_ids = telegramAllowedChats.trim();

      const verifyRes = await fetch(apiUrl('/api/connections/telegram/verify'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ auth_metadata: authMeta, live_check: true }),
      });
      const verifyData = await verifyRes.json();
      if (!verifyData.valid) {
        setTestResult({ valid: false, message: verifyData.message || t('connUiTokenVerificationFailed') });
        return;
      }

      const saveRes = await fetch(apiUrl('/api/connections'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: 'telegram',
          account_name: 'Telegram Companion',
          auth_metadata: authMeta,
          live_check: true,
        }),
      });
      if (saveRes.ok) {
        showToast(t('connUiTelegramCompanionConnectedAndActive'), 'success');
        setIsTelegramModalOpen(false);
        fetchAll();
      } else {
        const err = await saveRes.json();
        setTestResult({ valid: false, message: err.detail || t('connUiUnableToSaveTheTelegramConnection') });
      }
    } catch (err: any) {
      setTestResult({ valid: false, message: err.message || t('connUiServerConnectionError') });
    } finally {
      setVerifyingTelegram(false);
    }
  };

  const handleManualExchangeCode = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!googleManualCode.trim() || !googleState.trim()) {
      showToast(t('connUiBothTheAuthorizationCodeAndThe'), 'error');
      return;
    }
    setGoogleAuthPending(true);
    try {
      const res = await fetch(apiUrl('/api/connections/google_calendar/oauth/exchange'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: googleManualCode.trim(),
          state: googleState.trim(),
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || t('connUiAuthorizationCodeExchangeFailed'));
      }
      if (data.valid) {
        showToast(t('connUiGoogleCalendarAuthorizedAndVerifiedSuccessfully'), 'success');
        setIsGoogleModalOpen(false);
        setGoogleManualCode('');
        fetchAll();
      } else {
        showToast(t('connUiVerifyFailedMsg').replace('{message}', String(data.message)), 'error');
      }
    } catch (err: any) {
      showToast(err.message || t('connUiErrorDuringGoogleAuthorization'), 'error');
    } finally {
      setGoogleAuthPending(false);
    }
  };

  const handleOpenCalendarPicker = async () => {
    try {
      const res = await fetch(apiUrl('/api/connections/google_calendar/calendars'));
      const data = await res.json();
      if (data.calendars && Array.isArray(data.calendars)) {
        setGoogleCalendars(data.calendars);
        setIsCalendarPickerOpen(true);
      } else {
        showToast(t('connUiNoGoogleCalendarFoundOrRead'), 'error');
      }
    } catch {
      showToast(t('connUiUnableToLoadTheGoogleCalendars'), 'error');
    }
  };

  const handleSelectCalendar = async (calId: string, summary: string) => {
    try {
      const res = await fetch(apiUrl('/api/connections/google_calendar/select-calendar'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          calendar_id: calId,
          calendar_summary: summary,
        }),
      });
      if (res.ok) {
        showToast(t('connUiActiveCalendarSet').replace('{name}', summary), 'success');
        setIsCalendarPickerOpen(false);
        fetchAll();
      }
    } catch {
      showToast(t('connUiUnableToSelectTheCalendar'), 'error');
    }
  };

  const handleCreateEvent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    setCreatingEvent(true);
    try {
      const endpoint =
        selectedScheduleSource === 'google'
          ? '/api/connections/google_calendar/events'
          : '/api/connections/calendar/events';

      const res = await fetch(apiUrl(endpoint), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: newTitle.trim(),
          start_time: newStartTime || new Date().toISOString(),
          location: newLocation.trim(),
        }),
      });
      if (res.ok) {
        showToast(
          selectedScheduleSource === 'google'
            ? t('connUiAppointmentCreatedOnGoogleCalendar')
            : t('connUiAppointmentSavedToTheLocalCalendar'),
          'success'
        );
        setIsEventModalOpen(false);
        setNewTitle('');
        setNewStartTime('');
        setNewLocation('');
        fetchAll();
      }
    } catch {
      showToast(t('connUiErrorWhileCreatingTheAppointment'), 'error');
    } finally {
      setCreatingEvent(false);
    }
  };

  // Grouping & Filtering
  const filteredProviders = useMemo(() => {
    return AVAILABLE_PROVIDERS.filter((p) => {
      if (categoryFilter !== 'all' && p.category !== categoryFilter) return false;
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase().trim();
        const conn = connections.find((c) => c.provider === p.id);
        const nameMatch = p.name.toLowerCase().includes(query);
        const descMatch = p.description.toLowerCase().includes(query);
        const accountMatch = conn?.account_name?.toLowerCase().includes(query);
        const capMatch = p.capabilitiesList.some((cap) => cap.toLowerCase().includes(query));
        if (!nameMatch && !descMatch && !accountMatch && !capMatch) return false;
      }
      return true;
    });
  }, [categoryFilter, searchQuery, connections, AVAILABLE_PROVIDERS]);

  // Chronologically grouped calendar events
  const groupedEvents = useMemo(() => {
    const list = selectedScheduleSource === 'local' ? calendarEvents : googleCalendarEvents;
    const groups: { dateKey: string; label: string; isToday: boolean; events: CalendarEventItem[] }[] = [];
    const map = new Map<string, CalendarEventItem[]>();

    list.forEach((evt) => {
      const key = getEventDateKey(evt);
      if (!map.has(key)) {
        map.set(key, []);
      }
      map.get(key)!.push(evt);
    });

    const sortedKeys = Array.from(map.keys()).sort();
    sortedKeys.forEach((key) => {
      const { label, isToday } = formatDayLabel(key, t, locale);
      groups.push({
        dateKey: key,
        label,
        isToday,
        events: map.get(key)!,
      });
    });

    return groups;
  }, [selectedScheduleSource, calendarEvents, googleCalendarEvents, language]);

  // Filtered executions
  const filteredExecutions = useMemo(() => {
    if (actionStatusFilter === 'all') return executions;
    if (actionStatusFilter === 'pending') {
      return executions.filter((e) => e.status === 'pending_approval' || e.status === 'waiting_approval');
    }
    if (actionStatusFilter === 'succeeded') {
      return executions.filter((e) => e.status === 'success' || e.status === 'succeeded');
    }
    if (actionStatusFilter === 'failed') {
      return executions.filter((e) => e.status === 'failed' || e.status === 'error');
    }
    return executions;
  }, [executions, actionStatusFilter]);

  // Primary Connect Action Handler
  const handlePrimaryAction = (provider: ProviderDefinition, conn?: ConnectionItem) => {
    const isConn = conn && (conn.status === 'verified' || conn.status === 'connected');
    if (isConn) {
      setManageProvider(provider);
      return;
    }

    if (provider.id === 'calendar') {
      handleConnectCalendar();
      return;
    }

    if (provider.id === 'google_calendar') {
      const existing = connections.find((c) => c.provider === 'google_calendar');
      if (existing?.auth_metadata?.client_id && !googleClientId) {
        setGoogleClientId(existing.auth_metadata.client_id);
      }
      setIsGoogleModalOpen(true);
      return;
    }

    if (provider.id === 'telegram') {
      openTelegramModal(conn);
      return;
    }

    // Providers with OAuth capability (GitHub, Slack, Notion)
    const oInfo = oauthProviders[provider.id];
    if (provider.isOAuth && oInfo?.supports_oauth) {
      if (oInfo.ready_for_user_connect) {
        handleStartOAuth(provider.id);
      } else {
        openDevSetupModal(provider);
      }
      return;
    }

    // Default configuration form
    openConfigModal(provider, conn);
  };

  return (
    <PageContainer size="xl">
      {/* 1. Header Section */}
      <Section
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Layers size={26} color="hsl(var(--primary))" />
            <Heading level={1}>{t('connUiTitle')}</Heading>
          </div>
        }
        description={t('connUiConnectTheAppsYouUseEvery')}
        actions={
          <Stack direction="row" gap="sm" align="center">
            <Button
              variant="secondary"
              size="sm"
              onClick={fetchAll}
              disabled={loading}
              leftIcon={<RefreshCw size={14} className={loading ? 'animate-spin' : ''} />}
            >
              {t('connRefresh')}
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleSyncAll}
              disabled={syncingAll}
              leftIcon={<RefreshCw size={14} className={syncingAll ? 'animate-spin' : ''} />}
            >
              {syncingAll ? t('connSyncing') : t('connUiSyncAll')}
            </Button>
          </Stack>
        }
      />

      {/* 2. Navigation View Switcher (Tabs) */}
      <Stack direction="column" gap="lg" style={{ marginBottom: '24px' }}>
        <SegmentedControl
          value={activeTab}
          onChange={(tab) => setActiveTab(tab as any)}
          options={[
            {
              value: 'apps',
              label: t('connUiServices'),
              icon: <Globe size={15} />,
            },
            {
              value: 'calendar',
              label: t('connUiCalendarSchedule'),
              icon: <Calendar size={15} />,
            },
            {
              value: 'actions',
              label: t('connUiOperationsApprovalsHistory'),
              icon: <Clock size={15} />,
            },
          ]}
        />
      </Stack>

      {/* =========================================================================
          TAB 1: SERVIZI COLLEGATI (APPS)
          ========================================================================= */}
      {activeTab === 'apps' && (
        <Stack direction="column" gap="lg">
          {/* Filter Bar: Categories & Search */}
          <Panel variant="default" style={{ padding: '14px 18px' }}>
            <Stack
              direction="row"
              gap="md"
              align="center"
              justify="between"
              wrap
            >
              <SegmentedControl
                value={categoryFilter}
                onChange={(cat) => setCategoryFilter(cat as CategoryType)}
                options={[
                  { value: 'all', label: t('connUiAllServices') },
                  { value: 'productivity', label: t('connUiProductivity') },
                  { value: 'dev', label: t('connUiDevelopment') },
                  { value: 'communication', label: t('connFilterComm') },
                ]}
              />

              <div style={{ minWidth: '240px', flex: '1', maxWidth: '340px' }}>
                <AetherInput
                  placeholder={t('connUiSearchServiceOrCapability')}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>
            </Stack>
          </Panel>

          {/* Provider Grid */}
          {filteredProviders.length === 0 ? (
            <EmptyState
              icon={<Globe size={28} />}
              title={t('connUiNoServiceFound')}
              description={t('connUiNoServiceMatchesTheSearchCriteria')}
              action={
                <Button variant="secondary" onClick={() => { setSearchQuery(''); setCategoryFilter('all'); }}>
                  {t('connUiResetFilters')}
                </Button>
              }
            />
          ) : (
            <Grid minItemWidth={330} gap="lg">
              {filteredProviders.map((provider) => {
                const conn = connections.find((c) => c.provider === provider.id);
                const isConnected = conn && (conn.status === 'verified' || conn.status === 'connected');
                const isConnecting = oauthPendingProvider === provider.id || verifyingProvider === provider.id;
                const IconComponent = provider.icon;

                // Truthful status determination
                const oInfo = oauthProviders[provider.id];
                const needsDevSetup = provider.isOAuth && oInfo?.supports_oauth && !oInfo.ready_for_user_connect;

                let displayStatus = 'NOT_CONFIGURED';
                if (isConnecting) {
                  displayStatus = 'CONNECTING';
                } else if (conn && conn.status !== 'not_configured') {
                  displayStatus = conn.status;
                } else if (needsDevSetup) {
                  displayStatus = 'SETUP_REQUIRED';
                }

                return (
                  <Panel
                    key={provider.id}
                    variant="default"
                    className="ds-panel--interactive"
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between',
                      height: '100%',
                    }}
                    onClick={() => handlePrimaryAction(provider, conn)}
                  >
                    <Stack direction="column" gap="md">
                      {/* Card Header: Icon, Title & Status Badge */}
                      <Stack direction="row" gap="md" align="center" justify="between">
                        <Stack direction="row" gap="md" align="center">
                          <div
                            style={{
                              width: '42px',
                              height: '42px',
                              borderRadius: '10px',
                              backgroundColor: `${provider.color}18`,
                              color: provider.color,
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              flexShrink: 0,
                            }}
                          >
                            <IconComponent size={22} color={provider.color} />
                          </div>
                          <Stack gap="none">
                            <Heading level={4}>{provider.name}</Heading>
                            {isConnected && conn?.account_name && (
                              <Text size="xs" variant="muted" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                <Shield size={12} color="hsl(var(--success))" />
                                {conn.account_name}
                              </Text>
                            )}
                          </Stack>
                        </Stack>

                        <StatusBadge status={displayStatus} />
                      </Stack>

                      {/* Card Body: Simple description */}
                      <Text size="sm" variant="muted" style={{ minHeight: '40px' }}>
                        {provider.description}
                      </Text>

                      {/* Capabilities pill */}
                      <div
                        style={{
                          backgroundColor: 'hsl(var(--muted) / 0.4)',
                          borderRadius: '6px',
                          padding: '6px 10px',
                          fontSize: '12px',
                          color: 'hsl(var(--fg))',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                        }}
                      >
                        <Zap size={13} color="hsl(var(--primary))" style={{ flexShrink: 0 }} />
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {provider.capabilitiesText}
                        </span>
                      </div>

                      {/* Error notice if connection failed */}
                      {conn && (conn.status === 'error' || conn.status === 'verification_failed') && (
                        <AlertBanner variant="error" title={t('connUiAttentionRequired')}>
                          {conn.last_verification_error || t('connUiAuthenticationExpiredOrInvalid')}
                        </AlertBanner>
                      )}
                    </Stack>

                    {/* Card Footer: Single Primary Action */}
                    <div
                      style={{
                        marginTop: '16px',
                        paddingTop: '14px',
                        borderTop: '1px solid hsl(var(--border))',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: '8px',
                      }}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {isConnected ? (
                        <>
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => setManageProvider(provider)}
                            leftIcon={<Shield size={14} />}
                          >
                            {t('connManage')}
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={verifyingProvider === provider.id}
                            onClick={() => handleVerifyConnection(provider.id)}
                            leftIcon={
                              verifyingProvider === provider.id ? (
                                <LoadingSpinner size="sm" />
                              ) : (
                                <RefreshCw size={13} />
                              )
                            }
                          >
                            {t('connVerify')}
                          </Button>
                        </>
                      ) : (
                        <Button
                          variant={needsDevSetup ? 'secondary' : 'primary'}
                          size="sm"
                          fullWidth
                          disabled={isConnecting}
                          onClick={() => handlePrimaryAction(provider, conn)}
                          rightIcon={<ArrowRight size={14} />}
                        >
                          {isConnecting
                            ? t('connUiConnecting')
                            : provider.isOAuth
                            ? (needsDevSetup ? t('configure') : t('connConnect'))
                            : t('configure')}
                        </Button>
                      )}
                    </div>
                  </Panel>
                );
              })}
            </Grid>
          )}
        </Stack>
      )}

      {/* =========================================================================
          TAB 2: CALENDARIO & AGENDA
          ========================================================================= */}
      {activeTab === 'calendar' && (
        <Stack direction="column" gap="lg">
          <Panel variant="default" style={{ padding: '16px 20px' }}>
            <Stack direction="row" gap="md" align="center" justify="between" wrap>
              <SegmentedControl
                value={selectedScheduleSource}
                onChange={(src) => setSelectedScheduleSource(src as any)}
                options={[
                  {
                    value: 'local',
                    label: t('connUiAetherLocalCalendar'),
                    icon: <Calendar size={15} />,
                  },
                  {
                    value: 'google',
                    label: 'Google Calendar (Cloud)',
                    icon: <Globe size={15} />,
                  },
                ]}
              />

              <Stack direction="row" gap="sm">
                {selectedScheduleSource === 'google' && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleOpenCalendarPicker}
                    leftIcon={<Calendar size={14} />}
                  >
                    {t('connUiSelectCalendar')}
                  </Button>
                )}
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => setIsEventModalOpen(true)}
                  leftIcon={<Plus size={14} />}
                >
                  {t('connUiNewAppointment')}
                </Button>
              </Stack>
            </Stack>
          </Panel>

          {/* Events List */}
          {groupedEvents.length === 0 ? (
            <EmptyState
              icon={<Calendar size={28} />}
              title={t('connUiNoUpcomingAppointments')}
              description={
                selectedScheduleSource === 'google'
                  ? t('connUiNoEventsScheduledInTheComing')
                  : t('connUiTheLocalCalendarIsEmptyAdd')
              }
              action={
                <Button
                  variant="primary"
                  onClick={() => setIsEventModalOpen(true)}
                  leftIcon={<Plus size={15} />}
                >
                  {t('connUiAddAppointment')}
                </Button>
              }
            />
          ) : (
            <Stack direction="column" gap="xl">
              {groupedEvents.map((group) => (
                <div key={group.dateKey}>
                  {/* Day Header */}
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      marginBottom: '12px',
                      paddingBottom: '8px',
                      borderBottom: '1px solid hsl(var(--border) / 0.6)',
                    }}
                  >
                    <Stack direction="row" gap="sm" align="center">
                      <Heading level={4} style={{ fontSize: '15px', margin: 0 }}>
                        {group.label}
                      </Heading>
                      {group.isToday && (
                        <span
                          style={{
                            fontSize: '11px',
                            fontWeight: 600,
                            padding: '2px 8px',
                            borderRadius: '10px',
                            backgroundColor: 'hsl(var(--primary) / 0.15)',
                            color: 'hsl(var(--primary))',
                            textTransform: 'uppercase',
                            letterSpacing: '0.04em',
                          }}
                        >
                          {t('connUiToday')}
                        </span>
                      )}
                    </Stack>
                    <Text size="xs" variant="muted">
                      {group.events.length} {group.events.length === 1 ? t('connUiEvent') : t('connUiEvents')}
                    </Text>
                  </div>

                  {/* Day Events */}
                  <Grid minItemWidth={300} gap="md">
                    {group.events.map((evt) => {
                      const timeStr = formatEventTime(evt, t, locale);
                      const isAllDay = timeStr === t('connUiAllDay');

                      return (
                        <Panel key={evt.id} variant="default" style={{ padding: '16px' }}>
                          <Stack direction="column" gap="sm">
                            <Stack direction="row" align="center" justify="between" gap="sm">
                              <Heading level={4} style={{ fontSize: '15px' }}>
                                {evt.title}
                              </Heading>
                              <span
                                style={{
                                  fontSize: '12px',
                                  fontWeight: 500,
                                  padding: '3px 8px',
                                  borderRadius: '6px',
                                  backgroundColor: isAllDay
                                    ? 'hsl(var(--primary) / 0.12)'
                                    : 'hsl(var(--muted) / 0.5)',
                                  color: isAllDay ? 'hsl(var(--primary))' : 'hsl(var(--fg))',
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: '5px',
                                  flexShrink: 0,
                                }}
                              >
                                <Clock size={12} />
                                {timeStr}
                              </span>
                            </Stack>

                            {evt.description && (
                              <Text size="xs" variant="muted" style={{ lineHeight: '1.4' }}>
                                {evt.description}
                              </Text>
                            )}

                            {evt.location && (
                              <Text
                                size="xs"
                                variant="muted"
                                style={{ display: 'flex', alignItems: 'center', gap: '4px' }}
                              >
                                📍 {evt.location}
                              </Text>
                            )}
                          </Stack>
                        </Panel>
                      );
                    })}
                  </Grid>
                </div>
              ))}
            </Stack>
          )}
        </Stack>
      )}

      {/* =========================================================================
          TAB 3: STORICO OPERAZIONI & APPROVAZIONI
          ========================================================================= */}
      {activeTab === 'actions' && (
        <Stack direction="column" gap="lg">
          <Panel variant="default" style={{ padding: '14px 18px' }}>
            <Stack direction="row" gap="md" align="center" justify="between" wrap>
              <SegmentedControl
                value={actionStatusFilter}
                onChange={(f) => setActionStatusFilter(f)}
                options={[
                  { value: 'all', label: t('connUiAllActions') },
                  { value: 'pending', label: t('connUiAwaitingApproval') },
                  { value: 'succeeded', label: t('connUiCompleted') },
                  { value: 'failed', label: t('connUiFailedOrRejected') },
                ]}
              />
              <Text size="xs" variant="muted">
                {filteredExecutions.length} operazioni registrate
              </Text>
            </Stack>
          </Panel>

          {filteredExecutions.length === 0 ? (
            <EmptyState
              icon={<Clock size={28} />}
              title={t('connUiNoOperationsRecorded')}
              description={t('connUiWhenAetherRunsOrRequestsApproval')}
            />
          ) : (
            <Stack direction="column" gap="md">
              {filteredExecutions.map((exec) => {
                const isPending =
                  exec.status === 'pending_approval' || exec.status === 'waiting_approval';
                const isSuccess = exec.status === 'success' || exec.status === 'succeeded';

                return (
                  <Panel
                    key={exec.id}
                    variant="default"
                    id={`exec-card-${exec.id}`}
                    style={{
                      borderLeft: isPending
                        ? '3px solid hsl(var(--warning))'
                        : isSuccess
                        ? '3px solid hsl(var(--success))'
                        : '3px solid hsl(var(--destructive))',
                    }}
                  >
                    <Stack direction="row" gap="md" align="center" justify="between" wrap>
                      <Stack direction="column" gap="xs">
                        <Stack direction="row" gap="sm" align="center">
                          <Heading level={4}>{exec.action_id}</Heading>
                          <StatusBadge
                            status={
                              isPending
                                ? 'setup_required'
                                : isSuccess
                                ? 'connected'
                                : 'error'
                            }
                            label={
                              isPending
                                ? t('connUiAwaitingApproval')
                                : isSuccess
                                ? t('connUiCompletedSuccessfully')
                                : t('connUiFailed')
                            }
                          />
                        </Stack>
                        <Text size="xs" variant="muted">
                          {new Date(exec.created_at).toLocaleString(locale)} — ID: {exec.id}
                        </Text>
                      </Stack>

                      {isPending && (
                        <Stack direction="row" gap="sm">
                          <Button
                            variant="primary"
                            size="sm"
                            loading={actionLoadingId === exec.id}
                            onClick={() => handleApproveAction(exec.id)}
                          >
                            {t('connUiApproveAndRun')}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            loading={actionLoadingId === exec.id}
                            onClick={() => handleRejectAction(exec.id)}
                          >
                            {t('reject')}
                          </Button>
                        </Stack>
                      )}
                    </Stack>

                    {exec.error_message && (
                      <div style={{ marginTop: '12px' }}>
                        <AlertBanner variant="error" title={t('connUiErrorDetails')}>
                          {exec.error_message}
                        </AlertBanner>
                      </div>
                    )}
                  </Panel>
                );
              })}
            </Stack>
          )}
        </Stack>
      )}

      {/* =========================================================================
          MODALE 1: GOOGLE CALENDAR CONNECT (USER-FRIENDLY & TRUTHFUL PKCE SETUP)
          ========================================================================= */}
      {(() => {
        const googleOAuthInfo = oauthProviders['google_calendar'];
        const googleConn = connections.find((c) => c.provider === 'google_calendar');
        const hasClientId = Boolean(googleOAuthInfo?.has_client_id || (googleConn && googleConn.auth_metadata?.client_id));
        const hasClientSecret = Boolean(googleOAuthInfo?.has_client_secret || (googleConn && googleConn.auth_metadata?.client_secret));
        const lastError = googleConn?.last_verification_error || '';
        const isMissingSecretError = lastError.toLowerCase().includes('client_secret');
        const isFullyConfigured = hasClientId && hasClientSecret && !isMissingSecretError;
        const canSubmit = hasClientId || Boolean(googleClientId.trim());

        return (
          <Modal
            isOpen={isGoogleModalOpen}
            onClose={() => setIsGoogleModalOpen(false)}
            size="md"
            title={t('connUiConnectGoogleCalendar')}
            description={t('connUiAuthorizeAetherToAccessYourCalendars')}
            footer={
              <AetherFormActions align="between">
                <Button variant="ghost" onClick={() => setIsGoogleModalOpen(false)}>
                  {t('cancel')}
                </Button>
                <Button
                  variant="primary"
                  size="md"
                  disabled={!canSubmit}
                  loading={googleAuthPending}
                  onClick={handleStartGoogleOAuth}
                  leftIcon={<Globe size={16} />}
                >
                  {googleAuthPending
                    ? t('connUiWaitingForAuthorization')
                    : isFullyConfigured
                    ? t('connUiAuthorizeWithGoogle')
                    : t('connUiSaveAndAuthorizeWithGoogle')}
                </Button>
              </AetherFormActions>
            }
          >
            <Stack direction="column" gap="lg">
              {isMissingSecretError && (
                <AlertBanner variant="error" title={t('connUiClientSecretRequiredByGoogle')}>
                  {renderRich(t('connUiMissingSecretBody'))}
                </AlertBanner>
              )}

              {!isFullyConfigured ? (
                <>
                  {!isMissingSecretError && (
                    <AlertBanner variant="info" title={t('connUiGoogleCloudCredentialsSetup')}>
                      {renderRich(t('connUiGoogleCredsIntro'))}
                    </AlertBanner>
                  )}

                  <Panel variant="default" style={{ padding: '16px' }}>
                    <Text size="sm" weight="semibold" style={{ marginBottom: '8px' }}>
                      {t('connUiHowToGetYourCredentialsOn')}
                    </Text>
                    <ol style={{ fontSize: '13px', color: 'hsl(var(--fg))', margin: 0, paddingLeft: '20px', lineHeight: '1.6' }}>
                      <li>
                        {t('connUiStepOpenConsolePre')} <a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noopener noreferrer" style={{ color: 'hsl(var(--primary))', textDecoration: 'underline' }}>{t('connUiStepOpenConsoleLink')}</a> {renderRich(t('connUiStepOpenConsolePost'))}
                      </li>
                      <li>
                        {renderRich(t('connUiStepCreateCreds'))}
                      </li>
                      <li>
                        {renderRich(t('connUiStepAppType'))}
                      </li>
                      <li>
                        {renderRich(t('connUiStepRedirect'))} <code>http://127.0.0.1:8000/api/connections/google_calendar/oauth/callback</code>.
                      </li>
                      <li>
                        {renderRich(t('connUiStepCopyIds'))}
                      </li>
                    </ol>
                  </Panel>

                  <AetherForm onSubmit={handleStartGoogleOAuth}>
                    <AetherField label="Google Client ID" required helperText={t('connUiOAuthIdentifierEndsWithAppsGoogleusercontent')}>
                      <AetherInput
                        placeholder={t('connUiEG123456789AbcdefAppsGoogleusercontent')}
                        value={googleClientId}
                        onChange={(e) => setGoogleClientId(e.target.value)}
                        autoFocus={!googleClientId}
                      />
                    </AetherField>

                    <AetherField
                      label={isMissingSecretError ? t('connUiGoogleClientSecretRequiredByGoogle') : "Google Client Secret"}
                      helperText={t('connUiRequiredForWebApplicationsEG')}
                    >
                      <AetherPasswordInput
                        placeholder="es. GOCSPX-..."
                        value={googleClientSecret}
                        onChange={(e) => setGoogleClientSecret(e.target.value)}
                        autoFocus={Boolean(isMissingSecretError)}
                      />
                    </AetherField>
                  </AetherForm>
                </>
              ) : (
                <>
                  <AlertBanner variant="info" title={t('connUiSecureAndTransparentAuthorization')}>
                    {t('connUiTheAuthorizationFlowWillOpenYour')}
                  </AlertBanner>

                  <Panel variant="default" style={{ padding: '14px' }}>
                    <Stack direction="row" align="center" justify="between">
                      <div>
                        <Text size="sm" weight="medium">
                          {t('connUiClientIDAndClientSecret')}
                        </Text>
                        <Text size="xs" variant="muted">
                          ID: {googleOAuthInfo?.client_id_preview || (googleClientId ? `${googleClientId.slice(0, 8)}...` : t('connUiConfigured'))} • Secret: {hasClientSecret ? t('connUiConfigured') : t('connUiNotConfigured')}
                        </Text>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setGoogleAdvOpen(!googleAdvOpen)}
                      >
                        {googleAdvOpen ? t('close') : t('connUiEditCredentials')}
                      </Button>
                    </Stack>

                    {googleAdvOpen && (
                      <div style={{ marginTop: '16px', paddingTop: '14px', borderTop: '1px solid hsl(var(--border))' }}>
                        <AetherForm onSubmit={handleStartGoogleOAuth}>
                          <AetherField label="Google Client ID" required helperText={t('connUiOAuthIdentifierEndsWithAppsGoogleusercontent')}>
                            <AetherInput
                              placeholder={t('connUiEG123456789AppsGoogleusercontentCom')}
                              value={googleClientId}
                              onChange={(e) => setGoogleClientId(e.target.value)}
                            />
                          </AetherField>

                          <AetherField label="Google Client Secret" helperText={t('connUiRequiredForWebApplicationsEG2')}>
                            <AetherPasswordInput
                              placeholder="es. GOCSPX-..."
                              value={googleClientSecret}
                              onChange={(e) => setGoogleClientSecret(e.target.value)}
                            />
                          </AetherField>
                        </AetherForm>
                      </div>
                    )}
                  </Panel>

                  {googleState && (
                    <Panel variant="default" style={{ padding: '12px' }}>
                      <AetherForm onSubmit={handleManualExchangeCode}>
                        <AetherField label={t('connUiAuthorizationCodeToPasteIfThe')}>
                          <AetherInput
                            placeholder={t('connUiPasteHereTheAuthorizationCodeReturned')}
                            value={googleManualCode}
                            onChange={(e) => setGoogleManualCode(e.target.value)}
                          />
                        </AetherField>
                        <Button
                          variant="secondary"
                          size="sm"
                          style={{ marginTop: '8px' }}
                          onClick={handleManualExchangeCode}
                          loading={googleAuthPending}
                        >
                          {t('connUiExchangeCodeManually')}
                        </Button>
                      </AetherForm>
                    </Panel>
                  )}
                </>
              )}
            </Stack>
          </Modal>
        );
      })()}

      {/* =========================================================================
          MODALE 2: DEVELOPER APP SETUP MODAL (GITHUB, SLACK, NOTION)
          ========================================================================= */}
      <Modal
        isOpen={Boolean(devSetupModalProvider)}
        onClose={() => setDevSetupModalProvider(null)}
        size="md"
        title={t('connUiConnectNamed').replace('{name}', devSetupModalProvider?.name || t('connUiServiceWord'))}
        description={t('connUiAuthorizeTheServiceToLetAether')}
        footer={
          <AetherFormActions>
            <Button variant="ghost" onClick={() => setDevSetupModalProvider(null)}>
              {t('cancel')}
            </Button>
            <Button
              variant="primary"
              loading={savingDevConfig}
              onClick={handleSaveDevOAuthConfig}
            >
              {t('connUiSaveAndAuthorizeInTheBrowser')}
            </Button>
          </AetherFormActions>
        }
      >
        <AetherForm onSubmit={handleSaveDevOAuthConfig}>
          <AlertBanner variant="info" title={t('connUiApplicationSetup')}>
            {t('connUiToGuaranteePrivacyAndFullControl')}
          </AlertBanner>

          {devSetupModalProvider && oauthProviders[devSetupModalProvider.id] && (
            <Panel variant="default" style={{ padding: '12px 14px' }}>
              <Text size="xs" variant="muted" style={{ marginBottom: '6px' }}>
                {t('connUiRedirectURIForYourApp')}
              </Text>
              <Stack direction="row" gap="sm" align="center">
                <AetherInput
                  readOnly
                  value={oauthProviders[devSetupModalProvider.id].redirect_uri}
                />
                <IconButton
                  icon={copiedField === 'redirect' ? <Check size={16} /> : <Copy size={16} />}
                  ariaLabel={t('connUiCopyRedirectURI')}
                  onClick={() =>
                    copyToClipboard(
                      oauthProviders[devSetupModalProvider.id].redirect_uri,
                      'redirect'
                    )
                  }
                />
              </Stack>
            </Panel>
          )}

          <AetherField label="Client ID" required>
            <AetherInput
              placeholder={t('connUiEnterTheClientIDProvidedBy')}
              value={devClientId}
              onChange={(e) => setDevClientId(e.target.value)}
            />
          </AetherField>

          <AetherField label="Client Secret" required>
            <AetherPasswordInput
              placeholder={t('connUiEnterTheClientSecretProvidedBy')}
              value={devClientSecret}
              onChange={(e) => setDevClientSecret(e.target.value)}
            />
          </AetherField>
        </AetherForm>
      </Modal>

      {/* =========================================================================
          MODALE 3: TELEGRAM COMPANION GUIDED MODAL
          ========================================================================= */}
      <Modal
        isOpen={isTelegramModalOpen}
        onClose={() => setIsTelegramModalOpen(false)}
        size="md"
        title={t('connUiConnectTelegramCompanion')}
        description={t('connUiReceivePushNotificationsAndApproveAether')}
        footer={
          <AetherFormActions>
            <Button variant="ghost" onClick={() => setIsTelegramModalOpen(false)}>
              {t('cancel')}
            </Button>
            <Button
              variant="primary"
              loading={verifyingTelegram}
              onClick={handleConnectTelegramGuided}
              leftIcon={<Send size={15} />}
            >
              {t('connUiVerifyAndConnectBot')}
            </Button>
          </AetherFormActions>
        }
      >
        <AetherForm onSubmit={handleConnectTelegramGuided}>
          <Panel variant="default" style={{ padding: '16px' }}>
            <Heading level={4} style={{ marginBottom: '8px' }}>
              {t('connUiHowToGetTheBotToken')}
            </Heading>
            <Stack direction="column" gap="xs">
              <Text size="sm">
                {renderRich(t('connUiTgStep1'))}
              </Text>
              <Text size="sm">
                {renderRich(t('connUiTgStep2'))}
              </Text>
              <Text size="sm">
                {renderRich(t('connUiTgStep3'))}
              </Text>
            </Stack>
          </Panel>

          <AetherField label={t('connUiTelegramBotToken')} required>
            <AetherPasswordInput
              placeholder="es. 123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"
              value={telegramBotToken}
              onChange={(e) => setTelegramBotToken(e.target.value)}
            />
          </AetherField>

          {testResult && (
            <AlertBanner
              variant={testResult.valid ? 'success' : 'error'}
              title={testResult.valid ? t('connUiVerificationSucceeded') : t('connUiVerificationFailed2')}
            >
              {testResult.message}
            </AlertBanner>
          )}

          <Panel variant="default" style={{ padding: '12px 14px' }}>
            <Stack direction="row" align="center" justify="between">
              <div>
                <Text size="sm" weight="medium">
                  {t('connUiAdvancedSecuritySettings')}
                </Text>
                <Text size="xs" variant="muted">
                  {t('connUiLimitCommandsToYourSpecificTelegram')}
                </Text>
              </div>
              <Switch checked={telegramAdvOpen} onChange={setTelegramAdvOpen} />
            </Stack>

            {telegramAdvOpen && (
              <div style={{ marginTop: '14px', paddingTop: '12px', borderTop: '1px solid hsl(var(--border))' }}>
                <AetherField label={t('connUiDefaultChatIDOptional')}>
                  <AetherInput
                    placeholder="es. 987654321"
                    value={telegramDefaultChatId}
                    onChange={(e) => setTelegramDefaultChatId(e.target.value)}
                  />
                </AetherField>
              </div>
            )}
          </Panel>
        </AetherForm>
      </Modal>

      {/* =========================================================================
          MODALE 4: CONFIGURAZIONE GENERICA CREDENZIALI (EMAIL, HTTP, OPENAPI)
          ========================================================================= */}
      <Modal
        isOpen={Boolean(configModalProvider)}
        onClose={() => setConfigModalProvider(null)}
        size="md"
        title={t('connUiConfigureNamed').replace('{name}', configModalProvider?.name || t('connUiServiceWord'))}
        description={t('connUiEnterTheConnectionDetailsToEnable')}
        footer={
          <AetherFormActions align="between">
            <Button
              variant="outline"
              size="sm"
              loading={testingCreds}
              onClick={handleTestCreds}
            >
              {t('connUiTestConnection')}
            </Button>
            <Stack direction="row" gap="sm">
              <Button variant="ghost" onClick={() => setConfigModalProvider(null)}>
                {t('cancel')}
              </Button>
              <Button
                variant="primary"
                loading={savingCreds}
                onClick={handleSaveAndConnect}
              >
                {t('connUiSaveAndActivate')}
              </Button>
            </Stack>
          </AetherFormActions>
        }
      >
        <AetherForm onSubmit={handleSaveAndConnect}>
          <AetherField label={t('connUiReferenceAccountName')}>
            <AetherInput
              value={credAccountName}
              onChange={(e) => setCredAccountName(e.target.value)}
            />
          </AetherField>

          {configModalProvider?.id === 'email' && (
            <Stack direction="column" gap="md">
              <AetherField label={t('connUiSMTPServer')} required>
                <AetherInput
                  placeholder="smtp.gmail.com"
                  value={emailHost}
                  onChange={(e) => setEmailHost(e.target.value)}
                />
              </AetherField>

              <Grid cols={2} gap="md">
                <AetherField label={t('connUiPort')} required>
                  <AetherInput
                    placeholder="587"
                    value={emailPort}
                    onChange={(e) => setEmailPort(e.target.value)}
                  />
                </AetherField>
                <AetherField label={t('connUiSenderAddress')}>
                  <AetherInput
                    placeholder={t('connUiNameDomainCom')}
                    value={emailSenderAddr}
                    onChange={(e) => setEmailSenderAddr(e.target.value)}
                  />
                </AetherField>
              </Grid>

              <AetherField label={t('connUiUsernameLoginEmail')} required>
                <AetherInput
                  value={emailUser}
                  onChange={(e) => setEmailUser(e.target.value)}
                />
              </AetherField>

              <AetherField label={t('connUiPasswordOrAppPassword')} required>
                <AetherPasswordInput
                  value={emailPass}
                  onChange={(e) => setEmailPass(e.target.value)}
                />
              </AetherField>
            </Stack>
          )}

          {configModalProvider?.id === 'http' && (
            <Stack direction="column" gap="md">
              <AetherField label={t('connUiEndpointBaseURL')} required>
                <AetherInput
                  placeholder={t('connUiHttpsApiExampleComV1')}
                  value={httpBaseUrl}
                  onChange={(e) => setHttpBaseUrl(e.target.value)}
                />
              </AetherField>

              <AetherField label={t('connUiAuthenticationType')}>
                <AetherSelect
                  value={httpAuthType}
                  onChange={(e) => setHttpAuthType(e.target.value)}
                  options={[
                    { value: 'none', label: t('connUiNoAuthentication') },
                    { value: 'bearer', label: 'Bearer Token' },
                    { value: 'api_key', label: 'Header API Key (X-Api-Key)' },
                  ]}
                />
              </AetherField>

              {httpAuthType !== 'none' && (
                <AetherField label={t('connUiTokenOrSecretKey')} required>
                  <AetherPasswordInput
                    value={httpToken}
                    onChange={(e) => setHttpToken(e.target.value)}
                  />
                </AetherField>
              )}
            </Stack>
          )}

          {configModalProvider?.id === 'openapi' && (
            <Stack direction="column" gap="md">
              <AetherField label={t('connUiOpenAPISpecificationURLJSONYAML')}>
                <AetherInput
                  placeholder={t('connUiHttpsApiServiceComOpenapiJson')}
                  value={openapiSpecUrl}
                  onChange={(e) => setOpenapiSpecUrl(e.target.value)}
                />
              </AetherField>

              <AetherField label={t('connUiOrLocalFilePath')}>
                <AetherInput
                  placeholder={t('connUiUsersNameProjectsSpecYaml')}
                  value={openapiSpecPath}
                  onChange={(e) => setOpenapiSpecPath(e.target.value)}
                />
              </AetherField>
            </Stack>
          )}

          {testResult && (
            <AlertBanner
              variant={testResult.valid ? 'success' : 'error'}
              title={testResult.valid ? t('connUiTestPassed') : t('connUiTestFailed')}
            >
              {testResult.message}
            </AlertBanner>
          )}
        </AetherForm>
      </Modal>

      {/* =========================================================================
          MODALE 5: NUOVO APPUNTAMENTO CALENDARIO
          ========================================================================= */}
      <Modal
        isOpen={isEventModalOpen}
        onClose={() => setIsEventModalOpen(false)}
        size="md"
        title={t('connUiCreateNewAppointment')}
        description={
          selectedScheduleSource === 'google'
            ? t('connUiTheEventWillBeSyncedDirectly')
            : t('connUiTheEventWillBeStoredIn')
        }
        footer={
          <AetherFormActions>
            <Button variant="ghost" onClick={() => setIsEventModalOpen(false)}>
              {t('cancel')}
            </Button>
            <Button
              variant="primary"
              loading={creatingEvent}
              onClick={handleCreateEvent}
            >
              {t('connUiCreateEvent')}
            </Button>
          </AetherFormActions>
        }
      >
        <AetherForm onSubmit={handleCreateEvent}>
          <AetherField label={t('connUiAppointmentTitle')} required>
            <AetherInput
              placeholder={t('connUiEGWeeklyProjectAlignment')}
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
            />
          </AetherField>

          <AetherField label={t('connUiStartDateAndTime')} required>
            <AetherInput
              type="datetime-local"
              value={newStartTime}
              onChange={(e) => setNewStartTime(e.target.value)}
            />
          </AetherField>

          <AetherField label={t('connUiLocationOrMeetingLinkOptional')}>
            <AetherInput
              placeholder={t('connUiEGGoogleMeetMilanOffice')}
              value={newLocation}
              onChange={(e) => setNewLocation(e.target.value)}
            />
          </AetherField>
        </AetherForm>
      </Modal>

      {/* =========================================================================
          MODALE 6: SELETTORE CALENDARIO GOOGLE ATTIVO
          ========================================================================= */}
      <Modal
        isOpen={isCalendarPickerOpen}
        onClose={() => setIsCalendarPickerOpen(false)}
        size="md"
        title={t('connUiSelectGoogleCalendar')}
        description={t('connUiChooseWhichOfYourGoogleCalendars')}
      >
        <Stack direction="column" gap="sm">
          {googleCalendars.map((cal) => (
            <Panel
              key={cal.id}
              variant="default"
              className="ds-panel--interactive"
              onClick={() => handleSelectCalendar(cal.id, cal.summary)}
            >
              <Stack direction="row" justify="between" align="center">
                <div>
                  <Text weight="semibold">{cal.summary}</Text>
                  {cal.description && (
                    <Text size="xs" variant="muted">
                      {cal.description}
                    </Text>
                  )}
                </div>
                {cal.primary && (
                  <StatusBadge status="connected" label={t('connUiPrimary')} />
                )}
              </Stack>
            </Panel>
          ))}
        </Stack>
      </Modal>

      {/* =========================================================================
          DRAWER: GESTISCI SERVIZIO COLLEGATO
          ========================================================================= */}
      <Drawer
        isOpen={Boolean(manageProvider)}
        onClose={() => setManageProvider(null)}
        title={manageProvider?.name}
        description={t('connUiDetailsAndManagementOfTheActive')}
        footer={
          <AetherFormActions align="between">
            <Button
              variant="destructive"
              size="sm"
              onClick={() => {
                if (manageProvider) {
                  setDisconnectTarget({ id: manageProvider.id, name: manageProvider.name });
                }
              }}
              leftIcon={<Trash2 size={14} />}
            >
              {t('connUiDisconnectService')}
            </Button>
            <Button variant="secondary" size="sm" onClick={() => setManageProvider(null)}>
              {t('close')}
            </Button>
          </AetherFormActions>
        }
      >
        {manageProvider && (() => {
          const conn = connections.find((c) => c.provider === manageProvider.id);

          return (
            <Stack direction="column" gap="lg">
              {/* Header card with status */}
              <Panel variant="default" style={{ padding: '16px' }}>
                <Stack direction="row" justify="between" align="center">
                  <Stack gap="none">
                    <Text size="xs" variant="muted">{t('connUiOperationalStatus')}</Text>
                    <Heading level={4}>{conn?.account_name || manageProvider.name}</Heading>
                  </Stack>
                  <StatusBadge status={conn?.status || 'NOT_CONFIGURED'} />
                </Stack>
              </Panel>

              {/* Capabilities checklist */}
              <div>
                <Heading level={5} style={{ marginBottom: '8px' }}>
                  {t('connUiCapabilitiesGrantedToAether')}
                </Heading>
                <Stack direction="column" gap="xs">
                  {manageProvider.capabilitiesList.map((cap, i) => (
                    <div
                      key={i}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        fontSize: '13px',
                        color: 'hsl(var(--fg))',
                      }}
                    >
                      <CheckCircle2 size={15} color="hsl(var(--success))" />
                      <span>{cap}</span>
                    </div>
                  ))}
                </Stack>
              </div>

              {/* Live probe action */}
              <Panel variant="default" style={{ padding: '14px' }}>
                <Stack direction="row" justify="between" align="center">
                  <div>
                    <Text size="sm" weight="medium">{t('connUiIntegrityCheck')}</Text>
                    <Text size="xs" variant="muted">
                      {t('connUiSendARealPingToValidate')}
                    </Text>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    loading={verifyingProvider === manageProvider.id}
                    onClick={() => handleVerifyConnection(manageProvider.id)}
                  >
                    {t('connUiVerifyNow')}
                  </Button>
                </Stack>
              </Panel>

              {/* Advanced info toggle */}
              <Panel variant="default" style={{ padding: '12px 14px' }}>
                <Stack direction="row" justify="between" align="center">
                  <Text size="xs" variant="muted">{t('connUiAdvancedTechnicalDetails')}</Text>
                  <Switch checked={showTechDetails} onChange={setShowTechDetails} />
                </Stack>

                {showTechDetails && conn && (
                  <div style={{ marginTop: '12px', paddingTop: '10px', borderTop: '1px solid hsl(var(--border))' }}>
                    <Text size="xs" mono style={{ wordBreak: 'break-all' }}>
                      {t('connUiInternalId')}: {conn.id}
                      <br />
                      {t('connUiLastSync')}: {conn.last_synced_at || t('connUiNever')}
                      <br />
                      {t('connUiLastVerify')}: {conn.last_verified_at || t('connUiNever')}
                    </Text>
                  </div>
                )}
              </Panel>
            </Stack>
          );
        })()}
      </Drawer>

      {/* =========================================================================
          MODALE: CONFERMA DISCONNESSIONE
          ========================================================================= */}
      <Modal
        isOpen={Boolean(disconnectTarget)}
        onClose={() => setDisconnectTarget(null)}
        size="sm"
        title={t('connUiDisconnectTheService')}
        description={t('connUiDisconnectConfirm').replace('{name}', disconnectTarget?.name ?? '')}
        footer={
          <AetherFormActions>
            <Button variant="ghost" onClick={() => setDisconnectTarget(null)}>
              {t('cancel')}
            </Button>
            <Button
              variant="destructive"
              loading={disconnecting}
              onClick={confirmDisconnect}
            >
              {t('connUiDisconnectPermanently')}
            </Button>
          </AetherFormActions>
        }
      >
        <AlertBanner variant="warning" title={t('connUiWarning')}>
          {t('connUiAnySavedCredentialsAndTokensWill')}
        </AlertBanner>
      </Modal>
    </PageContainer>
  );
}
