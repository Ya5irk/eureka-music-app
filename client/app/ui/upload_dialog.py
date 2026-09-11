from PySide2.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QWidget


class UploadDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Upload Track")

        self._title_edit = QLineEdit()
        self._artist_edit = QLineEdit()
        self._album_edit = QLineEdit()
        self._genres_edit = QLineEdit()
        self._genres_edit.setPlaceholderText("comma, separated, genres")

        form = QFormLayout()
        form.addRow("Title", self._title_edit)
        form.addRow("Artist", self._artist_edit)
        form.addRow("Album (optional)", self._album_edit)
        form.addRow("Genres (optional)", self._genres_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        self.setLayout(form)

    def values(self) -> tuple[str, str, str, list[str]]:
        genres = [g.strip() for g in self._genres_edit.text().split(",") if g.strip()]
        return (
            self._title_edit.text().strip(),
            self._artist_edit.text().strip(),
            self._album_edit.text().strip(),
            genres,
        )
