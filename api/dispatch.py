"""BoliCheck's Vercel Functions entry point."""

from bolicheck import Handler


class handler(Handler):
    hosted = True
