document.addEventListener("DOMContentLoaded", function () {
    const video = document.getElementById("passport-camera-video");
    const photoCanvas = document.getElementById("passport-camera-canvas");
    const whiteScanStatus = document.getElementById("passport-white-scan-status");
    const photoInput = document.getElementById("passport-photo-data");
    const photoTokenInput = document.getElementById("passport-photo-token");
    const acceptPhotoButton = document.getElementById("passport-camera-accept");
    const photoPreview = document.getElementById("passport-camera-image");
    let pendingPhotoData = "";
    let pendingPhotoToken = "";
    let previewRequestId = 0;
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
        previewRequestId += 1;
        photoCaptureInProgress = false;
        pendingPhotoData = "";
        pendingPhotoToken = "";
        if (photoInput) photoInput.value = "";
        if (photoTokenInput) photoTokenInput.value = "";
        if (photoPreview) {
            photoPreview.removeAttribute("src");
            photoPreview.hidden = true;
        }
        if (photoPlaceholder) photoPlaceholder.hidden = false;
        if (acceptPhotoButton) acceptPhotoButton.hidden = true;
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

        // Keep the face in the upper portion of a full portrait composition.
        // Smaller face limits leave room for the head, shoulders and upper chest.
        const circleCenterX = 0.5;
        const circleCenterY = 0.38;
        const circleRadiusX = 0.42;
        const circleRadiusY = 0.48;

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

        // Capture the same centered 9:16 crop shown in the live preview.
        const sourceWidth = video.videoWidth;
        const sourceHeight = video.videoHeight;
        const targetAspect = 4 / 5;
        const sourceAspect = sourceWidth / sourceHeight;

        let cropX = 0;
        let cropY = 0;
        let cropWidth = sourceWidth;
        let cropHeight = sourceHeight;

        if (sourceAspect > targetAspect) {
            cropWidth = sourceHeight * targetAspect;
            cropX = (sourceWidth - cropWidth) / 2;
        } else if (sourceAspect < targetAspect) {
            cropHeight = sourceWidth / targetAspect;
            cropY = (sourceHeight - cropHeight) / 2;
        }

        photoCanvas.width = Math.round(cropWidth);
        photoCanvas.height = Math.round(cropHeight);

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
            cropX, cropY, cropWidth, cropHeight,
            0, 0, photoCanvas.width, photoCanvas.height
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
                        if (cameraStream) capturePhotoButton.disabled = false;
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

        let requestedStream = null;

        try {
            requestedStream = await navigator.mediaDevices.getUserMedia({
                audio: false,
                video: {
                    facingMode: "user",
                    width: { ideal: 720 },
                    height: { ideal: 1280 },
                    aspectRatio: { ideal: 0.8 }
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

            const activeVideoTrack = requestedStream.getVideoTracks()[0];
            console.info(
                "Passport camera dimensions:",
                `${video.videoWidth}x${video.videoHeight}`,
                activeVideoTrack ? activeVideoTrack.getSettings() : {}
            );

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

        window.addEventListener("pagehide", stopCamera);
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
