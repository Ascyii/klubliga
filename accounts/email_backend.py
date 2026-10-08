import ssl

from django.core.mail.backends.smtp import EmailBackend as SMTPEmailBackend
from django.utils.functional import cached_property


class LocalSMTPEmailBackend(SMTPEmailBackend):
    """
    SMTP backend for a trusted local mail server.

    Uses SMTP over SSL (e.g. port 465), but does not verify
    the server's TLS certificate.
    """

    @cached_property
    def ssl_context(self):
        context = ssl.create_default_context()

        # Local/trusted SMTP server:
        # deliberately disable certificate and hostname verification.
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        return context
