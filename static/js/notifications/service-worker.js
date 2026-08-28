self.addEventListener(
    "push",
    function (event) {
        let notificationData = {
            title: "EldVatten",
            message: "You have a new notification.",
            target_url: "/notifications/",
        };

        if (event.data) {
            try {
                const receivedData = event.data.json();

                notificationData = {
                    ...notificationData,
                    ...receivedData,
                };
            } catch (error) {
                console.error(
                    "Could not read push notification data.",
                    error
                );
            }
        }

        const options = {
            body: notificationData.message,
            data: {
                target_url: notificationData.target_url,
            },
        };

        event.waitUntil(
            self.registration.showNotification(
                notificationData.title,
                options
            )
        );
    }
);


self.addEventListener(
    "notificationclick",
    function (event) {
        event.notification.close();

        const targetUrl =
            event.notification.data?.target_url
            || "/notifications/";

        event.waitUntil(
            clients.matchAll({
                type: "window",
                includeUncontrolled: true,
            })
            .then(function (clientList) {
                for (const client of clientList) {
                    if ("focus" in client) {
                        client.navigate(targetUrl);

                        return client.focus();
                    }
                }

                if (clients.openWindow) {
                    return clients.openWindow(
                        targetUrl
                    );
                }

                return null;
            })
        );
    }
);