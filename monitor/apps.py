from django.apps import AppConfig


class MonitorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "monitor"

    def ready(self):
        self._disable_dev_server_keepalive()

    @staticmethod
    def _disable_dev_server_keepalive():
        """runserver-only console cleanup - see the long comment below.

        NOTE: an earlier version of this fix tried to set a
        `Connection: close` response header from a middleware instead.
        That's invalid under the WSGI spec - applications aren't
        allowed to set hop-by-hop headers like `Connection` at all,
        only the server may - so wsgiref's assertion rejected it and
        turned every API call into a 500. This version doesn't touch
        response headers; it configures the dev server's request
        handler directly, which is the correct place for this.
        """
        try:
            from django.core.servers.basehttp import WSGIRequestHandler
        except ImportError:
            # Only relevant to `runserver`; if this import ever fails
            # (e.g. Django internals change), just skip it rather than
            # block startup over a console-noise fix.
            return

        # Django's dev server (`runserver`) speaks HTTP/1.1 by default,
        # which keeps each connection open for reuse. A dashboard that
        # polls several JSON endpoints every few seconds leaves those
        # connections idle between polls; runserver's threaded handler
        # then sits blocked waiting on that idle socket and eventually
        # times out, printing a harmless-but-noisy TimeoutError
        # traceback (it's for the *next, never-sent* request on a
        # connection the browser kept open - no request is ever
        # dropped or mishandled).
        #
        # Dropping to HTTP/1.0 disables persistent connections
        # server-side: every request/response closes its own
        # connection immediately, so there's nothing idle left to time
        # out. WSGIRequestHandler is exclusive to `runserver` -
        # gunicorn/uWSGI/etc. never use it, so this has zero effect in
        # production.
        WSGIRequestHandler.protocol_version = "HTTP/1.0"
