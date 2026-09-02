// ============================================================
// Media capture adapter. The debate screen deals in semantic
// events only (recording started/stopped, turn ready, failed).
// Never coupled to MediaRecorder inside components.
// ============================================================

export type CaptureAdapter = {
  /** Pre-permission probe: returns availability without requesting. */
  checkAvailability(): Promise<"available" | "denied" | "unavailable">;
  requestPermission(): Promise<"allowed" | "denied" | "unavailable">;
  warmup?(): Promise<void>;
  release?(): Promise<void>;
  startRecording(): Promise<void>;
  stopRecording(): Promise<Blob | null>;
  cancelRecording(): Promise<void>;
  isRecording(): boolean;

  // Semantic convenience aliases
  start(): Promise<void>;
  stop(): Promise<{ blob: Blob } | null>;
  cancel(): Promise<void>;
};

class BrowserCapture implements CaptureAdapter {
  private recorder: MediaRecorder | null = null;
  private stream: MediaStream | null = null;
  private chunks: Blob[] = [];

  private getActiveStream(): MediaStream | null {
    if (this.stream) {
      const activeTracks = this.stream.getAudioTracks().filter((t) => t.readyState === "live");
      if (activeTracks.length > 0) {
        return this.stream;
      }
    }
    return null;
  }

  async checkAvailability(): Promise<"available" | "denied" | "unavailable"> {
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) return "unavailable";
    try {
      const perm = await navigator.permissions?.query({ name: "microphone" as PermissionName });
      if (perm?.state === "denied") return "denied";
      return "available";
    } catch {
      return "available";
    }
  }

  async requestPermission(): Promise<"allowed" | "denied" | "unavailable"> {
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) return "unavailable";
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this.stream = stream;
      return "allowed";
    } catch (e) {
      const name = (e as DOMException)?.name;
      return name === "NotAllowedError" || name === "SecurityError" ? "denied" : "unavailable";
    }
  }

  async warmup(): Promise<void> {
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) return;
    if (!this.getActiveStream()) {
      try {
        this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch {
        // Non-blocking warmup
      }
    }
  }

  async release(): Promise<void> {
    if (this.recorder && this.recorder.state !== "inactive") {
      try {
        this.recorder.stop();
      } catch {}
    }
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.recorder = null;
    this.chunks = [];
  }

  async startRecording() {
    let stream = this.getActiveStream();
    if (!stream) {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this.stream = stream;
    }
    this.chunks = [];
    this.recorder = new MediaRecorder(stream);
    this.recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) {
        this.chunks.push(e.data);
      }
    };
    this.recorder.start(100);
  }

  async stopRecording(): Promise<Blob | null> {
    return new Promise((resolve) => {
      if (!this.recorder || this.recorder.state === "inactive") return resolve(null);
      const rec = this.recorder;
      rec.onstop = () => {
        const mime = rec.mimeType || "audio/webm";
        const blob = new Blob(this.chunks, { type: mime });
        // Stream remains open for subsequent turns to prevent device re-init latency
        this.recorder = null;
        resolve(blob);
      };
      rec.stop();
    });
  }

  async cancelRecording(): Promise<void> {
    if (this.recorder && this.recorder.state !== "inactive") {
      try {
        this.recorder.stop();
      } catch {}
    }
    this.recorder = null;
    this.chunks = [];
  }

  isRecording() {
    return this.recorder?.state === "recording";
  }

  async start() {
    return this.startRecording();
  }

  async stop() {
    const blob = await this.stopRecording();
    return blob ? { blob } : null;
  }

  async cancel() {
    return this.cancelRecording();
  }
}

export const capture: CaptureAdapter =
  typeof window !== "undefined" && typeof MediaRecorder !== "undefined"
    ? new BrowserCapture()
    : {
        async checkAvailability() { return "unavailable"; },
        async requestPermission() { return "unavailable"; },
        async warmup() {},
        async release() {},
        async startRecording() { throw new Error("unavailable"); },
        async stopRecording() { return null; },
        async cancelRecording() {},
        isRecording() { return false; },
        async start() { throw new Error("unavailable"); },
        async stop() { return null; },
        async cancel() {},
      };
