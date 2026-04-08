# RERO Thumbnails
# Copyright (C) 2026 RERO.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Thumbnails MusicBrainz / Cover Art Archive provider."""

from importlib.metadata import version as _pkg_version

import requests
from flask import current_app

from rero_invenio_thumbnails.contrib.api import BaseProvider
from rero_invenio_thumbnails.contrib.utils import (
    clean_isbn,
    fetch_and_validate_thumbnail,
    fetch_with_retries,
    handle_provider_errors,
)


class MusicBrainzProvider(BaseProvider):
    """Thumbnail provider for music recordings via MusicBrainz / Cover Art Archive.

    Looks up a release on MusicBrainz by barcode (EAN/UPC/ISBN-13), then fetches
    the front cover from the Cover Art Archive (coverartarchive.org).

    MusicBrainz imposes a rate limit of **1 request per second** for anonymous
    clients.  Single calls to :meth:`get_thumbnail_url` are not throttled here;
    callers that process many barcodes in a loop (e.g. the Celery harvest task)
    are responsible for inserting the required delay between iterations.

    Example::

        provider = MusicBrainzProvider()
        url, name = provider.get_thumbnail_url("0602435885568")
    """

    name = "musicbrainz"

    #: MusicBrainz API base URL.
    _MB_API = "https://musicbrainz.org/ws/2"

    #: Cover Art Archive front-cover URL template (250 px thumbnail).
    _CAA_FRONT_URL = "https://coverartarchive.org/release/{mbid}/front-250"

    def __init__(self):
        """Initialize the MusicBrainz provider."""
        _version = _pkg_version("rero-invenio-thumbnails")
        # MusicBrainz requires a descriptive User-Agent that includes contact info.
        self.headers = {
            "User-Agent": (
                f"rero-invenio-thumbnails/{_version}"
                " (software@rero.ch +https://github.com/rero/rero-invenio-thumbnails)"
            )
        }

    def barcode_to_mbid(self, barcode):
        """Return the MusicBrainz Release ID (MBID) for a barcode.

        Queries the MusicBrainz search API with ``barcode:{barcode}`` and returns
        the ID of the first matching release.

        :param barcode: EAN-13, UPC, or ISBN-13 barcode (digits only).
        :returns: str or None — MBID of the first matching release, or None.

        Example::

            provider = MusicBrainzProvider()
            mbid = provider.barcode_to_mbid("0602435885568")
            # mbid == "a1b2c3d4-..."
        """
        try:
            url = f"{self._MB_API}/release/?query=barcode:{barcode}&fmt=json"
            response = fetch_with_retries(url, headers=self.headers, timeout=10)
            if response.status_code != requests.codes.ok:
                return None
            releases = response.json().get("releases", [])
            if releases:
                return releases[0]["id"]
        except (ValueError, KeyError) as exc:
            current_app.logger.warning(f"MusicBrainz response parse error for barcode {barcode}: {exc}")
        except requests.RequestException as exc:
            current_app.logger.warning(f"MusicBrainz request failed for barcode {barcode}: {exc}")
        except Exception as exc:
            current_app.logger.error(
                f"Unexpected error in MusicBrainz barcode_to_mbid for barcode {barcode}: {exc}",
                exc_info=True,
            )
        return None

    @handle_provider_errors("MusicBrainz")
    def get_thumbnail_url(self, isbn):
        """Retrieve the cover URL for a music recording from the Cover Art Archive.

        Converts the barcode to a MusicBrainz MBID, then validates the Cover Art
        Archive thumbnail URL.

        :param isbn: EAN/UPC/barcode of the recording (hyphens and spaces are stripped).
        :returns: tuple — ``(url, "musicbrainz")`` where *url* is the image URL or None.

        Example::

            provider = MusicBrainzProvider()
            url, name = provider.get_thumbnail_url("0602435885568")
            # url == "https://coverartarchive.org/release/<mbid>/front-250"
        """
        barcode = clean_isbn(isbn)
        mbid = self.barcode_to_mbid(barcode)
        if not mbid:
            return None, self.name

        url = self._CAA_FRONT_URL.format(mbid=mbid)
        if fetch_and_validate_thumbnail(url, "MusicBrainz", barcode, timeout=10, headers=self.headers):
            return url, self.name
        return None, self.name
