document.addEventListener("DOMContentLoaded", function () {
    const video = document.getElementById("passport-camera-video");
    const photoCanvas = document.getElementById("passport-camera-canvas");
    const whiteScanStatus = document.getElementById("passport-white-scan-status");
    const photoInput = document.getElementById("passport-photo-data");
    const photoPreview = document.getElementById("passport-camera-image");
    const photoPlaceholder = document.getElementById("passport-camera-placeholder");
    const startCameraButton = document.getElementById("passport-camera-start");
    const capturePhotoButton = document.getElementById("passport-camera-capture");
    const retakePhotoButton = document.getElementById("passport-camera-retake");
    const cameraStatus = document.getElementById("passport-camera-status");
    const cameraError = document.getElementById("passport-camera-error");
    const registrationForm = document.querySelector(".registration-card form");
    let cameraStream = null;
    let faceDetector = null;
    let faceDetectionLoading = null;
    let glassesDetector = null;
    let glassesDetectionLoading = null;
    let accessoryCheckInProgress = false;

    let faceScanFrame = null;
    let faceStableSince = null;
    let lastFaceScanAt = 0;
    let previousFaceBox = null;
    let photoCaptureInProgress = false;
    let latestFaceBox = null;
    let captureAttempts = 0;
    let captureRetryTimer = null;

    const MAX_CAPTURE_ATTEMPTS = 4;
    const CAPTURE_RETRY_DELAY_MS = 900;

    // passport-face-auto-detection
    const FACE_STABILITY_MS = 1500;
    const FACE_SCAN_INTERVAL_MS = 250;

    function stopFaceScan() {
        if (faceScanFrame !== null) {
            cancelAnimationFrame(faceScanFrame);
            faceScanFrame = null;
        }
        faceStableSince = null;
        previousFaceBox = null;
    }

    let cameraStartRequestId = 0;

    function stopCamera() {
        cameraStartRequestId += 1;
        stopFaceScan();

        if (captureRetryTimer !== null) {
            clearTimeout(captureRetryTimer);
            captureRetryTimer = null;
        }

        if (cameraStream) {
            cameraStream.getTracks().forEach(function (track) {
                track.stop();
            });
            cameraStream = null;
        }
        if (video) video.srcObject = null;
        if (capturePhotoButton) capturePhotoButton.disabled = true;
    }

    function clearCapturedPhoto() {
        photoCaptureInProgress = false;
        if (photoInput) photoInput.value = "";
        if (photoPreview) {
            photoPreview.removeAttribute("src");
            photoPreview.hidden = true;
        }
        if (photoPlaceholder) photoPlaceholder.hidden = false;
        if (retakePhotoButton) retakePhotoButton.hidden = true;
        if (cameraStatus) cameraStatus.textContent = "Photograph required.";
    }


    async function loadFaceDetector() {
        if (faceDetector) return faceDetector;
        if (faceDetectionLoading) return faceDetectionLoading;

        faceDetectionLoading = (async function () {
            const vision = await import(
                "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/+esm"
            );

            const files = await vision.FilesetResolver.forVisionTasks(
                "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm"
            );

            faceDetector = await vision.FaceDetector.createFromOptions(
                files,
                {
                    baseOptions: {
                        modelAssetPath:
                            "https://storage.googleapis.com/mediapipe-models/" +
                            "face_detector/blaze_face_short_range/float16/1/" +
                            "blaze_face_short_range.tflite"
                    },
                    runningMode: "VIDEO",
                    minDetectionConfidence: 0.65
                }
            );

            return faceDetector;
        })();

        try {
            return await faceDetectionLoading;
        } catch (error) {
            faceDetectionLoading = null;
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

    function faceIsWellPositioned(detection) {
        const box = detection && detection.boundingBox;
        if (!box || !video.videoWidth || !video.videoHeight) return false;

        const width = video.videoWidth;
        const height = video.videoHeight;

        const left = box.originX / width;
        const top = box.originY / height;
        const faceWidth = box.width / width;
        const faceHeight = box.height / height;
        const centerX = left + faceWidth / 2;
        const centerY = top + faceHeight / 2;

        // Keep the detected face well inside the central circular guide.
        // The extra margin helps prevent faces from touching the guide edge.
        const circleCenterX = 0.5;
        const circleCenterY = 0.48;
        const circleRadiusX = 0.34;
        const circleRadiusY = 0.39;

        const corners = [
            [left, top],
            [left + faceWidth, top],
            [left, top + faceHeight],
            [left + faceWidth, top + faceHeight]
        ];

        const faceInsideGuide = corners.every(function (point) {
            const dx = (point[0] - circleCenterX) / circleRadiusX;
            const dy = (point[1] - circleCenterY) / circleRadiusY;
            return (dx * dx) + (dy * dy) <= 1;
        });

        return (
            faceWidth >= 0.12 &&
            faceWidth <= 0.65 &&
            faceHeight >= 0.16 &&
            faceHeight <= 0.85 &&
            centerX >= 0.30 &&
            centerX <= 0.70 &&
            centerY >= 0.20 &&
            centerY <= 0.78 &&
            faceInsideGuide
        );
    }

    function faceBoxIsStable(detection) {
        const box = detection && detection.boundingBox;
        if (!box) return false;

        const current = {
            x: box.originX / video.videoWidth,
            y: box.originY / video.videoHeight,
            width: box.width / video.videoWidth,
            height: box.height / video.videoHeight
        };

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
        if (
            !cameraStream ||
            video.hidden ||
            photoCaptureInProgress ||
            !faceDetector
        ) {
            faceScanFrame = null;
            return;
        }

        if (timestamp - lastFaceScanAt >= FACE_SCAN_INTERVAL_MS) {
            lastFaceScanAt = timestamp;

            try {
                const result = faceDetector.detectForVideo(video, timestamp);
                const detections = result.detections || [];

                latestFaceBox = detections.length === 1
                    ? detections[0].boundingBox
                    : null;

                if (detections.length === 1 &&
                    faceIsWellPositioned(detections[0])) {
                    if (!faceBoxIsStable(detections[0])) {
                        faceStableSince = null;
                        cameraStatus.textContent =
                            "Face detected. Hold still while the camera checks your position.";
                    } else if (faceStableSince === null) {
                        faceStableSince = timestamp;
                    }

                    if (faceStableSince === null) {
                        faceScanFrame = requestAnimationFrame(scanForFace);
                        return;
                    }

                    const elapsed = timestamp - faceStableSince;
                    const remaining = Math.max(
                        0,
                        FACE_STABILITY_MS - elapsed
                    );

                    cameraStatus.textContent = remaining > 0
                        ? "Face detected. Hold still for " +
                          (remaining / 1000).toFixed(1) +
                          " seconds for automatic capture."
                        : "Capturing photograph…";

                    if (elapsed >= FACE_STABILITY_MS) {
                        capturePhoto();
                        return;
                    }
                } else {
                    faceStableSince = null;

                    if (detections.length > 1) {
                        cameraStatus.textContent =
                            "Only one person should be visible. Please try again.";
                    } else if (detections.length === 1) {
                        cameraStatus.textContent =
                            "Move your face into the centre of the frame.";
                    } else {
                        cameraStatus.textContent =
                            "Position your face in the centre and look at the camera.";
                    }
                }
            } catch (error) {
                stopFaceScan();
                cameraStatus.textContent =
                    "Automatic detection stopped. Use Capture photo manually.";
                return;
            }
        }

        faceScanFrame = requestAnimationFrame(scanForFace);
    }

    async function beginFaceScan() {
        try {
            await loadFaceDetector();

            if (!cameraStream || video.hidden) return;

            faceStableSince = null;
            previousFaceBox = null;
            lastFaceScanAt = 0;
            cameraStatus.textContent =
                "Face detection ready. Centre your face and hold still.";
            faceScanFrame = requestAnimationFrame(scanForFace);
        } catch (error) {
            // Camera and manual capture remain usable if the CDN/model fails.
            cameraStatus.textContent =
                "Automatic detection is unavailable. Centre your face and use Capture photo.";
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

            // Do not block capture retries using the browser's
            // approximate colour check. The server AI validates the photo.
            capturePhoto();
        }, CAPTURE_RETRY_DELAY_MS);
    }

    async function capturePhoto() {
        if (
            photoCaptureInProgress ||
            accessoryCheckInProgress ||
            !cameraStream ||
            !video.videoWidth ||
            !video.videoHeight
        ) {
            return;
        }

        // Require the glasses detector before accepting a photograph.
        accessoryCheckInProgress = true;
        cameraStatus.textContent = "Checking for eyeglasses…";

        try {
            const wearingGlasses = await checkForGlasses();
            if (wearingGlasses) {
                faceStableSince = null;
                cameraError.textContent =
                    "Please remove your eyeglasses before capture.";
                cameraError.hidden = false;
                cameraStatus.textContent =
                    "Eyeglasses detected. Remove them and try again.";
                return;
            }
        } catch (error) {
            cameraError.textContent =
                "The eyeglasses check is unavailable. Reload the page and try again.";
            cameraError.hidden = false;
            cameraStatus.textContent =
                "Photo capture is blocked until the glasses check works.";
            return;
        } finally {
            accessoryCheckInProgress = false;
        }

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
        stopFaceScan();

        // Crop a centered square from the camera frame.
        // This removes much of the distant background before validation.
        const sourceSide = Math.min(video.videoWidth, video.videoHeight);
        const sourceX = Math.floor((video.videoWidth - sourceSide) / 2);
        const sourceY = Math.floor((video.videoHeight - sourceSide) / 2);
        const outputSide = Math.min(sourceSide, 1200);
        const crop = {
            sourceX,
            sourceY,
            scale: outputSide / sourceSide
        };

        photoCanvas.width = outputSide;
        photoCanvas.height = outputSide;

        const context = photoCanvas.getContext("2d");
        if (!context) {
            photoCaptureInProgress = false;
            cameraError.textContent =
                "Photo capture is unavailable. Please reload the page and try again.";
            cameraError.hidden = false;
            return;
        }

        context.drawImage(
            video,
            sourceX, sourceY, sourceSide, sourceSide,
            0, 0, outputSide, outputSide
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

            reader.onload = async function () {
                const photoData = reader.result;
                const csrfInput = registrationForm
                    ? registrationForm.querySelector('[name="csrfmiddlewaretoken"]')
                    : null;
                const csrfToken = csrfInput ? csrfInput.value : "";
                const aiCheckUrl = whiteScanStatus
                    ? whiteScanStatus.dataset.aiCheckUrl
                    : "";

                if (!aiCheckUrl || !csrfToken) {
                    retryCapture(
                        "The AI check could not be started securely. Retrying automatically…"
                    );
                    return;
                }

                cameraStatus.textContent =
                    "AI is checking the person and white background…";

                try {
                    const response = await fetch(aiCheckUrl, {
                        method: "POST",
                        credentials: "same-origin",
                        headers: {
                            "Content-Type": "application/json",
                            "X-CSRFToken": csrfToken
                        },
                        body: JSON.stringify({ photo_data: photoData })
                    });

                    const result = await response.json();

                    if (!response.ok || !result.ok) {
                        retryCapture(
                            result.message ||
                            "AI did not approve the photo. Retrying automatically…"
                        );
                        return;
                    }

                    // Keep the exact frame that received AI approval.
                    photoInput.value = photoData;
                    photoPreview.src = photoData;
                    photoPreview.hidden = false;
                    video.hidden = true;
                    photoPlaceholder.hidden = true;
                    retakePhotoButton.hidden = false;
                    cameraError.hidden = true;
                    if (whiteScanStatus) {
                        whiteScanStatus.textContent =
                            "AI approved: person detected and background is white.";
                        whiteScanStatus.classList.add("is-white");
                        whiteScanStatus.classList.remove("is-not-white");
                    }
                    cameraStatus.textContent =
                        "AI approved the photograph. Review it before continuing.";
                    stopCamera();
                    photoCaptureInProgress = false;
                } catch (error) {
                    retryCapture(
                        "The AI check could not be reached. Retrying automatically…"
                    );
                }
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

        let requestedStream = null;

        try {
            requestedStream = await navigator.mediaDevices.getUserMedia({
                audio: false,
                video: {
                    facingMode: "user",
                    width: { ideal: 1280 },
                    height: { ideal: 720 }
                }
            });

            // A newer start/stop request superseded this request.
            if (startRequestId !== cameraStartRequestId) {
                requestedStream.getTracks().forEach(function (track) {
                    track.stop();
                });
                return;
            }

            cameraStream = requestedStream;
            video.srcObject = requestedStream;
            video.hidden = false;
            photoPreview.hidden = true;
            photoPlaceholder.hidden = true;

            await video.play();

            // Do not activate capture for a replaced or stopped stream.
            if (
                startRequestId !== cameraStartRequestId ||
                cameraStream !== requestedStream ||
                video.srcObject !== requestedStream
            ) {
                return;
            }

            capturePhotoButton.disabled = false;
            if (whiteScanStatus) {
                whiteScanStatus.textContent =
                    "AI will check the person and white background before accepting the photo.";
                whiteScanStatus.classList.remove("is-white", "is-not-white");
            }
            cameraStatus.textContent =
                "Loading face detection. You can also capture manually.";
            beginFaceScan();
        } catch (error) {
            // Never let a stale request stop a newer camera session.
            if (startRequestId !== cameraStartRequestId) {
                if (requestedStream) {
                    requestedStream.getTracks().forEach(function (track) {
                        track.stop();
                    });
                }
                return;
            }

            stopCamera();

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
            cameraError.textContent =
                `Camera error: ${error.name || "UnknownError"}. ${error.message || "Please try again."}`;
            cameraError.hidden = false;
            cameraStatus.textContent = "Camera capture is required.";
        }
    }

    if (video && photoCanvas && photoInput && startCameraButton) {
        startCameraButton.addEventListener("click", startCamera);

        capturePhotoButton.addEventListener("click", capturePhoto);

        retakePhotoButton.addEventListener("click", startCamera);

        if (photoInput.value) {
            photoPreview.src = photoInput.value;
            photoPreview.hidden = false;
            photoPlaceholder.hidden = true;
            retakePhotoButton.hidden = false;
            cameraStatus.textContent = "Previously captured photograph restored.";
        }

        window.addEventListener("pagehide", stopCamera);
    }

    if (registrationForm) {
        registrationForm.addEventListener("submit", function (event) {
            if (!photoInput || !photoInput.value) {
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
