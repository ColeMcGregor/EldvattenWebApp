document.addEventListener(
    "DOMContentLoaded",
    () => {
        initializeConversationSearch();
        initializeConversationModal();
        initializeMessageThread();
    }
);


function initializeConversationSearch() {
    const searchInput = document.querySelector(
        "[data-conversation-search]"
    );

    const conversationRows =
        document.querySelectorAll(
            "[data-conversation-row]"
        );

    if (
        !searchInput
        || conversationRows.length === 0
    ) {
        return;
    }

    searchInput.addEventListener(
        "input",
        () => {
            const searchText =
                searchInput.value
                    .trim()
                    .toLowerCase();

            conversationRows.forEach(
                (row) => {
                    const rowText =
                        (
                            row.dataset
                                .conversationSearchText
                            || ""
                        ).toLowerCase();

                    const shouldShow =
                        searchText === ""
                        || rowText.includes(
                            searchText
                        );

                    row.classList.toggle(
                        "is-filtered-out",
                        !shouldShow
                    );
                }
            );
        }
    );
}


function initializeConversationModal() {
    const modal = document.querySelector(
        "[data-conversation-modal]"
    );

    if (!modal) {
        return;
    }

    const openButtons =
        document.querySelectorAll(
            "[data-open-conversation-modal]"
        );

    const closeButtons =
        modal.querySelectorAll(
            "[data-close-conversation-modal]"
        );

    const conversationForm =
        modal.querySelector(
            "[data-conversation-form]"
        );

    const conversationTypeInput =
        modal.querySelector(
            "[data-conversation-type-input]"
        );

    const typeButtons =
        modal.querySelectorAll(
            "[data-conversation-type-choice]"
        );

    const typePanels =
        modal.querySelectorAll(
            "[data-conversation-type-panel]"
        );

    const participantSelect =
        modal.querySelector(
            ".conversation-participants"
        );

    const userSearchInput =
        modal.querySelector(
            "[data-conversation-user-search]"
        );

    const targetList =
        modal.querySelector(
            "[data-conversation-target-list]"
        );

    const emptyTargetTemplate =
        modal.querySelector(
            "[data-conversation-empty-target]"
        );

    const addTargetButton =
        modal.querySelector(
            "[data-add-conversation-target]"
        );

    const totalFormsInput =
        modal.querySelector(
            'input[name="targets-TOTAL_FORMS"]'
        );

    let previouslyFocusedElement = null;


    function getConversationType() {
        if (!conversationTypeInput) {
            return "DIRECT";
        }

        return (
            conversationTypeInput.value
            || "DIRECT"
        );
    }


    function setConversationType(type) {
        if (conversationTypeInput) {
            conversationTypeInput.value =
                type;
        }

        typeButtons.forEach(
            (button) => {
                const isActive =
                    button.dataset
                        .conversationTypeChoice
                    === type;

                button.classList.toggle(
                    "active",
                    isActive
                );

                button.setAttribute(
                    "aria-pressed",
                    String(isActive)
                );
            }
        );

        typePanels.forEach(
            (panel) => {
                const isActive =
                    panel.dataset
                        .conversationTypePanel
                    === type;

                panel.hidden = !isActive;
            }
        );

        if (participantSelect) {
            participantSelect.disabled =
                type !== "DIRECT";
        }

        if (type === "GROUP") {
            ensureVisibleTargetRow();
        }
    }


    function openModal(event) {
        if (event) {
            event.preventDefault();
        }

        previouslyFocusedElement =
            document.activeElement;

        modal.hidden = false;

        document.body.classList.add(
            "messages-modal-open"
        );

        setConversationType(
            getConversationType()
        );

        requestAnimationFrame(
            () => {
                if (
                    getConversationType()
                    === "DIRECT"
                    && userSearchInput
                ) {
                    userSearchInput.focus();
                    return;
                }

                const titleInput =
                    modal.querySelector(
                        ".conversation-title-input"
                    );

                if (titleInput) {
                    titleInput.focus();
                }
            }
        );
    }


    function closeModal() {
        modal.hidden = true;

        document.body.classList.remove(
            "messages-modal-open"
        );

        if (
            previouslyFocusedElement
            && typeof
                previouslyFocusedElement.focus
                === "function"
        ) {
            previouslyFocusedElement.focus();
        }
    }


    function filterUsers() {
        if (
            !userSearchInput
            || !participantSelect
        ) {
            return;
        }

        const searchText =
            userSearchInput.value
                .trim()
                .toLowerCase();

        const options = Array.from(
            participantSelect.options
        );

        options.forEach(
            (option) => {
                const optionText =
                    option.textContent
                        .trim()
                        .toLowerCase();

                option.hidden = (
                    searchText !== ""
                    && !optionText.includes(
                        searchText
                    )
                );
            }
        );
    }


    function replaceFormPrefix(
        html,
        index
    ) {
        return html.replaceAll(
            "__prefix__",
            String(index)
        );
    }


    function getTargetRows() {
        if (!targetList) {
            return [];
        }

        return Array.from(
            targetList.querySelectorAll(
                "[data-conversation-target-row]"
            )
        );
    }


    function rowIsDeleted(row) {
        const deleteInput =
            row.querySelector(
                'input[name$="-DELETE"]'
            );

        return Boolean(
            deleteInput
            && deleteInput.checked
        );
    }


    function getVisibleTargetRows() {
        return getTargetRows().filter(
            (row) => (
                !row.hidden
                && !rowIsDeleted(row)
            )
        );
    }


    function renumberTargetRows() {
        const visibleRows =
            getVisibleTargetRows();

        visibleRows.forEach(
            (row, index) => {
                const numberElement =
                    row.querySelector(
                        "[data-conversation-target-number]"
                    );

                if (numberElement) {
                    numberElement.textContent =
                        String(index + 1);
                }
            }
        );
    }


    function addTargetRow() {
        if (
            !targetList
            || !emptyTargetTemplate
            || !totalFormsInput
        ) {
            return;
        }

        const index = Number(
            totalFormsInput.value
        );

        const wrapper =
            document.createElement(
                "div"
            );

        wrapper.innerHTML =
            replaceFormPrefix(
                emptyTargetTemplate.innerHTML,
                index
            ).trim();

        const newRow =
            wrapper.firstElementChild;

        if (!newRow) {
            return;
        }

        targetList.appendChild(
            newRow
        );

        totalFormsInput.value =
            String(index + 1);

        renumberTargetRows();

        const firstSelect =
            newRow.querySelector(
                "select"
            );

        if (firstSelect) {
            firstSelect.focus();
        }
    }


    function markTargetRowDeleted(row) {
        const deleteInput =
            row.querySelector(
                'input[name$="-DELETE"]'
            );

        if (deleteInput) {
            deleteInput.checked = true;
        }

        row.hidden = true;

        renumberTargetRows();
    }


    function ensureVisibleTargetRow() {
        if (
            !targetList
            || getVisibleTargetRows().length > 0
        ) {
            return;
        }

        addTargetRow();
    }


    function handleTargetListClick(event) {
        const removeButton =
            event.target.closest(
                "[data-remove-conversation-target]"
            );

        if (!removeButton) {
            return;
        }

        const row =
            removeButton.closest(
                "[data-conversation-target-row]"
            );

        if (!row) {
            return;
        }

        markTargetRowDeleted(
            row
        );

        ensureVisibleTargetRow();
    }


    function handleTypeButtonClick(event) {
        const button =
            event.currentTarget;

        const type =
            button.dataset
                .conversationTypeChoice;

        if (!type) {
            return;
        }

        setConversationType(
            type
        );
    }


    function handleEscape(event) {
        if (
            event.key !== "Escape"
            || modal.hidden
        ) {
            return;
        }

        closeModal();
    }


    function handleModalKeydown(event) {
        if (
            event.key !== "Tab"
            || modal.hidden
        ) {
            return;
        }

        const focusableElements =
            Array.from(
                modal.querySelectorAll(
                    [
                        "button:not([disabled])",
                        "a[href]",
                        "input:not([disabled])",
                        "select:not([disabled])",
                        "textarea:not([disabled])",
                        '[tabindex]:not([tabindex="-1"])',
                    ].join(",")
                )
            ).filter(
                (element) => (
                    !element.hidden
                    && element.offsetParent
                    !== null
                )
            );

        if (
            focusableElements.length === 0
        ) {
            return;
        }

        const firstElement =
            focusableElements[0];

        const lastElement =
            focusableElements[
                focusableElements.length - 1
            ];

        if (
            event.shiftKey
            && document.activeElement
            === firstElement
        ) {
            event.preventDefault();
            lastElement.focus();
            return;
        }

        if (
            !event.shiftKey
            && document.activeElement
            === lastElement
        ) {
            event.preventDefault();
            firstElement.focus();
        }
    }


    openButtons.forEach(
        (button) => {
            button.addEventListener(
                "click",
                openModal
            );
        }
    );


    closeButtons.forEach(
        (button) => {
            button.addEventListener(
                "click",
                closeModal
            );
        }
    );


    typeButtons.forEach(
        (button) => {
            button.addEventListener(
                "click",
                handleTypeButtonClick
            );
        }
    );


    if (userSearchInput) {
        userSearchInput.addEventListener(
            "input",
            filterUsers
        );
    }


    if (addTargetButton) {
        addTargetButton.addEventListener(
            "click",
            addTargetRow
        );
    }


    if (targetList) {
        targetList.addEventListener(
            "click",
            handleTargetListClick
        );
    }


    document.addEventListener(
        "keydown",
        handleEscape
    );

    modal.addEventListener(
        "keydown",
        handleModalKeydown
    );


    if (conversationForm) {
        conversationForm.addEventListener(
            "submit",
            () => {
                setConversationType(
                    getConversationType()
                );
            }
        );
    }


    setConversationType(
        getConversationType()
    );

    renumberTargetRows();
}


function initializeMessageThread() {
    const thread = document.querySelector(
        "[data-message-thread]"
    );

    if (!thread) {
        return;
    }

    requestAnimationFrame(
        () => {
            thread.scrollTop =
                thread.scrollHeight;
        }
    );
}