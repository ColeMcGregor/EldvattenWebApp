const enablePushButton =
    document.getElementById("enable-push-button");

const pushStatus =
    document.getElementById("push-status");

const pushSetup =
    document.getElementById("push-setup");

const pushLoginSync =
    document.getElementById("push-login-sync");


function setPushStatus(message) {
    if (!pushStatus) {
        return;
    }

    pushStatus.textContent = message;
}


function browserSupportsPush() {
    return (
        "serviceWorker" in navigator &&
        "PushManager" in window &&
        "Notification" in window
    );
}


function getCookie(name) {
    const cookies = document.cookie
        ? document.cookie.split(";")
        : [];

    for (const cookie of cookies) {
        const trimmedCookie = cookie.trim();

        if (trimmedCookie.startsWith(`${name}=`)) {
            return decodeURIComponent(
                trimmedCookie.substring(
                    name.length + 1
                )
            );
        }
    }

    return null;
}


function urlBase64ToUint8Array(base64String) {
    const padding =
        "=".repeat(
            (4 - base64String.length % 4) % 4
        );

    const base64 =
        (base64String + padding)
            .replace(/-/g, "+")
            .replace(/_/g, "/");

    const rawData =
        window.atob(base64);

    return Uint8Array.from(
        [...rawData].map(
            character => character.charCodeAt(0)
        )
    );
}


async function getVapidPublicKey() {
    const response = await fetch(
        "/notifications/push/public-key/",
        {
            method: "GET",
            credentials: "same-origin",
        }
    );

    if (!response.ok) {
        throw new Error(
            "Could not get the push public key."
        );
    }

    const data = await response.json();

    if (!data.public_key) {
        throw new Error(
            "Push public key is missing."
        );
    }

    return data.public_key;
}


async function registerServiceWorker() {
    return navigator.serviceWorker.register(
        "/service-worker.js",
        {
            scope: "/",
        }
    );
}


async function getExistingPushSubscription(
    registration
) {
    return registration.pushManager
        .getSubscription();
}


async function getOrCreatePushSubscription(
    registration
) {
    const existingSubscription =
        await getExistingPushSubscription(
            registration
        );

    if (existingSubscription) {
        return existingSubscription;
    }

    const vapidPublicKey =
        await getVapidPublicKey();

    return registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey:
            urlBase64ToUint8Array(
                vapidPublicKey
            ),
    });
}


async function savePushSubscription(
    subscription
) {
    const subscriptionData =
        subscription.toJSON();

    const response = await fetch(
        "/notifications/push/subscribe/",
        {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type":
                    "application/json",
                "X-CSRFToken":
                    getCookie("csrftoken"),
            },
            body: JSON.stringify({
                endpoint:
                    subscriptionData.endpoint,
                keys:
                    subscriptionData.keys,
                device_name:
                    navigator.userAgent,
            }),
        }
    );

    if (!response.ok) {
        throw new Error(
            "Could not save the push subscription."
        );
    }

    return response.json();
}


async function getPushSubscriptionStatus(
    subscription
) {
    const response = await fetch(
        "/notifications/push/status/",
        {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type":
                    "application/json",
                "X-CSRFToken":
                    getCookie("csrftoken"),
            },
            body: JSON.stringify({
                endpoint:
                    subscription.endpoint,
            }),
        }
    );

    if (!response.ok) {
        throw new Error(
            "Could not get push subscription status."
        );
    }

    return response.json();
}


async function setPushSubscriptionActive(
    subscription,
    active
) {
    const response = await fetch(
        "/notifications/push/active/",
        {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type":
                    "application/json",
                "X-CSRFToken":
                    getCookie("csrftoken"),
            },
            body: JSON.stringify({
                endpoint:
                    subscription.endpoint,
                active:
                    active,
            }),
        }
    );

    if (!response.ok) {
        throw new Error(
            "Could not change push subscription status."
        );
    }

    return response.json();
}


async function syncExistingPushSubscription() {
    if (!browserSupportsPush()) {
        return;
    }

    if (Notification.permission !== "granted") {
        return;
    }

    const registration =
        await registerServiceWorker();

    await navigator.serviceWorker.ready;

    const subscription =
        await getExistingPushSubscription(
            registration
        );

    if (!subscription) {
        return;
    }

    const status =
        await getPushSubscriptionStatus(
            subscription
        );

    if (!status.registered) {
        return;
    }

    if (!status.enabled) {
        return;
    }

    if (!status.active) {
        await setPushSubscriptionActive(
            subscription,
            true
        );
    }
}


function getSetupRedirectUrl() {
    if (!pushSetup) {
        return "/tavern/main/";
    }

    return (
        pushSetup.dataset.redirectUrl
        || "/tavern/main/"
    );
}


function getLoginRedirectUrl() {
    if (!pushLoginSync) {
        return "/tavern/main/";
    }

    return (
        pushLoginSync.dataset.redirectUrl
        || "/tavern/main/"
    );
}


function updateInitialPushState() {
    if (!enablePushButton) {
        return;
    }

    if (!browserSupportsPush()) {
        enablePushButton.disabled = true;

        setPushStatus(
            "Push notifications are not supported by this browser."
        );

        return;
    }

    if (Notification.permission === "denied") {
        enablePushButton.disabled = true;

        setPushStatus(
            "Notifications are blocked by this browser or device."
        );

        return;
    }

    if (Notification.permission === "granted") {
        setPushStatus(
            "Notification permission is already enabled on this device."
        );
    }
}


async function requestPushPermission() {
    if (!browserSupportsPush()) {
        return;
    }

    enablePushButton.disabled = true;

    try {
        const permission =
            await Notification.requestPermission();

        if (permission !== "granted") {
            if (permission === "denied") {
                setPushStatus(
                    "Notifications are blocked by this browser or device."
                );

                return;
            }

            setPushStatus(
                "Notifications were not enabled."
            );

            enablePushButton.disabled = false;

            return;
        }

        setPushStatus(
            "Setting up notifications..."
        );

        const registration =
            await registerServiceWorker();

        await navigator.serviceWorker.ready;

        const subscription =
            await getOrCreatePushSubscription(
                registration
            );

        await savePushSubscription(
            subscription
        );

        setPushStatus(
            "Notifications are enabled on this device."
        );

        window.location.href =
            getSetupRedirectUrl();
    } catch (error) {
        console.error(
            "Push notification setup failed.",
            error
        );

        setPushStatus(
            "EldVatten could not enable notifications."
        );

        enablePushButton.disabled = false;
    }
}


async function runLoginPushSync() {
    if (!pushLoginSync) {
        return;
    }

    try {
        await syncExistingPushSubscription();
    } catch (error) {
        console.error(
            "Push notification login sync failed.",
            error
        );
    }

    window.location.replace(
        getLoginRedirectUrl()
    );
}


if (enablePushButton) {
    enablePushButton.addEventListener(
        "click",
        requestPushPermission
    );
}


updateInitialPushState();
runLoginPushSync();