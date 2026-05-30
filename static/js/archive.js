document.addEventListener("DOMContentLoaded", () => {
    const submissionType = document.getElementById("submission_type");
    const conditionalSections = document.querySelectorAll(".conditional-section");
    const sharedFields = document.getElementById("sharedFields");
    const typePrompt = document.getElementById("typePrompt");

    function updateConditionalSections() {
        if (!submissionType) return;

        const selectedType = submissionType.value;

        conditionalSections.forEach((section) => {
            section.classList.toggle("is-visible", section.dataset.type === selectedType);
        });

        if (sharedFields) {
            sharedFields.classList.toggle("is-visible", selectedType !== "");
        }

        if (typePrompt) {
            typePrompt.style.display = selectedType === "" ? "block" : "none";
        }
    }

    if (submissionType) {
        submissionType.addEventListener("change", updateConditionalSections);
        updateConditionalSections();
    }
});
