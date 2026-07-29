"""
zipper.py - Zero-Disk In-Flight Dynamic Zip Streamer
Uses zipstream-ng (imported as zipstream) to stream ZIP file archives directly over HTTP chunk-by-chunk.
As playlist tracks complete download and MP3 encoding, they are added to the zip stream.
"""

import asyncio
from typing import AsyncGenerator, List, Tuple
import zipstream
import os
import logging

logger = logging.getLogger(__name__)


async def stream_playlist_as_zip(
    file_list: List[Tuple[str, str]], chunk_size: int = 65536
) -> AsyncGenerator[bytes, None]:
    """
    Given a list of (file_path, archive_filename) tuples, streams a ZIP archive.
    """
    zs = zipstream.ZipStream()

    for file_path, arcname in file_list:
        if os.path.exists(file_path):
            zs.add_path(file_path, arcname=arcname)

    loop = asyncio.get_running_loop()
    iterator = iter(zs)

    while True:
        chunk = await loop.run_in_executor(None, next, iterator, None)
        if chunk is None:
            break
        yield chunk
