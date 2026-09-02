/**
 * Frontend logging abstraction for Rebutio.
 * Captures user flows, state transitions, API failures, media permissions,
 * and correlates with backend request IDs WITHOUT logging audio or speech data.
 */

type LogLevel = "debug" | "info" | "warn" | "error";

interface LogContext {
  [key: string]: any;
}

const SENSITIVE_FRONTEND_KEYS = new Set([
  "audio",
  "blob",
  "clip",
  "transcript",
  "userturn",
  "opponentturn",
  "phonemes",
  "languagefeedback",
  "text",
]);

function sanitizeContext(ctx?: LogContext): LogContext | undefined {
  if (!ctx) return undefined;
  const clean: LogContext = {};
  for (const [k, v] of Object.entries(ctx)) {
    const low = k.toLowerCase();
    if (SENSITIVE_FRONTEND_KEYS.has(low)) {
      clean[k] = "[REDACTED_CONTENT]";
    } else if (v instanceof Blob || (typeof v === "object" && v !== null && "size" in v && "type" in v)) {
      clean[k] = `[BLOB type=${(v as any).type} size=${(v as any).size}]`;
    } else if (typeof v === "object" && v !== null && !Array.isArray(v)) {
      clean[k] = sanitizeContext(v);
    } else {
      clean[k] = v;
    }
  }
  return clean;
}

class FrontendLogger {
  private lastRequestId: string | null = null;
  private isDev = typeof process !== "undefined" && process.env.NODE_ENV !== "production";

  public setRequestId(requestId: string | null) {
    if (requestId) {
      this.lastRequestId = requestId;
    }
  }

  public getRequestId(): string | null {
    return this.lastRequestId;
  }

  public debug(event: string, context?: LogContext) {
    if (!this.isDev) return;
    const sanitized = sanitizeContext(context);
    console.debug(`%c[DEBUG] ${event}`, "color: #888888", {
      ...sanitized,
      requestId: this.lastRequestId ?? undefined,
    });
  }

  public info(event: string, context?: LogContext) {
    if (!this.isDev) return;
    const sanitized = sanitizeContext(context);
    console.info(`%c[INFO] ${event}`, "color: #127a63; font-weight: bold", {
      ...sanitized,
      requestId: this.lastRequestId ?? undefined,
    });
  }

  public warn(event: string, context?: LogContext) {
    const sanitized = sanitizeContext(context);
    console.warn(`[WARN] ${event}`, {
      ...sanitized,
      requestId: this.lastRequestId ?? undefined,
    });
  }

  public error(event: string, context?: LogContext, error?: any) {
    const sanitized = sanitizeContext(context);
    const errDetails = error instanceof Error
      ? {
          name: error.name,
          message: error.message,
          stack: error.stack,
          status: (error as Error & { status?: number }).status,
          requestId: (error as Error & { requestId?: string }).requestId,
        }
      : error;
    console.error(`[ERROR] ${event}`, {
      ...sanitized,
      ...(errDetails !== undefined ? { error: errDetails } : {}),
      requestId: this.lastRequestId ?? undefined,
    });
  }
}

export const logger = new FrontendLogger();
