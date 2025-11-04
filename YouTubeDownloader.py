import os
import sys
import threading
import subprocess
import shutil
import re
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, StringVar

MUSIC_DIR = Path.home() / "Music"
VIDEO_DIR = Path.home() / "Videos"

def ensure_yt_dlp():
    try:
        import yt_dlp
    except ImportError:
        if getattr(sys, 'frozen', False):
            print("yt-dlp not found inside EXE. Please install it manually if running from source.")
            return
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"])
    else:
        if not getattr(sys, 'frozen', False):
            subprocess.run([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"])


def progress_hook(d, log_widget, stop_flag):
    if stop_flag["cancel"]:
        raise Exception("Download canceled by user.")

    status = d.get("status")
    filename = Path(d.get("filename", ""))

    if status == "downloading":
        percent = d.get("_percent_str", "").strip()
        speed = d.get("_speed_str", "").strip()
        eta = d.get("_eta_str", "").strip()
        line = f"Downloading: {filename.name} — {percent} ({speed}, ETA {eta})\n"
        log_widget.delete("end-2l", "end-1l")
        log_widget.insert(tk.END, line)
        log_widget.see(tk.END)
    elif status == "finished":
        log_widget.insert(tk.END, f"Download finished, processing {filename.name}...\n")
        log_widget.see(tk.END)
    elif status == "postprocessing":
        log_widget.insert(tk.END, "Post-processing with FFmpeg...\n")
        log_widget.see(tk.END)


def download_media(url, format_choice, log_widget, music_dir, video_dir, stop_flag):
    import yt_dlp

    if format_choice.startswith("---"):
        log_widget.insert(tk.END, "Please select a valid output format.\n")
        log_widget.see(tk.END)
        return

    # Detect ?index= in playlist links and force single video mode
    is_index_link = re.search(r"[?&]index=\d+", url)
    noplaylist_flag = True if is_index_link else False

    is_audio = format_choice in ["MP3", "M4A", "WAV", "OGG"]
    output_dir = music_dir if is_audio else video_dir
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Locate ffmpeg (supports frozen EXE and system install)
    if getattr(sys, "frozen", False):
        ffmpeg_path = os.path.join(sys._MEIPASS, "ffmpeg", "ffmpeg.exe")
    else:
        ffmpeg_path = shutil.which("ffmpeg") or r"C:\ffmpeg\bin\ffmpeg.exe"

    ydl_opts = {
        "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
        "quiet": True,
        "noprogress": True,
        "ignoreerrors": True,
        "noplaylist": noplaylist_flag,
        "progress_hooks": [lambda d: progress_hook(d, log_widget, stop_flag)],
        "ffmpeg_location": ffmpeg_path,
    }

    if is_audio:
        ydl_opts.update({
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": format_choice.lower(),
                    "preferredquality": "192",
                },
                {"key": "FFmpegMetadata"},
            ],
        })
    else:
        ydl_opts.update({
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": format_choice.lower(),
            "postprocessors": [
                {"key": "FFmpegVideoRemuxer", "preferedformat": format_choice.lower()},
                {"key": "FFmpegMetadata"},
            ],
        })

    try:
        log_widget.insert(tk.END, f"Starting download in {output_dir}...\n")
        log_widget.see(tk.END)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        if not stop_flag["cancel"]:
            log_widget.insert(tk.END, f"Download complete.\nSaved to: {output_dir}\n")
        else:
            log_widget.insert(tk.END, "Download canceled by user.\n")
        log_widget.see(tk.END)

    except Exception as e:
        if "canceled" not in str(e).lower():
            log_widget.insert(tk.END, f"Error: {e}\n")
        else:
            log_widget.insert(tk.END, "Download canceled.\n")
        log_widget.see(tk.END)

        if "canceled" in str(e).lower():
            for f in Path(output_dir).glob("*.part"):
                try:
                    f.unlink()
                    log_widget.insert(tk.END, f"Deleted partial file: {f.name}\n")
                except Exception:
                    pass


class ModernDownloaderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("YouTube / YouTube Music Downloader")
        self.geometry("620x520")
        self.resizable(True, True)

        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        self.configure(bg="#f2f2f2")
        self.style.configure("TLabel", background="#f2f2f2", font=("Segoe UI", 10, "bold"))
        self.style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=6)
        self.style.configure("TCombobox", font=("Segoe UI", 10))
        self.style.configure("TFrame", background="#f2f2f2")

        self.url_var = StringVar()
        self.format_var = StringVar(value="MP3")
        self.music_dir = MUSIC_DIR
        self.video_dir = VIDEO_DIR
        self.stop_flag = {"cancel": False}
        self.download_thread = None

        main_frame = ttk.Frame(self, padding=15)
        main_frame.pack(fill="both", expand=True)

        ttk.Label(main_frame, text="Enter YouTube or YouTube Music URL:").pack(anchor="w", pady=(5, 2))
        ttk.Entry(main_frame, textvariable=self.url_var, width=70).pack(pady=5)

        ttk.Label(main_frame, text="Select Output Format:").pack(anchor="w", pady=(8, 2))
        format_values = [
            "--- Audio Formats ---",
            "MP3", "M4A", "WAV", "OGG",
            "--- Video Formats ---",
            "MP4", "WEBM", "MKV", "MOV"
        ]
        ttk.Combobox(main_frame, textvariable=self.format_var, values=format_values, state="readonly", width=25).pack(pady=5)

        folder_frame = ttk.Frame(main_frame)
        folder_frame.pack(pady=10)
        ttk.Button(folder_frame, text="Change Music Folder", command=self.change_music_folder).pack(side="left", padx=5)
        ttk.Button(folder_frame, text="Change Video Folder", command=self.change_video_folder).pack(side="left", padx=5)

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=10)
        self.download_btn = ttk.Button(button_frame, text="Download", command=self.start_download)
        self.download_btn.pack(side="left", padx=10)
        self.cancel_btn = ttk.Button(button_frame, text="Cancel Download", command=self.cancel_download, state="disabled")
        self.cancel_btn.pack(side="left", padx=10)

        ttk.Label(main_frame, text="Log:").pack(anchor="w", pady=(8, 2))
        self.log_text = tk.Text(main_frame, height=15, wrap="word", font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True)
        self.log_text.insert(tk.END, f"Ready.\nDefault Music Folder: {self.music_dir}\nDefault Video Folder: {self.video_dir}\n")

    def change_music_folder(self):
        new_dir = filedialog.askdirectory(title="Select Music Download Folder")
        if new_dir:
            self.music_dir = Path(new_dir)
            self.log_text.insert(tk.END, f"Music folder changed to: {self.music_dir}\n")
            self.log_text.see(tk.END)

    def change_video_folder(self):
        new_dir = filedialog.askdirectory(title="Select Video Download Folder")
        if new_dir:
            self.video_dir = Path(new_dir)
            self.log_text.insert(tk.END, f"Video folder changed to: {self.video_dir}\n")
            self.log_text.see(tk.END)

    def start_download(self):
        url = self.url_var.get().strip()
        fmt = self.format_var.get()
        if not url:
            messagebox.showwarning("Input Error", "Please enter a valid YouTube or YouTube Music URL.")
            return
        if fmt.startswith("---"):
            messagebox.showwarning("Format Error", "Please select a valid output format.")
            return

        self.log_text.insert(tk.END, f"Preparing to download: {url}\n")
        self.log_text.see(tk.END)

        self.download_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.stop_flag["cancel"] = False

        self.download_thread = threading.Thread(target=self.run_download, args=(url, fmt))
        self.download_thread.daemon = True
        self.download_thread.start()

    def run_download(self, url, fmt):
        try:
            ensure_yt_dlp()
            download_media(url, fmt, self.log_text, self.music_dir, self.video_dir, self.stop_flag)
        finally:
            self.download_btn.config(state="normal")
            self.cancel_btn.config(state="disabled")

    def cancel_download(self):
        if self.download_thread and self.download_thread.is_alive():
            self.stop_flag["cancel"] = True
            self.log_text.insert(tk.END, "Attempting to cancel download...\n")
            self.log_text.see(tk.END)


if __name__ == "__main__":
    app = ModernDownloaderApp()
    app.mainloop()
