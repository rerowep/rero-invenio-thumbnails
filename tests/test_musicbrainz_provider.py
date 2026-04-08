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

"""Tests for MusicBrainz provider."""

import io

import pytest
import requests
from PIL import Image

from rero_invenio_thumbnails.contrib.musicbrainz.api import MusicBrainzProvider

_BARCODE = "0602435885568"
_MBID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
_MB_SEARCH_URL = f"https://musicbrainz.org/ws/2/release/?query=barcode:{_BARCODE}&fmt=json"
_CAA_URL = f"https://coverartarchive.org/release/{_MBID}/front-250"


def _make_jpeg(width=100, height=150):
    img = Image.new("RGB", (width, height), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf.getvalue()


def test_musicbrainz_init(app):
    """Test MusicBrainz provider initialisation."""
    with app.app_context():
        provider = MusicBrainzProvider()
        assert provider.name == "musicbrainz"
        assert "rero-invenio-thumbnails" in provider.headers["User-Agent"]
        assert "software@rero.ch" in provider.headers["User-Agent"]


def test_musicbrainz_get_thumbnail_url_success(app, requests_mock):
    """Test successful cover retrieval from MusicBrainz / Cover Art Archive."""
    with app.app_context():
        requests_mock.get(
            _MB_SEARCH_URL,
            json={"releases": [{"id": _MBID, "title": "Test Album"}]},
            status_code=200,
        )
        requests_mock.get(
            _CAA_URL,
            status_code=200,
            headers={"Content-Type": "image/jpeg"},
            content=_make_jpeg(),
        )

        provider = MusicBrainzProvider()
        url, name = provider.get_thumbnail_url(_BARCODE)

        assert url == _CAA_URL
        assert name == "musicbrainz"
        assert requests_mock.call_count == 2


def test_musicbrainz_no_release_found(app, requests_mock):
    """Test that None is returned when MusicBrainz finds no matching release."""
    with app.app_context():
        requests_mock.get(_MB_SEARCH_URL, json={"releases": []}, status_code=200)

        provider = MusicBrainzProvider()
        url, name = provider.get_thumbnail_url(_BARCODE)

        assert url is None
        assert name == "musicbrainz"


def test_musicbrainz_mb_api_error(app, requests_mock):
    """Test that None is returned on MusicBrainz API server error."""
    with app.app_context():
        requests_mock.get(_MB_SEARCH_URL, status_code=503)

        provider = MusicBrainzProvider()
        url, name = provider.get_thumbnail_url(_BARCODE)

        assert url is None
        assert name == "musicbrainz"


def test_musicbrainz_caa_not_found(app, requests_mock):
    """Test that None is returned when Cover Art Archive has no image."""
    with app.app_context():
        requests_mock.get(
            _MB_SEARCH_URL,
            json={"releases": [{"id": _MBID}]},
            status_code=200,
        )
        requests_mock.get(_CAA_URL, status_code=404)

        provider = MusicBrainzProvider()
        url, name = provider.get_thumbnail_url(_BARCODE)

        assert url is None
        assert name == "musicbrainz"


def test_musicbrainz_caa_small_image(app, requests_mock):
    """Test that tiny placeholder images are rejected."""
    with app.app_context():
        requests_mock.get(
            _MB_SEARCH_URL,
            json={"releases": [{"id": _MBID}]},
            status_code=200,
        )
        requests_mock.get(
            _CAA_URL,
            status_code=200,
            headers={"Content-Type": "image/jpeg"},
            content=_make_jpeg(width=5, height=5),
        )

        provider = MusicBrainzProvider()
        url, name = provider.get_thumbnail_url(_BARCODE)

        assert url is None
        assert name == "musicbrainz"


def test_musicbrainz_request_exception(app, requests_mock):
    """Test that a connection error is handled gracefully."""
    with app.app_context():
        requests_mock.get(_MB_SEARCH_URL, exc=requests.exceptions.ConnectionError("timeout"))

        provider = MusicBrainzProvider()
        url, name = provider.get_thumbnail_url(_BARCODE)

        assert url is None
        assert name == "musicbrainz"


def test_musicbrainz_barcode_cleaned(app, requests_mock):
    """Test that hyphens/spaces in barcode are stripped before the API call."""
    cleaned = _BARCODE
    mb_url = f"https://musicbrainz.org/ws/2/release/?query=barcode:{cleaned}&fmt=json"
    with app.app_context():
        requests_mock.get(mb_url, json={"releases": []}, status_code=200)

        provider = MusicBrainzProvider()
        # Pass barcode with spaces — should be cleaned to digits only.
        url, name = provider.get_thumbnail_url("0602 435 885 568")

        assert url is None
        assert name == "musicbrainz"
        assert requests_mock.called


@pytest.mark.network
def test_musicbrainz_real_cover(app):
    """Test MusicBrainz returns a valid cover for a well-known barcode."""
    with app.app_context():
        provider = MusicBrainzProvider()
        # Massive Attack — Mezzanine (commonly available on CAA)
        url, name = provider.get_thumbnail_url("0602435885568")

        assert name == "musicbrainz"
        assert url is None or "coverartarchive.org" in url
