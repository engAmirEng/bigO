import os
import tempfile

import telethon.sessions.sqlite

from django.core.files.base import ContentFile

from ..models import TelegramSession


class Session(telethon.sessions.SQLiteSession):
    def __init__(self, *args, session: TelegramSession, **kwargs):
        fd, filepath = tempfile.mkstemp(suffix=telethon.sessions.sqlite.EXTENSION)
        os.close(fd)
        if session.sqlite_file:
            with open(filepath, "wb") as f:
                f.write(session.sqlite_file.read())
                f.flush()
                os.fsync(f.fileno())
        self.session = session
        super().__init__(*args, session_id=filepath, **kwargs)

    def close(self):
        super().close()
        self.session.refresh_from_db()
        with open(self.filename, "rb") as f:
            final_db_bytes = f.read()
            self.session.sqlite_file.save(name=str(self.session.id), content=ContentFile(final_db_bytes))
        os.unlink(self.filename)
