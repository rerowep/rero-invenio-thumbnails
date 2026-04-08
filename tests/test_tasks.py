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

"""Tests for Celery harvest tasks."""

import io
from unittest.mock import patch

from PIL import Image

from rero_invenio_thumbnails.tasks import harvest_musicbrainz_covers

_MBID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


def _make_jpeg(width=100, height=150):
    img = Image.new("RGB", (width, height), color="green")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf.getvalue()


def test_harvest_musicbrainz_covers_found(app, requests_mock):
    """Test harvest task correctly reports found covers."""
    barcode = "0602435885568"
    mb_url = f"https://musicbrainz.org/ws/2/release/?query=barcode:{barcode}&fmt=json"
    caa_url = f"https://coverartarchive.org/release/{_MBID}/front-250"

    requests_mock.get(mb_url, json={"releases": [{"id": _MBID}]}, status_code=200)
    requests_mock.get(
        caa_url,
        status_code=200,
        headers={"Content-Type": "image/jpeg"},
        content=_make_jpeg(),
    )

    with app.app_context(), patch("rero_invenio_thumbnails.tasks.time.sleep") as mock_sleep:
        report = harvest_musicbrainz_covers([barcode], rate_limit_delay=0)

    assert barcode in report["found"]
    assert report["missing"] == []
    assert report["errors"] == []
    mock_sleep.assert_not_called()  # no delay after last (only) item


def test_harvest_musicbrainz_covers_missing(app, requests_mock):
    """Test harvest task correctly reports missing covers."""
    barcode = "0000000000000"
    mb_url = f"https://musicbrainz.org/ws/2/release/?query=barcode:{barcode}&fmt=json"
    requests_mock.get(mb_url, json={"releases": []}, status_code=200)

    with app.app_context():
        report = harvest_musicbrainz_covers([barcode], rate_limit_delay=0)

    assert report["found"] == []
    assert barcode in report["missing"]
    assert report["errors"] == []


def test_harvest_musicbrainz_covers_rate_limit_delay(app, requests_mock):
    """Test that rate-limit delay is applied between items but not after the last."""
    barcodes = ["0602435885568", "0000000000001"]
    for bc in barcodes:
        requests_mock.get(
            f"https://musicbrainz.org/ws/2/release/?query=barcode:{bc}&fmt=json",
            json={"releases": []},
            status_code=200,
        )

    with app.app_context(), patch("rero_invenio_thumbnails.tasks.time.sleep") as mock_sleep:
        harvest_musicbrainz_covers(barcodes, rate_limit_delay=1.0)

    # sleep called once between the two items, not after the last one
    assert mock_sleep.call_count == 1
    mock_sleep.assert_called_once_with(1.0)


def test_harvest_musicbrainz_covers_mixed(app, requests_mock):
    """Test harvest task with a mix of found and missing barcodes."""
    found_bc = "0602435885568"
    missing_bc = "0000000000000"

    requests_mock.get(
        f"https://musicbrainz.org/ws/2/release/?query=barcode:{found_bc}&fmt=json",
        json={"releases": [{"id": _MBID}]},
        status_code=200,
    )
    caa_url = f"https://coverartarchive.org/release/{_MBID}/front-250"
    requests_mock.get(
        caa_url,
        status_code=200,
        headers={"Content-Type": "image/jpeg"},
        content=_make_jpeg(),
    )
    requests_mock.get(
        f"https://musicbrainz.org/ws/2/release/?query=barcode:{missing_bc}&fmt=json",
        json={"releases": []},
        status_code=200,
    )

    with app.app_context():
        report = harvest_musicbrainz_covers([found_bc, missing_bc], rate_limit_delay=0)

    assert found_bc in report["found"]
    assert missing_bc in report["missing"]
    assert report["errors"] == []
