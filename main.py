import sys
import os
import json
import random
import base64
import subprocess
from datetime import datetime

import vlc
from mutagen import File as MutagenFile

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QFileDialog,
    QSlider,
    QLineEdit,
    QMessageBox,
    QFrame,
    QMenu,
    QInputDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QAbstractItemView,
    QSplitter,
)


# ============================================================
# CONFIG
# ============================================================

APP_NAME = "YuiMusic"

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

DATA_DIR = os.path.join(
    BASE_DIR,
    "data"
)

LIBRARY_FILE = os.path.join(
    DATA_DIR,
    "library.json"
)

SETTINGS_FILE = os.path.join(
    DATA_DIR,
    "settings.json"
)

SUPPORTED_EXTENSIONS = (
    ".mp3",
    ".mp4",
    ".m4a",
    ".wav",
    ".flac",
    ".ogg",
    ".aac",
)


# ============================================================
# HELPERS
# ============================================================

def ensure_data_dir():
    os.makedirs(
        DATA_DIR,
        exist_ok=True
    )


def artwork_to_base64(data):
    if not data:
        return None

    try:
        return base64.b64encode(data).decode("ascii")
    except Exception:
        return None


def artwork_from_base64(data):
    if not data:
        return None

    try:
        return base64.b64decode(data)
    except Exception:
        return None


def format_time(seconds):
    try:
        seconds = int(seconds)
    except Exception:
        seconds = 0

    if seconds < 0:
        seconds = 0

    minutes = seconds // 60
    seconds = seconds % 60

    return f"{minutes}:{seconds:02d}"


def safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


# ============================================================
# METADATA
# ============================================================

def read_metadata(file_path):

    file_path = os.path.abspath(file_path)

    title = os.path.splitext(
        os.path.basename(file_path)
    )[0]

    artist = "Unknown Artist"
    album = "Unknown Album"
    duration = 0
    artwork = None

    try:

        audio = MutagenFile(
            file_path,
            easy=False
        )

        if audio:

            if getattr(
                audio.info,
                "length",
                None
            ):
                duration = float(
                    audio.info.length
                )

            tags = audio.tags

            if tags:

                # MP3 / ID3
                if "TIT2" in tags:
                    value = tags["TIT2"]
                    if value:
                        title = str(value)

                if "TPE1" in tags:
                    value = tags["TPE1"]
                    if value:
                        artist = str(value)

                if "TALB" in tags:
                    value = tags["TALB"]
                    if value:
                        album = str(value)

                # MP4
                if "\xa9nam" in tags:
                    value = tags["\xa9nam"]
                    if value:
                        title = str(value[0])

                if "\xa9ART" in tags:
                    value = tags["\xa9ART"]
                    if value:
                        artist = str(value[0])

                if "\xa9alb" in tags:
                    value = tags["\xa9alb"]
                    if value:
                        album = str(value[0])

                # MP3 artwork
                for key in tags.keys():

                    if str(key).startswith(
                        "APIC"
                    ):

                        apic = tags[key]

                        if getattr(
                            apic,
                            "data",
                            None
                        ):
                            artwork = artwork_to_base64(
                                apic.data
                            )

                        break

                # MP4 artwork
                if artwork is None:

                    covr = tags.get(
                        "covr"
                    )

                    if covr:

                        artwork = artwork_to_base64(
                            bytes(covr[0])
                        )

    except Exception as exc:

        print(
            f"Metadata error: {file_path}"
        )
        print(exc)

    return {
        "title": title,
        "artist": artist,
        "album": album,
        "path": file_path,
        "duration": duration,
        "artwork": artwork,
        "added": datetime.now().isoformat(
            timespec="seconds"
        ),
        "liked": False,
    }


# ============================================================
# LIBRARY MANAGER
# ============================================================

class LibraryManager:

    def __init__(self):

        ensure_data_dir()

        self.songs = []
        self.playlists = {}
        self.recent = []

        self.load()

    # --------------------------------------------------------

    def load(self):

        if not os.path.exists(
            LIBRARY_FILE
        ):
            return

        try:

            with open(
                LIBRARY_FILE,
                "r",
                encoding="utf-8"
            ) as file:

                data = json.load(file)

            self.songs = data.get(
                "songs",
                []
            )

            self.playlists = data.get(
                "playlists",
                {}
            )

            self.recent = data.get(
                "recent",
                []
            )

        except Exception as exc:

            print(
                "Unable to load library:"
            )
            print(exc)

            self.songs = []
            self.playlists = {}
            self.recent = []

    # --------------------------------------------------------

    def save(self):

        ensure_data_dir()

        try:

            with open(
                LIBRARY_FILE,
                "w",
                encoding="utf-8"
            ) as file:

                json.dump(
                    {
                        "songs": self.songs,
                        "playlists": self.playlists,
                        "recent": self.recent,
                    },
                    file,
                    indent=4,
                    ensure_ascii=False
                )

        except Exception as exc:

            print(
                "Unable to save library:"
            )
            print(exc)

    # --------------------------------------------------------

    def cleanup_missing(self):

        existing = set()

        cleaned_songs = []

        for song in self.songs:

            path = song.get(
                "path",
                ""
            )

            if path and os.path.exists(
                path
            ):

                existing.add(
                    os.path.abspath(path)
                )

                cleaned_songs.append(
                    song
                )

        self.songs = cleaned_songs

        self.recent = [
            path
            for path in self.recent
            if os.path.abspath(path)
            in existing
        ]

        for name in list(
            self.playlists.keys()
        ):

            self.playlists[name] = [
                path
                for path in self.playlists[name]
                if os.path.abspath(path)
                in existing
            ]

        self.save()

    # --------------------------------------------------------

    def find(self, path):

        if not path:
            return None

        target = os.path.abspath(
            path
        )

        for song in self.songs:

            if os.path.abspath(
                song.get("path", "")
            ) == target:

                return song

        return None

    # --------------------------------------------------------

    def add_song(self, song):

        if not song:
            return False

        if self.find(
            song.get("path")
        ):

            return False

        self.songs.append(song)
        return True

    # --------------------------------------------------------

    def add_songs(self, songs):

        added = 0

        for song in songs:

            if self.add_song(song):
                added += 1

        if added:
            self.save()

        return added

    # --------------------------------------------------------

    def remove_song(self, path):

        target = os.path.abspath(
            path
        )

        self.songs = [
            song
            for song in self.songs
            if os.path.abspath(
                song.get("path", "")
            ) != target
        ]

        self.recent = [
            item
            for item in self.recent
            if os.path.abspath(item)
            != target
        ]

        for playlist in self.playlists:

            self.playlists[playlist] = [
                item
                for item in self.playlists[playlist]
                if os.path.abspath(item)
                != target
            ]

        self.save()

    # --------------------------------------------------------

    def add_recent(self, path):

        path = os.path.abspath(
            path
        )

        self.recent = [
            item
            for item in self.recent
            if os.path.abspath(item)
            != path
        ]

        self.recent.insert(
            0,
            path
        )

        self.recent = self.recent[:50]

        self.save()

    # --------------------------------------------------------

    def toggle_like(self, path):

        song = self.find(path)

        if not song:
            return False

        song["liked"] = not song.get(
            "liked",
            False
        )

        self.save()

        return song["liked"]

    # --------------------------------------------------------

    def create_playlist(self, name):

        if not name:
            return False

        name = name.strip()

        if not name:
            return False

        if name in self.playlists:
            return False

        self.playlists[name] = []

        self.save()

        return True

    # --------------------------------------------------------

    def rename_playlist(
        self,
        old_name,
        new_name
    ):

        if (
            old_name not in
            self.playlists
        ):
            return False

        if not new_name:
            return False

        new_name = new_name.strip()

        if (
            not new_name or
            new_name in self.playlists
        ):
            return False

        self.playlists[new_name] = (
            self.playlists.pop(old_name)
        )

        self.save()

        return True

    # --------------------------------------------------------

    def delete_playlist(self, name):

        if name not in self.playlists:
            return False

        del self.playlists[name]

        self.save()

        return True

    # --------------------------------------------------------

    def add_to_playlist(
        self,
        playlist,
        path
    ):

        if playlist not in self.playlists:
            return False

        path = os.path.abspath(
            path
        )

        if path not in self.playlists[
            playlist
        ]:

            self.playlists[
                playlist
            ].append(path)

            self.save()

            return True

        return False

    # --------------------------------------------------------

    def remove_from_playlist(
        self,
        playlist,
        path
    ):

        if playlist not in self.playlists:
            return False

        path = os.path.abspath(
            path
        )

        self.playlists[
            playlist
        ] = [
            item
            for item in self.playlists[
                playlist
            ]
            if os.path.abspath(item)
            != path
        ]

        self.save()

        return True


# ============================================================
# SETTINGS MANAGER
# ============================================================

class SettingsManager:

    DEFAULTS = {
        "volume": 70,
        "speed": 1.0,
        "shuffle": False,
        "repeat": 0,
        "window_width": 1450,
        "window_height": 900,
        "queue": [],
    }

    def __init__(self):

        ensure_data_dir()

        self.settings = dict(
            self.DEFAULTS
        )

        self.load()

    # --------------------------------------------------------

    def load(self):

        if not os.path.exists(
            SETTINGS_FILE
        ):
            return

        try:

            with open(
                SETTINGS_FILE,
                "r",
                encoding="utf-8"
            ) as file:

                saved = json.load(file)

            self.settings.update(
                saved
            )

        except Exception as exc:

            print(
                "Unable to load settings:"
            )
            print(exc)

    # --------------------------------------------------------

    def save(self):

        try:

            with open(
                SETTINGS_FILE,
                "w",
                encoding="utf-8"
            ) as file:

                json.dump(
                    self.settings,
                    file,
                    indent=4
                )

        except Exception as exc:

            print(
                "Unable to save settings:"
            )
            print(exc)

    # --------------------------------------------------------

    def get(self, key):

        return self.settings.get(
            key,
            self.DEFAULTS.get(key)
        )

    # --------------------------------------------------------

    def set(self, key, value):

        self.settings[key] = value


# ============================================================
# VLC PLAYER
# ============================================================

class VLCPlayer:

    def __init__(self):

        self.instance = vlc.Instance(
            "--no-video-title-show",
            "--quiet"
        )

        self.player = (
            self.instance.media_player_new()
        )

    # --------------------------------------------------------

    def load(self, path):

        media = (
            self.instance.media_new(path)
        )

        self.player.set_media(media)

    # --------------------------------------------------------

    def attach_video(self, widget):

        if sys.platform.startswith("win"):

            self.player.set_hwnd(
                int(widget.winId())
            )

        elif sys.platform.startswith(
            "linux"
        ):

            self.player.set_xwindow(
                int(widget.winId())
            )

        elif sys.platform == "darwin":

            self.player.set_nsobject(
                int(widget.winId())
            )

    # --------------------------------------------------------

    def play(self):

        return self.player.play()

    # --------------------------------------------------------

    def pause(self):

        self.player.pause()

    # --------------------------------------------------------

    def stop(self):

        self.player.stop()

    # --------------------------------------------------------

    def toggle(self):

        if self.is_playing():
            self.pause()
        else:
            self.play()

    # --------------------------------------------------------

    def is_playing(self):

        return bool(
            self.player.is_playing()
        )

    # --------------------------------------------------------

    def set_volume(self, volume):

        self.player.audio_set_volume(
            max(
                0,
                min(
                    100,
                    int(volume)
                )
            )
        )

    # --------------------------------------------------------

    def set_position(self, value):

        self.player.set_position(
            max(
                0.0,
                min(
                    1.0,
                    float(value)
                )
            )
        )

    # --------------------------------------------------------

    def position(self):

        value = (
            self.player.get_position()
        )

        if value < 0:
            value = 0

        return value

    # --------------------------------------------------------

    def duration(self):

        value = (
            self.player.get_length()
        )

        if value < 0:
            return 0

        return value / 1000

    # --------------------------------------------------------

    def set_rate(self, rate):

        try:
            self.player.set_rate(
                float(rate)
            )
        except Exception:
            pass

    # --------------------------------------------------------

    def mute(self, value):

        self.player.audio_set_mute(
            bool(value)
        )

    # --------------------------------------------------------

    def ended(self):

        try:

            return (
                self.player.get_state()
                == vlc.State.Ended
            )

        except Exception:

            return False


# ============================================================
# VIDEO WIDGET
# ============================================================

class VideoWidget(QFrame):

    fullscreenRequested = Signal()

    def __init__(self):

        super().__init__()

        self.setMinimumHeight(
            250
        )

        self.setStyleSheet(
            """
            QFrame {
                background: #000000;
                border-radius: 12px;
            }
            """
        )

        self.placeholder = QLabel(
            "No video playing"
        )

        self.placeholder.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.placeholder.setStyleSheet(
            """
            QLabel {
                color: #777777;
                background: #000000;
                font-size: 18px;
            }
            """
        )

        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            0, 0, 0, 0
        )

        layout.addWidget(
            self.placeholder
        )

    def mouseDoubleClickEvent(
        self,
        event
    ):

        self.fullscreenRequested.emit()

        super().mouseDoubleClickEvent(
            event
        )


# ============================================================
# PLAYLIST DIALOG
# ============================================================

class PlaylistDialog(QDialog):

    def __init__(
        self,
        playlists,
        parent=None
    ):

        super().__init__(parent)

        self.setWindowTitle(
            "Choose Playlist"
        )

        self.resize(
            400,
            350
        )

        layout = QVBoxLayout(self)

        self.list_widget = QListWidget()

        for name in playlists:

            self.list_widget.addItem(
                name
            )

        layout.addWidget(
            self.list_widget
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            |
            QDialogButtonBox.StandardButton.Cancel
        )

        buttons.accepted.connect(
            self.accept
        )

        buttons.rejected.connect(
            self.reject
        )

        layout.addWidget(
            buttons
        )

    def selected(self):

        item = self.list_widget.currentItem()

        if item:
            return item.text()

        return None


# ============================================================
# SETTINGS DIALOG
# ============================================================

class SettingsDialog(QDialog):

    def __init__(
        self,
        volume,
        speed,
        parent=None
    ):

        super().__init__(parent)

        self.setWindowTitle(
            "YuiMusic Settings"
        )

        self.resize(
            420,
            220
        )

        layout = QVBoxLayout(self)

        volume_label = QLabel(
            f"Volume: {volume}%"
        )

        layout.addWidget(
            volume_label
        )

        self.volume_slider = QSlider(
            Qt.Orientation.Horizontal
        )

        self.volume_slider.setRange(
            0,
            100
        )

        self.volume_slider.setValue(
            int(volume)
        )

        self.volume_slider.valueChanged.connect(
            lambda value:
            volume_label.setText(
                f"Volume: {value}%"
            )
        )

        layout.addWidget(
            self.volume_slider
        )

        layout.addSpacing(15)

        speed_label = QLabel(
            "Playback Speed"
        )

        layout.addWidget(
            speed_label
        )

        self.speed_combo = QComboBox()

        speeds = [
            0.5,
            0.75,
            1.0,
            1.25,
            1.5,
            1.75,
            2.0,
        ]

        for value in speeds:

            self.speed_combo.addItem(
                f"{value:g}x",
                value
            )

        index = self.speed_combo.findData(
            float(speed)
        )

        if index >= 0:
            self.speed_combo.setCurrentIndex(
                index
            )

        layout.addWidget(
            self.speed_combo
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            |
            QDialogButtonBox.StandardButton.Cancel
        )

        buttons.accepted.connect(
            self.accept
        )

        buttons.rejected.connect(
            self.reject
        )

        layout.addWidget(
            buttons
        )

    def values(self):

        return {
            "volume":
                self.volume_slider.value(),

            "speed":
                float(
                    self.speed_combo.currentData()
                ),
        }


# ============================================================
# MAIN WINDOW
# ============================================================

class MainWindow(QMainWindow):

    def __init__(self):

        super().__init__()

        self.library = LibraryManager()
        self.settings = SettingsManager()

        self.player = VLCPlayer()

        self.current_path = None
        self.view_mode = "home"
        self.current_playlist = None
        self.current_group = None

        self.visible_paths = []

        self.queue = [
            os.path.abspath(path)
            for path in self.settings.get("queue", [])
            if self.library.find(path) and os.path.exists(path)
        ]

        self.shuffle_enabled = bool(
            self.settings.get(
                "shuffle"
            )
        )

        self.repeat_mode = safe_int(
            self.settings.get(
                "repeat"
            ),
            0
        )

        self.is_seeking = False
        self.muted = False
        self.video_fullscreen = False
        self.was_ended = False

        width = safe_int(
            self.settings.get(
                "window_width"
            ),
            1450
        )

        height = safe_int(
            self.settings.get(
                "window_height"
            ),
            900
        )

        self.setWindowTitle(
            APP_NAME
        )

        self.resize(
            width,
            height
        )

        self.build_ui()
        self.setup_shortcuts()

        self.player.set_volume(
            self.settings.get(
                "volume"
            )
        )

        self.player.set_rate(
            self.settings.get(
                "speed"
            )
        )

        self.library.cleanup_missing()
        self.queue = [path for path in self.queue if self.library.find(path) and os.path.exists(path)]
        self.save_queue()

        self.refresh_playlists()
        self.refresh_queue()
        self.refresh_song_list()
        self.update_statistics()

        self.timer = QTimer(self)

        self.timer.timeout.connect(
            self.update_player
        )

        self.timer.start(
            500
        )

    # ========================================================
    # UI
    # ========================================================

    def build_ui(self):

        central = QWidget()

        self.setCentralWidget(
            central
        )

        main_layout = QVBoxLayout(
            central
        )

        main_layout.setContentsMargins(
            0,
            0,
            0,
            0
        )

        # ----------------------------------------------------
        # TOP BAR
        # ----------------------------------------------------

        top_bar = QFrame()

        top_bar.setObjectName(
            "TopBar"
        )

        top_layout = QHBoxLayout(
            top_bar
        )

        logo = QLabel(
            "YuiMusic"
        )

        logo.setObjectName(
            "Logo"
        )

        top_layout.addWidget(
            logo
        )

        self.search = QLineEdit()

        self.search.setPlaceholderText(
            "Search songs, artists or albums..."
        )

        self.search.textChanged.connect(
            self.refresh_song_list
        )

        top_layout.addWidget(
            self.search,
            1
        )

        add_music = QPushButton(
            "＋ Add Music"
        )

        add_music.clicked.connect(
            self.import_files
        )

        top_layout.addWidget(
            add_music
        )

        add_folder = QPushButton(
            "＋ Add Folder"
        )

        add_folder.clicked.connect(
            self.import_folder
        )

        top_layout.addWidget(
            add_folder
        )

        settings_button = QPushButton(
            "⚙ Settings"
        )

        settings_button.clicked.connect(
            self.open_settings
        )

        top_layout.addWidget(
            settings_button
        )

        main_layout.addWidget(
            top_bar
        )

        # ----------------------------------------------------
        # MAIN SPLITTER
        # ----------------------------------------------------

        splitter = QSplitter(
            Qt.Orientation.Horizontal
        )

        main_layout.addWidget(
            splitter,
            1
        )

        # ----------------------------------------------------
        # LEFT SIDEBAR
        # ----------------------------------------------------

        sidebar = QFrame()

        sidebar_layout = QVBoxLayout(
            sidebar
        )

        sidebar_layout.setContentsMargins(
            12,
            15,
            12,
            15
        )

        self.nav_buttons = []

        navigation = [
            ("⌂  Home", "home"),
            ("♫  Your Library", "library"),
            ("♥  Liked Songs", "liked"),
            ("◷  Recently Played", "recent"),
            ("★  Recently Added", "added"),
            ("▦  Albums", "albums"),
            ("♬  Artists", "artists"),
            ("☷  Queue", "queue"),
        ]

        for text, mode in navigation:

            button = QPushButton(
                text
            )

            button.setProperty(
                "nav",
                True
            )

            button.clicked.connect(
                lambda checked=False,
                m=mode:
                self.show_view(m)
            )

            sidebar_layout.addWidget(
                button
            )

            self.nav_buttons.append(
                button
            )

        sidebar_layout.addSpacing(
            15
        )

        playlist_title = QLabel(
            "PLAYLISTS"
        )

        playlist_title.setObjectName(
            "SectionTitle"
        )

        sidebar_layout.addWidget(
            playlist_title
        )

        self.playlist_list = QListWidget()

        self.playlist_list.itemClicked.connect(
            self.open_playlist_item
        )

        self.playlist_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )

        self.playlist_list.customContextMenuRequested.connect(
            self.playlist_context_menu
        )

        sidebar_layout.addWidget(
            self.playlist_list,
            1
        )

        create_playlist_button = QPushButton(
            "＋ New Playlist"
        )

        create_playlist_button.clicked.connect(
            self.create_playlist
        )

        sidebar_layout.addWidget(
            create_playlist_button
        )

        rescan_button = QPushButton(
            "↻ Rescan Library"
        )

        rescan_button.clicked.connect(
            self.rescan_library
        )

        sidebar_layout.addWidget(
            rescan_button
        )

        clean_button = QPushButton(
            "🧹 Clean Missing"
        )

        clean_button.clicked.connect(
            self.cleanup_missing_files
        )

        sidebar_layout.addWidget(
            clean_button
        )

        splitter.addWidget(
            sidebar
        )

        # ----------------------------------------------------
        # CENTER
        # ----------------------------------------------------

        center = QFrame()

        center_layout = QVBoxLayout(
            center
        )

        center_layout.setContentsMargins(
            20,
            15,
            20,
            10
        )

        header_layout = QHBoxLayout()

        self.page_title = QLabel(
            "Home"
        )

        self.page_title.setObjectName(
            "PageTitle"
        )

        header_layout.addWidget(
            self.page_title
        )

        header_layout.addStretch()

        self.stats_label = QLabel()

        self.stats_label.setObjectName(
            "StatsLabel"
        )

        header_layout.addWidget(
            self.stats_label
        )

        center_layout.addLayout(
            header_layout
        )

        # ----------------------------------------------------
        # BACK BUTTON
        # ----------------------------------------------------

        self.back_button = QPushButton(
            "← Back"
        )

        self.back_button.clicked.connect(
            self.back_from_group
        )

        self.back_button.hide()

        center_layout.addWidget(
            self.back_button
        )

        # ----------------------------------------------------
        # VIDEO
        # ----------------------------------------------------

        self.video_widget = VideoWidget()

        self.video_widget.fullscreenRequested.connect(
            self.toggle_video_fullscreen
        )

        self.video_widget.hide()

        center_layout.addWidget(
            self.video_widget
        )

        # ----------------------------------------------------
        # SONG LIST
        # ----------------------------------------------------

        self.song_list = QListWidget()

        self.song_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )

        self.song_list.setSpacing(
            3
        )

        self.song_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )

        self.song_list.customContextMenuRequested.connect(
            self.song_context_menu
        )

        # IMPORTANT:
        # Connect to the instance method directly.
        # Do NOT use MainWindow.song_list here.

        self.song_list.itemDoubleClicked.connect(
            self.song_list_double_click
        )

        center_layout.addWidget(
            self.song_list,
            1
        )

        # ----------------------------------------------------
        # NOW PLAYING
        # ----------------------------------------------------

        self.now_playing = QFrame()

        self.now_playing.setObjectName(
            "NowPlaying"
        )

        now_layout = QHBoxLayout(
            self.now_playing
        )

        self.cover_label = QLabel()

        self.cover_label.setFixedSize(
            60,
            60
        )

        self.cover_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.cover_label.setStyleSheet(
            """
            QLabel {
                background: #222222;
                border-radius: 8px;
            }
            """
        )

        now_layout.addWidget(
            self.cover_label
        )

        info_layout = QVBoxLayout()

        self.now_title = QLabel(
            "Nothing playing"
        )

        self.now_title.setObjectName(
            "NowTitle"
        )

        self.now_artist = QLabel(
            ""
        )

        self.now_artist.setObjectName(
            "NowArtist"
        )

        info_layout.addWidget(
            self.now_title
        )

        info_layout.addWidget(
            self.now_artist
        )

        now_layout.addLayout(
            info_layout
        )

        now_layout.addStretch()

        center_layout.addWidget(
            self.now_playing
        )

        # ----------------------------------------------------
        # PLAYER BAR
        # ----------------------------------------------------

        player_bar = QFrame()

        player_layout = QVBoxLayout(
            player_bar
        )

        progress_layout = QHBoxLayout()

        self.current_time = QLabel(
            "0:00"
        )

        self.progress_slider = QSlider(
            Qt.Orientation.Horizontal
        )

        self.progress_slider.setRange(
            0,
            1000
        )

        self.progress_slider.sliderPressed.connect(
            self.seek_started
        )

        self.progress_slider.sliderReleased.connect(
            self.seek_released
        )

        self.progress_slider.sliderMoved.connect(
            self.seek_moved
        )

        self.total_time = QLabel(
            "0:00"
        )

        progress_layout.addWidget(
            self.current_time
        )

        progress_layout.addWidget(
            self.progress_slider,
            1
        )

        progress_layout.addWidget(
            self.total_time
        )

        player_layout.addLayout(
            progress_layout
        )

        controls = QHBoxLayout()

        controls.addStretch()

        self.previous_button = QPushButton(
            "⏮"
        )

        self.previous_button.clicked.connect(
            self.previous_song
        )

        controls.addWidget(
            self.previous_button
        )

        self.play_button = QPushButton(
            "▶"
        )

        self.play_button.clicked.connect(
            self.toggle_play
        )

        controls.addWidget(
            self.play_button
        )

        self.next_button = QPushButton(
            "⏭"
        )

        self.next_button.clicked.connect(
            self.next_song
        )

        controls.addWidget(
            self.next_button
        )

        self.shuffle_button = QPushButton(
            "🔀"
        )

        self.shuffle_button.clicked.connect(
            self.toggle_shuffle
        )

        controls.addWidget(
            self.shuffle_button
        )

        self.repeat_button = QPushButton(
            "🔁"
        )

        self.repeat_button.clicked.connect(
            self.toggle_repeat
        )

        controls.addWidget(
            self.repeat_button
        )

        self.speed_button = QPushButton(
            "1x"
        )

        self.speed_button.clicked.connect(
            self.change_speed
        )

        controls.addWidget(
            self.speed_button
        )

        self.mute_button = QPushButton(
            "🔊"
        )

        self.mute_button.clicked.connect(
            self.toggle_mute
        )

        controls.addWidget(
            self.mute_button
        )

        self.volume_slider = QSlider(
            Qt.Orientation.Horizontal
        )

        self.volume_slider.setRange(
            0,
            100
        )

        self.volume_slider.setValue(
            safe_int(
                self.settings.get(
                    "volume"
                ),
                70
            )
        )

        self.volume_slider.setFixedWidth(
            130
        )

        self.volume_slider.valueChanged.connect(
            self.volume_changed
        )

        controls.addWidget(
            self.volume_slider
        )

        controls.addStretch()

        player_layout.addLayout(
            controls
        )

        center_layout.addWidget(
            player_bar
        )

        splitter.addWidget(
            center
        )

        # ----------------------------------------------------
        # RIGHT QUEUE
        # ----------------------------------------------------

        queue_panel = QFrame()

        queue_layout = QVBoxLayout(
            queue_panel
        )

        queue_title_layout = QHBoxLayout()

        queue_title = QLabel(
            "Queue"
        )

        queue_title.setObjectName(
            "PageTitle"
        )

        queue_title_layout.addWidget(
            queue_title
        )

        queue_title_layout.addStretch()

        clear_queue_button = QPushButton(
            "Clear"
        )

        clear_queue_button.clicked.connect(
            self.clear_queue
        )

        queue_title_layout.addWidget(
            clear_queue_button
        )

        queue_layout.addLayout(
            queue_title_layout
        )

        self.queue_list = QListWidget()

        self.queue_list.setDragDropMode(
            QAbstractItemView.DragDropMode.InternalMove
        )

        self.queue_list.setDefaultDropAction(
            Qt.DropAction.MoveAction
        )

        # Keep self.queue synchronized when items are dragged.
        self.queue_list.model().rowsMoved.connect(
            lambda *args:
            self.sync_queue_from_widget()
        )

        self.queue_list.itemDoubleClicked.connect(
            self.play_queue_item
        )

        self.queue_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )

        self.queue_list.customContextMenuRequested.connect(
            self.queue_context_menu
        )

        queue_layout.addWidget(
            self.queue_list,
            1
        )

        add_selected = QPushButton(
            "Add Selected"
        )

        add_selected.clicked.connect(
            self.add_selected_to_queue
        )

        queue_layout.addWidget(
            add_selected
        )

        splitter.addWidget(
            queue_panel
        )

        splitter.setSizes(
            [
                220,
                900,
                280,
            ]
        )

        self.apply_styles()

    # ========================================================
    # STYLE
    # ========================================================

    def apply_styles(self):

        self.setStyleSheet(
            """
            QMainWindow {
                background: #0f0f0f;
                color: #ffffff;
            }

            QWidget {
                color: #ffffff;
                font-size: 14px;
            }

            QFrame#TopBar {
                background: #181818;
                border-bottom: 1px solid #292929;
            }

            QLabel#Logo {
                color: #ffffff;
                font-size: 25px;
                font-weight: bold;
                padding: 8px 15px;
            }

            QLabel#PageTitle {
                font-size: 25px;
                font-weight: bold;
            }

            QLabel#SectionTitle {
                color: #888888;
                font-size: 11px;
                font-weight: bold;
                padding: 8px 5px;
            }

            QLabel#StatsLabel {
                color: #888888;
            }

            QLabel#NowTitle {
                font-weight: bold;
                font-size: 15px;
            }

            QLabel#NowArtist {
                color: #999999;
            }

            QFrame#NowPlaying {
                background: #181818;
                border-radius: 10px;
            }

            QLineEdit {
                background: #242424;
                border: 1px solid #333333;
                border-radius: 20px;
                padding: 10px 15px;
                color: white;
            }

            QPushButton {
                background: #242424;
                border: none;
                border-radius: 7px;
                padding: 9px 13px;
            }

            QPushButton:hover {
                background: #333333;
            }

            QPushButton:pressed {
                background: #444444;
            }

            QPushButton[nav="true"] {
                text-align: left;
                background: transparent;
                padding: 10px;
            }

            QPushButton[nav="true"]:hover {
                background: #242424;
            }

            QListWidget {
                background: #111111;
                border: none;
                outline: none;
            }

            QListWidget::item {
                padding: 9px;
                border-radius: 6px;
            }

            QListWidget::item:hover {
                background: #242424;
            }

            QListWidget::item:selected {
                background: #333333;
            }

            QSlider::groove:horizontal {
                height: 5px;
                background: #333333;
                border-radius: 2px;
            }

            QSlider::handle:horizontal {
                width: 13px;
                margin: -4px 0;
                background: #ffffff;
                border-radius: 7px;
            }

            QSplitter::handle {
                background: #222222;
            }

            QMenu {
                background: #202020;
                color: white;
                border: 1px solid #3a3a3a;
            }

            QMenu::item {
                padding: 8px 25px;
            }

            QMenu::item:selected {
                background: #383838;
            }

            QDialog {
                background: #181818;
            }

            QComboBox {
                background: #242424;
                border: 1px solid #333333;
                padding: 8px;
            }
            """
        )

    # ========================================================
    # IMPORT
    # ========================================================

    def import_files(self):

        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Music",
            "",
            "Media Files (*.mp3 *.mp4 *.m4a *.wav *.flac *.ogg *.aac)"
        )

        if not files:
            return

        songs = []

        for path in files:

            try:

                songs.append(
                    read_metadata(path)
                )

            except Exception as exc:

                print(exc)

        added = self.library.add_songs(
            songs
        )

        self.refresh_song_list()
        self.update_statistics()

        QMessageBox.information(
            self,
            "YuiMusic",
            f"Added {added} new file(s)."
        )

    # --------------------------------------------------------

    def import_folder(self):

        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Music Folder"
        )

        if not folder:
            return

        added = self.scan_folder(
            folder
        )

        self.refresh_song_list()
        self.update_statistics()

        QMessageBox.information(
            self,
            "YuiMusic",
            f"Added {added} new file(s)."
        )

    # --------------------------------------------------------

    def scan_folder(self, folder):

        songs = []

        for root, dirs, files in os.walk(
            folder
        ):

            for filename in files:

                if not filename.lower().endswith(
                    SUPPORTED_EXTENSIONS
                ):
                    continue

                path = os.path.join(
                    root,
                    filename
                )

                if self.library.find(
                    path
                ):
                    continue

                try:

                    songs.append(
                        read_metadata(path)
                    )

                except Exception as exc:

                    print(
                        f"Unable to read {path}:"
                    )
                    print(exc)

        return self.library.add_songs(
            songs
        )

    # --------------------------------------------------------

    def rescan_library(self):

        folders = set()

        for song in self.library.songs:

            path = song.get(
                "path",
                ""
            )

            if path and os.path.exists(
                path
            ):

                folders.add(
                    os.path.dirname(path)
                )

        added = 0

        for folder in folders:

            added += self.scan_folder(
                folder
            )

        self.library.cleanup_missing()

        self.refresh_playlists()
        self.refresh_song_list()
        self.update_statistics()

        QMessageBox.information(
            self,
            "YuiMusic",
            f"Library rescanned.\n\n"
            f"New files: {added}"
        )

    # --------------------------------------------------------

    def cleanup_missing_files(self):

        before = len(
            self.library.songs
        )

        self.library.cleanup_missing()

        after = len(
            self.library.songs
        )

        self.refresh_playlists()
        self.refresh_song_list()
        self.update_statistics()

        QMessageBox.information(
            self,
            "YuiMusic",
            f"Removed {before - after} missing file(s)."
        )

    # ========================================================
    # VIEWS
    # ========================================================

    def show_view(self, mode):

        self.view_mode = mode
        self.current_playlist = None
        self.current_group = None

        titles = {
            "home": "Home",
            "library": "Your Library",
            "liked": "Liked Songs",
            "recent": "Recently Played",
            "added": "Recently Added",
            "albums": "Albums",
            "artists": "Artists",
            "queue": "Queue",
        }

        self.page_title.setText(
            titles.get(
                mode,
                "YuiMusic"
            )
        )

        self.back_button.hide()

        self.refresh_song_list()

    # --------------------------------------------------------

    def get_current_songs(self):

        if self.view_mode in (
            "album_detail",
            "artist_detail"
        ):

            if not self.current_group:
                return []

            songs = []

            for path in self.current_group.get(
                "songs",
                []
            ):

                song = self.library.find(
                    path
                )

                if song:
                    songs.append(song)

            return songs

        songs = list(
            self.library.songs
        )

        if self.view_mode == "liked":

            songs = [
                song
                for song in songs
                if song.get(
                    "liked",
                    False
                )
            ]

        elif self.view_mode == "recent":

            songs = []

            for path in self.library.recent:

                song = self.library.find(
                    path
                )

                if song:
                    songs.append(
                        song
                    )

        elif self.view_mode == "added":

            songs.sort(
                key=lambda song:
                song.get(
                    "added",
                    ""
                ),
                reverse=True
            )

        elif self.view_mode == "queue":

            songs = []

            for path in self.queue:

                song = self.library.find(
                    path
                )

                if song:
                    songs.append(
                        song
                    )

        elif self.view_mode == "playlist":

            songs = []

            paths = self.library.playlists.get(
                self.current_playlist,
                []
            )

            for path in paths:

                song = self.library.find(
                    path
                )

                if song:
                    songs.append(
                        song
                    )

        return songs

    # --------------------------------------------------------

    def refresh_song_list(self):

        self.song_list.clear()

        self.visible_paths = []

        if self.view_mode in (
            "album_detail",
            "artist_detail"
        ):

            self.refresh_group_detail()
            return

        query = (
            self.search.text()
            .strip()
            .lower()
        )

        if self.view_mode == "home":

            self.build_home(
                query
            )

            return

        if self.view_mode == "albums":

            self.populate_albums(
                query
            )

            return

        if self.view_mode == "artists":

            self.populate_artists(
                query
            )

            return

        songs = self.get_current_songs()

        if query:

            tokens = query.split()

            songs = [
                song
                for song in songs
                if all(
                    token in " ".join(
                        [
                            song.get(
                                "title",
                                ""
                            ),
                            song.get(
                                "artist",
                                ""
                            ),
                            song.get(
                                "album",
                                ""
                            ),
                        ]
                    ).lower()
                    for token in tokens
                )
            ]

        for song in songs:

            self.add_song_row(
                song
            )

    # --------------------------------------------------------

    def build_home(self, query):

        self.page_title.setText(
            "Home"
        )

        self.add_section(
            "Recently Played"
        )

        recent = []

        for path in self.library.recent[:8]:

            song = self.library.find(
                path
            )

            if song:
                recent.append(
                    song
                )

        for song in recent:

            if query:

                text = " ".join(
                    [
                        song.get(
                            "title",
                            ""
                        ),
                        song.get(
                            "artist",
                            ""
                        ),
                        song.get(
                            "album",
                            ""
                        ),
                    ]
                ).lower()

                if not all(
                    token in text
                    for token in query.split()
                ):
                    continue

            self.add_song_row(
                song,
                "Recently Played"
            )

        self.add_section(
            "Recently Added"
        )

        added = sorted(
            self.library.songs,
            key=lambda song:
            song.get(
                "added",
                ""
            ),
            reverse=True
        )[:8]

        for song in added:

            if query:

                text = " ".join(
                    [
                        song.get(
                            "title",
                            ""
                        ),
                        song.get(
                            "artist",
                            ""
                        ),
                        song.get(
                            "album",
                            ""
                        ),
                    ]
                ).lower()

                if not all(
                    token in text
                    for token in query.split()
                ):
                    continue

            self.add_song_row(
                song,
                "Recently Added"
            )

        liked = [
            song
            for song in self.library.songs
            if song.get(
                "liked",
                False
            )
        ][:8]

        if liked:

            self.add_section(
                "Liked Songs"
            )

            for song in liked:

                self.add_song_row(
                    song,
                    "Liked"
                )

        if not self.library.songs:

            empty = QListWidgetItem(
                "Your library is empty.\n"
                "Use Add Music or Add Folder to begin."
            )

            self.song_list.addItem(
                empty
            )

    # --------------------------------------------------------

    def add_section(self, title):

        item = QListWidgetItem(
            f"── {title} ──"
        )

        item.setFlags(
            Qt.ItemFlag.NoItemFlags
        )

        item.setForeground(
            Qt.GlobalColor.gray
        )

        self.song_list.addItem(
            item
        )

    # --------------------------------------------------------

    def add_song_row(
        self,
        song,
        prefix=""
    ):

        title = song.get(
            "title",
            "Unknown"
        )

        artist = song.get(
            "artist",
            "Unknown Artist"
        )

        album = song.get(
            "album",
            "Unknown Album"
        )

        liked = " ♥" if song.get(
            "liked",
            False
        ) else ""

        text = (
            f"{title}{liked}\n"
            f"{artist} • {album}"
        )

        item = QListWidgetItem(
            text
        )

        item.setData(
            Qt.ItemDataRole.UserRole,
            song.get("path")
        )

        self.song_list.addItem(
            item
        )

        self.visible_paths.append(
            song.get("path")
        )

    # --------------------------------------------------------

    def populate_albums(self, query):

        groups = {}

        for song in self.library.songs:

            album = song.get(
                "album",
                "Unknown Album"
            )

            artist = song.get(
                "artist",
                "Unknown Artist"
            )

            key = (
                album,
                artist
            )

            groups.setdefault(
                key,
                []
            ).append(
                song.get("path")
            )

        for (
            album,
            artist
        ), paths in sorted(
            groups.items()
        ):

            text = (
                f"{album}\n"
                f"{artist} • "
                f"{len(paths)} song(s)"
            )

            if query:

                search_text = (
                    album + " " + artist
                ).lower()

                if not all(
                    token in search_text
                    for token in query.split()
                ):
                    continue

            item = QListWidgetItem(
                text
            )

            item.setData(
                Qt.ItemDataRole.UserRole,
                {
                    "type": "album",
                    "album": album,
                    "artist": artist,
                    "songs": paths,
                }
            )

            self.song_list.addItem(
                item
            )

            self.visible_paths.extend(
                paths
            )

    # --------------------------------------------------------

    def populate_artists(self, query):

        groups = {}

        for song in self.library.songs:

            artist = song.get(
                "artist",
                "Unknown Artist"
            )

            groups.setdefault(
                artist,
                []
            ).append(
                song.get("path")
            )

        for artist, paths in sorted(
            groups.items()
        ):

            if query:

                if not all(
                    token in artist.lower()
                    for token in query.split()
                ):
                    continue

            item = QListWidgetItem(
                f"{artist}\n"
                f"{len(paths)} song(s)"
            )

            item.setData(
                Qt.ItemDataRole.UserRole,
                {
                    "type": "artist",
                    "artist": artist,
                    "songs": paths,
                }
            )

            self.song_list.addItem(
                item
            )

            self.visible_paths.extend(
                paths
            )

    # --------------------------------------------------------

    def open_group_item(self, item):

        data = item.data(
            Qt.ItemDataRole.UserRole
        )

        if not isinstance(
            data,
            dict
        ):
            return

        item_type = data.get(
            "type"
        )

        if item_type not in (
            "album",
            "artist"
        ):
            return

        self.current_group = data

        if item_type == "album":

            self.view_mode = (
                "album_detail"
            )

            self.page_title.setText(
                data.get(
                    "album",
                    "Album"
                )
            )

        else:

            self.view_mode = (
                "artist_detail"
            )

            self.page_title.setText(
                data.get(
                    "artist",
                    "Artist"
                )
            )

        self.back_button.show()

        self.refresh_song_list()

    # --------------------------------------------------------

    def refresh_group_detail(self):

        if not self.current_group:
            return

        songs = self.get_current_songs()

        for song in songs:

            self.add_song_row(
                song
            )

    # --------------------------------------------------------

    def back_from_group(self):

        if self.view_mode == "album_detail":

            self.show_view(
                "albums"
            )

        elif self.view_mode == "artist_detail":

            self.show_view(
                "artists"
            )

    # ========================================================
    # DOUBLE CLICK
    # ========================================================

    def song_list_double_click(
        self,
        item
    ):

        data = item.data(
            Qt.ItemDataRole.UserRole
        )

        if isinstance(
            data,
            dict
        ):

            item_type = data.get(
                "type"
            )

            if item_type in (
                "album",
                "artist"
            ):

                self.open_group_item(
                    item
                )

                return

        self.play_item(
            item
        )

    # ========================================================
    # PLAYBACK
    # ========================================================

    def play_item(self, item):

        if isinstance(
            item,
            QListWidgetItem
        ):

            data = item.data(
                Qt.ItemDataRole.UserRole
            )

        else:

            data = item

        if isinstance(
            data,
            dict
        ):

            paths = data.get(
                "songs",
                []
            )

            if not paths:
                return

            self.queue = [
                path
                for path in paths
                if self.library.find(path)
            ]

            self.refresh_queue()

            self.play_path(
                self.queue[0]
            )

            return

        if isinstance(
            data,
            str
        ):

            self.play_path(
                data
            )

    # --------------------------------------------------------

    def play_path(self, path):

        song = self.library.find(
            path
        )

        if not song:
            return

        if not os.path.exists(
            path
        ):
            return

        self.current_path = (
            os.path.abspath(path)
        )

        self.library.add_recent(
            self.current_path
        )

        self.player.load(
            self.current_path
        )

        self.player.attach_video(
            self.video_widget
        )

        self.player.set_volume(
            self.volume_slider.value()
        )

        self.player.set_rate(
            self.settings.get(
                "speed"
            )
        )

        self.player.mute(
            self.muted
        )

        self.player.play()

        self.update_now_playing(
            song
        )

        self.update_video_visibility()

        self.play_button.setText(
            "⏸"
        )

        self.was_ended = False

    # --------------------------------------------------------

    def toggle_play(self):

        if not self.current_path:

            songs = self.get_playback_paths()

            if songs:

                self.play_path(
                    songs[0]
                )

            return

        self.player.toggle()

        if self.player.is_playing():

            self.play_button.setText(
                "⏸"
            )

        else:

            self.play_button.setText(
                "▶"
            )

    # --------------------------------------------------------

    def previous_song(self):

        paths = self.get_playback_paths()

        if not paths:
            return

        if self.current_path not in paths:

            self.play_path(
                paths[0]
            )

            return

        index = paths.index(
            self.current_path
        )

        if index <= 0:

            if self.repeat_mode == 2:

                self.play_path(
                    paths[-1]
                )

            return

        self.play_path(
            paths[index - 1]
        )

    # --------------------------------------------------------

    def next_song(self):

        paths = self.get_playback_paths()

        if not paths:
            return

        if self.shuffle_enabled:

            choices = [
                path
                for path in paths
                if path != self.current_path
            ]

            if choices:

                self.play_path(
                    random.choice(
                        choices
                    )
                )

            return

        if self.current_path not in paths:

            self.play_path(
                paths[0]
            )

            return

        index = paths.index(
            self.current_path
        )

        if index + 1 < len(paths):

            self.play_path(
                paths[index + 1]
            )

            return

        if self.repeat_mode == 1:

            self.play_path(
                paths[0]
            )

        elif self.repeat_mode == 2:

            self.play_path(
                self.current_path
            )

    # --------------------------------------------------------

    def get_playback_paths(self):

        if self.view_mode in (
            "album_detail",
            "artist_detail"
        ):

            return [
                song["path"]
                for song in self.get_current_songs()
                if song
            ]

        if self.view_mode in (
            "albums",
            "artists"
        ):

            return list(
                self.visible_paths
            )

        if self.view_mode == "home":

            return [
                song["path"]
                for song in self.library.songs
            ]

        return [
            song["path"]
            for song in self.get_current_songs()
            if song
        ]

    # --------------------------------------------------------

    def update_now_playing(
        self,
        song
    ):

        self.now_title.setText(
            song.get(
                "title",
                "Unknown"
            )
        )

        self.now_artist.setText(
            f"{song.get('artist', 'Unknown Artist')} "
            f"• "
            f"{song.get('album', 'Unknown Album')}"
        )

        artwork = artwork_from_base64(
            song.get(
                "artwork"
            )
        )

        if artwork:

            pixmap = QPixmap()

            if pixmap.loadFromData(
                artwork
            ):

                pixmap = pixmap.scaled(
                    60,
                    60,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )

                self.cover_label.setPixmap(
                    pixmap
                )

                return

        self.cover_label.clear()
        self.cover_label.setText(
            "♪"
        )

    # --------------------------------------------------------

    def update_now_playing_empty(
        self
    ):

        self.now_title.setText(
            "Nothing playing"
        )

        self.now_artist.setText(
            ""
        )

        self.cover_label.clear()

        self.cover_label.setText(
            "♪"
        )

    # --------------------------------------------------------

    def update_video_visibility(self):

        if not self.current_path:

            self.video_widget.hide()
            return

        extension = os.path.splitext(
            self.current_path
        )[1].lower()

        if extension == ".mp4":

            self.video_widget.show()

            self.video_widget.placeholder.hide()

        else:

            self.video_widget.hide()

    # --------------------------------------------------------

    def update_player(self):

        if not self.current_path:
            return

        duration = self.player.duration()

        position = self.player.position()

        if duration > 0:

            current = (
                duration * position
            )

            self.current_time.setText(
                format_time(
                    current
                )
            )

            self.total_time.setText(
                format_time(
                    duration
                )
            )

            if not self.is_seeking:

                self.progress_slider.setValue(
                    int(
                        position * 1000
                    )
                )

        if self.player.ended():

            if not self.was_ended:

                self.was_ended = True

                if self.repeat_mode == 2:

                    self.play_path(
                        self.current_path
                    )

                else:

                    self.next_song()

        else:

            self.was_ended = False

        if self.player.is_playing():

            self.play_button.setText(
                "⏸"
            )

        else:

            self.play_button.setText(
                "▶"
            )

    # ========================================================
    # SEEK
    # ========================================================

    def seek_started(self):

        self.is_seeking = True

    # --------------------------------------------------------

    def seek_moved(self, value):

        if not self.current_path:
            return

        duration = self.player.duration()

        if duration > 0:

            position = (
                value / 1000
            )

            self.current_time.setText(
                format_time(
                    duration * position
                )
            )

    # --------------------------------------------------------

    def seek_released(self):

        self.is_seeking = False

        if not self.current_path:
            return

        value = (
            self.progress_slider.value()
            / 1000
        )

        self.player.set_position(
            value
        )

    # ========================================================
    # PLAYER CONTROLS
    # ========================================================

    def volume_changed(self, value):

        self.player.set_volume(
            value
        )

        self.settings.set(
            "volume",
            value
        )

        self.settings.save()

    # --------------------------------------------------------

    def toggle_shuffle(self):

        self.shuffle_enabled = (
            not self.shuffle_enabled
        )

        self.settings.set(
            "shuffle",
            self.shuffle_enabled
        )

        self.settings.save()

        self.update_shuffle_button()

    # --------------------------------------------------------

    def update_shuffle_button(self):

        if self.shuffle_enabled:

            self.shuffle_button.setText(
                "🔀 ON"
            )

        else:

            self.shuffle_button.setText(
                "🔀"
            )

    # --------------------------------------------------------

    def toggle_repeat(self):

        self.repeat_mode = (
            self.repeat_mode + 1
        ) % 3

        self.settings.set(
            "repeat",
            self.repeat_mode
        )

        self.settings.save()

        if self.repeat_mode == 0:

            self.repeat_button.setText(
                "🔁"
            )

        elif self.repeat_mode == 1:

            self.repeat_button.setText(
                "🔁 ALL"
            )

        else:

            self.repeat_button.setText(
                "🔂 ONE"
            )

    # --------------------------------------------------------

    def change_speed(self):

        current = safe_float(
            self.settings.get(
                "speed"
            ),
            1.0
        )

        speeds = [
            0.5,
            0.75,
            1.0,
            1.25,
            1.5,
            1.75,
            2.0,
        ]

        try:

            index = speeds.index(
                current
            )

        except ValueError:

            index = 2

        index = (
            index + 1
        ) % len(speeds)

        speed = speeds[index]

        self.settings.set(
            "speed",
            speed
        )

        self.settings.save()

        self.player.set_rate(
            speed
        )

        self.speed_button.setText(
            f"{speed:g}x"
        )

    # --------------------------------------------------------

    def toggle_mute(self):

        self.muted = not self.muted

        self.player.mute(
            self.muted
        )

        if self.muted:

            self.mute_button.setText(
                "🔇"
            )

        else:

            self.mute_button.setText(
                "🔊"
            )

    # ========================================================
    # QUEUE
    # ========================================================

    def refresh_queue(self):

        self.queue_list.clear()

        for path in self.queue:

            song = self.library.find(
                path
            )

            if not song:
                continue

            item = QListWidgetItem(
                f"{song.get('title', 'Unknown')}\n"
                f"{song.get('artist', 'Unknown Artist')}"
            )

            item.setData(
                Qt.ItemDataRole.UserRole,
                path
            )

            self.queue_list.addItem(
                item
            )

    # --------------------------------------------------------

    def sync_queue_from_widget(self):

        paths = []

        for index in range(
            self.queue_list.count()
        ):

            item = (
                self.queue_list.item(index)
            )

            path = item.data(
                Qt.ItemDataRole.UserRole
            )

            if path:
                paths.append(
                    path
                )

        self.queue = paths
        self.save_queue()

    # --------------------------------------------------------

    def save_queue(self):

        self.settings.set(
            "queue",
            list(self.queue)
        )
        self.settings.save()

    # --------------------------------------------------------

    def add_selected_to_queue(self):

        item = (
            self.song_list.currentItem()
        )

        if not item:
            return

        data = item.data(
            Qt.ItemDataRole.UserRole
        )

        if isinstance(
            data,
            str
        ):

            if data not in self.queue:

                self.queue.append(
                    data
                )

        elif isinstance(
            data,
            dict
        ):

            for path in data.get(
                "songs",
                []
            ):

                if path not in self.queue:

                    self.queue.append(
                        path
                    )

        self.refresh_queue()
        self.save_queue()

    # --------------------------------------------------------

    def clear_queue(self):

        self.queue.clear()

        self.refresh_queue()

    # --------------------------------------------------------

    def play_queue_item(
        self,
        item
    ):

        path = item.data(
            Qt.ItemDataRole.UserRole
        )

        if path:

            self.play_path(
                path
            )

    # --------------------------------------------------------

    def queue_context_menu(
        self,
        position
    ):

        item = (
            self.queue_list.itemAt(
                position
            )
        )

        if not item:
            return

        menu = QMenu(
            self
        )

        play_action = menu.addAction(
            "Play"
        )

        remove_action = menu.addAction(
            "Remove from Queue"
        )

        action = menu.exec(
            self.queue_list.mapToGlobal(
                position
            )
        )

        if action == play_action:

            self.play_queue_item(
                item
            )

        elif action == remove_action:

            row = (
                self.queue_list.row(item)
            )

            self.queue_list.takeItem(
                row
            )

            self.sync_queue_from_widget()

    # ========================================================
    # PLAYLISTS
    # ========================================================

    def refresh_playlists(self):

        self.playlist_list.clear()

        for name in sorted(
            self.library.playlists.keys()
        ):

            item = QListWidgetItem(
                name
            )

            self.playlist_list.addItem(
                item
            )

    # --------------------------------------------------------

    def create_playlist(self):

        name, ok = QInputDialog.getText(
            self,
            "New Playlist",
            "Playlist name:"
        )

        if not ok:
            return

        if not self.library.create_playlist(
            name
        ):

            QMessageBox.warning(
                self,
                "YuiMusic",
                "Playlist already exists or name is invalid."
            )

            return

        self.refresh_playlists()

    # --------------------------------------------------------

    def open_playlist_item(
        self,
        item
    ):

        name = item.text()

        self.current_playlist = name
        self.view_mode = "playlist"

        self.page_title.setText(
            name
        )

        self.back_button.hide()

        self.refresh_song_list()

    # --------------------------------------------------------

    def playlist_context_menu(
        self,
        position
    ):

        item = (
            self.playlist_list.itemAt(
                position
            )
        )

        if not item:
            return

        name = item.text()

        menu = QMenu(
            self
        )

        rename_action = menu.addAction(
            "Rename"
        )

        delete_action = menu.addAction(
            "Delete"
        )

        action = menu.exec(
            self.playlist_list.mapToGlobal(
                position
            )
        )

        if action == rename_action:

            self.rename_playlist(
                name
            )

        elif action == delete_action:

            self.delete_playlist(
                name
            )

    # --------------------------------------------------------

    def rename_playlist(
        self,
        old_name
    ):

        name, ok = QInputDialog.getText(
            self,
            "Rename Playlist",
            "New name:",
            text=old_name
        )

        if not ok:
            return

        if not self.library.rename_playlist(
            old_name,
            name
        ):

            QMessageBox.warning(
                self,
                "YuiMusic",
                "Unable to rename playlist."
            )

            return

        if self.current_playlist == old_name:

            self.current_playlist = name

        self.refresh_playlists()
        self.refresh_song_list()

    # --------------------------------------------------------

    def delete_playlist(
        self,
        name
    ):

        answer = QMessageBox.question(
            self,
            "Delete Playlist",
            f"Delete playlist '{name}'?"
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        self.library.delete_playlist(
            name
        )

        if self.current_playlist == name:

            self.current_playlist = None

            self.show_view(
                "home"
            )

        self.refresh_playlists()

    # ========================================================
    # SONG CONTEXT MENU
    # ========================================================

    def song_context_menu(
        self,
        position
    ):

        item = (
            self.song_list.itemAt(
                position
            )
        )

        if not item:
            return

        data = item.data(
            Qt.ItemDataRole.UserRole
        )

        if not isinstance(
            data,
            str
        ):
            return

        song = self.library.find(
            data
        )

        if not song:
            return

        menu = QMenu(
            self
        )

        play_action = menu.addAction(
            "▶ Play"
        )

        queue_action = menu.addAction(
            "＋ Add to Queue"
        )

        menu.addSeparator()

        if song.get(
            "liked",
            False
        ):

            like_action = menu.addAction(
                "♥ Unlike"
            )

        else:

            like_action = menu.addAction(
                "♡ Like"
            )

        playlist_menu = menu.addMenu(
            "Add to Playlist"
        )

        playlist_actions = {}

        for name in sorted(
            self.library.playlists.keys()
        ):

            action = playlist_menu.addAction(
                name
            )

            playlist_actions[action] = name

        menu.addSeparator()

        location_action = menu.addAction(
            "Open File Location"
        )

        if self.view_mode == "playlist":

            remove_playlist_action = (
                menu.addAction(
                    "Remove from Playlist"
                )
            )

        else:

            remove_playlist_action = None

        remove_action = menu.addAction(
            "Remove from Library"
        )

        action = menu.exec(
            self.song_list.mapToGlobal(
                position
            )
        )

        if action == play_action:

            self.play_path(
                data
            )

        elif action == queue_action:

            if data not in self.queue:

                self.queue.append(
                    data
                )

                self.refresh_queue()

        elif action == like_action:

            self.library.toggle_like(
                data
            )

            self.refresh_song_list()

        elif action in playlist_actions:

            playlist = playlist_actions[
                action
            ]

            self.library.add_to_playlist(
                playlist,
                data
            )

        elif action == location_action:

            self.open_file_location(
                data
            )

        elif (
            remove_playlist_action
            and
            action == remove_playlist_action
        ):

            self.library.remove_from_playlist(
                self.current_playlist,
                data
            )

            self.refresh_song_list()

        elif action == remove_action:

            if (
                self.current_path
                ==
                os.path.abspath(data)
            ):

                self.player.stop()

                self.current_path = None

                self.update_now_playing_empty()

            self.library.remove_song(
                data
            )

            self.queue = [
                path
                for path in self.queue
                if os.path.abspath(path)
                != os.path.abspath(data)
            ]

            self.refresh_queue()
            self.save_queue()
            self.refresh_song_list()
            self.update_statistics()

    # --------------------------------------------------------

    def open_file_location(
        self,
        path
    ):

        if not os.path.exists(
            path
        ):
            return

        if sys.platform.startswith(
            "win"
        ):

            subprocess.Popen(
                [
                    "explorer",
                    "/select,",
                    os.path.normpath(path)
                ]
            )

        elif sys.platform == "darwin":

            subprocess.Popen(
                [
                    "open",
                    "-R",
                    path
                ]
            )

        else:

            subprocess.Popen(
                [
                    "xdg-open",
                    os.path.dirname(path)
                ]
            )

    # ========================================================
    # SETTINGS
    # ========================================================

    def open_settings(self):

        dialog = SettingsDialog(
            self.volume_slider.value(),
            self.settings.get(
                "speed"
            ),
            self
        )

        if dialog.exec() != (
            QDialog.DialogCode.Accepted
        ):
            return

        values = dialog.values()

        self.volume_slider.setValue(
            values["volume"]
        )

        self.settings.set(
            "volume",
            values["volume"]
        )

        self.settings.set(
            "speed",
            values["speed"]
        )

        self.settings.save()

        self.player.set_rate(
            values["speed"]
        )

        self.speed_button.setText(
            f"{values['speed']:g}x"
        )

        QMessageBox.information(
            self,
            "YuiMusic",
            "Settings saved."
        )

    # ========================================================
    # STATISTICS
    # ========================================================

    def update_statistics(self):

        total = len(
            self.library.songs
        )

        liked = sum(
            1
            for song in self.library.songs
            if song.get(
                "liked",
                False
            )
        )

        artists = len(
            set(
                song.get(
                    "artist",
                    "Unknown Artist"
                )
                for song in self.library.songs
            )
        )

        albums = len(
            set(
                (
                    song.get(
                        "album",
                        "Unknown Album"
                    ),
                    song.get(
                        "artist",
                        "Unknown Artist"
                    )
                )
                for song in self.library.songs
            )
        )

        self.stats_label.setText(
            f"{total} songs • "
            f"{artists} artists • "
            f"{albums} albums • "
            f"{liked} liked"
        )

    # ========================================================
    # FULLSCREEN
    # ========================================================

    def toggle_video_fullscreen(self):

        if self.video_fullscreen:

            self.showNormal()

            self.video_fullscreen = False

            self.video_widget.setMinimumHeight(
                250
            )

        else:

            self.showFullScreen()

            self.video_fullscreen = True

    # ========================================================
    # SHORTCUTS
    # ========================================================

    def setup_shortcuts(self):

        shortcut_space = QShortcut(
            QKeySequence("Space"),
            self
        )

        shortcut_space.activated.connect(
            self.toggle_play
        )

        shortcut_left = QShortcut(
            QKeySequence("Left"),
            self
        )

        shortcut_left.activated.connect(
            self.previous_song
        )

        shortcut_right = QShortcut(
            QKeySequence("Right"),
            self
        )

        shortcut_right.activated.connect(
            self.next_song
        )

        shortcut_m = QShortcut(
            QKeySequence("M"),
            self
        )

        shortcut_m.activated.connect(
            self.toggle_mute
        )

        shortcut_s = QShortcut(
            QKeySequence("S"),
            self
        )

        shortcut_s.activated.connect(
            self.toggle_shuffle
        )

        shortcut_r = QShortcut(
            QKeySequence("R"),
            self
        )

        shortcut_r.activated.connect(
            self.toggle_repeat
        )

        shortcut_escape = QShortcut(
            QKeySequence("Escape"),
            self
        )

        shortcut_escape.activated.connect(
            self.handle_escape
        )

    # --------------------------------------------------------

    def handle_escape(self):

        if self.video_fullscreen:

            self.showNormal()

            self.video_fullscreen = False

            return

        if self.view_mode in (
            "album_detail",
            "artist_detail"
        ):

            self.back_from_group()

    # ========================================================
    # DRAG AND DROP
    # ========================================================

    def dragEnterEvent(
        self,
        event
    ):

        if event.mimeData().hasUrls():

            event.acceptProposedAction()

        else:

            event.ignore()

    # --------------------------------------------------------

    def dropEvent(
        self,
        event
    ):

        files = []

        for url in event.mimeData().urls():

            if not url.isLocalFile():
                continue

            path = url.toLocalFile()

            if os.path.isfile(path):

                if path.lower().endswith(
                    SUPPORTED_EXTENSIONS
                ):

                    files.append(
                        path
                    )

            elif os.path.isdir(path):

                self.scan_folder(
                    path
                )

        songs = []

        for path in files:

            songs.append(
                read_metadata(path)
            )

        self.library.add_songs(
            songs
        )

        self.refresh_song_list()
        self.update_statistics()

        event.acceptProposedAction()

    # ========================================================
    # KEY PRESS
    # ========================================================

    def keyPressEvent(
        self,
        event
    ):

        if (
            event.key()
            ==
            Qt.Key.Key_Escape
        ):

            self.handle_escape()

            return

        super().keyPressEvent(
            event
        )

    # ========================================================
    # CLOSE
    # ========================================================

    def closeEvent(
        self,
        event
    ):

        self.settings.set(
            "window_width",
            self.width()
        )

        self.settings.set(
            "window_height",
            self.height()
        )

        self.settings.save()

        try:

            self.player.stop()

        except Exception:
            pass

        event.accept()


# ============================================================
# APPLICATION
# ============================================================

def main():

    ensure_data_dir()

    app = QApplication(
        sys.argv
    )

    app.setApplicationName(
        APP_NAME
    )

    window = MainWindow()

    window.show()

    sys.exit(
        app.exec()
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()