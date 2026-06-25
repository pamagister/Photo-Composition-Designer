"""GUI interface for Photo-Composition-Designer using tkinter with integrated logging.

This module provides a graphical user interface for the Photo-Composition-Designer
with settings dialog, file management, and centralized logging capabilities.

run gui: python -m Photo_Composition_Designer.gui
"""

import copy
import logging
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
from tkinter import filedialog, font, messagebox, ttk

import ttkbootstrap
from config_cli_gui.gui import SettingsDialogGenerator, ToolTip
from config_cli_gui.logging import (
    connect_gui_logging,
    disconnect_gui_logging,
    get_logger,
    initialize_logging,
)
from config_cli_gui.persistence import read_last_used_config
from PIL import Image, ImageTk

from Photo_Composition_Designer.common.Photo import Photo, get_photos_from_dir
from Photo_Composition_Designer.config.config import ConfigParameterManager
from Photo_Composition_Designer.core.base import CompositionDesigner
from Photo_Composition_Designer.gui.GuiLogWriter import GuiLogWriter
from Photo_Composition_Designer.tools.DescriptionsFileGenerator import (
    DescriptionsFileGenerator,
)
from Photo_Composition_Designer.tools.ImageDistributor import ImageDistributor


class MainGui:
    """Main GUI application class."""

    distribution_modes = [
        ("distribute_equally", "Distribute photos equally"),
        ("distribute_randomly", "Distribute photos randomly"),
        ("distribute_group_matching_dates", "Distribute photos by date"),
    ]

    composition_modes = [
        ("render_and_pdf", "Render images & generate PDF"),
        ("render_only", "Render images only"),
        ("pdf_only", "Generate PDF only"),
    ]

    def __init__(self, root, config=None):
        self.root = root
        self.root.title("Photo-Composition-Designer")
        self.root.geometry("1200x800")  # Increased width for new layout
        self.root.update_idletasks()
        self._config_path = None

        # Initialize configuration
        # Prefer the user's last used configuration if present; otherwise
        # load a local default config.yaml without marking it as "last used"
        # (so we don't overwrite the user's actual last-used file).
        try:
            last = read_last_used_config(ConfigParameterManager.get_app_name())
        except Exception:
            last = None

        if last and Path(last).exists():
            self._config = ConfigParameterManager(last)
            self._config_path = last
        elif Path("config.yaml").exists():
            # Load default config but do not persist it as the "last used"
            self._config = ConfigParameterManager("config.yaml", persist_last_used=False)
            self._config_path = "config.yaml"
        else:
            self._config = ConfigParameterManager()
            self._config_path = None

        # Initialize logging system using individual AppConfig values
        self.logger_manager = initialize_logging(
            log_level=self._config.app.log_level.value,
            log_file_max_size=self._config.app.log_file_max_size.value,
            enable_file_logging=self._config.app.enable_file_logging.value,
            enable_console_logging=self._config.app.enable_console_logging.value,
        )
        self.logger: logging.Logger = get_logger("gui.main")
        self.logger.info(f"Anniversaries used: {self._config.general.anniversariesConfig.value}")
        self.logger.info(f"Locations used: {self._config.general.locationsConfig.value}")

        self._build_widgets()
        self._create_menu()
        self._reload_config()
        self._update_window_title_with_config()

        # Setup GUI logging after widgets are created
        self._setup_gui_logging()

        # Handle window closing
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        self.logger.info("GUI application started")

    def _reload_config(self):
        # File lists
        self.composition_designer = CompositionDesigner(self._config, self.logger)
        self.composition_designer.progress_callback = self._progress_update

        self.preview_image_original = None

        self.photo_folders = []
        self.generated_compositions = []

        # Load initial folder list
        self._load_photo_folders()

        self.logger.info(f"Photo directory: {self.composition_designer.photoDir}")
        self.logger_manager.log_config_summary()

        if self.photo_folders:
            self.photo_dir_listbox.selection_set(0)
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
        vertical_paned.add(top_paned, weight=4)

        # -------------------------------------------------------------
        # LEFT SIDE — Photo Folder List
        # -------------------------------------------------------------
        photo_dir_frame = ttk.LabelFrame(top_paned, text="Photo Folders")
        top_paned.add(photo_dir_frame, weight=1)

        self.photo_dir_listbox = tk.Listbox(photo_dir_frame, selectmode=tk.EXTENDED)
        input_file_scrollbar = ttk.Scrollbar(
            photo_dir_frame, orient="vertical", command=self.photo_dir_listbox.yview
        )
        self.photo_dir_listbox.configure(yscrollcommand=input_file_scrollbar.set)

        self.photo_dir_listbox.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        input_file_scrollbar.pack(side="right", fill="y", pady=5)

        self.photo_dir_listbox.bind(
            "<Double-Button-1>",
            lambda event: self._open_selected_file(event, self.photo_folders),
        )
        self.photo_dir_listbox.bind("<<ListboxSelect>>", self._generate_preview_callback)

        # -------------------------------------------------------------
        # CENTER — Preview panel
        # -------------------------------------------------------------
        self.image_frame = ttk.LabelFrame(top_paned, text="Preview")
        top_paned.add(self.image_frame, weight=6)

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

        # RIGHT SIDE — FIXED-WIDTH BUTTON PANEL with Workflow Phases
        button_outer_frame = ttk.Frame(top_paned)
        # Add with weight=0 to keep fixed width
        top_paned.add(button_outer_frame, weight=0)

        # inner frame for padding
        button_frame = ttk.Frame(button_outer_frame)
        button_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # ===== PHASE 1: Configuration =====
        phase1_label = ttk.Label(
            button_frame, text="1 Configuration", font=("TkTextFont", 10, "bold")
        )
        phase1_label.pack(pady=(10, 5), fill=tk.X)

        select_config_button = ttk.Button(
            button_frame, text="Select config file", command=self._select_config
        )
        ToolTip(select_config_button, "Select and load a configuration file (.yaml)")
        select_config_button.pack(pady=2, fill=tk.X)

        ttk.Separator(button_frame, orient=tk.HORIZONTAL).pack(pady=10, fill=tk.X)

        # ===== PHASE 2: Image Distribution =====
        phase2_label = ttk.Label(
            button_frame, text="2 Image Distribution", font=("TkTextFont", 10, "bold")
        )
        phase2_label.pack(pady=(10, 5), fill=tk.X)

        # Distribution mode dropdown
        dist_frame = ttk.Frame(button_frame)
        dist_frame.pack(fill=tk.X, pady=2)

        ttk.Label(dist_frame, text="Method:", width=8).pack(side=tk.LEFT, padx=(0, 5))
        self.distribution_var = tk.StringVar(value="distribute_group_matching_dates")
        # Map IDs to labels for display
        self._dist_mode_map = {mode[0]: mode[1] for mode in self.distribution_modes}
        self.distribution_combo = ttk.Combobox(
            dist_frame,
            textvariable=self.distribution_var,
            values=[self._dist_mode_map[mode[0]] for mode in self.distribution_modes],
            state="readonly",
            width=20,
        )
        self.distribution_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        # Set initial display value
        self.distribution_combo.set(self._dist_mode_map["distribute_group_matching_dates"])

        # Add tooltips for distribution options
        tooltip_text = (
            "by date: Groups photos by their capture date\n"
            "equally: Distributes photos evenly across folders\n"
            "randomly: Distributes photos randomly"
        )
        ToolTip(self.distribution_combo, tooltip_text)

        # Distribution run button
        self.run_distribution_button = ttk.Button(
            button_frame,
            text="Distribute",
            command=self._run_distribution,
        )
        ToolTip(
            self.run_distribution_button,
            "Execute the selected distribution method\nfor all photos in the source directory",
        )
        self.run_distribution_button.pack(pady=5, fill=tk.X)

        ttk.Separator(button_frame, orient=tk.HORIZONTAL).pack(pady=10, fill=tk.X)

        # ===== PHASE 3: Descriptions =====
        phase3_label = ttk.Label(
            button_frame, text="3 Prepare Description File", font=("TkTextFont", 10, "bold")
        )
        phase3_label.pack(pady=(10, 5), fill=tk.X)

        # description file button
        self.generate_description_file_button = ttk.Button(
            button_frame,
            text="Generate Description File",
            command=self._generate_template_description_file,
        )
        ToolTip(
            self.generate_description_file_button,
            "Generate a template description file for all collages\n"
            "based on the generated photo directories",
        )
        self.generate_description_file_button.pack(pady=2, fill=tk.X)

        ttk.Separator(button_frame, orient=tk.HORIZONTAL).pack(pady=10, fill=tk.X)

        # ===== PHASE 4: Composition & Export =====
        phase4_label = ttk.Label(
            button_frame, text="4 Composition & Export", font=("TkTextFont", 10, "bold")
        )
        phase4_label.pack(pady=(10, 5), fill=tk.X)

        # Composition mode dropdown
        comp_frame = ttk.Frame(button_frame)
        comp_frame.pack(fill=tk.X, pady=2)

        ttk.Label(comp_frame, text="Action:", width=8).pack(side=tk.LEFT, padx=(0, 5))
        self.composition_var = tk.StringVar(value="render_and_pdf")
        # Map IDs to labels for display
        self._comp_mode_map = {mode[0]: mode[1] for mode in self.composition_modes}
        self.composition_combo = ttk.Combobox(
            comp_frame,
            textvariable=self.composition_var,
            values=[self._comp_mode_map[mode[0]] for mode in self.composition_modes],
            state="readonly",
            width=20,
        )
        self.composition_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        # Set initial display value
        self.composition_combo.set(self._comp_mode_map["render_and_pdf"])

        # Add tooltips for composition options
        tooltip_text = (
            "Render+PDF: Generate all composition images AND create PDF\n"
            "Render only: Generate composition images without PDF\n"
            "PDF only: Create PDF from existing composition images"
        )
        ToolTip(self.composition_combo, tooltip_text)

        # Composition run button
        self.run_composition_button = ttk.Button(
            button_frame,
            text="Generate",
            command=self._run_generate_compositions,
        )
        ToolTip(
            self.run_composition_button,
            "Execute the selected composition action\n"
            "This may take a while depending on the number of images",
        )
        self.run_composition_button.pack(pady=5, fill=tk.X)

        ttk.Separator(button_frame, orient=tk.HORIZONTAL).pack(pady=10, fill=tk.X)

        # ===== PHASE 4: Preview & Descriptions =====
        phase4_label = ttk.Label(button_frame, text="Preview", font=("TkTextFont", 10, "bold"))
        phase4_label.pack(pady=(10, 5), fill=tk.X)

        self.render_preview_button = ttk.Button(
            button_frame,
            text="Render Current Preview",
            command=self._render_and_save_preview,
        )
        ToolTip(
            self.render_preview_button,
            "Render the currently selected preview\nand save it to the compose output folder",
        )
        self.render_preview_button.pack(pady=2, fill=tk.X)

        ttk.Separator(button_frame, orient=tk.HORIZONTAL).pack(pady=10, fill=tk.X)

        # ===== Progress Bar =====
        self.progress = ttk.Progressbar(button_frame, mode="determinate")
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
        self.log_level_var = tk.StringVar(value=self._config.app.log_level.value)

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
        file_menu.add_command(label="Select config file", command=self._select_config)
        file_menu.add_separator()

        # Create Run menu options dynamically
        for mode, label in self.distribution_modes:
            file_menu.add_command(
                label=label,
                command=partial(self._run_processing_image_distribution, mode=mode),
            )

        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_closing)

        # Options menu
        options_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Options", menu=options_menu)
        options_menu.add_command(label="Settings", command=self._open_settings)
        options_menu.add_command(
            label="Clear object detector cache",
            command=self._clear_object_detector_cache,
        )

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="User help", command=self._open_help)
        help_menu.add_separator()
        help_menu.add_command(label="About", command=self._show_about)

    def _generate_preview_callback(self, event=None):
        selection = self.photo_dir_listbox.curselection()
        if not selection:
            return
        selection_index = selection[0]
        self._generate_preview(selection_index)

    def _generate_preview(self, selection_index):
        if not self.photo_folders:
            self.logger.warning(
                f"No photo folders available in directory {self.composition_designer.photoDir}"
            )
            return
        folder_name = self.photo_folders[selection_index].name

        # Get current dimensions of the preview_label
        w = self.preview_label.winfo_width()
        h = self.preview_label.winfo_height()

        margin = 10  # extra padding around the preview
        target_width = max(1, w - margin)
        target_height = max(1, h - margin)

        # Create a temporary CompositionDesigner instance to get the full unscaled width
        temp_designer = CompositionDesigner(self._config, self.logger)
        full_width_px = temp_designer.width_px
        full_height_px = temp_designer.height_px

        # Calculate the scale factor needed to fit the full composition into the preview area
        preview_scale_factor = max(
            0.1, min(target_width / full_width_px, target_height / full_height_px)
        )

        # Use a deep copy for preview config to avoid modifying the main config
        self._config_preview = copy.deepcopy(self._config)
        self._config_preview.size.dpi.value = self._config.size.dpi.value * preview_scale_factor

        # Create a new CompositionDesigner instance with the calculated scale factor
        preview_designer = CompositionDesigner(
            self._config_preview,
            self.logger,
        )

        preview_image: Image.Image | None = preview_designer.generate_compositions_from_folder(
            folder_name
        )

        if not preview_image:
            self.logger.info(f"Empty folder '{folder_name}'. No preview available.")
            return

        # The image is already scaled by generate_compositions_from_folder
        self.preview_image_original = preview_image
        self.preview_photo = ImageTk.PhotoImage(preview_image)
        self.preview_label.configure(image=self.preview_photo)

        self.logger.info(f"Preview generated for folder {folder_name}")

    def _load_photo_folders(self):
        """Scan self.photo_dir for subfolders and populate the listbox and internal list."""

        # Clear previous content
        self.photo_dir_listbox.delete(0, tk.END)
        self.photo_folders = []

        if (
            not self.composition_designer.photoDir.exists()
            or not self.composition_designer.photoDir.is_dir()
        ):
            self.logger.warning(
                f"Photo directory '{self.composition_designer.photoDir}' does not exist."
            )
            return

        # Collect subfolder names, sorted alphabetically
        subfolders = sorted(
            [item for item in self.composition_designer.photoDir.iterdir() if item.is_dir()],
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
        connect_gui_logging(self.gui_log_writer.write)

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
        """Generate all compositions in a background thread."""
        self.logger.info("Generate all compositions. This may take a while...")

        # Thread starten
        self._start_processing()
        thread = threading.Thread(target=self._run_generation_thread, daemon=True)
        thread.start()

    def _run_generation_thread(self):
        """Threaded backend call."""
        try:
            self.composition_designer.generate_compositions_from_folders()
            self.logger.info("Compositions generated")
        except Exception as e:
            self.logger.error(f"Error while generating compositions: {e}")
        finally:
            # Re-enable controls in main thread
            self.root.after(0, self._processing_finished)

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

    def _select_config(self):
        """Open file dialog to select and load a new config file."""
        config_file = filedialog.askopenfilename(
            title="Select config file",
            filetypes=[("YAML files", "*.yaml"), ("All files", "*.*")],
        )
        if not config_file:
            self.logger.debug("No config file selected.")
            return

        self.logger.info(f"Loading new configuration from: {config_file}")
        try:
            self._config = ConfigParameterManager(config_file)
            self._config_path = config_file
            self._reload_config()
            self._generate_preview(0)
            self._update_window_title_with_config()
        except Exception as e:
            self.logger.error(f"Failed to load config file: {e}", exc_info=True)
            messagebox.showerror("Config Error", f"Failed to load configuration: {e}")

    def _update_window_title_with_config(self):
        """Update window title to show the relative path to the config file."""
        if self._config_path:
            try:
                config_path = Path(self._config_path)
                # Try to get relative path from current working directory
                try:
                    rel_path = config_path.relative_to(Path.cwd())
                except ValueError:
                    # If not relative to cwd, use the absolute path
                    rel_path = config_path
                self.root.title(f"Photo-Composition-Designer - Config: {rel_path}")
            except Exception as e:
                self.logger.debug(f"Could not set title with config path: {e}")
                self.root.title("Photo-Composition-Designer")
        else:
            self.root.title("Photo-Composition-Designer")

    def _run_distribution(self):
        """Run image distribution using the selected mode from dropdown."""
        # Map displayed label back to mode ID
        display_label = self.distribution_var.get()
        mode_id = next(
            (mode[0] for mode in self.distribution_modes if mode[1] == display_label),
            "distribute_group_matching_dates",
        )
        self.logger.info(f"Starting distribution in mode: {mode_id}")
        self._run_processing_image_distribution(mode_id)

    def _render_and_save_preview(self):
        """Render the currently selected preview and save it."""
        selection = self.photo_dir_listbox.curselection()
        if not selection:
            messagebox.showwarning(
                "No Selection", "Please select a photo folder to render its preview."
            )
            return

        selection_index = selection[0]
        if not self.photo_folders:
            messagebox.showwarning("No Folders", "No photo folders available.")
            return

        folder_name = self.photo_folders[selection_index].name

        self.logger.info(f"Rendering and saving preview for folder: {folder_name}")

        self._start_processing()

        # Run in separate thread to avoid blocking GUI
        thread = threading.Thread(
            target=self._render_preview_thread,
            args=(folder_name,),
            daemon=True,
        )
        thread.start()

    def _render_preview_thread(self, folder_name):
        """Threaded backend for rendering and saving preview."""
        try:
            self.logger.info(f"Generating and saving preview for: {folder_name}")

            # Generate the preview image
            preview_designer = CompositionDesigner(self._config, self.logger)
            preview_image = preview_designer.generate_compositions_from_folder(folder_name)

            if not preview_image:
                self.logger.warning(f"Could not generate preview for {folder_name}")
                self.root.after(
                    0,
                    lambda: messagebox.showwarning(
                        "Error", f"Could not generate preview for folder {folder_name}"
                    ),
                )
                return

            # Save the image to the output folder
            output_dir = preview_designer.outputDir
            output_file = output_dir / f"{folder_name}.jpg"
            preview_image.save(output_file, quality=95)
            self.logger.info(f"Preview saved to: {output_file}")

        except Exception as e:
            self.logger.error(f"Error rendering preview: {e}", exc_info=True)
            self.root.after(
                0,
                lambda err=e: messagebox.showerror("Error", f"Preview rendering failed: {err}"),
            )

        finally:
            # Re-enable controls in main thread
            self.root.after(0, self._processing_finished)

    def _run_generate_compositions(self):
        """Run composition generation using the selected mode from dropdown."""
        # Map displayed label back to mode ID
        display_label = self.composition_var.get()
        mode_id = next(
            (mode[0] for mode in self.composition_modes if mode[1] == display_label),
            "render_and_pdf",
        )
        self.logger.info(f"Starting composition generation in mode: {mode_id}")

        self._start_processing()
        thread = threading.Thread(
            target=self._generate_compositions_thread,
            args=(mode_id,),
            daemon=True,
        )
        thread.start()

    def _generate_compositions_thread(self, mode="render_and_pdf"):
        """Threaded backend for composition generation with different modes."""
        try:
            self.logger.info(f"Generate compositions in mode: {mode}")

            if mode == "render_and_pdf":
                # Generate all compositions and PDF (default/original behavior)
                self.composition_designer.generate_compositions_from_folders()
            elif mode == "render_only":
                # Generate compositions without PDF
                # Temporarily disable PDF generation
                original_pdf_setting = self._config.layout.generatePdf.value
                self._config.layout.generatePdf.value = False
                try:
                    self.composition_designer.generate_compositions_from_folders()
                finally:
                    # Restore original setting
                    self._config.layout.generatePdf.value = original_pdf_setting
            elif mode == "pdf_only":
                # Generate PDF from existing composition images
                self.composition_designer.generate_pdf(self.composition_designer.outputDir)
            else:
                self.logger.warning(f"Unknown composition mode: {mode}")

            self.logger.info("Composition generation completed")

        except Exception as e:
            self.logger.error(f"Error generating compositions: {e}", exc_info=True)
            self.root.after(
                0,
                lambda err=e: messagebox.showerror(
                    "Error", f"Composition generation failed: {err}"
                ),
            )

        finally:
            # Re-enable controls in main thread
            self.root.after(0, self._processing_finished)

    def _run_processing_image_distribution(self, mode="distribute_group_matching_dates"):
        """Run the processing in a separate thread."""

        self.logger.info(f"Starting distribution of in mode: {mode}")

        self._start_processing()

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
            photos: list[Photo] = get_photos_from_dir(self.composition_designer.photoDir)
            if not photos:
                self.logger.warning(
                    f"No photos found in directory {self.composition_designer.photoDir}"
                )
                return
            # prepare image distribution
            collages_to_generate = self._config.calendar.collagesToGenerate.value
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

            start_date = self._config.calendar.startDate.value
            output_dir = self.composition_designer.photoDir
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
            self._reload_config()

        except Exception as err:
            self.logger.error(f"Processing failed: {err}", exc_info=True)
            # Show error dialog in main thread
            self.root.after(
                0,
                lambda e=err: messagebox.showerror("Error", f"Processing failed: {e}"),
            )

        finally:
            # Re-enable controls in main thread
            self.root.after(0, self._processing_finished)

    def _start_processing(self):
        """Disable all buttons during processing."""
        self.run_distribution_button.config(state="disabled")
        self.run_composition_button.config(state="disabled")
        self.render_preview_button.config(state="disabled")
        self.generate_description_file_button.config(state="disabled")
        self.distribution_combo.config(state="disabled")
        self.composition_combo.config(state="disabled")

        self.progress.configure(value=0, maximum=100)

    def _processing_finished(self):
        """Re-enable controls after processing is finished."""
        self.run_distribution_button.config(state="normal")
        self.run_composition_button.config(state="normal")
        self.render_preview_button.config(state="normal")
        self.generate_description_file_button.config(state="normal")
        self.distribution_combo.config(state="readonly")
        self.composition_combo.config(state="readonly")

        self.progress.stop()
        self.progress.configure(value=0)

    def _progress_update(self, value, total):
        percent = int((value / total) * 100)
        self.root.after(0, lambda: self.progress.configure(value=percent))

    def _open_settings(self):
        """Open the settings dialog."""
        self.logger.debug("Opening settings dialog")
        settings_dialog_generator = SettingsDialogGenerator(self._config)
        dialog = settings_dialog_generator.create_settings_dialog(self.root)
        self.root.wait_window(dialog.dialog)

        if dialog.result == "ok":
            self.logger.info("Settings updated successfully")
            # Update log level selector if it changed
            self.log_level_var.set(self._config.app.log_level.value)
            self._reload_config()

    def _clear_object_detector_cache(self):
        """Clear the object detector cache if object recognition is enabled."""
        try:
            od = getattr(self.composition_designer, "object_detector", None)
            if od:
                od.clear_cache()
                messagebox.showinfo("Cache cleared", "Object detector cache cleared.")
                self.logger.info("Object detector cache cleared via GUI")
            else:
                messagebox.showinfo(
                    "Not available",
                    "Object detector is not enabled in configuration.",
                )
        except Exception as e:
            self.logger.error(f"Failed to clear object detector cache: {e}", exc_info=True)
            messagebox.showerror("Error", f"Failed to clear cache: {e}")

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
            self.composition_designer.photoDir,
            self.composition_designer.outputDir,
        )

        if description_file_gen.description_file_exists():
            # ask user for overwrite permission
            overwrite = messagebox.askyesno(
                "Overwrite?",
                "A description file already exists. Do you want to overwrite it?",
            )

            if not overwrite:
                return

        description_file = description_file_gen.generate_description_file(overwrite=True)
        self.logger.info(f"Template description file generated: {description_file}")

        # Re-initialize the composition designer to recognize the new file
        self.composition_designer = CompositionDesigner(self._config, self.logger)
        self.composition_designer.progress_callback = self._progress_update

        # Refresh the preview for the currently selected folder
        selection = self.photo_dir_listbox.curselection()
        if selection:
            self._generate_preview(selection[0])

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

        # The image is already scaled, just update the PhotoImage
        self.preview_photo = ImageTk.PhotoImage(self.preview_image_original)
        self.preview_label.configure(image=self.preview_photo, anchor="center", compound="")


def main():
    """Main entry point for the GUI application."""

    # Determine theme from configuration (fall back to sandstone on error)

    # Try to restore the last used configuration file so the GUI can start
    # with the user's preferred theme and settings.
    last = read_last_used_config(ConfigParameterManager.get_app_name())
    if last and Path(last).exists():
        _config = ConfigParameterManager(last)
    else:
        _config = ConfigParameterManager()

    theme_choice = _config.app.theme.value

    root: ttkbootstrap.Window = ttkbootstrap.Window(themename=theme_choice)

    root.tk.call("tk", "scaling", 1.25)

    font.nametofont("TkDefaultFont").configure(size=11)
    font.nametofont("TkTextFont").configure(size=11)
    font.nametofont("TkMenuFont").configure(size=11)
    font.nametofont("TkTextFont").configure(size=11)

    try:
        MainGui(root)
        root.mainloop()
    except Exception as e:
        print(f"GUI startup failed: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
