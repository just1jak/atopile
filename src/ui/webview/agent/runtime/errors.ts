import { isLocalMode } from "../../common/localAgent";
export type AgentErrorKind =
  | 'out_of_credit'
  | 'sign_in'
  | 'too_large'
  | 'rate_limit'
  | 'generic';

export interface AgentError {
  kind: AgentErrorKind;
  message: string;
  /** When false, the UI auto-dismisses after a short timeout. */
  persistent: boolean;
}

export function sanitizeAgentError(err: unknown): AgentError {
  const raw =
    err instanceof Error ? err.message
    : typeof err === 'string' ? err
    : String(err);
  const s = raw.toLowerCase();

  if (/\b402\b|insufficient credit|balance is too low|out of credit/.test(s)) {
    return {
      kind: 'out_of_credit',
      message: isLocalMode ? 'Your AI provider rejected the request for billing or quota reasons. Check that provider account.' : 'Your account is out of credit. Please contact the atopile team to continue.',
      persistent: true,
    };
  }

  if (/\b401\b|authentication failed|authentication_error|not authenticated|session expired/.test(s)) {
    return {
      kind: 'sign_in',
      message: isLocalMode ? 'Your AI endpoint rejected authentication. Check AI settings and use Set AI API Key.' : 'Your session expired. Sign in again from the sidebar.',
      persistent: true,
    };
  }

  if (/\b413\b|request_too_large|too large/.test(s)) {
    return {
      kind: 'too_large',
      message: 'Your message is too large. Try trimming it or starting a new chat.',
      persistent: false,
    };
  }

  if (/\b429\b|\b529\b|rate[_ -]?limit|overloaded/.test(s)) {
    return {
      kind: 'rate_limit',
      message: 'The agent is busy right now. Please retry in a moment.',
      persistent: false,
    };
  }

  return {
    kind: 'generic',
    message: isLocalMode ? raw.replace(/sk-[\w-]+/g, "[REDACTED]").replace(/Bearer\s+[^\s]+/gi, "Bearer [REDACTED]") : 'Something went wrong on our end. Please try again.',
    persistent: false,
  };
}
