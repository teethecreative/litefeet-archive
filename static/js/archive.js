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

                card.hidden = !(matchesSearch && matchesRole && matchesStatus && matchesActivity);
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

function initPagedTables() {
    const wrappers = document.querySelectorAll("[data-paged-table-wrap]");

    wrappers.forEach((wrapper) => {
        const table = wrapper.querySelector("[data-paged-table]");
        if (!table) return;

        const rows = Array.from(table.querySelectorAll("[data-paged-row]"));
        const pageSize = parseInt(table.dataset.pageSize || "8", 10);
        const prevButton = wrapper.querySelector("[data-page-prev]");
        const nextButton = wrapper.querySelector("[data-page-next]");
        const status = wrapper.querySelector("[data-page-status]");

        let page = 1;
        const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));

        const renderPage = () => {
            rows.forEach((row, index) => {
                const start = (page - 1) * pageSize;
                const end = start + pageSize;
                row.hidden = !(index >= start && index < end);
            });

            if (status) {
                status.textContent = `Page ${page} of ${totalPages}`;
            }

            if (prevButton) {
                prevButton.disabled = page <= 1;
            }

            if (nextButton) {
                nextButton.disabled = page >= totalPages;
            }
        };

        if (prevButton) {
            prevButton.addEventListener("click", () => {
                page = Math.max(1, page - 1);
                renderPage();
            });
        }

        if (nextButton) {
            nextButton.addEventListener("click", () => {
                page = Math.min(totalPages, page + 1);
                renderPage();
            });
        }

        if (rows.length <= pageSize) {
            const pager = wrapper.querySelector(".table-pager");
            if (pager) {
                pager.hidden = true;
            }
        }

        renderPage();
    });
}

document.addEventListener("DOMContentLoaded", initPagedTables);

function initMusicFeedSearch() {
    const input = document.getElementById("musicFeedSearch");
    const list = document.getElementById("musicFeedList");

    if (!input || !list) {
        return;
    }

    const cards = Array.from(list.querySelectorAll(".music-release-card"));

    input.addEventListener("input", () => {
        const query = input.value.trim().toLowerCase();

        cards.forEach((card) => {
            const haystack = (card.dataset.search || "").toLowerCase();
            card.hidden = query && !haystack.includes(query);
        });
    });
}

document.addEventListener("DOMContentLoaded", initMusicFeedSearch);


function initPeopleDirectoryFilters() {
    const grid = document.querySelector("[data-profile-grid]");
    const cards = Array.from(document.querySelectorAll("[data-profile-card]"));
    const searchInput = document.querySelector("[data-profile-search]");
    const sortSelect = document.querySelector("[data-profile-sort]");
    const roleFilter = document.querySelector("[data-role-filter]");
    const activityFilter = document.querySelector("[data-activity-filter]");

    if (!grid || !cards.length) return;

    function applyFilters() {
        const query = searchInput ? searchInput.value.trim().toLowerCase() : "";
        const selectedRole = roleFilter ? roleFilter.value.trim().toLowerCase() : "";
        const selectedActivity = activityFilter ? activityFilter.value.trim().toLowerCase() : "";

        cards.forEach((card) => {
            const searchText = (card.dataset.search || "").toLowerCase();
            const roleText = (card.dataset.role || "").toLowerCase();
            const activityText = (card.dataset.activity || "unknown").toLowerCase();

            const matchesSearch = !query || searchText.includes(query);
            const matchesRole = !selectedRole || roleText.includes(selectedRole);
            const matchesActivity = !selectedActivity || activityText === selectedActivity;

            card.hidden = !(matchesSearch && matchesRole && matchesActivity);
        });

        applySort();
    }

    function applySort() {
        const sortValue = sortSelect ? sortSelect.value : "az";

        const sorted = cards.slice().sort((a, b) => {
            const nameA = (a.dataset.name || "").toLowerCase();
            const nameB = (b.dataset.name || "").toLowerCase();

            if (sortValue === "za") {
                return nameB.localeCompare(nameA);
            }

            return nameA.localeCompare(nameB);
        });

        sorted.forEach((card) => grid.appendChild(card));
    }

    if (searchInput) searchInput.addEventListener("input", applyFilters);
    if (sortSelect) sortSelect.addEventListener("change", applyFilters);
    if (roleFilter) roleFilter.addEventListener("change", applyFilters);
    if (activityFilter) activityFilter.addEventListener("change", applyFilters);

    applyFilters();
}

document.addEventListener("DOMContentLoaded", initPeopleDirectoryFilters);


function initGlobalMusicPlayerBehavior() {
    const playControls = Array.from(document.querySelectorAll(".ranking-play-control"));
    const nowPlayingBar = document.getElementById("globalNowPlayingBar");
    const nowPlayingTitle = document.getElementById("globalNowPlayingTitle");
    const nowPlayingMeta = document.getElementById("globalNowPlayingMeta");
    const stopButton = document.getElementById("globalNowPlayingStop");

    if (!playControls.length) return;

    function pauseAllAudioExcept(exceptAudio) {
        document.querySelectorAll("audio").forEach((audio) => {
            if (audio !== exceptAudio) {
                audio.pause();
            }
        });
    }

    function closeOtherPlayers(currentDetails) {
        playControls.forEach((details) => {
            if (details !== currentDetails) {
                details.removeAttribute("open");
            }
        });
    }

    function updateNowPlaying(details) {
        if (!nowPlayingBar || !nowPlayingTitle || !nowPlayingMeta) return;

        const title = details.dataset.nowPlayingTitle || "Unknown track";
        const producer = details.dataset.nowPlayingProducer || "Unknown producer";
        const source = details.dataset.nowPlayingSource || "";

        nowPlayingTitle.textContent = title;
        nowPlayingMeta.textContent = `${producer} · ${source}`;
        nowPlayingBar.hidden = false;
    }

    function clearNowPlaying() {
        pauseAllAudioExcept(null);

        playControls.forEach((details) => {
            details.removeAttribute("open");
        });

        if (nowPlayingBar) nowPlayingBar.hidden = true;
    }

    playControls.forEach((details) => {
        details.addEventListener("toggle", () => {
            if (!details.open) return;

            closeOtherPlayers(details);
            pauseAllAudioExcept(null);
            updateNowPlaying(details);
        });

        details.querySelectorAll("audio").forEach((audio) => {
            audio.addEventListener("play", () => {
                closeOtherPlayers(details);
                pauseAllAudioExcept(audio);
                updateNowPlaying(details);
            });

            audio.addEventListener("ended", () => {
                if (nowPlayingBar) nowPlayingBar.hidden = true;
            });
        });
    });

    if (stopButton) {
        stopButton.addEventListener("click", clearNowPlaying);
    }
}

document.addEventListener("DOMContentLoaded", initGlobalMusicPlayerBehavior);

function initMusicPlayCounting() {
    const playControls = Array.from(document.querySelectorAll(".ranking-play-control[data-play-item-id]"));
    const recentPlayKeys = new Map();

    if (!playControls.length) return;

    function updatePlayDisplays(itemId, playCount) {
        document.querySelectorAll(`.ranking-play-control[data-play-item-id="${itemId}"]`).forEach((control) => {
            const display = control.querySelector("[data-play-count-display]");
            if (display) display.textContent = playCount;
            control.dataset.playCount = playCount;
        });

        document.querySelectorAll(`[data-play-count-inline="${itemId}"]`).forEach((display) => {
            display.textContent = playCount;
        });
    }

    function shouldCountPlay(itemId) {
        const now = Date.now();
        const last = recentPlayKeys.get(itemId) || 0;

        if (now - last < 30000) {
            return false;
        }

        recentPlayKeys.set(itemId, now);
        return true;
    }

    function recordPlay(control) {
        const itemId = control.dataset.playItemId;
        if (!itemId || !shouldCountPlay(itemId)) return;

        fetch(`/music/${itemId}/play`, {
            method: "POST",
            headers: {
                "X-Requested-With": "XMLHttpRequest"
            }
        })
            .then((response) => response.json())
            .then((data) => {
                if (data && data.ok) {
                    updatePlayDisplays(itemId, data.play_count);
                }
            })
            .catch(() => {});
    }

    playControls.forEach((control) => {
        control.addEventListener("toggle", () => {
            if (control.open) {
                recordPlay(control);
            }
        });

        control.querySelectorAll("audio").forEach((audio) => {
            audio.addEventListener("play", () => {
                recordPlay(control);
            });
        });
    });
}

document.addEventListener("DOMContentLoaded", initMusicPlayCounting);


function initTopPlaylistPlayerBehavior() {
    const playButtons = Array.from(document.querySelectorAll(".playlist-play-button[data-play-item-id]"));
    if (!playButtons.length) return;

    const recentPlayKeys = new Map();

    function findPlayer(button) {
        const section = button.closest("section");
        return (section && section.querySelector("[data-top-playlist-player]")) || document.querySelector("[data-top-playlist-player]");
    }

    function updatePlayDisplays(itemId, playCount) {
        document.querySelectorAll(`[data-play-item-id="${itemId}"]`).forEach((control) => {
            control.dataset.playCount = playCount;
            const display = control.querySelector("[data-play-count-display]");
            if (display) display.textContent = playCount;
        });

        document.querySelectorAll(`[data-play-count-inline="${itemId}"]`).forEach((display) => {
            display.textContent = playCount;
        });
    }

    function shouldCountPlay(itemId) {
        if (window.LITEFEET_LEDGER_IS_ADMIN) return false;

        const now = Date.now();
        const last = recentPlayKeys.get(itemId) || 0;

        if (now - last < 30000) return false;

        recentPlayKeys.set(itemId, now);
        return true;
    }

    function recordPlay(itemId) {
        if (!itemId || !shouldCountPlay(itemId)) return Promise.resolve();

        return fetch(`/music/${itemId}/play`, {
            method: "POST",
            headers: {
                "X-Requested-With": "XMLHttpRequest"
            }
        })
            .then((response) => response.json())
            .then((data) => {
                if (data && data.ok && !data.admin_ignored) {
                    updatePlayDisplays(itemId, data.play_count);
                }
            })
            .catch(() => {});
    }

    function clearPlayerBody(bodyTarget) {
        while (bodyTarget.firstChild) {
            bodyTarget.removeChild(bodyTarget.firstChild);
        }
    }

    function renderLedgerAudioPlayer(button) {
        const player = findPlayer(button);
        if (!player) return;

        const itemId = button.dataset.playItemId || "";
        const title = button.dataset.playerTitle || "Untitled release";
        const artist = button.dataset.playerArtist || "Unknown producer";
        const platform = button.dataset.playerPlatform || "";
        const playableUrl = button.dataset.playerPlayableUrl || "";

        const titleTarget = player.querySelector("[data-player-title]");
        const metaTarget = player.querySelector("[data-player-meta]");
        const bodyTarget = player.querySelector("[data-player-body]");

        if (titleTarget) titleTarget.textContent = title;
        if (metaTarget) metaTarget.textContent = [artist, platform].filter(Boolean).join(" · ");

        if (bodyTarget) {
            clearPlayerBody(bodyTarget);

            const audio = document.createElement("audio");
            audio.controls = true;
            audio.autoplay = true;
            audio.preload = "none";
            audio.src = playableUrl;

            audio.addEventListener("play", () => recordPlay(itemId));

            bodyTarget.appendChild(audio);

            audio.play().catch(() => {});
        }

        document.querySelectorAll(".playlist-play-button.is-playing").forEach((activeButton) => {
            activeButton.classList.remove("is-playing");
        });

        button.classList.add("is-playing");

        player.hidden = false;
        player.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    function openExternalSource(button) {
        const itemId = button.dataset.playItemId || "";
        const sourceUrl = button.dataset.playerSourceUrl || "";

        recordPlay(itemId).finally(() => {
            if (sourceUrl) {
                window.open(sourceUrl, "_blank", "noopener");
            }
        });
    }

    function handlePlay(button) {
        const playableUrl = button.dataset.playerPlayableUrl || "";

        if (playableUrl) {
            renderLedgerAudioPlayer(button);
            return;
        }

        openExternalSource(button);
    }

    playButtons.forEach((button) => {
        const playableUrl = button.dataset.playerPlayableUrl || "";
        const sourceUrl = button.dataset.playerSourceUrl || "";

        if (!playableUrl && sourceUrl) {
            button.classList.add("external-source-play-button");
            button.setAttribute("title", "Open source and count Ledger Play");
        }

        button.addEventListener("click", () => handlePlay(button));
    });
}

document.addEventListener("DOMContentLoaded", initTopPlaylistPlayerBehavior);
