import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from configparser import ConfigParser
from pathlib import Path

from designer.CollageGenerator import CollageGenerator
from designer.common.Config import Config
from designer.tools.FolderGenerator import FolderGenerator


class ConfigEditorApp:
    def __init__(self, root, config=None):
        self.config = config or Config()

        self.root = root
        self.root.title("Config Editor")
        config_path = "../config/config.ini"
        self.config_path = Path(config_path)

        self.entries = {}  # Speichert die Eingabefelder
        self.checkbuttons = {}  # Speichert die Checkboxen
        self.start_date_vars = {}  # Speichert Tag, Monat, Jahr Drop-downs

        self.create_widgets()

    def create_widgets(self):
        """Erstellt dynamisch die GUI basierend auf der config.ini"""
        frame = ttk.Frame(self.root, padding=10)
        frame.grid(row=0, column=0, sticky="w")

        row = 0
        for section in self.config.config_items:
            #ttk.Label(frame, text=section.category, font=("Arial", 12, "bold")).grid(row=row, column=0, sticky="w", pady=5)
            row += 1

            # for key, value in self.config.items(section):
            key = section.key
            value = section.value
            comment = section.description

            label = ttk.Label(frame, text=key)
            label.grid(row=row, column=0, sticky="w")

            # Tooltips für Kommentare
            if comment:
                label.bind("<Enter>", lambda e, text=comment: self.show_tooltip(e, text))
                label.bind("<Leave>", self.hide_tooltip)

            if isinstance(value, bool):  # Boolean als Checkbox
                var = tk.BooleanVar(value=value)
                chk = ttk.Checkbutton(frame, variable=var)
                chk.grid(row=row, column=1, sticky="w")
                self.checkbuttons[(section, key)] = var

            elif key.lower() == "startdate":  # StartDate als drei Drop-downs
                day, month, year = value.split(".")
                self.start_date_vars[(section, key, "day")] = tk.StringVar(value=day)
                self.start_date_vars[(section, key, "month")] = tk.StringVar(value=month)
                self.start_date_vars[(section, key, "year")] = tk.StringVar(value=year)

                ttk.Combobox(frame, textvariable=self.start_date_vars[(section, key, "day")],
                             values=[str(i) for i in range(1, 32)], width=3).grid(row=row, column=1)
                ttk.Combobox(frame, textvariable=self.start_date_vars[(section, key, "month")],
                             values=[str(i) for i in range(1, 13)], width=3).grid(row=row, column=2)
                ttk.Combobox(frame, textvariable=self.start_date_vars[(section, key, "year")],
                             values=[str(i) for i in range(1900, 2100)], width=5).grid(row=row, column=3)

            elif "file" in key.lower():  # File-Pfad mit Auswahl-Dialog
                entry_var = tk.StringVar(value=value)
                entry = ttk.Entry(frame, textvariable=entry_var, width=40)
                entry.grid(row=row, column=1, sticky="w")
                self.entries[(section, key)] = entry_var

                def select_file(var=entry_var):
                    file_path = filedialog.askopenfilename()
                    if file_path:
                        var.set(file_path)

                ttk.Button(frame, text="...", command=select_file).grid(row=row, column=2, sticky="w")

            else:  # Standard Textfeld
                entry_var = tk.StringVar(value=value)
                entry = ttk.Entry(frame, textvariable=entry_var, width=20)
                entry.grid(row=row, column=1, sticky="w")
                self.entries[(section, key)] = entry_var

            row += 1

        # Buttons für Aktionen
        ttk.Button(frame, text="Ordner generieren", command=self.create_folders).grid(row=row, column=0, pady=10)
        ttk.Button(frame, text="Speichern", command=self.save_config).grid(row=row, column=1, pady=10)
        ttk.Button(frame, text="Generator starten", command=self.run_generator).grid(row=row, column=2, pady=10)

    def show_tooltip(self, event, text):
        """Zeigt ein Tooltip mit einem Kommentar an."""
        x, y, _, _ = event.widget.bbox("insert")
        x += event.widget.winfo_rootx() + 25
        y += event.widget.winfo_rooty() + 25

        self.tooltip = tk.Toplevel(self.root)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{x}+{y}")

        label = tk.Label(self.tooltip, text=text, background="yellow", relief="solid", borderwidth=1,
                         font=("Arial", 10))
        label.pack()

    def hide_tooltip(self, event):
        """Blendet das Tooltip aus."""
        if hasattr(self, "tooltip"):
            self.tooltip.destroy()

    def save_config(self):
        """Speichert die aktuellen Einstellungen in die config.ini"""

        self.config.write_config(self.config_path)
        # TODO

        messagebox.showinfo("Erfolg", "Konfiguration gespeichert.")

    @staticmethod
    def create_folders():
        folderGen = FolderGenerator()
        folderGen.generateFolders(56)

        messagebox.showinfo("Erfolg", f"Folders in '{folderGen.outputDir}' were created.")

    @staticmethod
    def run_generator():
        messagebox.showinfo("Info", "Generator has been started!")
        colGen = CollageGenerator()
        colGen.generateProjectFromSubFolders()



if __name__ == "__main__":
    root = tk.Tk()
    app = ConfigEditorApp(root)
    root.mainloop()
