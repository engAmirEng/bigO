from django.contrib.auth.views import LoginView


class CustomLoginView(LoginView):
    def get_redirect_url(self):
        """
        I need to redirect to anywhere because of external auths like nginx
        """
        redirect_to = self.request.POST.get(self.redirect_field_name, self.request.GET.get(self.redirect_field_name))
        return redirect_to
