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

"""Celery tasks for thumbnail harvesting.

Usage from rero-ils
-------------------

Harvest MusicBrainz covers for EDA (audio recording) documents that have no
thumbnail yet::

    from rero_invenio_thumbnails.tasks import harvest_musicbrainz_covers

    # 1. Collect barcodes/ISBNs from EDA documents missing a thumbnail.
    #    Adjust the Elasticsearch query to match your rero-ils index and
    #    document-type conventions.
    from invenio_search import current_search_client

    hits = current_search_client.search(
        index="documents-document-v0.0.1",
        body={
            "query": {
                "bool": {
                    "must": [
                        {"terms": {"type.main_type": ["docmaintype_music"]}},
                    ],
                    "must_not": [{"exists": {"field": "thumbnails"}}],
                }
            },
            "_source": ["identifiedBy"],
            "size": 1000,
        },
    )

    barcodes = [
        id_["value"]
        for hit in hits["hits"]["hits"]
        for id_ in hit["_source"].get("identifiedBy", [])
        if id_.get("type") in ("bf:Ean", "bf:Upc", "bf:Isbn")
    ]

    # 2. Dispatch the task (async).
    result = harvest_musicbrainz_covers.delay(barcodes)

    # 3. Inspect the result (synchronous example, useful for scripts).
    report = harvest_musicbrainz_covers(barcodes)
    # report == {"found": [...], "missing": [...], "errors": [...]}
"""

import time

from celery import shared_task
from flask import current_app

from rero_invenio_thumbnails.contrib.musicbrainz.api import MusicBrainzProvider

#: MusicBrainz enforces 1 request per second for anonymous clients.
_MB_RATE_LIMIT_DELAY = 1.0


@shared_task
def harvest_musicbrainz_covers(barcodes, rate_limit_delay=_MB_RATE_LIMIT_DELAY):
    """Harvest cover images from MusicBrainz for a list of barcodes.

    For each barcode the task queries MusicBrainz for a matching release and,
    if found, validates the Cover Art Archive thumbnail URL.  A delay of
    *rate_limit_delay* seconds is inserted **between** each barcode to comply
    with MusicBrainz's 1 req/s rate limit.

    :param barcodes: Iterable of EAN/UPC/ISBN-13 barcodes to process.
    :param rate_limit_delay: Seconds to sleep between requests (default: 1.0).
    :returns: dict with three keys:

        * ``"found"``   — barcodes for which a cover URL was resolved.
        * ``"missing"`` — barcodes for which no cover was found.
        * ``"errors"``  — barcodes that raised an unexpected exception.
    """
    provider = MusicBrainzProvider()
    found = []
    missing = []
    errors = []

    barcodes = list(barcodes)
    current_app.logger.info(f"MusicBrainz harvest started for {len(barcodes)} barcodes.")

    for index, barcode in enumerate(barcodes):
        try:
            url, _ = provider.get_thumbnail_url(barcode)
            if url:
                found.append(barcode)
                current_app.logger.debug(f"MusicBrainz cover found for {barcode}: {url}")
            else:
                missing.append(barcode)
                current_app.logger.debug(f"MusicBrainz cover not found for {barcode}.")
        except Exception as exc:
            current_app.logger.error(
                f"Error harvesting MusicBrainz cover for {barcode}: {exc}",
                exc_info=True,
            )
            errors.append(barcode)

        # Honour the MusicBrainz 1 req/s rate limit — skip delay after the last item.
        if index < len(barcodes) - 1:
            time.sleep(rate_limit_delay)

    current_app.logger.info(
        f"MusicBrainz harvest complete: "
        f"{len(found)} found, {len(missing)} missing, {len(errors)} errors."
    )
    return {"found": found, "missing": missing, "errors": errors}
