(() => {
    // TODO: Add project-specific comments here.
    const compareText = (a, b) => a.localeCompare(b, undefined, { sensitivity: "base" });
    const asTime = (value) => value === "" ? null : Number(value);

    document.querySelectorAll("[data-vote-list]").forEach((page) => {
        const controls = page.querySelector("[data-vote-controls]");
        if (!controls) return;

        const rows = Array.from(page.querySelectorAll("[data-vote-item]"));
        const parents = new Map(rows.map((row) => [row, row.parentElement]));
        const originalIndex = new Map(rows.map((row, index) => [row, index]));
        const sort = controls.querySelector("[data-vote-sort]");
        const status = controls.querySelector("[data-vote-status]");
        const response = controls.querySelector("[data-vote-response]");
        const privacy = controls.querySelector("[data-vote-privacy]");
        const query = controls.querySelector("[data-vote-query]");
        const count = controls.querySelector("[data-vote-count]");
        const empty = page.querySelector("[data-vote-empty]");

        const update = () => {
            const term = (query?.value || "").trim().toLocaleLowerCase();
            const sorted = [...rows].sort((a, b) => {
                const direction = sort.value;
                if (direction === "default") return originalIndex.get(a) - originalIndex.get(b);
                if (direction === "oldest") {
                    return Number(a.dataset.created) - Number(b.dataset.created)
                        || originalIndex.get(a) - originalIndex.get(b);
                }
                if (direction.startsWith("title_")) {
                    const order = compareText(a.dataset.title || "", b.dataset.title || "");
                    return (direction === "title_desc" ? -order : order)
                        || originalIndex.get(a) - originalIndex.get(b);
                }
                if (direction === "closes_soon" || direction === "closes_latest") {
                    const aTime = asTime(a.dataset.closes || "");
                    const bTime = asTime(b.dataset.closes || "");
                    if (aTime === null) return bTime === null ? originalIndex.get(a) - originalIndex.get(b) : 1;
                    if (bTime === null) return -1;
                    return (direction === "closes_latest" ? bTime - aTime : aTime - bTime)
                        || originalIndex.get(a) - originalIndex.get(b);
                }
                return originalIndex.get(a) - originalIndex.get(b);
            });

            let visible = 0;
            sorted.forEach((row) => {
                const matches = (!term || (row.dataset.title || "").toLocaleLowerCase().includes(term))
                    && (status.value === "all" || row.dataset.status === status.value)
                    && (!response || response.value === "all"
                        || (response.value === "responded" && row.dataset.responded === "true")
                        || (response.value === "pending" && row.dataset.responded === "false"))
                    && (!privacy || privacy.value === "all" || row.dataset.privacy === privacy.value);
                row.hidden = !matches;
                if (matches) visible += 1;
                parents.get(row).appendChild(row);
            });
            if (count) count.textContent = `${visible} of ${rows.length} votes shown`;
            if (empty) empty.hidden = visible !== 0;
        };
        controls.querySelectorAll("select, input").forEach((input) => {
            input.addEventListener(input.tagName === "INPUT" ? "input" : "change", update);
        });
        controls.querySelector("[data-vote-reset]")?.addEventListener("click", () => {
            controls.querySelectorAll("select").forEach((field) => { field.selectedIndex = 0; });
            if (query) query.value = "";
            update();
        });
        controls.hidden = false;
        update();
    });

    document.querySelectorAll("[data-vote-formset]").forEach((container) => {
        const prefix = container.dataset.prefix;
        const form = container.closest("form");
        const total = form?.querySelector(`[name="${prefix}-TOTAL_FORMS"]`);
        const maximum = form?.querySelector(`[name="${prefix}-MAX_NUM_FORMS"]`);
        const template = container.querySelector("[data-vote-empty-form]");
        const addButton = container.querySelector("[data-vote-add-row]");
        if (!total || !template || !addButton) return;

        addButton.addEventListener("click", () => {
            const index = Number(total.value);
            if (maximum && index >= Number(maximum.value)) return;
            const wrapper = document.createElement("div");
            wrapper.innerHTML = template.innerHTML.replaceAll("__prefix__", String(index));
            while (wrapper.firstChild) container.insertBefore(wrapper.firstChild, template);
            total.value = String(index + 1);
        });
    });
})();
