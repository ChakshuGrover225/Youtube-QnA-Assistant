"""ytchat - chat with any YouTube video or Instagram Reel from your terminal."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("video-summarisation-project")
except PackageNotFoundError:  # running from a source checkout that isn't installed
    __version__ = "0.0.0"
