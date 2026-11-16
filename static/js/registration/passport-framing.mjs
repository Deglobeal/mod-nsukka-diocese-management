export const PASSPORT_FRAME_WIDTH = 720;
export const PASSPORT_FRAME_HEIGHT = 900;
export const PASSPORT_FRAME_BACKGROUND = "#10151b";

export function containRect(sourceWidth, sourceHeight, targetWidth = PASSPORT_FRAME_WIDTH, targetHeight = PASSPORT_FRAME_HEIGHT) {
    if ([sourceWidth, sourceHeight, targetWidth, targetHeight].some((value) =>
        !Number.isFinite(value) || value <= 0
    )) return null;

    const scale = Math.min(targetWidth / sourceWidth, targetHeight / sourceHeight);
    const width = sourceWidth * scale;
    const height = sourceHeight * scale;
    return {
        x: (targetWidth - width) / 2,
        y: (targetHeight - height) / 2,
        width,
        height,
        scale
    };
}

export function passportCanvasRenderPlan(sourceWidth, sourceHeight) {
    return {
        width: PASSPORT_FRAME_WIDTH,
        height: PASSPORT_FRAME_HEIGHT,
        frame: containRect(sourceWidth, sourceHeight)
    };
}

export function mapRectToContainFrame(rect, sourceWidth, sourceHeight, targetWidth = PASSPORT_FRAME_WIDTH, targetHeight = PASSPORT_FRAME_HEIGHT) {
    const fit = containRect(sourceWidth, sourceHeight, targetWidth, targetHeight);
    if (!fit || !rect) return null;
    return {
        x: (fit.x + rect.x * fit.scale) / targetWidth,
        y: (fit.y + rect.y * fit.scale) / targetHeight,
        width: (rect.width * fit.scale) / targetWidth,
        height: (rect.height * fit.scale) / targetHeight
    };
}

export function mirrorRectHorizontally(rect, sourceWidth) {
    if (!rect || !Number.isFinite(sourceWidth) || sourceWidth <= 0) return null;
    return { ...rect, x: sourceWidth - rect.x - rect.width };
}

export function getPassportFaceGuidance(face, roll = 0, previous = null) {
    if (!face) return "no-face";
    const centerX = face.x + face.width / 2;
    const centerY = face.y + face.height / 2;

    const tooClose = face.width > 0.43 || face.height > 0.48;
    const stillLeavingCloseZone = face.width > 0.38 || face.height > 0.43;
    if (previous === "farther" ? stillLeavingCloseZone : tooClose) return "farther";

    const tooFar = face.width < 0.14 || face.height < 0.17;
    const stillLeavingFarZone = face.width < 0.18 || face.height < 0.21;
    if (previous === "closer" ? stillLeavingFarZone : tooFar) return "closer";
    if (Number.isFinite(roll) && Math.abs(roll) > 0.18) return "straight";
    if (face.x < 0.16 || centerX < 0.38) return "right";
    if (face.x + face.width > 0.84 || centerX > 0.62) return "left";
    if (face.y < 0.04 || centerY < 0.20) return "down";
    if (face.y + face.height > 0.50 || centerY > 0.38) return "up";
    return "ready";
}

export function nextFacingMode(current) {
    return current === "environment" ? "user" : "environment";
}

export function stopMediaTracks(stream) {
    if (!stream || typeof stream.getTracks !== "function") return;
    stream.getTracks().forEach((track) => {
        if (track && typeof track.stop === "function") track.stop();
    });
}

export function cameraConstraintFallbacks(facingMode) {
    const preferredVideo = {
        facingMode: { ideal: facingMode },
        width: { ideal: 720 },
        height: { ideal: 1280 },
        aspectRatio: { ideal: 9 / 16 }
    };
    return [
        {
            audio: false,
            video: preferredVideo
        },
        { audio: false, video: { facingMode: { ideal: facingMode } } },
        { audio: false, video: true }
    ];
}

export function minimumSupportedZoom(capabilities) {
    const zoom = capabilities && capabilities.zoom;
    if (!zoom || !Number.isFinite(zoom.min) || !Number.isFinite(zoom.max) || zoom.max < zoom.min) {
        return null;
    }
    return zoom.min;
}

export function selectWideCameraDevice(devices, facingMode, currentDeviceId = "") {
    if (!Array.isArray(devices)) return null;
    const directionPattern = facingMode === "user"
        ? /front|user|selfie/i
        : /rear|back|environment/i;
    const widePattern = /ultra[ -]?wide|\bwide\b|0\.5\s*x/i;
    const telePattern = /telephoto|tele[ -]?photo|zoom|2\s*x|3\s*x/i;
    const candidates = devices.filter((device) =>
        device && device.kind === "videoinput" && device.deviceId &&
        device.deviceId !== currentDeviceId && directionPattern.test(device.label || "")
    );
    const wideCandidates = candidates.filter((device) => widePattern.test(device.label || ""));
    const currentCamera = devices.find((device) => device && device.deviceId === currentDeviceId);
    // Prefer a camera explicitly identified as wide. Otherwise leave selection
    // to the browser's facingMode preference instead of guessing by device order.
    const labelledWide = wideCandidates.find((device) => !telePattern.test(device.label || ""));
    if (labelledWide) return labelledWide;
    if (currentCamera && telePattern.test(currentCamera.label || "")) {
        return candidates.find((device) => !telePattern.test(device.label || "")) || null;
    }
    return null;
}
