import { getFaceMeasurements, isForwardFacing, LivenessSession } from "./passport-liveness.mjs?v=3";
import {
    cameraConstraintFallbacks,
    getPassportFaceGuidance,
    isFaceSafeDuringLivenessChallenge,
    mapRectToCoverFrame,
    mirrorRectHorizontally,
    nextFacingMode,
    passportCanvasRenderPlan,
    selectPreferredCameraDevice,
    stopMediaTracks,
    zoomConstraintTarget
} from "./passport-framing.mjs?v=6";
import {
    AutoCaptureCountdown,
    CAPTURE_STABILITY_MS,
    isCaptureEligible
} from "./passport-capture.mjs?v=2";
import {
    MAX_PHOTO_BYTES,
    loadMediaPipeVisionRuntime,
    removePassportPhotoBackground
} from "./passport-background-removal.mjs?v=2";

document.addEventListener("DOMContentLoaded", function () {
    const video = document.getElementById("passport-camera-video");
    const photoCanvas = document.getElementById("passport-camera-canvas");
    const whiteScanStatus = document.getElementById("passport-white-scan-status");
    const photoInput = document.getElementById("passport-photo-data");
    const photoTokenInput = document.getElementById("passport-photo-token");
    const photoFileInput = document.getElementById("id_passport_photo");
    const acceptPhotoButton = document.getElementById("passport-camera-accept");
    const photoPreview = document.getElementById("passport-camera-image");
    const cameraGuide = document.querySelector(".registration-camera-guide");
    let pendingPhotoData = "";
    let pendingPhotoToken = "";
    let pendingPhotoSourceKind = "camera";
    let previewRequestId = 0;
    const photoPlaceholder = document.getElementById("passport-camera-placeholder");
    const startCameraButton = document.getElementById("passport-camera-start");
    const cameraSwitchButton = document.getElementById("passport-camera-switch");
    const cameraIndicator = document.getElementById("passport-camera-indicator");
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
    let lastFaceGuidanceShown = null;
    let preserveLivenessOnNextCameraStart = false;
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
        pendingPhotoSourceKind = "camera";
        if (photoInput) photoInput.value = "";
        if (photoTokenInput) photoTokenInput.value = "";
        if (photoFileInput) photoFileInput.value = "";
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
            const { vision, files } = await loadMediaPipeVisionRuntime();

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

    function blobToDataUrl(blob) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => {
                if (typeof reader.result !== "string") {
                    reject(new Error("The processed photograph could not be read."));
                    return;
                }
                resolve(reader.result);
            };
            reader.onerror = () => reject(
                new Error("The processed photograph could not be read.")
            );
            reader.readAsDataURL(blob);
        });
    }

    async function hasSupportedPhotoSignature(file) {
        const bytes = new Uint8Array(await file.slice(0, 8).arrayBuffer());
        const jpeg = bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff;
        const png = bytes.length === 8 &&
            bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e &&
            bytes[3] === 0x47 && bytes[4] === 0x0d && bytes[5] === 0x0a &&
            bytes[6] === 0x1a && bytes[7] === 0x0a;
        return jpeg || png;
    }

    async function processPhotoSource(source, sourceKind) {
        if (photoCaptureInProgress) return;

        const requestId = ++previewRequestId;
        photoCaptureInProgress = true;
        pendingPhotoData = "";
        pendingPhotoToken = "";
        photoInput.value = "";
        photoTokenInput.value = "";
        acceptPhotoButton.hidden = true;
        retakePhotoButton.hidden = true;
        photoPreview.hidden = true;
        cameraError.hidden = true;
        capturePhotoButton.disabled = true;
        startCameraButton.disabled = true;
        if (photoFileInput) photoFileInput.disabled = true;
        registrationForm.querySelectorAll('button[type="submit"]').forEach((button) => {
            button.disabled = true;
        });

        const showProgress = (message) => {
            cameraStatus.textContent = message;
            if (whiteScanStatus) {
                whiteScanStatus.textContent = message;
                whiteScanStatus.classList.remove("is-white", "is-not-white");
            }
        };

        try {
            const processedBlob = await removePassportPhotoBackground(
                source,
                showProgress
            );
            const processedData = await blobToDataUrl(processedBlob);
            showProgress("Checking the processed photograph…");

            const csrfInput = registrationForm.querySelector(
                'input[name="csrfmiddlewaretoken"]'
            );
            const requestData = new FormData();
            requestData.append("passport_photo_data", processedData);
            const response = await fetch(photoInput.dataset.processUrl, {
                method: "POST",
                body: requestData,
                credentials: "same-origin",
                headers: csrfInput ? { "X-CSRFToken": csrfInput.value } : {}
            });
            const result = await response.json();
            if (!response.ok) {
                throw new Error(
                    result.error || "The processed photograph was rejected. Please retry."
                );
            }
            if (requestId !== previewRequestId) return;

            pendingPhotoData = result.photo_data;
            pendingPhotoToken = result.photo_token;
            pendingPhotoSourceKind = sourceKind;
            if (sourceKind === "upload" && photoFileInput) {
                // Never send the unprocessed selected file on the final form POST.
                photoFileInput.value = "";
            }
            photoPreview.src = pendingPhotoData;
            photoPreview.hidden = false;
            photoPreview.parentElement.classList.add("is-reviewing");
            video.hidden = true;
            photoPlaceholder.hidden = true;
            acceptPhotoButton.hidden = false;
            retakePhotoButton.hidden = false;
            retakePhotoButton.textContent = "Retake / choose another";
            cameraError.hidden = true;
            if (whiteScanStatus) {
                whiteScanStatus.textContent =
                    "Background removal complete. Review the white-background photo.";
                whiteScanStatus.classList.remove("is-white", "is-not-white");
            }
            cameraStatus.textContent =
                "Review the processed photo. Choose Use this photo or Retake / choose another.";
            stopCamera();
        } catch (error) {
            if (requestId !== previewRequestId) return;
            pendingPhotoData = "";
            pendingPhotoToken = "";
            photoInput.value = "";
            photoTokenInput.value = "";
            photoPreview.removeAttribute("src");
            photoPreview.hidden = true;
            photoPreview.parentElement.classList.remove("is-reviewing");
            acceptPhotoButton.hidden = true;
            cameraError.textContent = error.message ||
                "Background removal failed. Please retry or choose another photograph.";
            cameraError.hidden = false;
            if (whiteScanStatus) {
                whiteScanStatus.textContent = "Processing failed. Your original photo was not submitted.";
            }
            if (sourceKind === "camera") {
                cameraStatus.textContent =
                    "Background removal failed. Restart the camera and try again.";
                startCameraButton.disabled = false;
                if (cameraStream) stopCamera();
                video.hidden = true;
                photoPlaceholder.hidden = false;
            } else {
                cameraStatus.textContent =
                    "Background removal failed. Choose the photo again or select another.";
                if (photoFileInput) {
                    photoFileInput.value = "";
                    photoFileInput.disabled = false;
                }
                startCameraButton.disabled = false;
            }
        } finally {
            if (requestId === previewRequestId) {
                photoCaptureInProgress = false;
                startCameraButton.disabled = false;
                if (photoFileInput) photoFileInput.disabled = false;
                registrationForm.querySelectorAll('button[type="submit"]').forEach((button) => {
                    button.disabled = false;
                });
                if (sourceKind === "camera" && cameraStream) {
                    capturePhotoButton.disabled = true;
                }
            }
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
        return mapRectToCoverFrame({
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

    function updateCameraIndicator(mode) {
        if (!cameraIndicator) return;
        const direction = mode === "environment" ? "Rear" : "Front";
        cameraIndicator.textContent = `${direction} camera`;
    }

    function faceBoxIsStable(frameBox) {
        if (!frameBox) return false;
        const current = frameBox;
        const previous = previousFaceBox;
        previousFaceBox = current;

        if (!previous) return false;

        return (
            Math.abs(current.x - previous.x) < 0.04 &&
            Math.abs(current.y - previous.y) < 0.04 &&
            Math.abs(current.width - previous.width) < 0.06 &&
            Math.abs(current.height - previous.height) < 0.06
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
                const guidanceChanged = previousFaceGuidance !== faceGuidance;
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
                        positioned: livenessSession.state === "challenge"
                            ? isFaceSafeDuringLivenessChallenge(frameFaceBox)
                            : positioned,
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
                        if (guidanceChanged || lastFaceGuidanceShown !== faceGuidance) {
                            cameraStatus.textContent = faceGuidanceMessage(faceGuidance);
                            lastFaceGuidanceShown = faceGuidance;
                        }
                    } else if (status.challenge === "blink") {
                        lastFaceGuidanceShown = null;
                        cameraStatus.textContent =
                            `Liveness check ${status.step} of ${status.total}: Blink naturally, then open your eyes.`;
                    } else {
                        cameraStatus.textContent = "Liveness check: Blink naturally, then open your eyes.";
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

            const preserveLiveness = preserveLivenessOnNextCameraStart && Boolean(livenessSession);
            preserveLivenessOnNextCameraStart = false;
            faceStableSince = null;
            previousFaceBox = null;
            previousFaceGuidance = null;
            lastFaceGuidanceShown = null;
            lastFaceScanAt = 0;
            lastLightingCheckAt = -Infinity;
            lightingAdequate = false;
            capturePhotoButton.disabled = true;
            if (!preserveLiveness) {
                livenessSession = new LivenessSession();
                livenessPassed = false;
                glassesCheckPassed = false;
            }
            cameraStatus.textContent = preserveLiveness
                ? "Camera switched. Continue the current liveness check."
                : "Face landmarks ready. Centre your face to begin the liveness checks.";
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

        // Capture first; the server validates and normalizes the accepted image.
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

        // Draw one source crop identical to the CSS cover preview.
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

        context.fillStyle = "#fff";
        context.fillRect(0, 0, photoCanvas.width, photoCanvas.height);
        context.drawImage(
            video,
            renderPlan.frame.x,
            renderPlan.frame.y,
            renderPlan.frame.width,
            renderPlan.frame.height,
            0, 0, photoCanvas.width, photoCanvas.height
        );

        // Segmentation happens locally before any image data is sent to Django.
        photoCaptureInProgress = false;
        processPhotoSource(photoCanvas, "camera");
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
            console.info("Passport getUserMedia constraints:", constraints);
            let lastConstraintError = null;
            for (const constraint of constraints) {
                try {
                    console.info("Passport camera constraint attempt:", constraint);
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

            let selectedDevice = null;
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
                    const preferredCamera = selectPreferredCameraDevice(
                        devices, requestedFacingMode, initialSettings.deviceId || ""
                    );
                    if (preferredCamera) {
                        try {
                            const wideStream = await navigator.mediaDevices.getUserMedia({
                                audio: false,
                                video: {
                                    deviceId: { exact: preferredCamera.deviceId },
                                    width: { ideal: 720 },
                                    height: { ideal: 900 },
                                    aspectRatio: { ideal: 4 / 5 }
                                }
                            });
                            if (startRequestId !== cameraStartRequestId) {
                                stopMediaTracks(wideStream);
                                stopMediaTracks(requestedStream);
                                return;
                            }
                            stopMediaTracks(requestedStream);
                            requestedStream = wideStream;
                            selectedDevice = preferredCamera;
                        } catch (wideCameraError) {
                            console.info("Preferred camera unavailable; keeping browser-selected camera.");
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
            let trackSettings = activeVideoTrack && activeVideoTrack.getSettings
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
            let trackCapabilities = {};
            try {
                trackCapabilities = activeVideoTrack && activeVideoTrack.getCapabilities
                    ? activeVideoTrack.getCapabilities()
                    : {};
            } catch (capabilityError) {
                // Capability reporting is optional and must not block camera use.
            }
            const currentZoom = trackSettings.zoom;
            const zoomTarget = zoomConstraintTarget(trackCapabilities, trackSettings);
            if (zoomTarget !== null && activeVideoTrack && activeVideoTrack.applyConstraints &&
                (!Number.isFinite(currentZoom) || Math.abs(currentZoom - zoomTarget) > 0.01)) {
                try {
                    await activeVideoTrack.applyConstraints({ advanced: [{ zoom: zoomTarget }] });
                } catch (zoomError) {
                    console.info("Camera did not accept the bounded zoom preference.");
                }
            }
            if (activeVideoTrack && activeVideoTrack.getSettings) {
                trackSettings = activeVideoTrack.getSettings();
            }
            let selectedDeviceDetails = selectedDevice;
            if (navigator.mediaDevices.enumerateDevices) {
                try {
                    selectedDeviceDetails = (await navigator.mediaDevices.enumerateDevices())
                        .find((device) => device.deviceId === trackSettings.deviceId) || selectedDevice;
                } catch (deviceInfoError) {
                    // Camera labels are optional diagnostics; keep startup functional.
                }
            }
            if (["user", "environment"].includes(trackSettings.facingMode)) {
                requestedFacingMode = trackSettings.facingMode;
                video.classList.toggle("passport-camera-video-mirrored", requestedFacingMode === "user");
                updateCameraSwitchLabel();
            }
            updateCameraIndicator(
                trackSettings.facingMode || requestedFacingMode,
                selectedDeviceDetails ? selectedDeviceDetails.label : ""
            );
            console.info(
                "Passport camera diagnostics:",
                {
                    resolution: `${video.videoWidth}x${video.videoHeight}`,
                    deviceLabel: selectedDeviceDetails ? selectedDeviceDetails.label : "not reported",
                    deviceId: trackSettings.deviceId || "not reported",
                    groupId: trackSettings.groupId || "not reported",
                    settings: trackSettings,
                    capabilities: trackCapabilities
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
                    "Face and liveness checks are active. A plain, evenly lit wall gives the best background removal.";
                whiteScanStatus.classList.remove("is-white", "is-not-white");
            }
            cameraStatus.textContent =
                "Loading local face landmarks and liveness checks…";
            beginFaceScan();
        } catch (error) {
            preserveLivenessOnNextCameraStart = false;
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
                preserveLivenessOnNextCameraStart = true;
                requestedFacingMode = nextFacingMode(requestedFacingMode);
                updateCameraSwitchLabel();
                startCamera();
            });
        }

        capturePhotoButton.addEventListener("click", capturePhoto);

        if (photoFileInput) {
            photoFileInput.addEventListener("change", function () {
                const file = photoFileInput.files && photoFileInput.files[0];
                if (!file) return;
                if (photoCaptureInProgress) return;

                photoCaptureInProgress = true;
                cameraError.hidden = true;
                photoInput.value = "";
                photoTokenInput.value = "";
                pendingPhotoData = "";
                pendingPhotoToken = "";
                photoPreview.hidden = true;
                acceptPhotoButton.hidden = true;
                retakePhotoButton.hidden = true;
                photoFileInput.disabled = true;
                startCameraButton.disabled = true;
                capturePhotoButton.disabled = true;
                registrationForm.querySelectorAll('button[type="submit"]').forEach((button) => {
                    button.disabled = true;
                });
                cameraStatus.textContent = "Checking the selected photograph…";

                (async function () {
                    let validationError = "";
                    if (!new Set(["image/jpeg", "image/png"]).has(file.type.toLowerCase())) {
                        validationError = "Choose a JPEG or PNG passport photograph.";
                    } else if (file.size > MAX_PHOTO_BYTES) {
                        validationError = "The selected photograph must not exceed 5 MB.";
                    } else if (!await hasSupportedPhotoSignature(file)) {
                        validationError = "The selected file is not a valid JPEG or PNG image.";
                    }

                    photoCaptureInProgress = false;
                    photoFileInput.disabled = false;
                    startCameraButton.disabled = false;
                    registrationForm.querySelectorAll('button[type="submit"]').forEach((button) => {
                        button.disabled = false;
                    });

                    if (validationError) {
                        photoFileInput.value = "";
                        cameraError.textContent = validationError;
                        cameraError.hidden = false;
                        cameraStatus.textContent = "Choose a valid passport photograph to continue.";
                        return;
                    }

                    cameraError.hidden = true;
                    if (cameraStream) stopCamera();
                    video.hidden = true;
                    photoPlaceholder.hidden = true;
                    processPhotoSource(file, "upload");
                })().catch(function () {
                    photoCaptureInProgress = false;
                    photoFileInput.disabled = false;
                    startCameraButton.disabled = false;
                    registrationForm.querySelectorAll('button[type="submit"]').forEach((button) => {
                        button.disabled = false;
                    });
                    photoFileInput.value = "";
                    cameraError.textContent = "The selected photograph could not be read. Please try another image.";
                    cameraError.hidden = false;
                });
            });
        }

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
            cameraStatus.textContent = "Photo accepted.";
            if (whiteScanStatus) {
                whiteScanStatus.textContent = "Photo accepted. Check the preview to confirm the background looks clean.";
                whiteScanStatus.classList.remove("is-white", "is-not-white");
            }
        });

        retakePhotoButton.addEventListener("click", function () {
            const previousSourceKind = pendingPhotoSourceKind;
            clearCapturedPhoto();
            if (previousSourceKind === "upload" && photoFileInput) {
                photoFileInput.click();
                return;
            }
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
            if (photoCaptureInProgress) {
                event.preventDefault();
                cameraError.textContent =
                    "Please wait for background removal to finish before submitting.";
                cameraError.hidden = false;
                return;
            }
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
