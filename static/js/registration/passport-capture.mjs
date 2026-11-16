export const CAPTURE_STABILITY_MS = 1500;

const VOICE_COMMANDS = new Map([
    ["start camera", "start-camera"],
    ["take photo", "take-photo"],
    ["retake photo", "retake-photo"],
    ["capture passport", "capture-passport"],
    ["stop camera", "stop-camera"],
    ["repeat instructions", "repeat-instructions"]
]);

export function parseVoiceCommand(transcript) {
    if (typeof transcript !== "string") return null;
    const normalized = transcript
        .trim()
        .toLocaleLowerCase()
        .replace(/[.!?,;:]+$/g, "")
        .replace(/\s+/g, " ");
    return VOICE_COMMANDS.get(normalized) || null;
}

export function supportsOnDeviceRecognition(Recognition) {
    return typeof Recognition === "function" &&
        "processLocally" in Recognition.prototype;
}

export class VoiceCommandDeduplicator {
    constructor(cooldownMs = 1800) {
        this.cooldownMs = cooldownMs;
        this.lastCommand = null;
        this.lastAt = -Infinity;
    }

    accept(command, now) {
        if (!command) return false;
        if (command === this.lastCommand && now - this.lastAt < this.cooldownMs) {
            return false;
        }
        this.lastCommand = command;
        this.lastAt = now;
        return true;
    }
}

export class VoiceCommandGate {
    constructor(cooldownMs = 1800) {
        this.enabled = false;
        this.deduplicator = new VoiceCommandDeduplicator(cooldownMs);
    }

    enable() { this.enabled = true; }
    disable() { this.enabled = false; }

    accept(transcript, now) {
        if (!this.enabled) return null;
        const command = parseVoiceCommand(transcript);
        return this.deduplicator.accept(command, now) ? command : null;
    }
}

export function voiceCaptureAllowed(command, eligible) {
    return (command === "take-photo" || command === "capture-passport") &&
        eligible === true;
}

export function isFatalVoiceRecognitionError(error) {
    return [
        "not-allowed",
        "service-not-allowed",
        "language-not-supported",
        "audio-capture"
    ].includes(error);
}

export function voiceRecognitionErrorMessage(error) {
    if (error === "not-allowed" || error === "service-not-allowed") {
        return "Microphone permission was denied. Use the camera buttons instead.";
    }
    if (error === "language-not-supported") {
        return "An on-device language pack is unavailable. Use the camera buttons instead.";
    }
    if (error === "audio-capture") {
        return "A microphone is unavailable. Use the camera buttons instead.";
    }
    return "Voice recognition stopped. Camera buttons remain available.";
}

export function isCaptureEligible({
    faceCount,
    positioned,
    livenessPassed,
    facingForward,
    glassesCheckPassed,
    lightingAdequate,
    stableForMs,
    captureInProgress
}) {
    return faceCount === 1 && positioned === true &&
        livenessPassed === true && facingForward === true &&
        glassesCheckPassed === true && lightingAdequate === true &&
        Number.isFinite(stableForMs) && stableForMs >= CAPTURE_STABILITY_MS &&
        captureInProgress !== true;
}

export class AutoCaptureCountdown {
    constructor(durationMs = 3000) {
        this.durationMs = durationMs;
        this.dueAt = null;
        this.fired = false;
    }

    cancel() {
        this.dueAt = null;
        this.fired = false;
    }

    update(eligible, enabled, now) {
        if (!eligible || !enabled) {
            this.cancel();
            return { state: enabled ? "waiting" : "manual" };
        }
        if (this.fired) return { state: "fired" };
        if (this.dueAt === null) this.dueAt = now + this.durationMs;
        const remainingMs = Math.max(0, this.dueAt - now);
        if (remainingMs === 0) {
            this.fired = true;
            return { state: "capture", seconds: 0 };
        }
        return {
            state: "countdown",
            seconds: Math.ceil(remainingMs / 1000)
        };
    }
}
