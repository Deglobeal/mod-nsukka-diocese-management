from django.http import HttpResponse
from django.views import View


class HomeView(View):
    """Temporary project landing page; replace with the designed public homepage."""

    def get(self, request):
        return HttpResponse(
            "M.O.D. Nsukka Diocese Membership Management System — project scaffold ready.",
            content_type="text/plain; charset=utf-8",
        )
