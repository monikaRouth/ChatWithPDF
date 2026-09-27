let navigationInProgress = false;

async function navigateWithoutReload(url, addToHistory = true) {
    if (navigationInProgress) return;
    navigationInProgress = true;

    try {
        const response = await fetch(url, {
            headers: { "X-Requested-With": "XMLHttpRequest" },
        });
        if (!response.ok) throw new Error(`Navigation failed: ${response.status}`);

        const html = await response.text();
        const parsedPage = new DOMParser().parseFromString(html, "text/html");
        document.body.innerHTML = parsedPage.body.innerHTML;
        document.title = parsedPage.title;

        if (addToHistory) history.pushState({}, "", url);
        initializeApp();

        const hash = new URL(url, window.location.origin).hash;
        if (hash) document.querySelector(hash)?.scrollIntoView({ behavior: "smooth" });
        else window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (error) {
        window.location.href = url;
    } finally {
        navigationInProgress = false;
    }
}

document.addEventListener("click", (event) => {
    const link = event.target.closest("a[href]");
    if (!link || link.target === "_blank" || link.hasAttribute("download")) return;

    const url = new URL(link.href, window.location.origin);
    if (url.origin !== window.location.origin) return;

    const current = new URL(window.location.href);
    if (url.pathname === current.pathname && url.search === current.search) {
        if (url.hash) {
            event.preventDefault();
            document.querySelector(url.hash)?.scrollIntoView({ behavior: "smooth" });
        }
        return;
    }

    event.preventDefault();
    navigateWithoutReload(url.href);
});

window.addEventListener("popstate", () => navigateWithoutReload(window.location.href, false));

function initializeApp() {
    const questionInput = document.getElementById("question-input");
    const clearQuestion = document.getElementById("clear-question");
    const fileInput = document.querySelector('input[type="file"]');
    const fileName = document.getElementById("file-name");
    const librarySearch = document.getElementById("library-search");
    const clearSearch = document.getElementById("clear-search");
    const libraryItems = Array.from(document.querySelectorAll("[data-library-item]"));
    const emptyLibrary = document.querySelector("[data-empty-library]");
    const chatForm = document.querySelector(".chat-form");
    const chatWindow = document.querySelector(".chat-window");
    const sendButton = chatForm?.querySelector(".send-button");

    document.querySelectorAll("form[method=\"POST\"]:not(.chat-form)").forEach((form) => {
        form.addEventListener("submit", async (event) => {
            event.preventDefault();

            try {
                const response = await fetch(form.action, {
                    method: "POST",
                    headers: { "X-Requested-With": "XMLHttpRequest" },
                    body: new FormData(form),
                });
                if (!response.ok) throw new Error(`Form submission failed: ${response.status}`);

                const parsedPage = new DOMParser().parseFromString(await response.text(), "text/html");
                document.body.innerHTML = parsedPage.body.innerHTML;
                document.title = parsedPage.title;
                history.replaceState({}, "", window.location.href);
                initializeApp();
            } catch (error) {
                form.submit();
            }
        });
    });

    function setQuestion(value) {
        if (!questionInput) return;
        questionInput.value = value;
        questionInput.focus();
    }

    document.querySelectorAll("[data-question]").forEach((button) => {
        button.addEventListener("click", () => setQuestion(button.dataset.question));
    });

    clearQuestion?.addEventListener("click", () => {
        if (questionInput) {
            questionInput.value = "";
            questionInput.focus();
        }
    });

    function addChatMessage(type, text) {
        if (!chatWindow) return;
        const message = document.createElement("div");
        message.className = `chat-message ${type}-message`;
        const meta = document.createElement("div");
        meta.className = "message-meta";
        const avatar = document.createElement("span");
        avatar.className = `message-avatar ${type === "user" ? "user-avatar" : "ai-avatar"}`;
        avatar.textContent = type === "user" ? "Y" : "P";
        const label = document.createElement("span");
        label.className = "message-label";
        label.textContent = type === "user" ? "You" : "Papertrail AI";
        const content = document.createElement("p");
        content.textContent = text;
        meta.append(avatar, label);
        message.append(meta, content);
        chatWindow.appendChild(message);
        chatWindow.scrollTop = chatWindow.scrollHeight;
    }

    chatForm?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const question = questionInput?.value.trim();
        const pdfId = chatForm.querySelector('[name="pdf_id"]')?.value;
        if (!question || !pdfId) return;

        const formData = new FormData(chatForm);
        addChatMessage("user", question);
        questionInput.value = "";
        questionInput.disabled = true;
        if (sendButton) {
            sendButton.disabled = true;
            sendButton.querySelector("span")?.replaceChildren(document.createTextNode("Thinking..."));
        }

        try {
            const response = await fetch(chatForm.action, {
                method: "POST",
                headers: { "X-Requested-With": "XMLHttpRequest" },
                body: formData,
            });
            const result = await response.json();
            addChatMessage("assistant", result.answer || result.error || "Unable to get an answer.");
        } catch (error) {
            addChatMessage("assistant", "Unable to contact the server. Please try again.");
        } finally {
            questionInput.disabled = false;
            questionInput.focus();
            if (sendButton) {
                sendButton.disabled = false;
                sendButton.querySelector("span")?.replaceChildren(document.createTextNode("Send"));
            }
        }
    });

    document.querySelectorAll("[data-pdf-id]").forEach((documentButton) => {
        documentButton.addEventListener("click", () => {
            const pdfId = documentButton.dataset.pdfId;
            navigateWithoutReload(`/?pdf_id=${encodeURIComponent(pdfId)}#ask-card`);
        });
    });

    fileInput?.addEventListener("change", () => {
        const selectedFile = fileInput.files?.[0];
        if (fileName && selectedFile) fileName.textContent = selectedFile.name;
    });

    function filterLibrary() {
        const query = librarySearch?.value.trim().toLowerCase() || "";
        let visibleItems = 0;
        libraryItems.forEach((item) => {
            const matches = item.textContent.toLowerCase().includes(query);
            item.hidden = !matches;
            if (matches) visibleItems += 1;
        });
        if (emptyLibrary) {
            emptyLibrary.hidden = visibleItems > 0 || libraryItems.length === 0;
            emptyLibrary.textContent = visibleItems === 0 && libraryItems.length > 0
                ? "No documents match that search."
                : "Your library is ready for its first document.";
        }
    }

    librarySearch?.addEventListener("input", filterLibrary);
    clearSearch?.addEventListener("click", () => {
        if (librarySearch) {
            librarySearch.value = "";
            filterLibrary();
            librarySearch.focus();
        }
    });
}

initializeApp();
