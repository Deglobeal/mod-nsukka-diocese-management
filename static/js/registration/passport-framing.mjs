export const PASSPORT_FRAME_WIDTH = 720;
export const PASSPORT_FRAME_HEIGHT = 900;

export function coverRect(sourceWidth, sourceHeight, targetWidth = PASSPORT_FRAME_WIDTH, targetHeight = PASSPORT_FRAME_HEIGHT) {
    if ([sourceWidth, sourceHeight, targetWidth, targetHeight].some((value) =>
        !Number.isFinite(value) || value <= 0
    )) return null;

    const targetAspect = targetWidth / targetHeight;
    let x = 0;
    let y = 0;
    let width = sourceWidth;
    let height = sourceHeight;
    if (sourceWidth / sourceHeight > targetAspect) {
        width = sourceHeight * targetAspect;
        x = (sourceWidth - width) / 2;
    } else {
        height = sourceWidth / targetAspect;
        y = (sourceHeight - height) / 2;
    }
    return {
        x,
        y,
        width,
        height,
        scale: targetWidth / width
    };
}

export function passportCanvasRenderPlan(sourceWidth, sourceHeight) {
    return {
        width: PASSPORT_FRAME_WIDTH,
        height: PASSPORT_FRAME_HEIGHT,
        frame: coverRect(sourceWidth, sourceHeight)
    };
}

export function mapRectToCoverFrame(rect, sourceWidth, sourceHeight, targetWidth = PASSPORT_FRAME_WIDTH, targetHeight = PASSPORT_FRAME_HEIGHT) {
    const crop = coverRect(sourceWidth, sourceHeight, targetWidth, targetHeight);
    if (!crop || !rect) return null;
    return {
        x: (rect.x - crop.x) / crop.width,
        y: (rect.y - crop.y) / crop.height,
        width: rect.width / crop.width,
        height: rect.height / crop.height
    };
}

export function getPassportFaceGuidance(face) {
    if (!face) return "no-face";
    const centerX = face.x + face.width / 2;
    const centerY = face.y + face.height / 2;

    if (face.width < 0.14 || face.height < 0.18) return "closer";
    if (face.width > 0.40 || face.height > 0.46) return "farther";
    if (face.x < 0.16 || centerX < 0.38) return "right";
    if (face.x + face.width > 0.84 || centerX > 0.62) return "left";
    if (face.y < 0.04 || centerY < 0.20) return "down";
    if (face.y + face.height > 0.50 || centerY > 0.38) return "up";
    return "ready";
}

export function nextFacingMode(current) {
    return current === "environment" ? "user" : "environment";
}

export function cameraConstraintFallbacks(facingMode) {
    return [
        {
            audio: false,
            video: {
                facingMode: { ideal: facingMode },
                width: { ideal: 720 },
                height: { ideal: 1280 }
            }
        },
        { audio: false, video: { facingMode: { ideal: facingMode } } },
        { audio: false, video: true }
    ];
}
