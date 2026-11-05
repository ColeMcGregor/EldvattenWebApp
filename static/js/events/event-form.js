document.addEventListener("DOMContentLoaded", () => {
    const editor = document.querySelector("[data-event-editor]");

    if (!editor) {
        return;
    }

    const invitationVisibility = editor.querySelector(
        'input[name="visible_to_invited_only"]'
    );
    const visibilitySelect = editor.querySelector(
        'select[name="visibility"]'
    );
    const separateVisibilityControls = document.getElementById(
        "separate-visibility-controls"
    );
    const customVisibilityTargets = document.getElementById(
        "custom-visibility-targets"
    );

    function updateVisibilityControls() {
        if (!invitationVisibility || !visibilitySelect) {
            return;
        }

        const invitedOnly = invitationVisibility.checked;
        separateVisibilityControls.hidden = invitedOnly;
        customVisibilityTargets.hidden = (
            invitedOnly || visibilitySelect.value !== "CUSTOM"
        );
    }

    invitationVisibility?.addEventListener(
        "change",
        updateVisibilityControls
    );
    visibilitySelect?.addEventListener(
        "change",
        updateVisibilityControls
    );
    updateVisibilityControls();

    editor.querySelectorAll("[data-add-event-target]").forEach((button) => {
        button.addEventListener("click", () => {
            const prefix = button.dataset.addEventTarget;
            const list = editor.querySelector(
                `[data-event-target-formset="${prefix}"]`
            );
            const template = document.getElementById(
                `event-${prefix}-empty-form`
            );
            const count = editor.querySelector(
                `input[name="${prefix}-TOTAL_FORMS"]`
            );

            if (!list || !template || !count) {
                return;
            }

            const nextIndex = Number(count.value);
            if (!Number.isSafeInteger(nextIndex) || nextIndex < 0) {
                return;
            }

            const wrapper = document.createElement("div");
            wrapper.innerHTML = template.innerHTML.replaceAll(
                "__prefix__",
                String(nextIndex)
            );

            const newRow = wrapper.firstElementChild;
            if (!newRow) {
                return;
            }

            list.appendChild(newRow);
            count.value = String(nextIndex + 1);
            newRow.querySelector("select, input")?.focus();
        });
    });

    editor.querySelectorAll("[data-event-target-formset]").forEach((list) => {
        list.addEventListener("click", (event) => {
            const remove = event.target.closest("[data-remove-event-target]");
            if (!remove) {
                return;
            }

            const row = remove.closest("[data-event-target-row]");
            const deleteField = row?.querySelector('input[name$="-DELETE"]');
            if (!row || !deleteField) {
                return;
            }

            deleteField.checked = true;
            row.hidden = true;
        });
    });
});
