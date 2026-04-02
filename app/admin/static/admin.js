const flashNode = document.getElementById("admin-flash");

function showFlash(message, isError = false) {
    if (!flashNode) {
        return;
    }
    flashNode.textContent = message;
    flashNode.classList.remove("hidden", "error");
    if (isError) {
        flashNode.classList.add("error");
    }
}

async function runSync(button) {
    const syncUrl = button.dataset.syncUrl;
    const accountId = button.dataset.accountId;
    if (!syncUrl || !accountId) {
        return;
    }

    button.disabled = true;
    const previousLabel = button.textContent;
    button.textContent = "Syncing...";

    try {
        const response = await fetch(syncUrl, {
            method: "POST",
            headers: {
                "Accept": "application/json",
            },
        });
        const payload = await response.json();
        if (!response.ok) {
            const detail = payload.detail?.message || payload.detail || "Sync failed.";
            showFlash(`Account ${accountId}: ${detail}`, true);
            return;
        }
        const status = payload.status || payload.payload?.status || "success";
        showFlash(`Account ${accountId}: sync job finished with status ${status}.`);
        window.setTimeout(() => window.location.reload(), 900);
    } catch (error) {
        showFlash(`Account ${accountId}: ${error}`, true);
    } finally {
        button.disabled = false;
        button.textContent = previousLabel;
    }
}

document.querySelectorAll(".sync-button").forEach((button) => {
    button.addEventListener("click", () => {
        void runSync(button);
    });
});
