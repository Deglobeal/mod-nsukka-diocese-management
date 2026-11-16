import { getFaceMeasurements, isForwardFacing, LivenessSession } from "./passport-liveness.mjs?v=2";
import {
    cameraConstraintFallbacks,
    getPassportFaceGuidance,
    mapRectToContainFrame,
    mirrorRectHorizontally,
    minimumSupportedZoom,
    nextFacingMode,
    passportCanvasRenderPlan,
    selectWideCameraDevice,
    PASSPORT_FRAME_BACKGROUND,
    stopMediaTracks
} from "./passport-framing.mjs?v=3";
import {
    AutoCaptureCountdown,
    CAPTURE_STABILITY_MS,
    isCaptureEligible
} from "./passport-capture.mjs?v=2";

document.addEventListener("DOMContentLoaded", function () {
    const video = document.getElementById("passport-camera-video");
    const photoCanvas = document.getElementById("passport-camera-canvas");
    const whiteScanStatus = document.getElementById("passport-white-scan-status");
    const photoInput = document.getElementById("passport-photo-data");
    const photoTokenInput = document.getElementById("passport-photo-token");
    const acceptPhotoButton = document.getElementById("passport-camera-accept");
    const photoPreview = document.getElementById("passport-camera-image");
    const cameraGuide = document.querySelector(".registration-camera-guide");
    let pendingPhotoData = "";
    let pendingPhotoToken = "";
    let previewRequestId = 0;
    const photoPlaceholder = document.getElementById("passport-camera-placeholder");
    const startCameraButton = document.getElementById("passport-camera-start");
    const cameraSwitchButton = document.getElementById("passport-camera-switch");
    const capturePhotoButton = document.getElementById("passport-camera-capture");
    const retakePhotoButton = document.getElementById("passport-camera-retake");
    const cameraStatus = document.getElementById("passport-camera-status");
    const cameraError = document.getElementById("passport-camera-error");
    const autoCaptureInput = document.getElementById("passport-auto-capture");
    const countdownStatus = document.getElementById("passport-capture-countdown");
    const registrationForm = document.querySelector(".registration-card form");
    let cameraStream = null;
    let requestedFacingMode = "user";
    let faceLandmarker = null;
    let faceLandmarkerLoading = null;
    let livenessSession = null;
    // Client-side challenge state gates the camera UI; it is not server proof of physical presence.
    let livenessPassed = false;
    let glassesCheckPassed = false;
    let glassesDetector = null;
    let glassesDetectionLoading = null;
    let accessoryCheckInProgress = false;

    let faceScanFrame = null;
    let faceStableSince = null;
    let lastFaceScanAt = 0;
    let previousFaceBox = null;
    let previousFaceGuidance = null;
    let photoCaptureInProgress = false;
    let captureAttempts = 0;
    let captureRetryTimer = null;
    let lightingCanvas = null;
    let lightingContext = null;
    let lightingAdequate = false;
    let lastLightingCheckAt = -Infinity;
    let latestCaptureChecks = null;
    let latestCaptureEligible = false;
    const autoCaptureCountdown = new AutoCaptureCountdown(3000);

    const MAX_CAPTURE_ATTEMPTS = 4;
    const CAPTURE_RETRY_DELAY_MS = 900;

    // passport-face-auto-detection
    const FACE_STABILITY_MS = CAPTURE_STABILITY_MS;
    const FACE_SCAN_INTERVAL_MS = 100;
    // Official MediaPipe Face Landmarker task asset (~3.6 MB, Apache 2.0).
    const FACE_LANDMARKER_MODEL_URL =
        "https://storage.googleapis.com/mediapipe-models/" +
        "face_landmarker/face_landmarker/float16/1/face_landmarker.task";

    function stopFaceScan() {
        if (faceScanFrame !== null) {
            cancelAnimationFrame(faceScanFrame);
            faceScanFrame = null;
        }
        faceStableSince = null;
        previousFaceBox = null;
        previousFaceGuidance = null;
    }

    function secureRandom() {
        const value = new Uint32Array(1);
        crypto.getRandomValues(value);
        return value[0] / 0x100000000;
    }

    function updateLighting(timestamp, faceBox) {
        if (timestamp - lastLightingCheckAt < 250) return lightingAdequate;
        lastLightingCheckAt = timestamp;
        try {
            if (!lightingCanvas) {
                lightingCanvas = document.createElement("canvas");
                lightingCanvas.width = 24;
                lightingCanvas.height = 24;
                lightingContext = lightingCanvas.getContext("2d", { willReadFrequently: true });
            }
            const left = Math.max(0, faceBox.originX);
            const top = Math.max(0, faceBox.originY);
            const width = Math.min(video.videoWidth - left, faceBox.width);
            const height = Math.min(video.videoHeight - top, faceBox.height);
            if (width <= 0 || height <= 0) return false;
            lightingContext.drawImage(
                video, left, top, width, height, 0, 0, 24, 24
            );
            const pixels = lightingContext.getImageData(0, 0, 24, 24).data;
            let luminanceTotal = 0;
            for (let index = 0; index < pixels.length; index += 4) {
                luminanceTotal += 0.2126 * pixels[index] +
                    0.7152 * pixels[index + 1] + 0.0722 * pixels[index + 2];
            }
            lightingAdequate = luminanceTotal / (pixels.length / 4) >= 38;
        } catch (error) {
            lightingAdequate = false;
        }
        return lightingAdequate;
    }

    let cameraStartRequestId = 0;

    function stopCamera() {
        cameraStartRequestId += 1;
        stopFaceScan();
        autoCaptureCountdown.cancel();
        latestCaptureEligible = false;
        latestCaptureChecks = null;
        if (countdownStatus) countdownStatus.hidden = true;
        if (captureRetryTimer !== null) {
            clearTimeout(captureRetryTimer);
            captureRetryTimer = null;
        }

        if (cameraStream) {
            stopMediaTracks(cameraStream);
            cameraStream = null;
        }
        if (video) {
            video.srcObject = null;
            video.hidden = true;
        }
        if (cameraGuide) delete cameraGuide.dataset.state;
        if (photoPlaceholder && (!photoPreview || photoPreview.hidden)) {
            photoPlaceholder.hidden = false;
        }
        if (capturePhotoButton) capturePhotoButton.disabled = true;
        if (startCameraButton) startCameraButton.textContent = "Start camera";
        document.body.classList.remove("passport-camera-stage-open");
    }

    function clearCapturedPhoto() {
        previewRequestId += 1;
        photoCaptureInProgress = false;
        latestCaptureEligible = false;
        latestCaptureChecks = null;
        autoCaptureCountdown.cancel();
        if (countdownStatus) countdownStatus.hidden = true;
        pendingPhotoData = "";
        pendingPhotoToken = "";
        if (photoInput) photoInput.value = "";
        if (photoTokenInput) photoTokenInput.value = "";
        if (photoPreview) {
            photoPreview.removeAttribute("src");
            photoPreview.hidden = true;
            photoPreview.parentElement.classList.remove("is-reviewing");
        }
        if (photoPlaceholder) photoPlaceholder.hidden = false;
        if (acceptPhotoButton) acceptPhotoButton.hidden = true;
        if (retakePhotoButton) retakePhotoButton.hidden = true;
        if (retakePhotoButton) retakePhotoButton.textContent = "Retake photo";
        if (cameraStatus) cameraStatus.textContent = "Start the camera to begin your photo check.";
    }


    async function loadFaceLandmarker() {
        if (faceLandmarker) return faceLandmarker;
        if (faceLandmarkerLoading) return faceLandmarkerLoading;

        faceLandmarkerLoading = (async function () {
            const vision = await import(
                "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/+esm"
            );

            const files = await vision.FilesetResolver.forVisionTasks(
                "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm"
            );

            faceLandmarker = await vision.FaceLandmarker.createFromOptions(
                files,
                {
                    baseOptions: {
                        modelAssetPath: FACE_LANDMARKER_MODEL_URL
                    },
                    runningMode: "VIDEO",
                    numFaces: 2,
                    minFaceDetectionConfidence: 0.65,
                    minFacePresenceConfidence: 0.65,
                    minTrackingConfidence: 0.65,
                    outputFaceBlendshapes: false
                }
            );

            return faceLandmarker;
        })();

        try {
            return await faceLandmarkerLoading;
        } catch (error) {
            faceLandmarkerLoading = null;
            throw error;
        }
    }

    async function loadGlassesDetector() {
        if (glassesDetector) return glassesDetector;
        if (glassesDetectionLoading) return glassesDetectionLoading;

        glassesDetectionLoading = (async function () {
            const module = await import(
                "https://esm.sh/@framefind/core"
            );
            const Detector = module.GlassesDetector;
            if (!Detector) {
                throw new Error("GlassesDetector export was not found.");
            }

            const detector = new Detector({
                threshold: 0.5,
                smoothingWindow: 5,
                preferGpu: false
            });
            await detector.load();
            glassesDetector = detector;
            return detector;
        })();

        try {
            return await glassesDetectionLoading;
        } catch (error) {
            glassesDetectionLoading = null;
            throw error;
        }
    }

    async function checkForGlasses() {
        const detector = await loadGlassesDetector();
        const result = await detector.detectFromVideoFrame(
            video,
            photoCanvas
        );

        if (!result || result.faceDetected !== true) {
            throw new Error(
                "The glasses check could not confirm a visible face."
            );
        }

        return result.glasses === true;
    }

    function getFaceFrameBox(detection) {
        const box = detection && detection.boundingBox;
        if (!box || !video.videoWidth || !video.videoHeight) return null;
        const sourceFaceBox = {
            x: box.originX,
            y: box.originY,
            width: box.width,
            height: box.height
        };
        const displayedFaceBox = requestedFacingMode === "user"
            ? mirrorRectHorizontally(sourceFaceBox, video.videoWidth)
            : sourceFaceBox;
        return mapRectToContainFrame({
            x: displayedFaceBox.x,
            y: displayedFaceBox.y,
            width: displayedFaceBox.width,
            height: displayedFaceBox.height
        }, video.videoWidth, video.videoHeight);
    }

    function faceGuidanceMessage(guidance) {
        const messages = {
            "no-face": "No face detected. Move into view and improve the lighting.",
            closer: requestedFacingMode === "user"
                ? "Move your phone slightly closer to the camera."
                : "Move the camera slightly closer.",
            farther: requestedFacingMode === "user"
                ? "Move your phone slightly farther away so your full head fits."
                : "Move farther away so the full head and shoulders fit.",
            straight: "Keep your head straight and look at the camera.",
            right: "Move your face slightly to your right.",
            left: "Move your face slightly to your left.",
            down: "Move your face slightly down into the guide.",
            up: "Move your face slightly up into the guide.",
            ready: "Perfect positioning. Hold still."
        };
        return messages[guidance] || "Centre your face in the guide.";
    }

    function updateCameraSwitchLabel() {
        if (!cameraSwitchButton) return;
        const nextMode = nextFacingMode(requestedFacingMode);
        cameraSwitchButton.textContent = nextMode === "user"
            ? "Use front camera"
            : "Use rear camera";
        cameraSwitchButton.setAttribute("aria-label", cameraSwitchButton.textContent);
    }

    function faceBoxIsStable(frameBox) {
        if (!frameBox) return false;
        const current = frameBox;
        const previous = previousFaceBox;
        previousFaceBox = current;

        if (!previous) return false;

        return (
            Math.abs(current.x - previous.x) < 0.025 &&
            Math.abs(current.y - previous.y) < 0.025 &&
            Math.abs(current.width - previous.width) < 0.04 &&
            Math.abs(current.height - previous.height) < 0.04
        );
    }

    function scanForFace(timestamp) {
        if (!cameraStream || video.hidden || photoCaptureInProgress || !faceLandmarker) {
            faceScanFrame = null;
            return;
        }

        if (timestamp - lastFaceScanAt >= FACE_SCAN_INTERVAL_MS) {
            lastFaceScanAt = timestamp;
            try {
                const result = faceLandmarker.detectForVideo(video, timestamp);
                const faces = result.faceLandmarks || [];
                const measurements = faces.length === 1
                    ? getFaceMeasurements(faces[0])
                    : null;
                const detection = measurements ? {
                    boundingBox: {
                        originX: measurements.bounds.left * video.videoWidth,
                        originY: measurements.bounds.top * video.videoHeight,
                        width: (measurements.bounds.right - measurements.bounds.left) * video.videoWidth,
                        height: (measurements.bounds.bottom - measurements.bounds.top) * video.videoHeight
                    }
                } : null;
                const frameFaceBox = getFaceFrameBox(detection);
                const faceGuidance = getPassportFaceGuidance(
                    frameFaceBox,
                    measurements ? measurements.roll : null,
                    previousFaceGuidance
                );
                previousFaceGuidance = faceGuidance;
                const positioned = faceGuidance === "ready";
                if (cameraGuide) cameraGuide.dataset.state = faceGuidance;

                if (!livenessPassed) {
                    const faceBox = detection ? {
                        x: detection.boundingBox.originX / video.videoWidth,
                        y: detection.boundingBox.originY / video.videoHeight,
                        width: detection.boundingBox.width / video.videoWidth,
                        height: detection.boundingBox.height / video.videoHeight
                    } : null;
                    const status = livenessSession.step({
                        faceCount: faces.length,
                        positioned,
                        eyeAspect: measurements ? measurements.eyeAspect : null,
                        yaw: measurements ? measurements.yaw : null,
                        faceBox
                    }, timestamp);
                    if (status.state === "complete") {
                        livenessPassed = true;
                        faceStableSince = null;
                        previousFaceBox = null;
                        cameraStatus.textContent =
                            "Liveness checks passed. Face forward and hold still for 1.5 seconds.";
                    } else if (status.state === "timeout") {
                        stopFaceScan();
                        cameraStatus.textContent =
                            "The liveness check timed out. Tap Try again to repeat the checks.";
                        retakePhotoButton.hidden = false;
                        retakePhotoButton.textContent = "Try again";
                        return;
                    } else if (status.state === "multiple-faces") {
                        cameraStatus.textContent = "Only one person should be visible. Please try again.";
                    } else if (status.state === "no-face") {
                        cameraStatus.textContent = "No face detected. Move into view and improve the lighting.";
                    } else if (status.state === "position") {
                        cameraStatus.textContent = faceGuidanceMessage(faceGuidance);
                    } else if (status.challenge === "blink") {
                        cameraStatus.textContent =
                            `Liveness check ${status.step} of ${status.total}: Blink naturally, then open your eyes.`;
                    } else if (status.challenge === "turn-left") {
                        const screenSide = requestedFacingMode === "user" ? "right" : "left";
                        cameraStatus.textContent =
                            `Liveness check ${status.step} of ${status.total}: Slowly turn your nose toward the ${screenSide} side of the screen, then face forward.`;
                    } else if (status.challenge === "turn-right") {
                        const screenSide = requestedFacingMode === "user" ? "left" : "right";
                        cameraStatus.textContent =
                            `Liveness check ${status.step} of ${status.total}: Slowly turn your nose toward the ${screenSide} side of the screen, then face forward.`;
                    } else {
                        cameraStatus.textContent = "Hold your face steady while checks begin…";
                    }
                    faceScanFrame = requestAnimationFrame(scanForFace);
                    return;
                }

                if (!glassesCheckPassed) {
                    accessoryCheckInProgress = true;
                    stopFaceScan();
                    cameraStatus.textContent = "Checking for eyeglasses…";
                    checkForGlasses().then(function (wearingGlasses) {
                        accessoryCheckInProgress = false;
                        if (!cameraStream) return;
                        if (wearingGlasses) {
                            cameraError.textContent = "Please remove your eyeglasses and try again.";
                            cameraError.hidden = false;
                            cameraStatus.textContent = "Eyeglasses detected. Remove them, then repeat the checks.";
                            retakePhotoButton.hidden = false;
                            retakePhotoButton.textContent = "Try again";
                            return;
                        }
                        glassesCheckPassed = true;
                        faceStableSince = null;
                        previousFaceBox = null;
                        cameraError.hidden = true;
                        cameraStatus.textContent = "No eyeglasses detected. Face forward and hold still for 1.5 seconds.";
                        faceScanFrame = requestAnimationFrame(scanForFace);
                    }).catch(function () {
                        accessoryCheckInProgress = false;
                        if (!cameraStream) return;
                        cameraError.textContent = "The eyeglasses check is unavailable. Check your connection and try again.";
                        cameraError.hidden = false;
                        cameraStatus.textContent = "Photo capture is blocked until the eyeglasses check works.";
                        retakePhotoButton.hidden = false;
                        retakePhotoButton.textContent = "Try again";
                    });
                    return;
                }

                const faceCount = faces.length;
                const facingForward = Boolean(
                    measurements && livenessSession &&
                    isForwardFacing(measurements.yaw, livenessSession.forwardYaw)
                );
                const lightingOkay = faceCount === 1 && positioned
                    ? updateLighting(timestamp, detection.boundingBox)
                    : false;

                if (faceCount !== 1 || !positioned || !facingForward || !lightingOkay) {
                    faceStableSince = null;
                    previousFaceBox = null;
                    latestCaptureEligible = false;
                    latestCaptureChecks = null;
                    autoCaptureCountdown.update(false, autoCaptureInput.checked, timestamp);
                    countdownStatus.hidden = true;
                    capturePhotoButton.disabled = true;
                    if (faceCount > 1) {
                        cameraStatus.textContent = "Only one person should be visible. Please try again.";
                    } else if (faceCount === 0) {
                        cameraStatus.textContent = "No face detected. Move into view and improve the lighting.";
                    } else if (!positioned) {
                        cameraStatus.textContent = faceGuidanceMessage(faceGuidance);
                    } else if (!facingForward) {
                        cameraStatus.textContent = "Face forward and look at the camera.";
                    } else {
                        cameraStatus.textContent = "The lighting is too low. Move to a brighter place.";
                    }
                } else if (!faceBoxIsStable(frameFaceBox)) {
                    faceStableSince = null;
                    latestCaptureEligible = false;
                    latestCaptureChecks = null;
                    autoCaptureCountdown.update(false, autoCaptureInput.checked, timestamp);
                    countdownStatus.hidden = true;
                    capturePhotoButton.disabled = true;
                    cameraStatus.textContent = "Perfect positioning. Hold still while the camera checks your position.";
                } else {
                    if (faceStableSince === null) faceStableSince = timestamp;
                    const stableForMs = timestamp - faceStableSince;
                    latestCaptureChecks = {
                        faceCount,
                        positioned,
                        livenessPassed,
                        facingForward,
                        glassesCheckPassed,
                        lightingAdequate: lightingOkay,
                        stableForMs,
                        captureInProgress: photoCaptureInProgress
                    };
                    latestCaptureEligible = isCaptureEligible(latestCaptureChecks);
                    capturePhotoButton.disabled = !latestCaptureEligible;
                    const countdown = autoCaptureCountdown.update(
                        latestCaptureEligible,
                        autoCaptureInput.checked,
                        timestamp
                    );

                    if (countdown.state === "countdown") {
                        countdownStatus.hidden = false;
                        countdownStatus.textContent = `Automatic capture in ${countdown.seconds}… Keep facing forward and hold still.`;
                        cameraStatus.textContent = "Checks passed. You can capture now or wait for automatic capture.";
                    } else if (countdown.state === "capture") {
                        countdownStatus.hidden = false;
                        countdownStatus.textContent = "Capturing your passport photo…";
                        capturePhoto();
                        return;
                    } else {
                        countdownStatus.hidden = true;
                        cameraStatus.textContent = "Checks passed. Tap Capture photo when you are ready.";
                    }
                }
            } catch (error) {
                stopFaceScan();
                cameraStatus.textContent = "Liveness detection stopped. Tap Try again to restart the checks.";
                retakePhotoButton.hidden = false;
                retakePhotoButton.textContent = "Try again";
                return;
            }
        }
        faceScanFrame = requestAnimationFrame(scanForFace);
    }

    async function beginFaceScan() {
        try {
            await loadFaceLandmarker();

            if (!cameraStream || video.hidden) return;

            faceStableSince = null;
            previousFaceBox = null;
            lastFaceScanAt = 0;
            lastLightingCheckAt = -Infinity;
            lightingAdequate = false;
            capturePhotoButton.disabled = true;
            livenessSession = new LivenessSession({ random: secureRandom });
            livenessPassed = false;
            glassesCheckPassed = false;
            cameraStatus.textContent =
                "Face landmarks ready. Centre your face to begin the liveness checks.";
            faceScanFrame = requestAnimationFrame(scanForFace);
        } catch (error) {
            // Liveness must not silently fall back to an unverified capture.
            cameraStatus.textContent =
                "Liveness detection is unavailable. Check your connection and try again.";
            cameraError.textContent = cameraStatus.textContent;
            cameraError.hidden = false;
            stopCamera();
        }
    }

    function retryCapture(message) {
        photoCaptureInProgress = false;
        cameraError.textContent = message;
        cameraError.hidden = false;

        if (!cameraStream) return;

        if (captureAttempts >= MAX_CAPTURE_ATTEMPTS) {
            cameraStatus.textContent =
                "Capture stopped after 4 attempts. Restart the camera to try again.";
            stopCamera();
            return;
        }

        cameraStatus.textContent =
            "Capture attempt " + captureAttempts + " of " +
            MAX_CAPTURE_ATTEMPTS + " failed. Retrying automatically…";

        if (captureRetryTimer !== null) {
            clearTimeout(captureRetryTimer);
        }

        captureRetryTimer = setTimeout(function () {
            captureRetryTimer = null;

            if (!cameraStream) return;
            livenessPassed = false;
            livenessSession = null;
            cameraStatus.textContent = "Repeat the liveness checks before trying another capture.";
            beginFaceScan();
        }, CAPTURE_RETRY_DELAY_MS);
    }

    async function capturePhoto() {
        if (
            photoCaptureInProgress ||
            accessoryCheckInProgress ||
            !cameraStream ||
            !isCaptureEligible({
                ...(latestCaptureChecks || {}),
                captureInProgress: photoCaptureInProgress
            }) ||
            !video.videoWidth ||
            !video.videoHeight
        ) {
            cameraStatus.textContent = "Capture is unavailable until every liveness, position, lighting and stability check passes.";
            return;
        }

        autoCaptureCountdown.cancel();
        latestCaptureEligible = false;
        if (countdownStatus) countdownStatus.hidden = true;

        if (
            !cameraStream ||
            photoCaptureInProgress ||
            !video.videoWidth ||
            !video.videoHeight
        ) {
            return;
        }

        // Capture first; server-side AI checks the actual uploaded photo.
        if (captureAttempts >= MAX_CAPTURE_ATTEMPTS) {
            cameraStatus.textContent =
                "Capture stopped after 4 attempts. Restart the camera to try again.";
            stopFaceScan();
            return;
        }

        captureAttempts += 1;
        cameraError.hidden = true;
        photoCaptureInProgress = true;
        capturePhotoButton.disabled = true;
        stopFaceScan();

        // Fit the full camera image into the same 4:5 viewfinder used by the preview.
        const renderPlan = passportCanvasRenderPlan(video.videoWidth, video.videoHeight);
        photoCanvas.width = renderPlan.width;
        photoCanvas.height = renderPlan.height;

        const context = photoCanvas.getContext("2d");
        if (!context) {
            photoCaptureInProgress = false;
            cameraError.textContent =
                "Photo capture is unavailable. Please reload the page and try again.";
            cameraError.hidden = false;
            return;
        }

        context.fillStyle = PASSPORT_FRAME_BACKGROUND;
        context.fillRect(0, 0, photoCanvas.width, photoCanvas.height);
        context.drawImage(
            video,
            0, 0, video.videoWidth, video.videoHeight,
            renderPlan.frame.x, renderPlan.frame.y,
            renderPlan.frame.width, renderPlan.frame.height
        );

        // Do not reject the crop using the browser's approximate
        // colour test. The server-side AI checks the submitted photo.
        photoCanvas.toBlob(function (blob) {
            if (!blob) {
                retryCapture(
                    "The photograph could not be created. Retrying automatically…"
                );
                return;
            }

            if (blob.size > 5 * 1024 * 1024) {
                retryCapture(
                    "The photograph exceeds 5 MB. Retrying automatically…"
                );
                return;
            }

            const reader = new FileReader();

            reader.onload = function () {
                const photoData = reader.result;

                if (
                    typeof photoData !== "string" ||
                    !photoData.startsWith("data:image/jpeg;base64,")
                ) {
                    retryCapture(
                        "The photograph could not be prepared. Retrying automatically…"
                    );
                    return;
                }

                // Process the captured image before displaying the preview.
                const requestId = ++previewRequestId;
                const csrfInput = registrationForm
                    ? registrationForm.querySelector('input[name="csrfmiddlewaretoken"]')
                    : null;
                const requestData = new FormData();
                requestData.append("passport_photo_data", photoData);

                cameraStatus.textContent = "Processing your photo…";
                capturePhotoButton.disabled = true;
                startCameraButton.disabled = true;

                if (whiteScanStatus) {
                    whiteScanStatus.textContent =
                        "Removing the background and preparing your photo…";
                    whiteScanStatus.classList.remove("is-white", "is-not-white");
                }

                fetch(photoInput.dataset.processUrl, {
                    method: "POST",
                    body: requestData,
                    credentials: "same-origin",
                    headers: csrfInput
                        ? {"X-CSRFToken": csrfInput.value}
                        : {}
                })
                    .then(async function (response) {
                        const result = await response.json();
                        if (!response.ok) {
                            throw new Error(result.error || "Photo processing failed.");
                        }
                        return result;
                    })
                    .then(function (result) {
                        if (requestId !== previewRequestId) return;

                        pendingPhotoData = result.photo_data;
                        pendingPhotoToken = result.photo_token;
                        photoPreview.src = pendingPhotoData;
                        photoPreview.hidden = false;
                        photoPreview.parentElement.classList.add("is-reviewing");
                        video.hidden = true;
                        photoPlaceholder.hidden = true;
                        acceptPhotoButton.hidden = false;
                        retakePhotoButton.hidden = false;
                        cameraError.hidden = true;

                        if (whiteScanStatus) {
                            whiteScanStatus.textContent =
                                "Review the processed photo and its white background.";
                            whiteScanStatus.classList.remove("is-white", "is-not-white");
                        }

                        cameraStatus.textContent =
                            "Review the processed photo. Choose Use this photo or Retake photo.";
                        stopCamera();
                    })
                    .catch(function (error) {
                        if (requestId !== previewRequestId) return;
                        cameraError.textContent =
                            error.message || "Photo processing failed. Please retake it.";
                        cameraError.hidden = false;
                        cameraStatus.textContent =
                            "The photo could not be processed. Please retake it.";
                        if (whiteScanStatus) {
                            whiteScanStatus.textContent =
                                "Processing failed. Capture another photo.";
                        }
                        clearCapturedPhoto();
                        video.hidden = false;
                        startCameraButton.disabled = false;
                        if (cameraStream) capturePhotoButton.disabled = true;
                    })
                    .finally(function () {
                        if (requestId === previewRequestId) {
                            photoCaptureInProgress = false;
                        }
                    });
            };

            reader.onerror = function () {
                retryCapture(
                    "The photograph could not be read. Retrying automatically…"
                );
            };

            reader.readAsDataURL(blob);
        }, "image/jpeg", 0.88);
    }

    async function startCamera() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            cameraError.textContent =
                "Camera access is unavailable. Open this form using HTTPS or localhost in a supported browser.";
            cameraError.hidden = false;
            return;
        }

        stopCamera();
        const startRequestId = ++cameraStartRequestId;

        captureAttempts = 0;
        clearCapturedPhoto();
        cameraError.hidden = true;
        cameraStatus.textContent = "Waiting for camera permission…";
        if (cameraSwitchButton) cameraSwitchButton.disabled = true;

        let requestedStream = null;

        try {
            const constraints = cameraConstraintFallbacks(requestedFacingMode);
            let lastConstraintError = null;
            for (const constraint of constraints) {
                try {
                    requestedStream = await navigator.mediaDevices.getUserMedia(constraint);
                    break;
                } catch (constraintError) {
                    lastConstraintError = constraintError;
                    if (!constraintError || !["OverconstrainedError", "NotFoundError"].includes(constraintError.name)) {
                        throw constraintError;
                    }
                }
            }
            if (!requestedStream) throw lastConstraintError || new Error("Camera unavailable");

            // Browser labels become available after permission. If a device
            // explicitly exposes a wide camera, prefer it; otherwise retain
            // the browser's facingMode selection.
            if (navigator.mediaDevices.enumerateDevices) {
                try {
                    const initialTrack = requestedStream.getVideoTracks()[0];
                    const initialSettings = initialTrack && initialTrack.getSettings
                        ? initialTrack.getSettings() : {};
                    const devices = await navigator.mediaDevices.enumerateDevices();
                    if (startRequestId !== cameraStartRequestId) {
                        stopMediaTracks(requestedStream);
                        return;
                    }
                    const wideCamera = selectWideCameraDevice(
                        devices, requestedFacingMode, initialSettings.deviceId || ""
                    );
                    if (wideCamera) {
                        try {
                            const wideStream = await navigator.mediaDevices.getUserMedia({
                                audio: false,
                                video: {
                                    deviceId: { exact: wideCamera.deviceId },
                                    width: { ideal: 720 },
                                    height: { ideal: 1280 },
                                    aspectRatio: { ideal: 9 / 16 }
                                }
                            });
                            if (startRequestId !== cameraStartRequestId) {
                                stopMediaTracks(wideStream);
                                stopMediaTracks(requestedStream);
                                return;
                            }
                            stopMediaTracks(requestedStream);
                            requestedStream = wideStream;
                        } catch (wideCameraError) {
                            console.info("Wide camera unavailable; keeping browser-selected camera.");
                        }
                    }
                } catch (deviceListError) {
                    console.info("Camera list unavailable; keeping browser-selected camera.");
                }
            }

            // A newer start/stop request superseded this request.
            if (startRequestId !== cameraStartRequestId) {
                stopMediaTracks(requestedStream);
                return;
            }

            cameraStream = requestedStream;
            requestedStream.getVideoTracks().forEach(function (track) {
                track.addEventListener("ended", function () {
                    if (cameraStream !== requestedStream) return;
                    stopCamera();
                    cameraStatus.textContent =
                        "The camera connection ended. Tap Start camera to try again.";
                }, { once: true });
            });
            video.srcObject = requestedStream;
            video.classList.toggle(
                "passport-camera-video-mirrored",
                requestedFacingMode === "user"
            );
            video.hidden = false;
            photoPreview.hidden = true;
            photoPlaceholder.hidden = true;

            await video.play();

            const activeVideoTrack = requestedStream.getVideoTracks()[0];
            const trackSettings = activeVideoTrack && activeVideoTrack.getSettings
                ? activeVideoTrack.getSettings()
                : {};
            if (["user", "environment"].includes(trackSettings.facingMode)) {
                requestedFacingMode = trackSettings.facingMode;
                video.classList.toggle(
                    "passport-camera-video-mirrored",
                    requestedFacingMode === "user"
                );
                updateCameraSwitchLabel();
            }
            const trackCapabilities = activeVideoTrack && activeVideoTrack.getCapabilities
                ? activeVideoTrack.getCapabilities()
                : {};
            const minimumZoom = minimumSupportedZoom(trackCapabilities);
            if (minimumZoom !== null && activeVideoTrack && activeVideoTrack.applyConstraints) {
                try {
                    await activeVideoTrack.applyConstraints({ advanced: [{ zoom: minimumZoom }] });
                } catch (zoomError) {
                    console.info("Camera does not support applying its minimum zoom setting.");
                }
            }
            console.info(
                "Passport camera dimensions:",
                `${video.videoWidth}x${video.videoHeight}`,
                {
                    facingMode: trackSettings.facingMode || "not reported",
                    width: trackSettings.width || video.videoWidth,
                    height: trackSettings.height || video.videoHeight,
                    zoomRange: trackCapabilities.zoom || "unsupported",
                    zoom: activeVideoTrack && activeVideoTrack.getSettings
                        ? activeVideoTrack.getSettings().zoom ?? "not reported"
                        : "not reported"
                }
            );

            // Do not activate capture for a replaced or stopped stream.
            if (
                startRequestId !== cameraStartRequestId ||
                cameraStream !== requestedStream ||
                video.srcObject !== requestedStream
            ) {
                return;
            }

            capturePhotoButton.disabled = true;
            startCameraButton.textContent = "Close camera";
            if (cameraSwitchButton) cameraSwitchButton.disabled = false;
            document.body.classList.add("passport-camera-stage-open");
            if (whiteScanStatus) {
                whiteScanStatus.textContent =
                    "AI will check the person and white background before accepting the photo.";
                whiteScanStatus.classList.remove("is-white", "is-not-white");
            }
            cameraStatus.textContent =
                "Loading local face landmarks and liveness checks…";
            beginFaceScan();
        } catch (error) {
            // Never let a stale request stop a newer camera session.
            if (startRequestId !== cameraStartRequestId) {
                if (requestedStream) {
                    stopMediaTracks(requestedStream);
                }
                return;
            }

            stopCamera();
            if (cameraSwitchButton) cameraSwitchButton.disabled = false;

            // AbortError can occur when browser playback is interrupted.
            // Report it as a recoverable interruption, not a fatal error.
            if (error && error.name === "AbortError") {
                cameraStatus.textContent =
                    "Camera startup was interrupted. Tap Start camera to try again.";
                return;
            }

            console.error(
                "Passport camera startup failed:",
                error.name,
                error.message
            );
            const cameraMessages = {
                NotAllowedError: "Allow camera access in your browser’s site settings, then tap Start camera again.",
                NotFoundError: "No camera was found. Connect or enable a camera, then try again.",
                NotReadableError: "The camera is busy in another app. Close that app and try again."
            };
            cameraError.textContent = cameraMessages[error.name] ||
                `Camera unavailable (${error.name || "unknown error"}). Please check the camera and try again.`;
            cameraError.hidden = false;
            cameraStatus.textContent = "Camera capture is required.";
        }
    }

    if (video && photoCanvas && photoInput && startCameraButton) {
        startCameraButton.addEventListener("click", function () {
            if (!cameraStream) {
                startCamera();
                return;
            }
            stopCamera();
            video.hidden = true;
            photoPlaceholder.hidden = false;
            cameraStatus.textContent = "Camera closed. Tap Start camera when you are ready.";
        });

        updateCameraSwitchLabel();
        if (cameraSwitchButton) {
            cameraSwitchButton.addEventListener("click", function () {
                requestedFacingMode = nextFacingMode(requestedFacingMode);
                updateCameraSwitchLabel();
                startCamera();
            });
        }

        capturePhotoButton.addEventListener("click", capturePhoto);

        acceptPhotoButton.addEventListener("click", function () {
            if (!pendingPhotoData || !pendingPhotoToken) {
                cameraError.textContent =
                    "Please wait until your processed photo is ready.";
                cameraError.hidden = false;
                return;
            }

            photoInput.value = pendingPhotoData;
            photoTokenInput.value = pendingPhotoToken;
            acceptPhotoButton.hidden = true;
            cameraError.hidden = true;
            cameraStatus.textContent = "Processed photo accepted.";
            if (whiteScanStatus) {
                whiteScanStatus.textContent = "Photo accepted with a processed white background.";
                whiteScanStatus.classList.add("is-white");
                whiteScanStatus.classList.remove("is-not-white");
            }
        });

        retakePhotoButton.addEventListener("click", function () {
            clearCapturedPhoto();
            video.hidden = false;
            startCameraButton.disabled = false;
            startCamera();
        });

        if (photoInput.value && photoTokenInput.value) {
            photoPreview.src = photoInput.value;
            photoPreview.hidden = false;
            photoPlaceholder.hidden = true;
            retakePhotoButton.hidden = false;
            cameraStatus.textContent = "Previously accepted processed photo restored.";
        } else {
            clearCapturedPhoto();
        }

        window.addEventListener("pagehide", function () { stopCamera(); });
        document.addEventListener("visibilitychange", function () {
            if (document.hidden && cameraStream) {
                stopCamera();
                cameraStatus.textContent =
                    "Camera paused after leaving this page. Tap Start camera to repeat the checks.";
                startCameraButton.disabled = false;
            }
        });
    }

    if (autoCaptureInput) {
        autoCaptureInput.addEventListener("change", function () {
            autoCaptureCountdown.cancel();
            countdownStatus.hidden = true;
            if (!autoCaptureInput.checked && latestCaptureEligible) {
                cameraStatus.textContent = "Checks passed. Automatic capture is off; tap Capture photo when ready.";
            }
        });
    }

    if (registrationForm) {
        registrationForm.addEventListener("submit", function (event) {
            if (
                !photoInput || !photoInput.value ||
                !photoTokenInput || !photoTokenInput.value
            ) {
                event.preventDefault();
                cameraError.textContent =
                    "Capture and accept your passport photograph before submitting.";
                cameraError.hidden = false;
                if (startCameraButton) {
                    startCameraButton.scrollIntoView({
                        behavior: "smooth",
                        block: "center"
                    });
                    startCameraButton.focus();
                }
            }
        });
    }
});
