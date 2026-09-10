document.addEventListener("DOMContentLoaded", () => {
    const postForms = document.querySelectorAll(
        "[data-post-form]"
    );

    postForms.forEach((postForm) => {
        initializePostForm(postForm);
    });

    initializeTavernPosts();
    initializeTavernFeedScrollbar();
});


function initializePostForm(postForm) {
    const visibilitySelect = postForm.querySelector(
        'select[name="visibility"]'
    );

    const openTargetButton = postForm.querySelector(
        "[data-open-target-modal]"
    );

    const modal = postForm.querySelector(
        "[data-target-modal]"
    );

    const targetList = postForm.querySelector(
        "[data-target-list]"
    );

    const emptyTargetTemplate = postForm.querySelector(
        "[data-empty-target-form]"
    );

    const totalFormsInput = postForm.querySelector(
        'input[name="targets-TOTAL_FORMS"]'
    );

    const closeTargetButtons = postForm.querySelectorAll(
        "[data-close-target-modal]"
    );

    const useTargetsButton = postForm.querySelector(
        "[data-use-targets]"
    );

    const addTargetButton = postForm.querySelector(
        "[data-add-target]"
    );

    const selectedGroupsValue = "SELECTED_GROUPS";


    function isSelectedGroups() {
        return (
            visibilitySelect
            && visibilitySelect.value === selectedGroupsValue
        );
    }


    function showTargetButton() {
        if (!openTargetButton) {
            return;
        }

        openTargetButton.hidden = !isSelectedGroups();
    }


    function openModal() {
        if (!modal) {
            return;
        }

        modal.classList.add("open");

        modal.setAttribute(
            "aria-hidden",
            "false"
        );

        document.body.style.overflow = "hidden";
    }


    function closeModal() {
        if (!modal) {
            return;
        }

        modal.classList.remove("open");

        modal.setAttribute(
            "aria-hidden",
            "true"
        );

        document.body.style.overflow = "";
    }


    function rowHasValue(row) {
        const fields = row.querySelectorAll(
            "select, input:not([type='hidden']):not([type='checkbox'])"
        );

        for (const field of fields) {
            if (field.value) {
                return true;
            }
        }

        return false;
    }


    function targetCount() {
        if (!targetList) {
            return 0;
        }

        const rows = targetList.querySelectorAll(
            "[data-target-row]"
        );

        let count = 0;

        rows.forEach((row) => {
            const deleteInput = row.querySelector(
                'input[name$="-DELETE"]'
            );

            if (
                deleteInput
                && deleteInput.checked
            ) {
                return;
            }

            if (rowHasValue(row)) {
                count += 1;
            }
        });

        return count;
    }


    function updateTargetButtonText() {
        if (!openTargetButton) {
            return;
        }

        const count = targetCount();

        if (count === 0) {
            openTargetButton.textContent =
                "Choose Audience";

            return;
        }

        if (count === 1) {
            openTargetButton.textContent =
                "1 Target";

            return;
        }

        openTargetButton.textContent =
            `${count} Targets`;
    }


    function replaceFormIndex(
        html,
        index
    ) {
        return html.replaceAll(
            "__prefix__",
            String(index)
        );
    }


    function addTargetRow() {
        if (
            !emptyTargetTemplate
            || !targetList
            || !totalFormsInput
        ) {
            return;
        }

        const index = Number(
            totalFormsInput.value
        );

        const wrapper = document.createElement(
            "div"
        );

        wrapper.innerHTML = replaceFormIndex(
            emptyTargetTemplate.innerHTML,
            index
        ).trim();

        const newRow = wrapper.firstElementChild;

        if (!newRow) {
            return;
        }

        targetList.appendChild(
            newRow
        );

        totalFormsInput.value =
            String(index + 1);
    }


    function clearRowFields(row) {
        const selects = row.querySelectorAll(
            "select"
        );

        selects.forEach((select) => {
            select.value = "";
        });

        const textInputs = row.querySelectorAll(
            'input[type="text"], input[type="number"]'
        );

        textInputs.forEach((input) => {
            input.value = "";
        });
    }


    function removeTargetRow(row) {
        const deleteInput = row.querySelector(
            'input[name$="-DELETE"]'
        );

        const idInput = row.querySelector(
            'input[name$="-id"]'
        );

        const isExistingRow = (
            idInput
            && idInput.value
        );

        if (
            isExistingRow
            && deleteInput
        ) {
            deleteInput.checked = true;
            row.hidden = true;
        } else {
            clearRowFields(row);

            if (deleteInput) {
                deleteInput.checked = true;
            }

            row.hidden = true;
        }

        updateTargetButtonText();
    }


    function ensureVisibleTargetRow() {
        if (!targetList) {
            return;
        }

        const rows = targetList.querySelectorAll(
            "[data-target-row]"
        );

        const hasVisibleRow = Array.from(
            rows
        ).some(
            (row) => !row.hidden
        );

        if (!hasVisibleRow) {
            addTargetRow();
        }
    }


    function handleRemoveButton(event) {
        const removeButton = event.target.closest(
            "[data-remove-target]"
        );

        if (!removeButton) {
            return;
        }

        const row = removeButton.closest(
            "[data-target-row]"
        );

        if (!row) {
            return;
        }

        removeTargetRow(row);
        ensureVisibleTargetRow();
    }


    function prepareTargetsForNonSelectedSubmission() {
        if (!targetList) {
            return;
        }

        const rows = targetList.querySelectorAll(
            "[data-target-row]"
        );

        rows.forEach((row) => {
            const deleteInput = row.querySelector(
                'input[name$="-DELETE"]'
            );

            if (deleteInput) {
                deleteInput.checked = true;
            }
        });
    }


    if (visibilitySelect) {
        visibilitySelect.addEventListener(
            "change",
            () => {
                showTargetButton();

                if (isSelectedGroups()) {
                    ensureVisibleTargetRow();
                    openModal();
                } else {
                    closeModal();
                }
            }
        );
    }


    if (openTargetButton) {
        openTargetButton.addEventListener(
            "click",
            () => {
                ensureVisibleTargetRow();
                openModal();
            }
        );
    }


    closeTargetButtons.forEach(
        (button) => {
            button.addEventListener(
                "click",
                closeModal
            );
        }
    );


    if (useTargetsButton) {
        useTargetsButton.addEventListener(
            "click",
            () => {
                updateTargetButtonText();
                closeModal();
            }
        );
    }


    if (addTargetButton) {
        addTargetButton.addEventListener(
            "click",
            () => {
                addTargetRow();
            }
        );
    }


    if (targetList) {
        targetList.addEventListener(
            "click",
            handleRemoveButton
        );

        targetList.addEventListener(
            "change",
            updateTargetButtonText
        );
    }


    document.addEventListener(
        "keydown",
        (event) => {
            if (
                event.key === "Escape"
                && modal
                && modal.classList.contains("open")
            ) {
                closeModal();
            }
        }
    );


    postForm.addEventListener(
        "submit",
        (event) => {
            if (isSelectedGroups()) {
                if (targetCount() === 0) {
                    event.preventDefault();

                    ensureVisibleTargetRow();
                    openModal();
                }

                return;
            }

            prepareTargetsForNonSelectedSubmission();
        }
    );


    showTargetButton();
    updateTargetButtonText();

    if (
        isSelectedGroups()
        && targetCount() === 0
    ) {
        ensureVisibleTargetRow();
    }
}


function initializeTavernPosts() {
    const posts = document.querySelectorAll(
        "[data-tavern-post]"
    );

    if (posts.length === 0) {
        return;
    }


    function setPostExpanded(
        post,
        expanded
    ) {
        const discussion = post.querySelector(
            "[data-post-discussion]"
        );

        const toggleButtons = post.querySelectorAll(
            "[data-post-toggle]"
        );

        post.classList.toggle(
            "is-expanded",
            expanded
        );

        if (discussion) {
            discussion.hidden = !expanded;
        }

        toggleButtons.forEach((button) => {
            button.setAttribute(
                "aria-expanded",
                String(expanded)
            );
        });
    }


    function postIsExpanded(post) {
        return post.classList.contains(
            "is-expanded"
        );
    }


    function clickShouldNotTogglePost(target) {
        return Boolean(
            target.closest(
                [
                    "a",
                    "button",
                    "input",
                    "textarea",
                    "select",
                    "label",
                    "form",
                    "details",
                    "summary",
                    "[data-post-discussion]",
                ].join(",")
            )
        );
    }


    posts.forEach((post) => {
        const toggleButtons = post.querySelectorAll(
            "[data-post-toggle]"
        );

        toggleButtons.forEach((button) => {
            button.addEventListener(
                "click",
                () => {
                    setPostExpanded(
                        post,
                        !postIsExpanded(post)
                    );
                }
            );
        });

        post.addEventListener(
            "click",
            (event) => {
                if (
                    clickShouldNotTogglePost(
                        event.target
                    )
                ) {
                    return;
                }

                const selection =
                    window.getSelection();

                if (
                    selection
                    && selection.toString()
                ) {
                    return;
                }

                setPostExpanded(
                    post,
                    !postIsExpanded(post)
                );
            }
        );
    });


    const inlineFormButtons =
        document.querySelectorAll(
            [
                "[data-comment-edit-toggle]",
                "[data-reply-toggle]",
            ].join(",")
        );

    inlineFormButtons.forEach((button) => {
        button.addEventListener(
            "click",
            () => {
                const formId =
                    button.dataset.formId;

                if (!formId) {
                    return;
                }

                const form =
                    document.getElementById(
                        formId
                    );

                if (!form) {
                    return;
                }

                const shouldOpen =
                    form.hidden;

                const post = button.closest(
                    "[data-tavern-post]"
                );

                if (post) {
                    post
                        .querySelectorAll(
                            "[data-inline-comment-form]"
                        )
                        .forEach(
                            (otherForm) => {
                                if (
                                    otherForm
                                    !== form
                                ) {
                                    otherForm.hidden =
                                        true;
                                }
                            }
                        );
                }

                form.hidden = !shouldOpen;

                if (shouldOpen) {
                    const textarea =
                        form.querySelector(
                            "textarea"
                        );

                    if (textarea) {
                        textarea.focus();
                    }
                }
            }
        );
    });


    const cancelButtons =
        document.querySelectorAll(
            "[data-comment-form-cancel]"
        );

    cancelButtons.forEach((button) => {
        button.addEventListener(
            "click",
            () => {
                const form = button.closest(
                    "[data-inline-comment-form]"
                );

                if (form) {
                    form.hidden = true;
                }
            }
        );
    });


    const parameters = new URLSearchParams(
        window.location.search
    );

    const openPostId = parameters.get(
        "open_post"
    );

    if (!openPostId) {
        return;
    }

    const postToOpen = document.getElementById(
        `post-${openPostId}`
    );

    if (
        !postToOpen
        || !postToOpen.matches(
            "[data-tavern-post]"
        )
    ) {
        return;
    }

    setPostExpanded(
        postToOpen,
        true
    );

    requestAnimationFrame(
        () => {
            postToOpen.scrollIntoView(
                {
                    block: "nearest",
                    inline: "nearest",
                }
            );
        }
    );
}


function initializeTavernFeedScrollbar() {
    const feed = document.querySelector(
        ".tavern-feed"
    );

    if (!feed) {
        return;
    }

    let hideScrollbarTimeout = null;

    feed.addEventListener(
        "scroll",
        () => {
            feed.classList.add(
                "is-scrolling"
            );

            if (hideScrollbarTimeout) {
                clearTimeout(
                    hideScrollbarTimeout
                );
            }

            hideScrollbarTimeout =
                setTimeout(
                    () => {
                        feed.classList.remove(
                            "is-scrolling"
                        );
                    },
                    2000
                );
        },
        {
            passive: true,
        }
    );
}