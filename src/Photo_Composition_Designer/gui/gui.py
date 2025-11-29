"""GUI interface for Photo-Composition-Designer using tkinter with integrated logging.

This module provides a graphical user interface for the Photo-Composition-Designer
with settings dialog, file management, and centralized logging capabilities.

run gui: python -m Photo_Composition_Designer.gui
"""

import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import traceback
import webbrowser
from datetime import timedelta
from functools import partial
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from config_cli_gui.gui import SettingsDialogGenerator, ToolTip
from PIL import Image, ImageTk

from Photo_Composition_Designer.common.logging import (
    connect_gui_logging,
    disconnect_gui_logging,
    get_logger,
    initialize_logging,
)
from Photo_Composition_Designer.common.Photo import Photo, get_photos_from_dir
from Photo_Composition_Designer.CompositionDesigner import CompositionDesigner
from Photo_Composition_Designer.config.config import ConfigParameterManager
from Photo_Composition_Designer.gui.GuiLogWriter import GuiLogWriter
from Photo_Composition_Designer.tools.DescriptionsFileGenerator import DescriptionsFileGenerator
from Photo_Composition_Designer.tools.ImageDistributor import ImageDistributor


class MainGui:
    """Main GUI application class."""

    distribution_modes = [
        ("distribute_equally", "Distribute photos equally"),
        ("distribute_randomly", "Distribute photos randomly"),
        ("distribute_group_matching_dates", "Distribute photos by date"),
    ]

    def __init__(self, root):
        self.root = root
        self.root.title("Photo-Composition-Designer")
        self.root.geometry("1200x600")  # Increased width for new layout
        self.root.update_idletasks()

        # Initialize configuration
        try:
            self.config_manager = ConfigParameterManager("config.yaml")
        except Exception:
            self.config_manager = ConfigParameterManager()

        # Initialize logging system
        self.logger_manager = initialize_logging(self.config_manager)
        self.logger = get_logger("gui.main")

        # File lists
        self.composition_designer = CompositionDesigner(self.config_manager)
        self.preview_image_original = None

        self.photo_folders = []
        self.generated_compositions = []

        self._build_widgets()
        self._create_menu()

        # Load initial folder list
        self._load_photo_folders()

        # Setup GUI logging after widgets are created
        self._setup_gui_logging()

        # Handle window closing
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

        self.logger.info("GUI application started")
        self.logger.info(f"Photo directory: {self.composition_designer.photoDirectory}")
        self.logger_manager.log_config_summary()
        self._generate_preview(1)
        self._generate_preview(0)

    def _build_widgets(self):
        """Build the main GUI widgets using paned windows for full resize behavior."""
        # Main container
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # === TOP-LEVEL PANED WINDOW (vertical: top area + log area) ===
        vertical_paned = ttk.PanedWindow(main_frame, orient=tk.VERTICAL)
        vertical_paned.pack(fill=tk.BOTH, expand=True)

        # === UPPER PANED (horizontal: file list + preview + fixed button panel) ===
        top_paned = ttk.PanedWindow(vertical_paned, orient=tk.HORIZONTAL)
        vertical_paned.add(top_paned, weight=3)

        # -------------------------------------------------------------
        # LEFT SIDE — Input File List
        # -------------------------------------------------------------
        photo_dir_frame = ttk.LabelFrame(top_paned, text="Input Files")
        top_paned.add(photo_dir_frame, weight=1)

        self.photo_dir_listbox = tk.Listbox(photo_dir_frame, selectmode=tk.EXTENDED)
        input_file_scrollbar = ttk.Scrollbar(
            photo_dir_frame, orient="vertical", command=self.photo_dir_listbox.yview
        )
        self.photo_dir_listbox.configure(yscrollcommand=input_file_scrollbar.set)

        self.photo_dir_listbox.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        input_file_scrollbar.pack(side="right", fill="y", pady=5)

        self.photo_dir_listbox.bind(
            "<Double-Button-1>", lambda event: self._open_selected_file(event, self.photo_folders)
        )
        self.photo_dir_listbox.bind(
            "<Button-1>", lambda event: self._generate_preview_callback(event)
        )
        self.photo_dir_listbox.bind("<Up>", lambda event: self._generate_preview_callback())
        self.photo_dir_listbox.bind("<Down>", lambda event: self._generate_preview_callback())

        # -------------------------------------------------------------
        # CENTER — Preview panel
        # -------------------------------------------------------------
        self.image_frame = ttk.LabelFrame(top_paned, text="Preview")
        top_paned.add(self.image_frame, weight=4)

        self.preview_label = ttk.Label(self.image_frame)
        self.preview_label.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.preview_label.bind("<Configure>", self._refresh_preview)
        self.image_frame.bind("<Configure>", self._refresh_preview)
        self.preview_label.bind("<Configure>", self._refresh_preview)

        # -------------------------------------------------------------
        # RIGHT SIDE — FIXED-WIDTH BUTTON PANEL
        # -------------------------------------------------------------
        button_outer_frame = ttk.Frame(top_paned)
        # Add with weight=0 to keep fixed width
        top_paned.add(button_outer_frame, weight=0)

        # inner frame for padding
        button_frame = ttk.Frame(button_outer_frame)
        button_frame.pack(fill=tk.Y, padx=5, pady=5)

        # folder selection
        select_folder_button = ttk.Button(
            button_frame, text="Select photos directory", command=self._select_folder
        )
        select_folder_button.pack(pady=10, fill=tk.X)

        # dynamic run buttons
        self.run_buttons = {}
        for mode, label in self.distribution_modes:
            button = ttk.Button(
                button_frame, text=label, command=partial(self._run_processing, mode=mode)
            )
            ToolTip(button, f"Distribute all images into folders using \nthe method '{label}'")
            button.pack(pady=2, fill=tk.X)
            self.run_buttons[mode] = button

        # description file button
        self.generate_description_file_button = ttk.Button(
            button_frame,
            text="Generate Description File",
            command=self._generate_template_description_file,
        )
        ToolTip(
            self.generate_description_file_button,
            "Generate a template description file for all collages \n"
            "based on the generated photo directories",
        )
        self.generate_description_file_button.pack(pady=20, fill=tk.X)

        # compositions button
        self.generate_compositions_button = ttk.Button(
            button_frame, text="Generate Compositions", command=self._generate_compositions
        )
        self.generate_compositions_button.pack(pady=0, fill=tk.X)

        # progress bar
        self.progress = ttk.Progressbar(button_frame, mode="indeterminate")
        self.progress.pack(
            pady=10,
            fill=tk.X,
        )

        # === LOWER AREA — Log Output ===
        log_frame = ttk.LabelFrame(vertical_paned, text="Log Output")
        vertical_paned.add(log_frame, weight=1)

        # log text area with scrollbar
        log_text_frame = ttk.Frame(log_frame)
        log_text_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.log_text = tk.Text(log_text_frame, height=10, wrap=tk.WORD)
        log_text_scrollbar = ttk.Scrollbar(
            log_text_frame, orient="vertical", command=self.log_text.yview
        )
        self.log_text.configure(yscrollcommand=log_text_scrollbar.set)

        self.log_text.pack(side="left", fill="both", expand=True)
        log_text_scrollbar.pack(side="right", fill="y")

        # log controls
        log_controls = ttk.Frame(log_frame)
        log_controls.pack(fill=tk.X, padx=5, pady=(0, 5))

        ttk.Button(log_controls, text="Clear Log", command=self._clear_log).pack(side=tk.LEFT)

        ttk.Label(log_controls, text="Log Level:").pack(side=tk.LEFT, padx=(10, 5))
        self.log_level_var = tk.StringVar(value=self.config_manager.app.log_level.value)

        log_level_combo = ttk.Combobox(
            log_controls,
            textvariable=self.log_level_var,
            values=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            state="readonly",
            width=10,
        )
        log_level_combo.pack(side=tk.LEFT)
        log_level_combo.bind("<<ComboboxSelected>>", self._on_log_level_changed)

    def _create_menu(self):
        """Create the application menu."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open...", command=self._select_folder)
        file_menu.add_separator()

        # Create Run menu options dynamically
        for mode, label in self.distribution_modes:
            file_menu.add_command(label=label, command=partial(self._run_processing, mode=mode))

        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_closing)

        # Options menu
        options_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Options", menu=options_menu)
        options_menu.add_command(label="Settings", command=self._open_settings)

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="User help", command=self._open_help)
        help_menu.add_separator()
        help_menu.add_command(label="About", command=self._show_about)

    def _generate_preview_callback(self, event=None):
        if event:
            selection_index = event.widget.nearest(event.y)
            if selection_index == -1:
                return
        else:
            selection = self.photo_dir_listbox.curselection()
            if not selection:
                return
            selection_index = selection[0]
        self._generate_preview(selection_index)

    def _generate_preview(self, selection_index):
        folder_name = self.photo_folders[selection_index].name
        preview_image: Image.Image = self.composition_designer.generate_compositions_from_folder(
            folder_name
        )

        if not preview_image:
            self.logger.info(f"Empty folder '{folder_name}'. No preview available.")
            return
        # Save original unscaled image
        img = preview_image.copy()
        self.preview_image_original = img

        # Scale to current preview widget
        w = self.preview_label.winfo_width()
        h = self.preview_label.winfo_height()

        if w > 0 and h > 0:
            img.thumbnail((w, h))

        self.preview_photo = ImageTk.PhotoImage(img)
        self.preview_label.configure(image=self.preview_photo)

        self.logger.info(f"Preview generated for folder {folder_name}")

        # self.preview_label.after(10, lambda: self._refresh_preview(tk.Event()))

    def _load_photo_folders(self):
        """Scan self.photo_dir for subfolders and populate the listbox and internal list."""

        # Clear previous content
        self.photo_dir_listbox.delete(0, tk.END)
        self.photo_folders = []

        if (
            not self.composition_designer.photoDirectory.exists()
            or not self.composition_designer.photoDirectory.is_dir()
        ):
            self.logger.warning(
                f"Photo directory '{self.composition_designer.photoDirectory}' does not exist."
            )
            return

        # Collect subfolder names, sorted alphabetically
        subfolders = sorted(
            [item for item in self.composition_designer.photoDirectory.iterdir() if item.is_dir()],
            key=lambda p: p.name.lower(),
        )

        # Populate internal list AND the listbox
        for folder in subfolders:
            self.photo_folders.append(folder)
            self.photo_dir_listbox.insert(tk.END, folder.name)

        self.logger.info(f"Loaded {len(self.photo_folders)} photo subfolders.")

    def _setup_gui_logging(self):
        """Setup GUI logging integration."""
        # Create GUI log writer
        self.gui_log_writer = GuiLogWriter(self.log_text)

        # Connect to logging system
        connect_gui_logging(self.gui_log_writer)

    def _on_log_level_changed(self, event=None):
        """Handle log level change."""
        new_level = self.log_level_var.get()
        self.logger_manager.set_log_level(new_level)
        self.logger.info(f"Log level changed to {new_level}")

    def _clear_log(self):
        """Clear the log text widget."""
        self.log_text.delete(1.0, tk.END)
        self.logger.debug("Log display cleared")

    def _generate_compositions(self):
        """Generate all compositions"""
        pass
        self.logger.info("Generate all compositions...")
        self.composition_designer.generate_compositions_from_folders()
        self.logger.info("Compositions generated")

    def _open_selected_file(self, event, file_list_source):
        """Opens the selected file in the system's default application or explorer."""
        selection_index = event.widget.nearest(event.y)
        if selection_index == -1:  # No item clicked
            return

        file_path_str = file_list_source[selection_index]["path"]
        file_path = Path(file_path_str)

        if not file_path.exists():
            self.logger.error(f"File not found: {file_path}")
            messagebox.showerror("Error", f"File not found: {file_path}")
            return

        try:
            if sys.platform == "win32":
                os.startfile(file_path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", file_path])
            else:
                subprocess.Popen(["xdg-open", file_path])
            self.logger.info(f"Opened file: {file_path}")
        except Exception as e:
            self.logger.error(f"Could not open file {file_path}: {e}")
            messagebox.showerror("Error", f"Could not open file {file_path}: {e}")

    def _select_folder(self):
        """Open file dialog and add files to list."""
        folder = filedialog.askdirectory(
            title="Select folder with photos",
        )

        self.photo_folders = folder

        if folder > 0:
            self.logger.info(f"Added {folder} new files to processing list")
        else:
            self.logger.debug("No new files selected")
        self._generate_preview(0)

    def _run_processing(self, mode="distribute_group_matching_dates"):
        """Run the processing in a separate thread."""

        self.logger.info(f"Starting distribution of in mode: {mode}")

        # Disable all buttons during processing
        for button in self.run_buttons.values():
            button.config(state="disabled")

        self.generate_compositions_button.config(state="disabled")
        self.progress.start()

        # Run in separate thread to avoid blocking GUI
        thread = threading.Thread(
            target=self._distribute_images,
            args=(mode,),
            daemon=True,
        )
        thread.start()

    def _distribute_images(self, mode="compress_files"):
        """Process the selected files."""
        grouped_images = []
        try:
            self.logger.info("=== Processing Started ===")
            self.logger.info("Processing files...")

            # prepare image sorting:
            photos: list[Photo] = get_photos_from_dir(self.composition_designer.photoDirectory)

            # prepare image distribution
            collages_to_generate = self.config_manager.calendar.collagesToGenerate.value
            image_distributor = ImageDistributor(photos, collages_to_generate)
            # implement switch case for different processing modes
            if mode == "distribute_equally":
                grouped_images = image_distributor.distribute_equally()
            elif mode == "distribute_randomly":
                grouped_images = image_distributor.distribute_randomly()
            elif mode == "distribute_group_matching_dates":
                grouped_images = image_distributor.distribute_group_matching_dates()
            else:
                self.logger.warning(f"Unknown mode: {mode}")

            start_date = self.config_manager.calendar.startDate.value
            output_dir = self.composition_designer.photoDirectory
            for week in range(collages_to_generate):
                week_start = start_date + timedelta(weeks=week)
                folder_name = f"{week:02d}_{week_start.strftime('%b-%d')}"
                folder_path = os.path.join(output_dir, folder_name)
                os.makedirs(folder_path, exist_ok=True)
                self.logger.info(f"Folder created: {folder_path}")

                if not grouped_images:
                    continue
                images_in_group = grouped_images.pop(0)
                for photo in images_in_group:
                    image_file_name = photo.file_path.name
                    destination_path = os.path.join(folder_path, image_file_name)
                    shutil.copy2(photo.file_path, destination_path)
                    self.logger.info(
                        f"  --> Image {photo.file_path.name} sorted into {folder_name}"
                    )

            self.logger.info(f"Completed: {len(grouped_images)} files processed")
            self.logger.info("=== All files processed successfully! ===")

        except Exception as err:
            self.logger.error(f"Processing failed: {err}", exc_info=True)
            # Show error dialog in main thread
            self.root.after(
                0, lambda e=err: messagebox.showerror("Error", f"Processing failed: {e}")
            )

        finally:
            # Re-enable controls in main thread
            self.root.after(0, self._processing_finished)

    def _processing_finished(self):
        """Re-enable controls after processing is finished."""
        for button in self.run_buttons.values():
            button.config(state="normal")

        self.generate_compositions_button.config(state="normal")
        self.progress.stop()

    def _open_settings(self):
        """Open the settings dialog."""
        self.logger.debug("Opening settings dialog")
        settings_dialog_generator = SettingsDialogGenerator(self.config_manager)
        dialog = settings_dialog_generator.create_settings_dialog(self.root)
        self.root.wait_window(dialog.dialog)

        if dialog.result == "ok":
            self.logger.info("Settings updated successfully")
            # Update log level selector if it changed
            self.log_level_var.set(self.config_manager.app.log_level.value)

    def _open_help(self):
        """Open help documentation in browser."""
        self.logger.debug("Opening help documentation")
        webbrowser.open("https://Photo-Composition-Designer.readthedocs.io/en/stable/")

    def _show_about(self):
        """Show about dialog."""
        self.logger.debug("Showing about dialog")
        messagebox.showinfo("About", "Photo-Composition-Designer\n\nCopyright by Paul")

    def _on_closing(self):
        """Handle application closing."""
        self.logger.info("Closing GUI application")
        disconnect_gui_logging()
        self.root.quit()
        self.root.destroy()

    def _generate_template_description_file(self):
        description_file_gen = DescriptionsFileGenerator(
            self.composition_designer.photoDirectory,
            self.composition_designer.outputDir,
        )

        if description_file_gen.description_file_exists():
            # ask user for overwrite permission
            overwrite = messagebox.askyesno(
                "Overwrite?", "A description file already exists. Do you want to overwrite it?"
            )

            if not overwrite:
                return

        description_file = description_file_gen.generate_description_file(overwrite=True)
        self.logger.info(f"Template description file generated: {description_file}")

    def _refresh_preview(self, event=None):
        if not hasattr(self, "preview_image_original"):
            return

        if not self.preview_image_original:
            return

        height = (
            event.height
            if event is not None and hasattr(event, "height")
            else self.preview_label.winfo_height()
        )
        width = (
            event.width
            if event is not None and hasattr(event, "width")
            else self.preview_label.winfo_width()
        )

        margin = 30  # extra padding around the preview
        if width <= margin or height <= margin:
            return

        img = self.preview_image_original.copy()
        img.thumbnail((width - margin, height - margin))
        self.preview_photo = ImageTk.PhotoImage(img)
        self.preview_label.configure(image=self.preview_photo, anchor="center", compound="")


def main():
    """Main entry point for the GUI application."""
    root = tk.Tk()
    try:
        MainGui(root)
        root.mainloop()
    except Exception as e:
        print(f"GUI startup failed: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
