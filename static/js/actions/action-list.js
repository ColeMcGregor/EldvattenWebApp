(() => {
    "use strict";

    const page = document.querySelector("[data-action-list-page]");
    if (!page) {
        return;
    }

    const filters = page.querySelector("[data-action-filters]");
    const sortControl = filters?.querySelector("[data-action-sort]");
    if (!filters || !sortControl) {
        return;
    }

    const statusControl = filters.querySelector("[data-action-status]");
    const requiredControl = filters.querySelector("[data-action-required]");
    const assignmentControl = filters.querySelector("[data-action-assignment-filter]");
    const searchControl = filters.querySelector("[data-action-search]");
    const resetButton = filters.querySelector("[data-action-reset]");
    const resultSummary = page.querySelector("[data-action-results]");
    const noMatches = page.querySelector("[data-action-no-results]");

    function readDate(value) {
        return value === "" ? null : Number(value);
    }

    const sections = Array.from(page.querySelectorAll("[data-action-section]"))
        .map((section) => {
            const container = section.querySelector("[data-action-list]");
            const items = container
                ? Array.from(container.querySelectorAll("[data-action-item]")).map((element, index) => ({
                    element,
                    index,
                    title: element.dataset.title.toLocaleLowerCase(),
                    deadline: readDate(element.dataset.deadline),
                    assigned: readDate(element.dataset.assigned || ""),
                    created: readDate(element.dataset.created || ""),
                    status: element.dataset.status || "",
                    required: element.dataset.required === "1",
                    activeAssignments: Number(element.dataset.activeAssignments || 0),
                    totalAssignments: Number(element.dataset.totalAssignments || 0),
                    targets: Number(element.dataset.targets || 0),
                }))
                : [];
            return { section, container, items };
        });

    const totalItems = sections.reduce((total, section) => total + section.items.length, 0);
    if (totalItems === 0) {
        return;
    }

    function compareDates(left, right, field, ascending) {
        if (left[field] === null && right[field] === null) {
            return 0;
        }
        if (left[field] === null) {
            return 1;
        }
        if (right[field] === null) {
            return -1;
        }
        return ascending ? left[field] - right[field] : right[field] - left[field];
    }

    function compareItems(left, right, sort) {
        let result = 0;
        switch (sort) {
            case "deadline_asc":
                result = compareDates(left, right, "deadline", true);
                break;
            case "deadline_desc":
                result = compareDates(left, right, "deadline", false);
                break;
            case "assigned_desc":
                result = compareDates(left, right, "assigned", false);
                break;
            case "created_desc":
                result = compareDates(left, right, "created", false);
                break;
            case "created_asc":
                result = compareDates(left, right, "created", true);
                break;
            case "title_asc":
                result = left.title.localeCompare(right.title);
                break;
            case "title_desc":
                result = right.title.localeCompare(left.title);
                break;
            case "required_first":
                result = Number(right.required) - Number(left.required);
                break;
            case "assignments_desc":
                result = right.totalAssignments - left.totalAssignments;
                break;
            default:
                break;
        }
        return result || left.index - right.index;
    }

    function matchesFilters(item) {
        const required = requiredControl?.value || "all";
        if (required === "required" && !item.required) {
            return false;
        }
        if (required === "optional" && item.required) {
            return false;
        }

        const status = statusControl?.value || "all";
        if (status !== "all" && item.status !== status) {
            return false;
        }

        const assignment = assignmentControl?.value || "all";
        if (assignment === "active" && item.activeAssignments === 0) {
            return false;
        }
        if (assignment === "no_active" && item.activeAssignments !== 0) {
            return false;
        }
        if (assignment === "no_targets" && item.targets !== 0) {
            return false;
        }

        const search = searchControl?.value.trim().toLocaleLowerCase() || "";
        return item.title.includes(search);
    }

    function updateList() {
        let shown = 0;
        for (const { section, container, items } of sections) {
            const ordered = [...items].sort((left, right) => compareItems(left, right, sortControl.value));
            let sectionShown = 0;
            for (const item of ordered) {
                item.element.hidden = !matchesFilters(item);
                if (!item.element.hidden) {
                    sectionShown += 1;
                }
                container.appendChild(item.element);
            }
            section.hidden = sectionShown === 0;
            shown += sectionShown;
        }

        if (resultSummary) {
            resultSummary.textContent = `${shown} of ${totalItems} actions shown`;
        }
        if (noMatches) {
            noMatches.hidden = shown !== 0;
        }
    }

    filters.addEventListener("input", updateList);
    filters.addEventListener("change", updateList);
    resetButton?.addEventListener("click", () => {
        sortControl.value = "default";
        if (statusControl) statusControl.value = "all";
        if (requiredControl) requiredControl.value = "all";
        if (assignmentControl) assignmentControl.value = "all";
        if (searchControl) searchControl.value = "";
        updateList();
    });

    filters.hidden = false;
    if (resultSummary) {
        resultSummary.hidden = false;
    }
    updateList();
})();
