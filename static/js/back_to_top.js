
(() => {
    const button = document.getElementById(
        "app-back-to-top"
    );

    const mainContent = document.querySelector(
        ".app-main-content"
    );

    if (!button || !mainContent) {
        return;
    }

    const scrollThreshold = 300;

    const documentScroller = (
        document.scrollingElement
        || document.documentElement
    );

    const reducedMotion = window.matchMedia(
        "(prefers-reduced-motion: reduce)"
    );

    let activeScroller = documentScroller;


    function isScrollable(element) {
        if (!(element instanceof HTMLElement)) {
            return false;
        }

        if (
            element.matches(
                "textarea, input, select, [contenteditable]"
            )
        ) {
            return false;
        }

        const overflow = window.getComputedStyle(
            element
        ).overflowY;

        return (
            ["auto", "scroll", "overlay"].includes(overflow)
            && element.scrollHeight > element.clientHeight + 1
        );
    }


    function updateVisibility() {
        if (
            activeScroller !== documentScroller
            && (
                !activeScroller.isConnected
                || !isScrollable(activeScroller)
            )
        ) {
            activeScroller = documentScroller;
        }

        const visible = (
            activeScroller.scrollTop > scrollThreshold
        );

        button.classList.toggle(
            "is-visible",
            visible
        );

        button.disabled = !visible;

        button.setAttribute(
            "aria-hidden",
            String(!visible)
        );

        button.tabIndex = visible ? 0 : -1;
    }


    function updatePosition() {
        const bounds = mainContent.getBoundingClientRect();

        const preferredRight = (
            window.innerWidth - bounds.right + 20
        );

        const maximumRight = Math.max(
            16,
            window.innerWidth - button.offsetWidth - 16
        );

        const right = Math.min(
            Math.max(16, preferredRight),
            maximumRight
        );

        button.style.right = `${right}px`;
    }


    function handleScroll(event) {
        const target = event.target;

        if (
            target === document
            || target === document.documentElement
            || target === document.body
            || target === window
        ) {
            activeScroller = documentScroller;
            updateVisibility();
            return;
        }

        if (
            target instanceof HTMLElement
            && mainContent.contains(target)
            && isScrollable(target)
        ) {
            activeScroller = target;
            updateVisibility();
        }
    }


    function findInitialScroller() {
        let mostScrolled = documentScroller;

        for (
            const element of mainContent.querySelectorAll("*")
        ) {
            if (
                isScrollable(element)
                && element.scrollTop > mostScrolled.scrollTop
            ) {
                mostScrolled = element;
            }
        }

        activeScroller = mostScrolled;
    }


    function focusTopHeading(container) {
        const heading = (
            container.querySelector(
                "h1, h2, [role='heading']"
            )
            || mainContent.querySelector(
                "h1, h2, [role='heading']"
            )
        );

        if (!heading) {
            return;
        }

        const originalTabIndex = heading.getAttribute(
            "tabindex"
        );

        heading.setAttribute("tabindex", "-1");

        heading.focus({
            preventScroll: true
        });

        heading.addEventListener(
            "blur",
            () => {
                if (originalTabIndex === null) {
                    heading.removeAttribute("tabindex");
                } else {
                    heading.setAttribute(
                        "tabindex",
                        originalTabIndex
                    );
                }
            },
            { once: true }
        );
    }


    function scrollToTop() {
        const behavior = reducedMotion.matches
            ? "instant"
            : "smooth";

        const scroller = activeScroller;

        if (scroller === documentScroller) {
            window.scrollTo({
                top: 0,
                behavior
            });
        } else {
            scroller.scrollTo({
                top: 0,
                behavior
            });
        }

        focusTopHeading(
            scroller === documentScroller
                ? mainContent
                : scroller
        );
    }


    button.addEventListener(
        "click",
        scrollToTop
    );

    document.addEventListener(
        "scroll",
        handleScroll,
        {
            capture: true,
            passive: true
        }
    );

    window.addEventListener(
        "scroll",
        handleScroll,
        { passive: true }
    );

    window.addEventListener(
        "resize",
        () => {
            updatePosition();
            updateVisibility();
        }
    );

    findInitialScroller();
    updatePosition();
    updateVisibility();
})();
