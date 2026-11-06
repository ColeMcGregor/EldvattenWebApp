from django.test import RequestFactory, SimpleTestCase, override_settings
from django.views import defaults
from django.views.csrf import csrf_failure


@override_settings(DEBUG=False)
class ErrorPageTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/missing-page/")

    def test_missing_url_uses_custom_404_page(self):
        response = self.client.get("/this-page-does-not-exist/")
        self.assertContains(response, "Page Not Found", status_code=404)
        self.assertContains(response, 'href="/"', status_code=404)

    def test_bad_request_uses_custom_400_page(self):
        response = defaults.bad_request(
            self.request,
            Exception("private 400 detail"),
        )
        self.assertContains(response, "Request Not Accepted", status_code=400)
        self.assertNotContains(response, "private 400 detail", status_code=400)

    def test_permission_denied_uses_custom_403_page(self):
        response = defaults.permission_denied(
            self.request,
            Exception("private 403 detail"),
        )
        self.assertContains(response, "Access Denied", status_code=403)
        self.assertNotContains(response, "private 403 detail", status_code=403)

    def test_server_error_uses_custom_500_page(self):
        response = defaults.server_error(self.request)
        self.assertContains(response, "Something Went Wrong", status_code=500)

    def test_csrf_failure_uses_specific_page_without_leaking_reason(self):
        response = csrf_failure(
            self.request,
            reason="private csrf rejection detail",
        )
        self.assertContains(response, "Request Not Verified", status_code=403)
        self.assertNotContains(
            response,
            "private csrf rejection detail",
            status_code=403,
        )
