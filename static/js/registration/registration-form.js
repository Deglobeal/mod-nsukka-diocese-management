document.addEventListener("DOMContentLoaded", function () {
    const form = document.querySelector(".registration-card form");
    if (!form) return;

    const sections = Array.from(
        form.querySelectorAll(".registration-section")
    );
    const submitButton = form.querySelector('button[type="submit"]');

    if (!sections.length || !submitButton) return;

    form.noValidate = true;

    /*
     * Preserve the existing Deanery -> Parish -> Station filtering.
     */
    const deanery = document.getElementById("id_deanery");
    const parish = document.getElementById("id_parish");
    const station = document.getElementById("id_station");

    function filterOptions(select, attribute, selectedValue) {
        if (!select) return;

        Array.from(select.options).forEach(function (option) {
            const parentValue = option.dataset[attribute];
            const allowed = !option.value || !selectedValue ||
                parentValue === selectedValue;

            option.hidden = !allowed;
            option.disabled = !allowed;
        });

        const current = select.selectedOptions[0];
        if (current && current.disabled) select.value = "";
    }

    function updateStations() {
        filterOptions(station, "parishId", parish ? parish.value : "");
    }

    function updateParishes() {
        filterOptions(parish, "deaneryId", deanery ? deanery.value : "");
        updateStations();
    }

    if (deanery) deanery.addEventListener("change", updateParishes);
    if (parish) parish.addEventListener("change", updateStations);
    updateParishes();


    // State of Origin -> Local Government Area.
    const stateOfOrigin = document.getElementById("id_state_of_origin");
    const localGovernmentArea = document.getElementById("id_local_government_area");

    if (stateOfOrigin && localGovernmentArea) {
        const dataUrl = stateOfOrigin.dataset.lgaDataUrl;
        let lgaData = null;

        function populateLgas(preserveSelection) {
            const previous = preserveSelection ? localGovernmentArea.value : "";
            const state = stateOfOrigin.value;
            const lgas = lgaData && Array.isArray(lgaData[state])
                ? lgaData[state]
                : [];

            localGovernmentArea.replaceChildren();
            const placeholder = document.createElement("option");
            placeholder.value = "";
            placeholder.textContent = "Select LGA (optional)";
            localGovernmentArea.appendChild(placeholder);

            lgas.forEach(function (lga) {
                const option = document.createElement("option");
                option.value = lga;
                option.textContent = lga;
                localGovernmentArea.appendChild(option);
            });

            localGovernmentArea.value = lgas.includes(previous) ? previous : "";
        }

        stateOfOrigin.addEventListener("change", function () {
            if (lgaData) populateLgas(false);
        });

        if (dataUrl) {
            fetch(dataUrl, { credentials: "same-origin" })
                .then(function (response) {
                    if (!response.ok) throw new Error("LGA data request failed");
                    return response.json();
                })
                .then(function (data) {
                    lgaData = data;
                    populateLgas(true);
                })
                .catch(function (error) {
                    // Server-rendered options remain available if loading fails.
                    console.error("Could not load state/LGA data.", error);
                });
        }
    }

    /*
     * Build the step controls dynamically so the approved field markup
     * and form content remain unchanged.
     */
    const progress = document.createElement("div");
    progress.className = "registration-progress";
    progress.setAttribute("aria-label", "Registration progress");

    const progressText = document.createElement("p");
    progressText.className = "registration-progress-text";
    progressText.setAttribute("aria-live", "polite");
    progressText.setAttribute("aria-atomic", "true");

    const progressTrack = document.createElement("div");
    progressTrack.className = "registration-progress-track";
    progressTrack.setAttribute("role", "progressbar");
    progressTrack.setAttribute("aria-valuemin", "1");
    progressTrack.setAttribute("aria-valuemax", String(sections.length));
    progressTrack.setAttribute("aria-valuenow", "1");
    progressTrack.setAttribute("aria-label", "Current registration section");

    const progressFill = document.createElement("div");
    progressFill.className = "registration-progress-fill";
    progressTrack.appendChild(progressFill);
    progress.append(progressText, progressTrack);

    sections[0].before(progress);

    // Validate custom rules before allowing an applicant to advance.
    const phoneFieldIds = [
        "id_phone_number",
        "id_next_of_kin_phone",
        "id_emergency_contact_phone",
        "id_emergency_contact_2_phone",
        "id_sponsor_additional_phone"
    ];

    const nameFieldIds = [
        "id_first_name",
        "id_middle_name",
        "id_last_name",
        "id_next_of_kin_name",
        "id_emergency_contact_name",
        "id_emergency_contact_2_name"
    ];

    function validateCustomField(field) {
        if (!field) return true;

        const value = field.value.trim();
        let message = "";

        if (phoneFieldIds.includes(field.id) && value) {
            const normalized = value.replace(/[\s()-]/g, "");
            const localValid = /^0[0-9]{10}$/.test(normalized);
            const internationalValid = /^\+234[0-9]{10}$/.test(normalized);

            if (!localValid && !internationalValid) {
                message =
                    "Use a Nigerian number such as 08012345678 or +2348012345678.";
            }
        }

        if (nameFieldIds.includes(field.id) && value) {
            const allowed = /^[\p{L}\p{M} '\u2019-]+$/u.test(value);
            const letterCount = (value.match(/\p{L}/gu) || []).length;

            if (!allowed || letterCount < 2) {
                message =
                    "Enter a valid name using at least two letters. Numbers and symbols are not allowed.";
            }
        }

        field.setCustomValidity(message);
        return !message;
    }

    function validateSection(section, focusInvalid = true) {
        const fields = Array.from(
            section.querySelectorAll("input, select, textarea")
        ).filter(function (field) {
            return !field.disabled &&
                field.type !== "button" &&
                field.type !== "submit" &&
                field.type !== "hidden";
        });

        fields.forEach(validateCustomField);

        // Emergency contacts must differ by name, phone, and relationship.
        const contact2NameField = document.getElementById(
            "id_emergency_contact_2_name"
        );

        if (contact2NameField && section.contains(contact2NameField)) {
            const contact1NameField = document.getElementById(
                "id_emergency_contact_name"
            );
            const contact1PhoneField = document.getElementById(
                "id_emergency_contact_phone"
            );
            const contact2PhoneField = document.getElementById(
                "id_emergency_contact_2_phone"
            );
            const contact1RelationshipField = document.getElementById(
                "id_emergency_contact_relationship"
            );
            const contact2RelationshipField = document.getElementById(
                "id_emergency_contact_2_relationship"
            );

            function normalizeContactName(value) {
                return (value || "").trim().replace(/\\s+/g, " ").toLocaleLowerCase();
            }

            function normalizeContactPhone(value) {
                let digits = (value || "").replace(/\\D/g, "");
                if (digits.length === 13 && digits.startsWith("234")) {
                    digits = "0" + digits.slice(3);
                }
                return digits;
            }

            function normalizeRelationship(value) {
                return (value || "").trim().toLocaleLowerCase();
            }

            if (contact2NameField) {
                const duplicateName =
                    normalizeContactName(contact1NameField && contact1NameField.value) &&
                    normalizeContactName(contact1NameField && contact1NameField.value) ===
                        normalizeContactName(contact2NameField.value);

                contact2NameField.setCustomValidity(
                    duplicateName
                        ? "Emergency Contact 1 and Emergency Contact 2 must be different people."
                        : ""
                );
            }

            if (contact2PhoneField) {
                const phone1 = normalizeContactPhone(
                    contact1PhoneField && contact1PhoneField.value
                );
                const phone2 = normalizeContactPhone(contact2PhoneField.value);
                const duplicatePhone = phone1 && phone1 === phone2;

                contact2PhoneField.setCustomValidity(
                    duplicatePhone
                        ? "Emergency Contact 1 and Emergency Contact 2 must have different phone numbers."
                        : ""
                );
            }

            if (contact2RelationshipField) {
                const relationship1 = normalizeRelationship(
                    contact1RelationshipField && contact1RelationshipField.value
                );
                const relationship2 = normalizeRelationship(
                    contact2RelationshipField.value
                );
                const duplicateRelationship =
                    relationship1 && relationship1 === relationship2;

                contact2RelationshipField.setCustomValidity(
                    duplicateRelationship
                        ? "Emergency Contact 1 and Emergency Contact 2 must have different relationships."
                        : ""
                );
            }
        }

        const invalidField = fields.find(function (field) {
            return !field.checkValidity();
        });

        if (invalidField) {
            if (focusInvalid) {
                invalidField.reportValidity();
                invalidField.focus();
                invalidField.scrollIntoView({
                    behavior: "smooth",
                    block: "center"
                });
            }
            return false;
        }

        // Camera photo is a required step-one item.
        const photoInput = document.getElementById("passport-photo-data");
        if (photoInput && section.contains(photoInput) && !photoInput.value) {
            const cameraError = document.getElementById("passport-camera-error");
            const startButton = document.getElementById("passport-camera-start");

            if (cameraError) {
                cameraError.textContent =
                    "Capture and accept your passport photograph before continuing.";
                cameraError.hidden = false;
            }

            if (startButton) {
                startButton.focus();
                startButton.scrollIntoView({
                    behavior: "smooth",
                    block: "center"
                });
            }
            return false;
        }

        // Require signature capture before leaving the signature section.
        const signatureInput = document.getElementById("id_signature_image");
        if (
            signatureInput &&
            section.contains(signatureInput) &&
            (!signatureInput.files || signatureInput.files.length === 0)
        ) {
            const signatureError = document.getElementById("signature-camera-error");
            const signatureStart = document.getElementById("signature-camera-start");
            if (signatureError) {
                signatureError.textContent =
                    "Capture your handwritten signature before continuing.";
                signatureError.hidden = false;
            }
            if (signatureStart) {
                signatureStart.focus();
                signatureStart.scrollIntoView({
                    behavior: "smooth",
                    block: "center"
                });
            }
            return false;
        }

        return true;
    }

    phoneFieldIds.concat(nameFieldIds).forEach(function (id) {
        const field = document.getElementById(id);
        if (!field) return;

        field.addEventListener("input", function () {
            validateCustomField(field);
        });
        field.addEventListener("blur", function () {
            validateCustomField(field);
        });
        field.addEventListener("change", function () {
            validateCustomField(field);
        });
    });

    const navigations = sections.map(function (section, index) {
        const navigation = document.createElement("nav");
        navigation.className = "registration-step-navigation";
        navigation.setAttribute(
            "aria-label",
            "Navigation for section " + (index + 1)
        );

        const previous = document.createElement("button");
        previous.type = "button";
        previous.className =
            "registration-step-button registration-step-button-secondary";
        previous.textContent = "Previous";
        previous.hidden = index === 0;
        previous.addEventListener("click", function () {
            showSection(index - 1, true);
        });

        const next = document.createElement("button");
        next.type = "button";
        next.className =
            "registration-step-button registration-step-button-primary";
        next.textContent = "Next";
        next.hidden = index === sections.length - 1;
        next.addEventListener("click", function () {
            if (!validateSection(sections[index])) return;
            showSection(index + 1, true);
        });

        if (index === sections.length - 1) {
            navigation.append(previous, submitButton);
        } else {
            navigation.append(previous, next);
        }
        section.after(navigation);

        return navigation;
    });

    // Final safety check: no invalid section may be submitted.
    form.addEventListener("submit", function (event) {
        for (let index = 0; index < sections.length; index += 1) {
            if (!validateSection(sections[index], false)) {
                event.preventDefault();

                // Reveal the invalid section before reporting/focusing its field.
                showSection(index, true);
                validateSection(sections[index], true);
                return;
            }
        }
    });

    let currentIndex = 0;

    function showSection(index, moveFocus) {
        if (index < 0 || index >= sections.length) return;

        currentIndex = index;

        sections.forEach(function (section, sectionIndex) {
            const active = sectionIndex === currentIndex;
            section.hidden = !active;
            section.setAttribute("aria-hidden", String(!active));

            const navigation = navigations[sectionIndex];
            navigation.hidden = !active;
            navigation.setAttribute("aria-hidden", String(!active));
        });

        const currentNumber = currentIndex + 1;
        progressText.textContent =
            "Section " + currentNumber + " of " + sections.length;
        progressTrack.setAttribute("aria-valuenow", String(currentNumber));
        progressFill.style.width =
            (currentNumber / sections.length * 100) + "%";

        submitButton.hidden = currentIndex !== sections.length - 1;

        if (moveFocus) {
            const heading = sections[currentIndex].querySelector(
                ".registration-section-title"
            );

            if (heading) {
                if (!heading.hasAttribute("tabindex")) {
                    heading.setAttribute("tabindex", "-1");
                }
                heading.focus();
            }

            sections[currentIndex].scrollIntoView({
                behavior: "auto",
                block: "start"
            });
        }
    }

    /*
     * If the server returned form errors, open the section containing
     * the first field error instead of leaving that field hidden.
     */
    let initialIndex = 0;
    const firstErrorLink = form.querySelector(
        ".registration-error-summary a[href^='#']"
    );

    if (firstErrorLink) {
        const targetId = firstErrorLink.getAttribute("href").slice(1);
        let targetField = null;

        try {
            targetField = document.getElementById(
                decodeURIComponent(targetId)
            );
        } catch (error) {
            targetField = document.getElementById(targetId);
        }

        const errorSection = targetField
            ? targetField.closest(".registration-section")
            : null;

        if (errorSection) {
            const errorIndex = sections.indexOf(errorSection);
            if (errorIndex >= 0) initialIndex = errorIndex;
        }
    }

    showSection(initialIndex, false);

    if (firstErrorLink && initialIndex > 0) {
        const errorSection = sections[initialIndex];
        const targetId = firstErrorLink.getAttribute("href").slice(1);
        const targetField = document.getElementById(targetId);

        if (targetField && errorSection.contains(targetField)) {
            targetField.focus();
        }
    }
});
