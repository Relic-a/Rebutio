// ============================================================
// Media capture adapter. The debate screen deals in semantic
// events only (recording started/stopped, turn ready, failed).
// Never coupled to MediaRecorder inside components.
// ============================================================

export type CaptureAdapter = {
  /** Pre-permission probe: returns availability without requesting. */
  checkAvailability(): Promise<"available" | "denied" | "unavailable">;
  requestPermission(): Promise<"allowed" | "denied" | "unavailable">;
  startRecording(): Promise<void>;
  stopRecording(): Promise<Blob | null>;
  isRecording(): boolean;
};

class BrowserCapture implements CaptureAdapter {
  private recorder: MediaRecorder | null = null;
  private stream: MediaStream | null = null;
  private chunks: Blob[] = [];

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
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this.stream.getTracks().forEach((t) => t.stop());
      this.stream = null;
      return "allowed";
    } catch (e) {
      const name = (e as DOMException)?.name;
      return name === "NotAllowedError" || name === "SecurityError" ? "denied" : "unavailable";
    }
  }

  async startRecording() {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.chunks = [];
    this.recorder = new MediaRecorder(this.stream);
    this.recorder.ondataavailable = (e) => e.data.size > 0 && this.chunks.push(e.data);
    this.recorder.start();
  }

  async stopRecording(): Promise<Blob | null> {
    return new Promise((resolve) => {
      if (!this.recorder || this.recorder.state === "inactive") return resolve(null);
      this.recorder.onstop = () => {
        const blob = new Blob(this.chunks, { type: this.recorder?.mimeType || "audio/webm" });
        this.stream?.getTracks().forEach((t) => t.stop());
        this.stream = null;
        this.recorder = null;
        resolve(blob);
      };
      this.recorder.stop();
    });
  }

  isRecording() {
    return this.recorder?.state === "recording";
  }
}

export const capture: CaptureAdapter =
  typeof window !== "undefined" && typeof MediaRecorder !== "undefined"
    ? new BrowserCapture()
    : {
        // Graceful fallback: SSR or unsupported browsers get a no-op adapter
        // so the debate flow remains demoable.
        async checkAvailability() { return "unavailable"; },
        async requestPermission() { return "unavailable"; },
        async startRecording() { throw new Error("unavailable"); },
        async stopRecording() { return null; },
        isRecording() { return false; },
      };
