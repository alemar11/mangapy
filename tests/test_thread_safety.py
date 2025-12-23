import threading

from mangapy.chapter_archiver import ChapterArchiver
from mangapy.fanfox import FanFoxRepository


def test_chapter_archiver_session_is_thread_local(tmp_path):
    archiver = ChapterArchiver(str(tmp_path))
    main_session_id = id(archiver._get_session())
    session_ids = []
    lock = threading.Lock()

    def worker():
        session = archiver._get_session()
        with lock:
            session_ids.append(id(session))

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    assert session_ids[0] != main_session_id


def test_fanfox_repository_session_is_thread_local():
    repo = FanFoxRepository()
    main_session_id = id(repo.session)
    session_ids = []
    lock = threading.Lock()

    def worker():
        session = repo.session
        with lock:
            session_ids.append(id(session))

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    assert session_ids[0] != main_session_id
