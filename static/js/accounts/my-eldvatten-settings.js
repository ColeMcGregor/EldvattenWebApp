const passwordChangeModal =
    document.getElementById(
        "password-change-modal"
    );

const openPasswordModalButton =
    document.getElementById(
        "open-password-modal-button"
    );

const closePasswordModalControls =
    document.querySelectorAll(
        "[data-close-password-modal]"
    );


function openPasswordModal() {
    if (!passwordChangeModal) {
        return;
    }

    passwordChangeModal.classList.add(
        "open"
    );

    passwordChangeModal.setAttribute(
        "aria-hidden",
        "false"
    );

    const firstInput =
        passwordChangeModal.querySelector(
            "input"
        );

    if (firstInput) {
        firstInput.focus();
    }
}


function closePasswordModal() {
    if (!passwordChangeModal) {
        return;
    }

    passwordChangeModal.classList.remove(
        "open"
    );

    passwordChangeModal.setAttribute(
        "aria-hidden",
        "true"
    );

    if (openPasswordModalButton) {
        openPasswordModalButton.focus();
    }
}


if (openPasswordModalButton) {
    openPasswordModalButton.addEventListener(
        "click",
        openPasswordModal
    );
}


for (
    const control
    of closePasswordModalControls
) {
    control.addEventListener(
        "click",
        closePasswordModal
    );
}


document.addEventListener(
    "keydown",
    event => {
        if (
            event.key === "Escape"
            && passwordChangeModal
            && passwordChangeModal.classList
                .contains("open")
        ) {
            closePasswordModal();
        }
    }
);


if (
    passwordChangeModal
    && passwordChangeModal.classList
        .contains("open")
) {
    const firstInput =
        passwordChangeModal.querySelector(
            "input"
        );

    if (firstInput) {
        firstInput.focus();
    }
}