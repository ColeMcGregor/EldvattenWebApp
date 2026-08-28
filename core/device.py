def is_mobile_request(request):
    user_agent = request.META.get(
        "HTTP_USER_AGENT",
        "",
    ).lower()

    mobile_markers = (
        "android",
        "iphone",
        "ipod",
        "mobile",
    )

    return any(
        marker in user_agent
        for marker in mobile_markers
    )


def get_app_template(
    request,
    *,
    desktop_template,
    mobile_template,
):
    if is_mobile_request(request):
        return mobile_template

    return desktop_template