
from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .forms import BugReportForm
from .services import create_bug_report


def _submission_rate_limit(request):
    # TODO: Replace or configure with a shared production rate-limit backend.
    identifier = (
        f"user:{request.user.pk}"
        if request.user.is_authenticated
        else f"ip:{request.META.get('REMOTE_ADDR', 'unknown')}"
    )

    key = f"feedback:submission:{identifier}"

    return cache.add(
        key,
        True,
        timeout=60,
    )


@require_http_methods(["GET", "POST"])
def report_bug(request):
    if request.method == "POST":
        form = BugReportForm(request.POST)

        if form.is_valid():
            if not _submission_rate_limit(request):
                return HttpResponse(
                    "Please wait before submitting another report.",
                    status=429,
                )

            report = form.save(commit=False)

            create_bug_report(
                report=report,
                request=request,
            )

            return redirect(
                "feedback:report_received",
            )

    else:
        form = BugReportForm(
            initial={
                "contact_email": (
                    request.user.email
                    if request.user.is_authenticated
                    else ""
                ),
                "page_url": request.GET.get(
                    "page",
                    "",
                ),
            },
        )

    return render(
        request,
        "feedback/report_form.html",
        {
            "form": form,
        },
    )


def report_received(request):
    return render(
        request,
        "feedback/report_received.html",
    )
