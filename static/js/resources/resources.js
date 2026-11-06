
document.addEventListener("DOMContentLoaded", () => {
    const resourceList = document.querySelector("[data-resource-list]");

    if (!resourceList) {
        return;
    }

    const controls = resourceList.querySelector(
        "[data-resource-controls]"
    );

    const container = resourceList.querySelector(
        "[data-resource-items]"
    );

    if (!controls || !container) {
        return;
    }

    const queryInput = controls.querySelector(
        "[data-resource-query]"
    );

    const typeSelect = controls.querySelector(
        "[data-resource-type]"
    );

    const statusSelect = controls.querySelector(
        "[data-resource-status]"
    );

    const sortSelect = controls.querySelector(
        "[data-resource-sort]"
    );

    const resetButton = controls.querySelector(
        "[data-resource-reset]"
    );

    const countOutput = controls.querySelector(
        "[data-resource-count]"
    );

    const emptyMessage = resourceList.querySelector(
        "[data-resource-empty]"
    );

    const items = Array.from(
        container.querySelectorAll("[data-resource-item]")
    );

    const originalOrder = new Map(
        items.map((item, index) => [item, index])
    );

    const collator = new Intl.Collator(undefined, {
        sensitivity: "base",
        numeric: true,
    });

    function getSearchText(item) {
        return [
            item.dataset.title || "",
            item.dataset.description || "",
        ].join(" ").toLocaleLowerCase();
    }

    function matchesFilters(item) {
        const query = (
            queryInput?.value || ""
        ).trim().toLocaleLowerCase();

        const selectedType = typeSelect?.value || "all";
        const selectedStatus = statusSelect?.value || "all";

        if (query && !getSearchText(item).includes(query)) {
            return false;
        }

        if (
            selectedType !== "all"
            && item.dataset.type !== selectedType
        ) {
            return false;
        }

        if (
            selectedStatus !== "all"
            && item.dataset.status !== selectedStatus
        ) {
            return false;
        }

        return true;
    }

    function compareItems(first, second) {
        const sort = sortSelect?.value || "default";

        if (sort === "title_asc") {
            return collator.compare(
                first.dataset.title || "",
                second.dataset.title || ""
            );
        }

        if (sort === "title_desc") {
            return collator.compare(
                second.dataset.title || "",
                first.dataset.title || ""
            );
        }

        return (
            originalOrder.get(first)
            - originalOrder.get(second)
        );
    }

    function updateResourceList() {
        const sortedItems = [...items].sort(compareItems);

        for (const item of sortedItems) {
            container.appendChild(item);
        }

        let visibleCount = 0;

        for (const item of sortedItems) {
            const visible = matchesFilters(item);

            item.hidden = !visible;

            if (visible) {
                visibleCount += 1;
            }
        }

        if (countOutput) {
            countOutput.textContent = (
                `${visibleCount} of ${items.length} resources`
            );
        }

        if (emptyMessage) {
            emptyMessage.hidden = visibleCount !== 0;
        }
    }

    function resetFilters() {
        if (queryInput) {
            queryInput.value = "";
        }

        if (typeSelect) {
            typeSelect.value = "all";
        }

        if (statusSelect) {
            statusSelect.value = "all";
        }

        if (sortSelect) {
            sortSelect.value = "default";
        }

        updateResourceList();
    }

    queryInput?.addEventListener(
        "input",
        updateResourceList
    );

    typeSelect?.addEventListener(
        "change",
        updateResourceList
    );

    statusSelect?.addEventListener(
        "change",
        updateResourceList
    );

    sortSelect?.addEventListener(
        "change",
        updateResourceList
    );

    resetButton?.addEventListener(
        "click",
        resetFilters
    );

    controls.hidden = false;

    updateResourceList();
});
