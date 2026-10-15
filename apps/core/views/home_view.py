from django.shortcuts import render
from django.views import View


class HomeView(View):
    """Public homepage for M.O.D. Nsukka Diocese."""

    template_name = "home.html"

    def get(self, request):
        return render(request, self.template_name)
