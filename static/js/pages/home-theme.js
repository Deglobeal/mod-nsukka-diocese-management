(function () {
    "use strict";

    var button = document.getElementById("home-theme-switch");
    if (!button) return;

    var label = button.querySelector(".home-theme-toggle-label");
    var storageKey = "mod-nsukka-home-theme";
    var themes = {
        catholic: {
            label: "Theme: Catholic Heritage",
            nextLabel: "Switch to Command & Discipline theme"
        },
        command: {
            label: "Theme: Command & Discipline",
            nextLabel: "Switch to Catholic Heritage theme"
        }
    };

    function readSavedTheme() {
        try {
            var saved = window.localStorage.getItem(storageKey);
            return saved === "command" ? "command" : "catholic";
        } catch (error) {
            return "catholic";
        }
    }

    function applyTheme(theme, save) {
        var selected = theme === "command" ? "command" : "catholic";
        var details = themes[selected];

        if (selected === "command") {
            document.body.setAttribute("data-mod-theme", "command");
        } else {
            document.body.removeAttribute("data-mod-theme");
        }

        if (label) label.textContent = details.label;
        button.setAttribute("aria-label", details.nextLabel);
        button.setAttribute("aria-pressed", String(selected === "command"));

        if (save) {
            try {
                window.localStorage.setItem(storageKey, selected);
            } catch (error) {
                // Theme switching still works for this page view.
            }
        }
    }

    applyTheme(readSavedTheme(), false);

    button.addEventListener("click", function () {
        var current = document.body.getAttribute("data-mod-theme");
        applyTheme(current === "command" ? "catholic" : "command", true);
    });
}());
