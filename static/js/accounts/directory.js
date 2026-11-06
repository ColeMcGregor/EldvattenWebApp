(() => {
    const list = document.querySelector("[data-directory-list]");
    const panel = document.querySelector("[data-directory-profile]");

    if (!list || !panel) {
        return;
    }

    let lastRequest = 0;

    list.addEventListener("click", async (event) => {
        const link = event.target.closest("a[data-directory-member]");

        if (!link || !list.contains(link)) {
            return;
        }

        event.preventDefault();
        const requestNumber = ++lastRequest;

        try {
            const response = await fetch(link.href, {
                headers: { "X-Requested-With": "XMLHttpRequest" },
                credentials: "same-origin",
            });

            if (!response.ok) {
                window.location.assign(link.href);
                return;
            }

            const html = await response.text();

            if (requestNumber !== lastRequest) {
                return;
            }

            panel.innerHTML = html;

            for (const item of list.querySelectorAll("[data-directory-member]")) {
                item.classList.remove("active");
                item.removeAttribute("aria-current");
            }

            link.classList.add("active");
            link.setAttribute("aria-current", "true");
        } catch (error) {
            window.location.assign(link.href);
        }
    });
})();
