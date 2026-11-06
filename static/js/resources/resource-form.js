
document.addEventListener("DOMContentLoaded", () => {
    const form = document.querySelector("[data-resource-form]");

    if (!form) {
        return;
    }

    const resourceTypeSelect = form.querySelector(
        'select[name="resource_type"]'
    );

    const fileField = form.querySelector(
        "[data-resource-file-field]"
    );

    const linkField = form.querySelector(
        "[data-resource-link-field]"
    );

    const targetList = form.querySelector(
        "[data-resource-target-list]"
    );

    const targetTemplate = form.querySelector(
        "[data-resource-target-template]"
    );

    const addTargetButton = form.querySelector(
        "[data-resource-add-target]"
    );

    function updateResourceTypeFields() {
        if (!resourceTypeSelect) {
            return;
        }

        const resourceType = resourceTypeSelect.value;

        if (fileField) {
            fileField.hidden = resourceType === "LINK";
        }

        if (linkField) {
            linkField.hidden = resourceType === "FILE";
        }
    }

    resourceTypeSelect?.addEventListener(
        "change",
        updateResourceTypeFields
    );

    updateResourceTypeFields();

    if (!targetList || !targetTemplate || !addTargetButton) {
        return;
    }

    const prefix = targetList.dataset.prefix;

    if (!prefix) {
        return;
    }

    const totalForms = form.querySelector(
        `input[name="${prefix}-TOTAL_FORMS"]`
    );

    const maxForms = form.querySelector(
        `input[name="${prefix}-MAX_NUM_FORMS"]`
    );

    if (!totalForms) {
        return;
    }

    function getTotalForms() {
        return Number.parseInt(
            totalForms.value,
            10
        );
    }

    function getMaxForms() {
        const maximum = Number.parseInt(
            maxForms?.value || "",
            10
        );

        return Number.isFinite(maximum)
            ? maximum
            : Infinity;
    }

    function updateAddTargetButton() {
        const total = getTotalForms();
        const maximum = getMaxForms();

        addTargetButton.disabled = (
            !Number.isSafeInteger(total)
            || total < 0
            || total >= maximum
        );
    }

    function updateTargetRemovalState(row) {
        const deleteCheckbox = row.querySelector(
            'input[name$="-DELETE"]'
        );

        if (!deleteCheckbox) {
            return;
        }

        row.classList.toggle(
            "resources-target-form-removed",
            deleteCheckbox.checked
        );
    }

    function addVisibilityTarget() {
        const nextIndex = getTotalForms();
        const maximum = getMaxForms();

        if (
            !Number.isSafeInteger(nextIndex)
            || nextIndex < 0
            || nextIndex >= maximum
        ) {
            return;
        }

        const wrapper = document.createElement("div");

        wrapper.innerHTML = (
            targetTemplate.innerHTML.replaceAll(
                "__prefix__",
                String(nextIndex)
            )
        );

        const newRow = wrapper.querySelector(
            "[data-resource-target-row]"
        );

        if (!newRow) {
            return;
        }

        targetList.appendChild(newRow);

        totalForms.value = String(nextIndex + 1);

        updateTargetRemovalState(newRow);
        updateAddTargetButton();

        const firstField = newRow.querySelector(
            'select, input:not([type="hidden"])'
        );

        firstField?.focus();
    }

    addTargetButton.addEventListener(
        "click",
        addVisibilityTarget
    );

    targetList.addEventListener("change", (event) => {
        const target = event.target;

        if (
            !target.matches(
                'input[name$="-DELETE"]'
            )
        ) {
            return;
        }

        const row = target.closest(
            "[data-resource-target-row]"
        );

        if (row) {
            updateTargetRemovalState(row);
        }
    });

    targetList.querySelectorAll(
        "[data-resource-target-row]"
    ).forEach(updateTargetRemovalState);

    updateAddTargetButton();
});
