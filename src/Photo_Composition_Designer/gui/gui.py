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

from config_cli_gui.gui import SettingsDialogGenerator

from Photo_Composition_Designer.common.logging import (
    connect_gui_logging,
    disconnect_gui_logging,
    get_logger,
    initialize_logging,
)
from Photo_Composition_Designer.common.Photo import Photo, get_photos_from_dir
from Photo_Composition_Designer.config.config import ConfigParameterManager
from Photo_Composition_Designer.tools.ImageDistributor import ImageDistributor


class GuiLogWriter:
    """Log writer that handles GUI text widget updates in a thread-safe way."""

    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.root = text_widget.winfo_toplevel()
        self.hyperlink_tags = {}  # To store clickable links

    def write(self, text):
        """Write text to the widget in a thread-safe manner."""
        # Schedule the GUI update in the main thread
        self.root.after(0, self._update_text, text)

    def _update_text(self, text):
        """Update the text widget (must be called from main thread)."""
        try:
            current_end = self.text_widget.index(tk.END)
            self.text_widget.insert(tk.END, text)

            # Check for a directory path (simplified regex for common path formats)
            # This regex looks for paths that start with a drive letter (C:\), a forward slash (/)
            # or a backslash (\) followed by word characters, and ends with a word character.
            # This is a basic approach; more robust path detection might be needed for edge cases.
            import re

            path_match = re.search(
                r"([A-Za-z]:[\\/][\S ]*|[\\][\\/][\S ]*|[\w/.-]+[/][\S ]*)\b", text
            )
            if path_match:
                path = path_match.group(0).strip()
                # Ensure the path exists and is a directory to make it clickable
                if Path(path).is_dir():
                    start_index = self.text_widget.search(path, current_end, tk.END)
                    if start_index:
                        end_index = f"{start_index}+{len(path)}c"
                        tag_name = f"link_{len(self.hyperlink_tags)}"
                        self.text_widget.tag_config(tag_name, foreground="blue", underline=True)
                        self.text_widget.tag_bind(
                            tag_name, "<Button-1>", lambda e, p=path: self._open_path_in_explorer(p)
                        )
                        self.text_widget.tag_bind(
                            tag_name, "<Enter>", lambda e: self.text_widget.config(cursor="hand2")
                        )
                        self.text_widget.tag_bind(
                            tag_name, "<Leave>", lambda e: self.text_widget.config(cursor="")
                        )
                        self.text_widget.tag_add(tag_name, start_index, end_index)
                        self.hyperlink_tags[tag_name] = path

            self.text_widget.see(tk.END)
            self.text_widget.update_idletasks()
        except tk.TclError:
            # Widget might be destroyed
            pass

    def _open_path_in_explorer(self, path):
        """Opens the given path in the file explorer."""
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            get_logger("gui.main").error(f"Failed to open path {path}: {e}")

    def flush(self):
        """Flush method for compatibility."""
        pass


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

        # Initialize configuration
        self.config_manager = ConfigParameterManager("config.yaml")

        # Initialize logging system
        self.logger_manager = initialize_logging(self.config_manager)
        self.logger = get_logger("gui.main")

        # File lists
        self.input_files = []
        self.output_files = []

        self._build_widgets()
        self._create_menu()

        # Setup GUI logging after widgets are created
        self._setup_gui_logging()

        # Handle window closing
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

        self.logger.info("GUI application started")
        self.logger_manager.log_config_summary()

    def _build_widgets(self):
        """Build the main GUI widgets."""
        # Main container
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Top frame for file lists and buttons
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=tk.BOTH, expand=True)

        # Left side - Input File list
        input_file_frame = ttk.LabelFrame(top_frame, text="Input Files")
        input_file_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        self.input_file_listbox = tk.Listbox(input_file_frame, selectmode=tk.EXTENDED)
        input_file_scrollbar = ttk.Scrollbar(
            input_file_frame, orient="vertical", command=self.input_file_listbox.yview
        )
        self.input_file_listbox.configure(yscrollcommand=input_file_scrollbar.set)

        self.input_file_listbox.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        input_file_scrollbar.pack(side="right", fill="y", pady=5)
        self.input_file_listbox.bind(
            "<Double-Button-1>", lambda event: self._open_selected_file(event, self.input_files)
        )

        # Middle - Output File list
        output_file_frame = ttk.LabelFrame(top_frame, text="Generated Files")
        output_file_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 5))

        self.output_file_listbox = tk.Listbox(output_file_frame)
        output_file_scrollbar = ttk.Scrollbar(
            output_file_frame, orient="vertical", command=self.output_file_listbox.yview
        )
        self.output_file_listbox.configure(yscrollcommand=output_file_scrollbar.set)

        self.output_file_listbox.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        output_file_scrollbar.pack(side="right", fill="y", pady=5)
        self.output_file_listbox.bind(
            "<Double-Button-1>", lambda event: self._open_selected_file(event, self.output_files)
        )

        # Right side - Buttons
        button_frame = ttk.Frame(top_frame)
        button_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))

        open_button = ttk.Button(
            button_frame, text="Select photos directory", command=self._open_files
        )
        open_button.pack(pady=8, fill=tk.X)

        # Create buttons dynamically
        self.run_buttons = {}
        for mode, label in self.distribution_modes:
            button = ttk.Button(
                button_frame, text=label, command=partial(self._run_processing, mode=mode)
            )
            button.pack(pady=1, fill=tk.X)
            # Save buttons in dictionary for later access
            self.run_buttons[mode] = button

        # Clear files button
        self.clear_input_button = ttk.Button(
            button_frame, text="Generate Preview", command=self._generate_preview
        )
        self.clear_input_button.pack(pady=8, fill=tk.X)

        self.clear_output_button = ttk.Button(
            button_frame, text="Generate Compositions", command=self._generate_compositions
        )
        self.clear_output_button.pack(pady=1, fill=tk.X)

        # Progress bar
        self.progress = ttk.Progressbar(button_frame, mode="indeterminate")
        self.progress.pack(pady=5, fill=tk.X)

        # Bottom frame - Log output
        log_frame = ttk.LabelFrame(main_frame, text="Log Output")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

        # Log text widget with scrollbar
        log_text_frame = ttk.Frame(log_frame)
        log_text_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.log_text = tk.Text(log_text_frame, height=10, wrap=tk.WORD)
        log_text_scrollbar = ttk.Scrollbar(
            log_text_frame, orient="vertical", command=self.log_text.yview
        )
        self.log_text.configure(yscrollcommand=log_text_scrollbar.set)

        self.log_text.pack(side="left", fill="both", expand=True)
        log_text_scrollbar.pack(side="right", fill="y")

        # Log controls
        log_controls = ttk.Frame(log_frame)
        log_controls.pack(fill=tk.X, padx=5, pady=(0, 5))

        ttk.Button(log_controls, text="Clear Log", command=self._clear_log).pack(side=tk.LEFT)

        # Log level selector
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
        file_menu.add_command(label="Open...", command=self._open_files)
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

    def _generate_preview(self):
        """Clear the input file list."""
        self.input_files.clear()
        self.input_file_listbox.delete(0, tk.END)
        self.logger.info("Input file list cleared")

    def _generate_compositions(self):
        """Clear the output file list."""
        self.output_files.clear()
        self.output_file_listbox.delete(0, tk.END)
        self.logger.info("Generated file list cleared")

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

    def _open_files(self):
        """Open file dialog and add files to list."""
        folder = filedialog.askdirectory(
            title="Select folder with photos",
        )

        self.input_files = folder

        if folder > 0:
            self.logger.info(f"Added {folder} new files to processing list")
        else:
            self.logger.debug("No new files selected")

    def _update_output_listbox(self, generated_files_info):
        """Updates the output file listbox with newly generated files."""
        self.output_file_listbox.delete(0, tk.END)  # Clear current list
        self.output_files.clear()  # Clear internal list
        for file_path_str in generated_files_info:
            file_path = Path(file_path_str)
            try:
                file_size_kb = file_path.stat().st_size / 1024
                self.output_files.append({"path": file_path_str, "size": file_size_kb})
                self.output_file_listbox.insert(tk.END, f"{file_path.name} ({file_size_kb:.2f} KB)")
            except Exception as e:
                self.logger.warning(f"Could not get size for generated file {file_path_str}: {e}")
                self.output_files.append({"path": file_path_str, "size": 0})
                self.output_file_listbox.insert(tk.END, f"{file_path.name} (N/A KB)")

        if generated_files_info:
            output_dir = Path(generated_files_info[0]).parent
            self.logger.info(f"Generated files saved in: {output_dir}")  # Log directory

    def _run_processing(self, mode="distribute_group_matching_dates"):
        """Run the processing in a separate thread."""

        self.logger.info(f"Starting distribution of in mode: {mode}")

        # Disable all buttons during processing
        for button in self.run_buttons.values():
            button.config(state="disabled")
        self.clear_input_button.config(state="disabled")
        self.clear_output_button.config(state="disabled")
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
            photo_dir = (
                Path(self.config_manager.general.photoDirectory.value).expanduser().resolve()
            )
            photos: list[Photo] = get_photos_from_dir(photo_dir)

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
            output_dir = photo_dir
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

            # self.root.after(0, self._update_output_listbox, generated_files_paths)

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
        self.clear_input_button.config(state="normal")
        self.clear_output_button.config(state="normal")
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
