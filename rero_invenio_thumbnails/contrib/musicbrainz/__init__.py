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

"""MusicBrainz / Cover Art Archive thumbnail provider module.

This module provides thumbnail retrieval for music recordings by looking up
releases on MusicBrainz and fetching cover artwork from the Cover Art Archive.

The provider implements a two-step process:

1. Look up the MusicBrainz Release ID (MBID) from a barcode (EAN/UPC/ISBN-13)
   via the MusicBrainz Search API.
2. Fetch the front cover image from coverartarchive.org using the MBID.

MusicBrainz Rate Limiting:
    The MusicBrainz API enforces a limit of **1 request per second** for
    anonymous clients.  The bulk-harvest Celery task
    (:func:`rero_invenio_thumbnails.tasks.harvest_musicbrainz_covers`)
    respects this limit by sleeping 1 second between each barcode processed.

Example::

    from rero_invenio_thumbnails.contrib.musicbrainz.api import MusicBrainzProvider
    provider = MusicBrainzProvider()
    url, name = provider.get_thumbnail_url("0602435885568")
    # url == "https://coverartarchive.org/release/<mbid>/front-250"

API Documentation:
    - MusicBrainz Search API: https://musicbrainz.org/doc/MusicBrainz_API/Search
    - Cover Art Archive API: https://musicbrainz.org/doc/Cover_Art_Archive/API
"""
