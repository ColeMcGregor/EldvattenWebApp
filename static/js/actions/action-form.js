document.addEventListener("DOMContentLoaded", () => {
    const editor = document.querySelector("[data-action-editor]");

    if (!editor) {
        return;
    }

    const targetList = editor.querySelector(
        "[data-action-target-list]"
    );

    const addButton = editor.querySelector(
        "[data-add-action-target]"
    );

    const emptyForm = document.getElementById(
        "action-target-empty-form"
    );

    if (!targetList || !addButton || !emptyForm) {
        return;
    }

    const prefix = targetList.dataset.formsetPrefix;

    const totalForms = editor.querySelector(
        `input[name="${prefix}-TOTAL_FORMS"]`
    );

    const maxForms = editor.querySelector(
        `input[name="${prefix}-MAX_NUM_FORMS"]`
    );

    if (!totalForms) {
        return;
    }

    addButton.addEventListener("click", () => {
        const nextIndex = Number(totalForms.value);
        const maximum = Number(maxForms?.value);

        if (
            !Number.isSafeInteger(nextIndex)
            || nextIndex < 0
        ) {
            return;
        }

        if (
            Number.isSafeInteger(maximum)
            && maximum > 0
            && nextIndex >= maximum
        ) {
            return;
        }

        const wrapper = document.createElement("div");

        wrapper.innerHTML = emptyForm.innerHTML.replaceAll(
            "__prefix__",
            String(nextIndex)
        );

        const newRow = wrapper.firstElementChild;

        if (!newRow) {
            return;
        }

        targetList.appendChild(newRow);

        totalForms.value = String(nextIndex + 1);

        const firstField = newRow.querySelector(
            "select, input:not([type='hidden'])"
        );

        firstField?.focus();
    });

    targetList.addEventListener("click", (event) => {
        const removeButton = event.target.closest(
            "[data-remove-action-target]"
        );

        if (!removeButton) {
            return;
        }

        const row = removeButton.closest(
            "[data-action-target-row]"
        );

        if (!row) {
            return;
        }

        const deleteField = row.querySelector(
            'input[name$="-DELETE"]'
        );

        if (!deleteField) {
            return;
        }

        deleteField.checked = true;
        row.hidden = true;

        addButton.focus();
    });
});