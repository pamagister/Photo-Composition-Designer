import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path

from config_cli_gui.logging import get_logger


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
        self.root.update_idletasks()
