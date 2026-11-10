
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .forms import BugReportForm
from .rate_limiting import SubmissionRateLimitExceeded
from .services import create_bug_report


@require_http_methods(["GET", "POST"])
def report_bug(request):
    if request.method == "POST":
        form = BugReportForm(request.POST)

        if form.is_valid():
            report = form.save(
                commit=False
            )

            try:
                create_bug_report(
                    report=report,
                    request=request,
                )

            except SubmissionRateLimitExceeded as error:
                response = HttpResponse(
                    (
                        "You have reached the bug report "
                        "submission limit. Please try again later."
                    ),
                    status=429,
                )

                response["Retry-After"] = str(
                    error.retry_after
                )

                return response

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
