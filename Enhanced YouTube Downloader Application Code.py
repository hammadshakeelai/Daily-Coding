# ---------------------------------------------
# Imports
# ---------------------------------------------
from tkinter import *
from tkinter import ttk, filedialog, messagebox
from PIL import ImageTk, Image
from pytube import YouTube, Stream
import pytube.request
import os
import threading
import time

# Use a larger chunk size so progress updates are less chatty & downloads are faster
pytube.request.default_range_size = 1024 * 1024  # 1 MB

# Global variables for download control
download_in_progress = False
current_stream = None

# ---------------------------------------------
# Helper functions
# ---------------------------------------------
def reset_progress():
    """Reset progress bar and percentage labels."""
    progress_bar['value'] = 0
    label_percentage.config(text="0%")
    label_download_completed.config(text="")
    window.update_idletasks()


def disable_quality_radios():
    """Disable all quality radio buttons and reset their colors."""
    bg_color = window.cget("bg")
    for rb in (radio_res_720, radio_res_480, radio_res_360, radio_res_240):
        rb.config(state=DISABLED, bg=bg_color, fg="black")


def enable_resolution_radio(resolution: str):
    """Enable a resolution radio button and style it."""
    color_map = {
        "720p": ("#aad179", "#527824"),
        "480p": ("#aad179", "#527824"),
        "360p": ("#aad179", "#527824"),
        "240p": ("#aad179", "#527824")
    }
    
    if resolution in color_map:
        bg_color, select_color = color_map[resolution]
        radio_buttons = {
            "720p": radio_res_720,
            "480p": radio_res_480,
            "360p": radio_res_360,
            "240p": radio_res_240
        }
        rb = radio_buttons[resolution]
        rb.configure(state=NORMAL, bg=bg_color, fg="black", selectcolor=select_color)


def update_ui_state(enabled=True):
    """Enable or disable UI elements during download."""
    state = NORMAL if enabled else DISABLED
    btn_get_info.config(state=state)
    btn_browse.config(state=state)
    radio_audio.config(state=state)
    radio_video.config(state=state)
    btn_download.config(state=state)
    entry_videoLink.config(state=state)
    
    # Disable quality radios if video is not selected
    if audio_video.get() != 2:
        disable_quality_radios()
    else:
        # Re-enable available resolutions
        update_available_resolutions()


def update_available_resolutions():
    """Update available resolution radio buttons based on video selection."""
    if audio_video.get() == 2 and 'available_resolutions' in globals():
        disable_quality_radios()
        for res in available_resolutions:
            enable_resolution_radio(res)


# ---------------------------------------------
# Core logic functions
# ---------------------------------------------
def get_info():
    """Fetch video info & available streams for the given URL."""
    url = entry_videoLink.get().strip()
    if not url:
        messagebox.showwarning("Missing URL", "Please paste a YouTube video link.")
        return

    reset_progress()
    disable_quality_radios()
    radio_audio.config(state=DISABLED)
    radio_video.config(state=DISABLED)
    btn_download.config(state=DISABLED)
    
    # Show loading indicator
    label_download_completed.config(text="Fetching video info...", fg="blue")
    window.update_idletasks()

    try:
        yt = YouTube(url)
        
        # Update title and duration display
        title = yt.title[:50] + "..." if len(yt.title) > 50 else yt.title
        minutes, seconds = divmod(yt.length, 60)
        label_video_info.config(text=f"{title} ({minutes}:{seconds:02d})")
        
    except Exception as e:
        messagebox.showerror("Error", f"Could not retrieve video info:\n{e}")
        label_download_completed.config(text="")
        return

    # Streams
    streams_audio_only = yt.streams.filter(only_audio=True)
    streams_progressive = yt.streams.filter(progressive=True)
    streams_adaptive = yt.streams.filter(adaptive=True)

    # Enable audio / video options where available
    if streams_audio_only:
        radio_audio.config(state=NORMAL)

    if streams_progressive:
        radio_video.config(state=NORMAL)

    # Check which progressive resolutions exist
    global available_resolutions
    available_resolutions = []
    resolutions = ["720p", "480p", "360p", "240p"]
    
    for res in resolutions:
        stream = streams_progressive.filter(res=res).first()
        if stream is not None:
            enable_resolution_radio(res)
            available_resolutions.append(res)
            found_resolution = True

    # Set default quality to highest available
    if available_resolutions:
        highest_res = max([int(r.replace('p', '')) for r in available_resolutions])
        video_quality.set(highest_res)

    if not (streams_audio_only or available_resolutions):
        messagebox.showinfo("No Streams", "Could not find any downloadable streams for this video.")
        label_download_completed.config(text="")
        return

    # If we have something downloadable, enable the Download button
    btn_download.config(state=NORMAL)
    label_download_completed.config(text="Ready to download", fg="green")


def select_location():
    """Open a folder dialog and let the user choose a download location."""
    # Default to user home folder, more robust than a hard-coded drive
    initial_dir = os.path.expanduser("~")
    folder = filedialog.askdirectory(initialdir=initial_dir)
    if folder:
        label_download_location_box.config(text=folder)


def download_video():
    """Download audio or video based on current UI selections."""
    global download_in_progress, current_stream
    
    if download_in_progress:
        messagebox.showinfo("Download in Progress", "A download is already in progress.")
        return
    
    video_url = entry_videoLink.get().strip()
    if not video_url:
        messagebox.showwarning("Missing URL", "Please paste a YouTube video link.")
        return

    save_location = label_download_location_box["text"].strip()
    if not save_location:
        messagebox.showwarning("No Folder Selected", "Please choose a download location first.")
        return

    # Start download in separate thread
    download_thread = threading.Thread(target=perform_download, daemon=True)
    download_thread.start()


def perform_download():
    """Perform the actual download in a separate thread."""
    global download_in_progress, current_stream
    
    download_in_progress = True
    update_ui_state(False)
    
    reset_progress()
    label_download_completed.config(text="Starting download...", fg="blue")
    
    video_url = entry_videoLink.get().strip()
    save_location = label_download_location_box["text"].strip()
    av = audio_video.get()        # 1 = audio, 2 = video
    selected_quality = video_quality.get()

    try:
        yt = YouTube(video_url, on_progress_callback=progress_callback)
    except Exception as e:
        messagebox.showerror("Error", f"Could not start download:\n{e}")
        download_in_progress = False
        update_ui_state(True)
        return

    # Choose the correct stream
    try:
        if av == 1:
            # Audio only: get highest bitrate audio
            stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
            if stream is None:
                stream = yt.streams.get_audio_only()
        else:
            # Progressive video (audio + video)
            res_str = f"{selected_quality}p"
            stream = yt.streams.filter(progressive=True, res=res_str).first()
        
        current_stream = stream
        
        if stream is None:
            messagebox.showerror(
                "Error",
                "Could not find a stream matching your selection.\n"
                "Try a different quality or choose Audio only."
            )
            download_in_progress = False
            update_ui_state(True)
            return
        
        # Update UI with file size
        file_size_mb = stream.filesize / (1024 * 1024) if stream.filesize else 0
        label_file_size.config(text=f"Size: {file_size_mb:.1f} MB")
        
        # Start download
        stream.download(output_path=save_location)
        
        # Success
        progress_bar['value'] = 100
        label_percentage.config(text="100%")
        label_download_completed.config(text="Download completed successfully!", fg="green")
        
    except Exception as e:
        messagebox.showerror("Error", f"Download failed:\n{e}")
        label_download_completed.config(text="Download failed", fg="red")
    
    finally:
        download_in_progress = False
        current_stream = None
        update_ui_state(True)


def progress_callback(stream: Stream, chunk: bytes, bytes_remaining: int):
    """Update progress bar during download."""
    total_size = stream.filesize
    downloaded_size = total_size - bytes_remaining
    
    if total_size > 0:
        downloaded_percentage = int((downloaded_size / total_size) * 100)
        progress_bar['value'] = downloaded_percentage
        label_percentage.config(text=f"{downloaded_percentage}%")
        
        # Calculate download speed (simplified)
        if hasattr(stream, '_download_start_time'):
            elapsed_time = time.time() - stream._download_start_time
            if elapsed_time > 0:
                speed_mbps = (downloaded_size / (1024 * 1024)) / elapsed_time
                label_speed.config(text=f"Speed: {speed_mbps:.1f} MB/s")
        else:
            stream._download_start_time = time.time()
        
        window.update_idletasks()


def on_closing():
    """Handle window closing event."""
    global download_in_progress
    
    if download_in_progress:
        if messagebox.askyesno("Download in Progress", 
                              "A download is in progress. Are you sure you want to exit?"):
            window.destroy()
    else:
        window.destroy()


# ---------------------------------------------
# Tkinter Window Setup
# ---------------------------------------------
window = Tk()

# 1. Window size and position
window.geometry("700x700")
window.resizable(False, False)

# Center window on screen
window.update_idletasks()
screen_width = window.winfo_screenwidth()
screen_height = window.winfo_screenheight()
x = (screen_width - 700) // 2
y = (screen_height - 700) // 2
window.geometry(f"700x700+{x}+{y}")

# 2. Window title
window.title("YouTube Downloader 1.2")

# 3. Window icon (safe: don't crash if icon missing)
favicon_location = 'images\\fav.ico'
if os.path.exists(favicon_location):
    try:
        window.iconbitmap(favicon_location)
    except Exception:
        pass

# 4. Logo image (safe: fall back to a text label if missing)
logo_location = 'images\\logo.png'
if os.path.exists(logo_location):
    try:
        logo_img = ImageTk.PhotoImage(Image.open(logo_location))
        label_logo = Label(window, image=logo_img)
        label_logo.image = logo_img  # prevent garbage collection
        label_logo.place(x=200, y=20)
    except Exception:
        label_logo = Label(window, text="YouTube Downloader", font=("Arial", 16, "bold"))
        label_logo.place(x=230, y=40)
else:
    label_logo = Label(window, text="YouTube Downloader", font=("Arial", 16, "bold"))
    label_logo.place(x=230, y=40)

# Label: App Title
label_appTitle = Label(window, text="YouTube Downloader", font=("Arial", 12, "bold"))
label_appTitle.place(x=280, y=185)

# Label: App Version
label_appVersion = Label(window, text="Version 1.2", font=("Arial", 10))
label_appVersion.place(x=310, y=210)


# ---------------------------------------------
# Tkinter Widgets
# ---------------------------------------------
# Label: Video Link
label_videoLink = Label(window, text="Video Link: ")
label_videoLink.place(x=90, y=240)

# Entry: Video Link
entry_videoLink = Entry(window, width=70, bg="white", fg="black", borderwidth=1)
entry_videoLink.place(x=90, y=265)
entry_videoLink.insert(0, "https://www.youtube.com/watch?v=QC8iQqtG0hg")

# Button: Get Info
btn_get_info = Button(window, text="Get Info", bg="#4CAF50", fg="white", 
                      font=("Arial", 9, "bold"), command=get_info)
btn_get_info.place(x=520, y=263)

# Label: Video Info
label_video_info = Label(window, text="No video selected", fg="gray", font=("Arial", 9))
label_video_info.place(x=90, y=290)

# Label: Download Location
label_download_location = Label(window, text="Download Location: ")
label_download_location.place(x=90, y=315)

# Label: Displaying chosen location
label_download_location_box = Label(window, width=60, bg="white", fg="black", 
                                    borderwidth=1, anchor=W, relief="sunken")
label_download_location_box.place(x=90, y=340)
# Set default download location
default_location = os.path.join(os.path.expanduser("~"), "Downloads")
label_download_location_box.config(text=default_location)

# Button: Browse
btn_browse = Button(window, text="Browse", bg="#2196F3", fg="white",
                    font=("Arial", 9, "bold"), command=select_location)
btn_browse.place(x=520, y=338)

# Label: Audio/Video
label_audio_video = Label(window, text="Audio/Video: ")
label_audio_video.place(x=90, y=375)

# Radio Buttons: Audio/Video selection
audio_video = IntVar()
audio_video.set(1)

def on_av_selection():
    """Handle audio/video selection change."""
    if audio_video.get() == 1:  # Audio selected
        disable_quality_radios()
    else:  # Video selected
        update_available_resolutions()

radio_audio = Radiobutton(window, text="Audio/MP3", variable=audio_video, value=1, 
                         indicatoron=False, command=on_av_selection)
radio_audio.configure(state=DISABLED)
radio_audio.place(x=90, y=400)

radio_video = Radiobutton(window, text="Video/MP4", variable=audio_video, value=2, 
                         indicatoron=False, command=on_av_selection)
radio_video.configure(state=DISABLED)
radio_video.place(x=161, y=400)

# Label: Quality
label_video_quality = Label(window, text="Choose video quality: ")
label_video_quality.place(x=300, y=375)

# Radio Buttons: Video Quality
video_quality = IntVar()
video_quality.set(720)  # default to 720p where available

radio_res_720 = Radiobutton(window, text="720p", variable=video_quality, value=720, 
                           indicatoron=False, width=7)
radio_res_720.configure(state=DISABLED)
radio_res_720.place(x=300, y=400)

radio_res_480 = Radiobutton(window, text="480p", variable=video_quality, value=480, 
                           indicatoron=False, width=7)
radio_res_480.configure(state=DISABLED)
radio_res_480.place(x=371, y=400)

radio_res_360 = Radiobutton(window, text="360p", variable=video_quality, value=360, 
                           indicatoron=False, width=7)
radio_res_360.configure(state=DISABLED)
radio_res_360.place(x=442, y=400)

radio_res_240 = Radiobutton(window, text="240p", variable=video_quality, value=240, 
                           indicatoron=False, width=7)
radio_res_240.configure(state=DISABLED)
radio_res_240.place(x=513, y=400)

# File size label
label_file_size = Label(window, text="Size: -- MB", fg="gray")
label_file_size.place(x=580, y=400)

# Speed label
label_speed = Label(window, text="Speed: -- MB/s", fg="gray")
label_speed.place(x=90, y=470)

# Label: Progress text
label_progress = Label(window, text="Progress: ")
label_progress.place(x=90, y=440)

# Label: Percentage
label_percentage = Label(window, text="0%")
label_percentage.place(x=540, y=440)

# Progress Bar
style = ttk.Style()
style.theme_use('default')
style.configure("green.Horizontal.TProgressbar", 
                background='#4CAF50', 
                troughcolor='#E0E0E0',
                bordercolor='#4CAF50',
                lightcolor='#4CAF50',
                darkcolor='#4CAF50')

progress_bar = ttk.Progressbar(window, orient=HORIZONTAL, length=485, 
                              mode='determinate', style="green.Horizontal.TProgressbar")
progress_bar.place(x=90, y=465)

# Label: Download Completed
label_download_completed = Label(window, text="", fg="green", font=("Arial", 10))
label_download_completed.place(x=285, y=500)

# Button: Download
btn_download = Button(window, text="Download", bg="#C03224", fg="white",
                      height=2, width=20, font=("Arial", 10, "bold"),
                      command=download_video)
btn_download.configure(state=DISABLED)
btn_download.place(x=280, y=535)

# Status bar
status_bar = Label(window, text="Ready", bd=1, relief=SUNKEN, anchor=W)
status_bar.pack(side=BOTTOM, fill=X)

# Handle window closing
window.protocol("WM_DELETE_WINDOW", on_closing)

# Event Loop
window.mainloop()