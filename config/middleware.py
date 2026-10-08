from django.conf import settings
from django.utils import translation
from django.utils.cache import patch_vary_headers


class LanguageMiddleware:
    """Activate the UI language chosen with the language switch.

    The choice is kept in Django's language cookie (set by the ``set_language``
    view). Without a valid choice the default ``LANGUAGE_CODE`` is used; unlike
    Django's LocaleMiddleware, the browser's Accept-Language header is ignored.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        language = settings.LANGUAGE_CODE
        chosen = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
        if chosen:
            try:
                language = translation.get_supported_language_variant(chosen)
            except LookupError:
                pass
        request.LANGUAGE_CODE = language
        with translation.override(language):
            response = self.get_response(request)
        patch_vary_headers(response, ["Cookie"])
        response.headers.setdefault("Content-Language", language)
        return response
