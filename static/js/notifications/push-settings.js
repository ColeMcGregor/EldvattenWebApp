const devicePushStatus =
    document.getElementById("device-push-status");

const enableDevicePushButton =
    document.getElementById(
        "enable-device-push-button"
    );

const disableDevicePushButton =
    document.getElementById(
        "disable-device-push-button"
    );


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


function setDeviceStatus(message) {
    if (!devicePushStatus) {
        return;
    }

    devicePushStatus.textContent = message;
}


function setDeviceButtons({
    enableVisible,
    disableVisible,
}) {
    if (enableDevicePushButton) {
        enableDevicePushButton.hidden =
            !enableVisible;
    }

    if (disableDevicePushButton) {
        disableDevicePushButton.hidden =
            !disableVisible;
    }
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


async function getServiceWorkerRegistration() {
    const registration =
        await navigator.serviceWorker.register(
            "/service-worker.js",
            {
                scope: "/",
            }
        );

    await navigator.serviceWorker.ready;

    return registration;
}


async function getCurrentSubscription() {
    const registration =
        await getServiceWorkerRegistration();

    return registration.pushManager
        .getSubscription();
}


async function saveSubscription(subscription) {
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


async function getServerSubscriptionStatus(
    subscription
) {
    if (!subscription) {
        return {
            registered: false,
        };
    }

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
            "Could not get push status."
        );
    }

    return response.json();
}


async function setSubscriptionEnabled(
    subscription,
    enabled
) {
    const response = await fetch(
        "/notifications/push/enabled/",
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
                enabled:
                    enabled,
            }),
        }
    );

    if (!response.ok) {
        throw new Error(
            "Could not change push preference."
        );
    }

    return response.json();
}


async function refreshDevicePushStatus() {
    if (!browserSupportsPush()) {
        setDeviceStatus(
            "Push notifications are not supported by this browser."
        );

        setDeviceButtons({
            enableVisible: false,
            disableVisible: false,
        });

        return;
    }

    if (Notification.permission === "denied") {
        setDeviceStatus(
            "Notifications are blocked in your browser settings."
        );

        setDeviceButtons({
            enableVisible: false,
            disableVisible: false,
        });

        return;
    }

    const subscription =
        await getCurrentSubscription();

    if (!subscription) {
        setDeviceStatus(
            "Push notifications are not enabled on this device."
        );

        setDeviceButtons({
            enableVisible: true,
            disableVisible: false,
        });

        return;
    }

    const status =
        await getServerSubscriptionStatus(
            subscription
        );

    if (!status.registered) {
        setDeviceStatus(
            "This browser has permission, but it is not registered with your EldVatten account."
        );

        setDeviceButtons({
            enableVisible: true,
            disableVisible: false,
        });

        return;
    }

    if (!status.enabled) {
        setDeviceStatus(
            "Push notifications are disabled on this device."
        );

        setDeviceButtons({
            enableVisible: true,
            disableVisible: false,
        });

        return;
    }

    if (!status.active) {
        setDeviceStatus(
            "Push notifications are not active for this session."
        );

        setDeviceButtons({
            enableVisible: true,
            disableVisible: false,
        });

        return;
    }

    if (status.paused) {
        setDeviceStatus(
            "Push notifications are paused on this device."
        );

        setDeviceButtons({
            enableVisible: false,
            disableVisible: true,
        });

        return;
    }

    setDeviceStatus(
        "Push notifications are enabled on this device."
    );

    setDeviceButtons({
        enableVisible: false,
        disableVisible: true,
    });
}


async function enableDevicePush() {
    if (!browserSupportsPush()) {
        return;
    }

    enableDevicePushButton.disabled = true;

    try {
        const permission =
            await Notification.requestPermission();

        if (permission !== "granted") {
            setDeviceStatus(
                "Notifications were not enabled."
            );

            return;
        }

        const registration =
            await getServiceWorkerRegistration();

        let subscription =
            await registration.pushManager
                .getSubscription();

        if (!subscription) {
            const vapidPublicKey =
                await getVapidPublicKey();

            subscription =
                await registration.pushManager
                    .subscribe({
                        userVisibleOnly: true,
                        applicationServerKey:
                            urlBase64ToUint8Array(
                                vapidPublicKey
                            ),
                    });
        }

        await saveSubscription(
            subscription
        );

        await refreshDevicePushStatus();
    } catch (error) {
        console.error(
            "Could not enable push notifications.",
            error
        );

        setDeviceStatus(
            "EldVatten could not enable push notifications on this device."
        );
    } finally {
        enableDevicePushButton.disabled = false;
    }
}


async function disableDevicePush() {
    disableDevicePushButton.disabled = true;

    try {
        const subscription =
            await getCurrentSubscription();

        if (!subscription) {
            await refreshDevicePushStatus();

            return;
        }

        await setSubscriptionEnabled(
            subscription,
            false
        );

        await refreshDevicePushStatus();
    } catch (error) {
        console.error(
            "Could not disable push notifications.",
            error
        );

        setDeviceStatus(
            "EldVatten could not disable push notifications on this device."
        );
    } finally {
        disableDevicePushButton.disabled = false;
    }
}


if (enableDevicePushButton) {
    enableDevicePushButton.addEventListener(
        "click",
        enableDevicePush
    );
}


if (disableDevicePushButton) {
    disableDevicePushButton.addEventListener(
        "click",
        disableDevicePush
    );
}


refreshDevicePushStatus().catch(
    error => {
        console.error(
            "Could not load push notification status.",
            error
        );

        setDeviceStatus(
            "EldVatten could not read this device's notification status."
        );
    }
);