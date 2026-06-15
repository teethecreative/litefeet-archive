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

function initProfileControls() {
    const controlBlocks = document.querySelectorAll("[data-profile-controls]");

    controlBlocks.forEach((controls) => {
        const section = controls.closest(".content-section");
        if (!section) return;

        const grid = section.querySelector(".dancer-grid");
        if (!grid) return;

        const searchInput = controls.querySelector("[data-profile-search]");
        const sortSelect = controls.querySelector("[data-profile-sort]");
        const roleSelect = controls.querySelector("[data-profile-role]");
        const statusSelect = controls.querySelector("[data-profile-status]");

        const applyControls = () => {
            const cards = Array.from(grid.querySelectorAll("[data-profile-card]"));
            const searchValue = (searchInput?.value || "").trim().toLowerCase();
            const roleValue = (roleSelect?.value || "").trim().toLowerCase();
            const statusValue = (statusSelect?.value || "").trim().toLowerCase();
            const sortValue = (sortSelect?.value || "az").trim().toLowerCase();

            cards.forEach((card) => {
                const searchable = card.dataset.search || "";
                const roles = card.dataset.roles || "";
                const status = card.dataset.status || "";

                const matchesSearch = !searchValue || searchable.includes(searchValue);
                const matchesRole = !roleValue || roles.includes(roleValue);
                const matchesStatus = !statusValue || status === statusValue;

                card.hidden = !(matchesSearch && matchesRole && matchesStatus);
            });

            cards.sort((a, b) => {
                if (sortValue === "za") {
                    return (b.dataset.name || "").localeCompare(a.dataset.name || "");
                }

                if (sortValue === "status") {
                    const statusCompare = (a.dataset.status || "").localeCompare(b.dataset.status || "");
                    if (statusCompare !== 0) return statusCompare;
                }

                return (a.dataset.name || "").localeCompare(b.dataset.name || "");
            });

            cards.forEach((card) => grid.appendChild(card));
        };

        [searchInput, sortSelect, roleSelect, statusSelect].forEach((input) => {
            if (input) {
                input.addEventListener("input", applyControls);
                input.addEventListener("change", applyControls);
            }
        });

        applyControls();
    });
}

document.addEventListener("DOMContentLoaded", initProfileControls);
