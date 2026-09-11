import sys

from PySide2.QtCore import QThreadPool
from PySide2.QtWidgets import QApplication

from app.api_client import ApiClient
from app.config import load_settings
from app.dao import LocalLibraryDao, PlaylistDao, PlayStateDao
from app.database import init_db
from app.services.download_manager import DownloadManager
from app.services.player_controller import PlayerController
from app.services.playlist_service import PlaylistService
from app.services.upload_manager import UploadManager
from app.ui.main_window import MainWindow


def main() -> None:
    settings = load_settings()
    init_db(settings.db_path)

    app = QApplication(sys.argv)
    app.setApplicationName("Eureka Music")

    api = ApiClient(settings.api_base_url)
    library_dao = LocalLibraryDao(settings.db_path)
    playlist_dao = PlaylistDao(settings.db_path)
    state_dao = PlayStateDao(settings.db_path)

    download_manager = DownloadManager(api, library_dao, settings.downloads_dir)
    upload_manager = UploadManager(api)
    playlist_service = PlaylistService(playlist_dao)
    player = PlayerController(library_dao, playlist_dao, state_dao)

    window = MainWindow(
        api=api,
        library_dao=library_dao,
        playlist_service=playlist_service,
        download_manager=download_manager,
        upload_manager=upload_manager,
        player=player,
    )
    window.resize(1080, 680)
    window.show()

    player.restore_last_state()

    exit_code = app.exec_()
    # Let in-flight downloads/uploads/searches finish rather than tearing
    # down their Qt signal objects out from under a still-running worker
    # thread on process exit.
    QThreadPool.globalInstance().waitForDone(3000)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
