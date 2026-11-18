import {
    constrainCropRect,
    exportSignatureCrop,
    initialCropRect,
    moveCropRect,
    resizeCropRect
} from "./signature-crop.mjs";

document.addEventListener("DOMContentLoaded", function () {
    const input = document.getElementById("id_signature_image");
    const form = document.querySelector(".registration-card form");
    const capturePanel = document.getElementById("signature-capture-panel");
    const video = document.getElementById("signature-camera-video");
    const captureCanvas = document.getElementById("signature-camera-canvas");
    const placeholder = document.getElementById("signature-camera-placeholder");
    const startButton = document.getElementById("signature-camera-start");
    const captureButton = document.getElementById("signature-camera-capture");
    const cropEditor = document.getElementById("signature-crop-editor");
    const cropViewport = document.getElementById("signature-crop-viewport");
    const cropSource = document.getElementById("signature-crop-source");
    const cropOverlay = document.getElementById("signature-crop-overlay");
    const cropSelection = document.getElementById("signature-crop-selection");
    const cropConfirmButton = document.getElementById("signature-crop-confirm");
    const cropRetakeButton = document.getElementById("signature-crop-retake");
    const review = document.getElementById("signature-review");
    const preview = document.getElementById("registration-signature-preview");
    const adjustCropButton = document.getElementById("signature-adjust-crop");
    const reviewRetakeButton = document.getElementById("signature-review-retake");
    const status = document.getElementById("registration-signature-upload-status");
    const error = document.getElementById("signature-camera-error");

    if (
        !input || !form || !capturePanel || !video || !captureCanvas ||
        !placeholder || !startButton || !captureButton || !cropEditor ||
        !cropViewport || !cropSource || !cropOverlay || !cropSelection ||
        !cropConfirmButton || !cropRetakeButton || !review || !preview ||
        !adjustCropButton || !reviewRetakeButton || !status || !error
    ) return;

    const MAX_SOURCE_DIMENSION = 1600;
    const MAX_SIGNATURE_BYTES = 2 * 1024 * 1024;
    const CAMERA_RETRY_DELAY_MS = 700;
    const MAX_CAMERA_ATTEMPTS = 3;

    let stream = null;
    let sourceBlob = null;
    let sourceUrl = null;
    let previewUrl = null;
    let cropRect = null;
    let previousCropBounds = null;
    let activePointer = null;
    let cameraStarting = false;
    let encoding = false;
    let cropEditing = false;
    let signatureConfirmed = false;

    function setSubmitButtonsDisabled(disabled) {
        form.querySelectorAll('button[type="submit"]').forEach((button) => {
            button.disabled = disabled;
        });
    }

    function showError(message) {
        error.textContent = message;
        error.hidden = false;
    }

    function clearError() {
        error.textContent = "";
        error.hidden = true;
    }

    function stopCamera() {
        if (stream) {
            stream.getTracks().forEach((track) => track.stop());
            stream = null;
        }
        video.srcObject = null;
        video.hidden = true;
        captureButton.disabled = true;
    }

    function releasePhotoUrls() {
        if (sourceUrl) URL.revokeObjectURL(sourceUrl);
        if (previewUrl) URL.revokeObjectURL(previewUrl);
        sourceUrl = null;
        previewUrl = null;
    }

    function clearSignature() {
        input.value = "";
        sourceBlob = null;
        cropRect = null;
        previousCropBounds = null;
        activePointer = null;
        cropEditing = false;
        signatureConfirmed = false;
        releasePhotoUrls();
        cropSource.removeAttribute("src");
        preview.removeAttribute("src");
        capturePanel.hidden = false;
        cropEditor.hidden = true;
        review.hidden = true;
        placeholder.hidden = false;
        startButton.hidden = false;
        setSubmitButtonsDisabled(false);
        status.textContent = "Start the camera to capture your signature.";
        clearError();
    }

    function cameraErrorMessage(exception) {
        if (exception && ["NotAllowedError", "SecurityError"].includes(exception.name)) {
            return "Camera permission was denied. Allow camera access in your browser settings, then try again.";
        }
        if (exception && ["NotFoundError", "OverconstrainedError"].includes(exception.name)) {
            return "No usable camera was found on this device.";
        }
        if (exception && exception.name === "NotReadableError") {
            return "The camera is busy. Close other apps using the camera and try again.";
        }
        return "The camera could not start. Check camera permissions and try again.";
    }

    async function acquireCamera() {
        let lastError = null;
        for (let attempt = 1; attempt <= MAX_CAMERA_ATTEMPTS; attempt += 1) {
            try {
                return await navigator.mediaDevices.getUserMedia({
                    audio: false,
                    video: {
                        facingMode: { ideal: "environment" },
                        width: { ideal: 1280 },
                        height: { ideal: 720 }
                    }
                });
            } catch (exception) {
                lastError = exception;
                if (exception && ["NotAllowedError", "SecurityError"].includes(exception.name)) {
                    throw exception;
                }
                if (exception && ["NotFoundError", "OverconstrainedError"].includes(exception.name)) {
                    try {
                        return await navigator.mediaDevices.getUserMedia({
                            audio: false,
                            video: {
                                facingMode: { ideal: "user" },
                                width: { ideal: 1280 },
                                height: { ideal: 720 }
                            }
                        });
                    } catch (fallbackError) {
                        throw fallbackError;
                    }
                }
                if (attempt < MAX_CAMERA_ATTEMPTS) {
                    await new Promise((resolve) => {
                        window.setTimeout(resolve, CAMERA_RETRY_DELAY_MS);
                    });
                }
            }
        }
        throw lastError || new Error("Camera unavailable.");
    }

    async function startCamera() {
        if (cameraStarting || encoding) return;
        cameraStarting = true;
        stopCamera();
        clearSignature();
        cameraStarting = true;
        clearError();
        status.textContent = "Waiting for camera permission…";

        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            showError("Camera access is unavailable. Open this page over HTTPS or localhost in a supported browser.");
            status.textContent = "Camera access is unavailable.";
            cameraStarting = false;
            return;
        }

        try {
            stream = await acquireCamera();
            video.srcObject = stream;
            video.hidden = false;
            placeholder.hidden = true;
            await video.play();
            captureButton.disabled = false;
            startButton.hidden = true;
            status.textContent = "Frame your complete signature, then capture the photograph.";
        } catch (exception) {
            stopCamera();
            status.textContent = "Camera is ready when you are.";
            showError(cameraErrorMessage(exception));
        } finally {
            cameraStarting = false;
        }
    }

    function showCropEditor(blob) {
        sourceBlob = blob;
        if (sourceUrl) URL.revokeObjectURL(sourceUrl);
        sourceUrl = URL.createObjectURL(blob);
        capturePanel.hidden = true;
        review.hidden = true;
        cropEditor.hidden = false;
        cropEditing = true;
        signatureConfirmed = false;
        setSubmitButtonsDisabled(true);
        status.textContent = "Drag the crop box around the complete signature.";
        cropSource.onload = function () {
            requestAnimationFrame(function () {
                const bounds = {
                    width: cropOverlay.clientWidth,
                    height: cropOverlay.clientHeight
                };
                if (!bounds.width || !bounds.height) {
                    showError("The crop editor could not be displayed. Retake the photograph and try again.");
                    return;
                }
                cropRect = initialCropRect(bounds);
                previousCropBounds = bounds;
                renderCropRect();
            });
        };
        cropSource.onerror = function () {
            showError("The captured photograph could not be opened. Retake it and try again.");
        };
        cropSource.src = sourceUrl;
    }

    function currentCropBounds() {
        return {
            width: cropOverlay.clientWidth,
            height: cropOverlay.clientHeight
        };
    }

    function renderCropRect() {
        if (!cropRect) return;
        const bounds = currentCropBounds();
        if (!bounds.width || !bounds.height) return;
        cropRect = constrainCropRect(cropRect, bounds);
        cropSelection.style.left = `${cropRect.x}px`;
        cropSelection.style.top = `${cropRect.y}px`;
        cropSelection.style.width = `${cropRect.width}px`;
        cropSelection.style.height = `${cropRect.height}px`;
    }

    function beginCropPointer(event) {
        if (!cropEditing || !cropRect || encoding) return;
        const handleElement = event.target.closest("[data-crop-handle]");
        const isSelection = event.target.closest("#signature-crop-selection");
        if (!handleElement && !isSelection) return;

        event.preventDefault();
        const bounds = currentCropBounds();
        activePointer = {
            pointerId: event.pointerId,
            mode: handleElement ? "resize" : "move",
            handle: handleElement ? handleElement.dataset.cropHandle : "",
            startX: event.clientX,
            startY: event.clientY,
            startRect: { ...cropRect },
            bounds
        };
        cropOverlay.setPointerCapture(event.pointerId);
    }

    function moveCropPointer(event) {
        if (!activePointer || event.pointerId !== activePointer.pointerId) return;
        event.preventDefault();
        const deltaX = event.clientX - activePointer.startX;
        const deltaY = event.clientY - activePointer.startY;
        cropRect = activePointer.mode === "move"
            ? moveCropRect(activePointer.startRect, deltaX, deltaY, activePointer.bounds)
            : resizeCropRect(
                activePointer.startRect,
                activePointer.handle,
                deltaX,
                deltaY,
                activePointer.bounds
            );
        renderCropRect();
    }

    function endCropPointer(event) {
        if (!activePointer || event.pointerId !== activePointer.pointerId) return;
        if (cropOverlay.hasPointerCapture(event.pointerId)) {
            cropOverlay.releasePointerCapture(event.pointerId);
        }
        activePointer = null;
    }

    function handleCropKeyboard(event) {
        if (!cropRect || encoding) return;
        const step = event.shiftKey ? 12 : 4;
        const directions = {
            ArrowLeft: [-step, 0],
            ArrowRight: [step, 0],
            ArrowUp: [0, -step],
            ArrowDown: [0, step]
        };
        const delta = directions[event.key];
        if (!delta) return;
        event.preventDefault();
        const bounds = currentCropBounds();
        const handle = event.target.closest("[data-crop-handle]");
        cropRect = handle
            ? resizeCropRect(cropRect, handle.dataset.cropHandle, delta[0], delta[1], bounds)
            : moveCropRect(cropRect, delta[0], delta[1], bounds);
        renderCropRect();
    }

    async function confirmCrop() {
        if (!sourceBlob || !cropRect || encoding) return;
        encoding = true;
        cropConfirmButton.disabled = true;
        cropRetakeButton.disabled = true;
        status.textContent = "Preparing the cropped JPEG…";
        clearError();
        try {
            const blob = await exportSignatureCrop(
                cropSource,
                cropRect,
                currentCropBounds(),
                { maxBytes: MAX_SIGNATURE_BYTES }
            );
            const file = new File([blob], "applicant-signature.jpg", {
                type: "image/jpeg",
                lastModified: Date.now()
            });
            const transfer = new DataTransfer();
            transfer.items.add(file);
            input.files = transfer.files;

            if (previewUrl) URL.revokeObjectURL(previewUrl);
            previewUrl = URL.createObjectURL(blob);
            preview.src = previewUrl;
            cropEditor.hidden = true;
            review.hidden = false;
            cropEditing = false;
            signatureConfirmed = true;
            setSubmitButtonsDisabled(false);
            status.textContent = "Cropped signature ready. Review it before submitting.";
        } catch (exception) {
            showError(exception.message || "The cropped signature could not be prepared. Adjust the crop or retake the photo.");
            status.textContent = "Adjust the crop or retake the photograph.";
        } finally {
            encoding = false;
            cropConfirmButton.disabled = false;
            cropRetakeButton.disabled = false;
        }
    }

    function adjustCrop() {
        if (!sourceBlob || encoding) return;
        input.value = "";
        signatureConfirmed = false;
        cropEditing = true;
        review.hidden = true;
        cropEditor.hidden = false;
        setSubmitButtonsDisabled(true);
        status.textContent = "Adjust the crop to include your complete signature.";
        clearError();
        requestAnimationFrame(function () {
            const bounds = currentCropBounds();
            if (previousCropBounds && bounds.width && bounds.height) {
                cropRect = constrainCropRect({
                    x: cropRect.x * bounds.width / previousCropBounds.width,
                    y: cropRect.y * bounds.height / previousCropBounds.height,
                    width: cropRect.width * bounds.width / previousCropBounds.width,
                    height: cropRect.height * bounds.height / previousCropBounds.height
                }, bounds);
            }
            previousCropBounds = bounds;
            renderCropRect();
        });
    }

    function captureFullPhotograph() {
        if (!stream || !video.videoWidth || !video.videoHeight || encoding) return;
        encoding = true;
        captureButton.disabled = true;
        clearError();
        status.textContent = "Capturing the full photograph…";

        const scale = Math.min(
            1,
            MAX_SOURCE_DIMENSION / Math.max(video.videoWidth, video.videoHeight)
        );
        const width = Math.max(1, Math.round(video.videoWidth * scale));
        const height = Math.max(1, Math.round(video.videoHeight * scale));
        captureCanvas.width = width;
        captureCanvas.height = height;
        const context = captureCanvas.getContext("2d", { alpha: false });
        if (!context) {
            encoding = false;
            stopCamera();
            startButton.hidden = false;
            placeholder.hidden = false;
            status.textContent = "Signature capture required.";
            showError("Signature capture is unavailable in this browser.");
            return;
        }
        context.fillStyle = "#fff";
        context.fillRect(0, 0, width, height);
        context.drawImage(video, 0, 0, width, height);
        stopCamera();

        captureCanvas.toBlob(function (blob) {
            encoding = false;
            if (!blob || blob.type !== "image/jpeg") {
                startButton.hidden = false;
                placeholder.hidden = false;
                showError("The photograph could not be prepared. Start the camera and try again.");
                status.textContent = "Signature capture required.";
                return;
            }
            showCropEditor(blob);
        }, "image/jpeg", 0.92);
    }

    function handleViewportResize() {
        if (cropEditor.hidden || !cropRect) return;
        const bounds = currentCropBounds();
        if (!bounds.width || !bounds.height) return;
        if (previousCropBounds) {
            cropRect = constrainCropRect({
                x: cropRect.x * bounds.width / previousCropBounds.width,
                y: cropRect.y * bounds.height / previousCropBounds.height,
                width: cropRect.width * bounds.width / previousCropBounds.width,
                height: cropRect.height * bounds.height / previousCropBounds.height
            }, bounds);
        }
        previousCropBounds = bounds;
        renderCropRect();
    }

    startButton.addEventListener("click", startCamera);
    captureButton.addEventListener("click", captureFullPhotograph);
    cropConfirmButton.addEventListener("click", confirmCrop);
    cropRetakeButton.addEventListener("click", startCamera);
    reviewRetakeButton.addEventListener("click", startCamera);
    adjustCropButton.addEventListener("click", adjustCrop);

    cropOverlay.addEventListener("pointerdown", beginCropPointer);
    cropOverlay.addEventListener("pointermove", moveCropPointer);
    cropOverlay.addEventListener("pointerup", endCropPointer);
    cropOverlay.addEventListener("pointercancel", endCropPointer);
    cropOverlay.addEventListener("lostpointercapture", function () {
        activePointer = null;
    });
    cropOverlay.addEventListener("keydown", handleCropKeyboard);
    window.addEventListener("resize", handleViewportResize);

    form.addEventListener("submit", function (event) {
        if (encoding || cropEditing || !signatureConfirmed || !input.files.length) {
            event.preventDefault();
            if (cropEditing || encoding) {
                showError("Finish and confirm the signature crop before submitting.");
            } else {
                showError("Capture, crop, and confirm your handwritten signature before submitting.");
                capturePanel.hidden = false;
                startButton.scrollIntoView({ behavior: "smooth", block: "center" });
                startButton.focus();
            }
        }
    });

    window.addEventListener("pagehide", function () {
        stopCamera();
        releasePhotoUrls();
    });
});
