import tkinter as tk
from datetime import datetime
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

from designer.CollageGenerator import CollageGenerator
from designer.common.Config import Config
from designer.tools.FolderGenerator import FolderGenerator


class ConfigEditorApp:
    def __init__(self, root, config=None):
        self.config = config or Config()

        self.root = root
        self.root.title("Config Editor")
        self.config_path = None

        self.entries = {}  # Speichert Eingabefelder
        self.checkbuttons = {}  # Speichert Checkboxen
        self.start_date_vars = {}  # Speichert Tag, Monat, Jahr Drop-downs

        self.create_widgets()

    def create_widgets(self):
        """Erstellt dynamisch die GUI basierend auf der config.ini"""
        frame = ttk.Frame(self.root, padding=10)
        frame.grid(row=0, column=0, sticky="w")

        row = 0
        for config_item in self.config.config_items:
            key = config_item.key
            value = config_item.value
            processedValue = getattr(self.config, key)
            comment = config_item.description

            label = ttk.Label(frame, text=key)
            label.grid(row=row, column=0, sticky="w")

            if comment:
                label.bind("<Enter>", lambda e, text=comment: self.show_tooltip(e, text))
                label.bind("<Leave>", self.hide_tooltip)

            if isinstance(value, bool):  # Boolean als Checkbox
                var = tk.BooleanVar(value=value)
                chk = ttk.Checkbutton(frame, variable=var)
                chk.grid(row=row, column=1, sticky="w")
                self.checkbuttons[key] = var

            elif isinstance(processedValue, datetime):  # StartDate als drei Drop-downs
                day, month, year = processedValue.strftime("%d.%m.%Y").split(".")
                self.start_date_vars[key] = {
                    "day": tk.StringVar(value=day),
                    "month": tk.StringVar(value=month),
                    "year": tk.StringVar(value=year),
                }

                ttk.Combobox(frame, textvariable=self.start_date_vars[key]["day"],
                             values=[str(i) for i in range(1, 32)], width=3).grid(row=row, column=1)
                ttk.Combobox(frame, textvariable=self.start_date_vars[key]["month"],
                             values=[str(i) for i in range(1, 13)], width=3).grid(row=row, column=2)
                ttk.Combobox(frame, textvariable=self.start_date_vars[key]["year"],
                             values=[str(i) for i in range(1900, 2100)], width=5).grid(row=row, column=3)

            elif isinstance(processedValue, Path):  # File-Pfad mit Auswahl-Dialog
                entry_var = tk.StringVar(value=str(value))
                entry = ttk.Entry(frame, textvariable=entry_var, width=30)
                entry.grid(row=row, column=1, sticky="w")
                self.entries[key] = entry_var

                def select_file(var=entry_var):
                    file_path = filedialog.askopenfilename()
                    if file_path:
                        var.set(file_path)

                ttk.Button(frame, text="...", command=select_file).grid(row=row, column=2, pady=5, sticky="w")

            else:  # Standard Textfeld
                if isinstance(processedValue, tuple):
                    value = ",".join(map(str, processedValue))

                entry_var = tk.StringVar(value=str(value))
                entry = ttk.Entry(frame, textvariable=entry_var, width=20)
                entry.grid(row=row, column=1, sticky="w")
                self.entries[key] = entry_var

            row += 1

        # Buttons für Aktionen
        ttk.Button(frame, text="Konfiguration öffnen...", command=self.open_config).grid(row=row, column=0, pady=10)
        ttk.Button(frame, text="Speichern", command=self.save_config).grid(row=row, column=1, pady=10)
        ttk.Button(frame, text="Generator starten", command=self.run_generator).grid(row=row, column=2, pady=10)
        row += 1

        ttk.Button(frame, text="Ordner generieren", command=self.create_folders).grid(row=row, column=0, pady=10)

    def save_config(self):
        """Speichert die aktuellen Einstellungen in die Konfigurationsdatei"""
        for key, entry_var in self.entries.items():
            setattr(self.config, key, entry_var.get())

        for key, var in self.checkbuttons.items():
            setattr(self.config, key, var.get())

        for key, date_vars in self.start_date_vars.items():
            day, month, year = date_vars["day"].get(), date_vars["month"].get(), date_vars["year"].get()
            setattr(self.config, key, f"{day}.{month}.{year}")

        self.config_path = self.config.get_config_path()
        self.config.update_config_items()
        self.config.write_config(self.config_path)
        print(f'Config saved as: {self.config_path}')
        messagebox.showinfo("Erfolg", "Konfiguration gespeichert.")

    def open_config(self):
        """Öffnet einen File-Dialog zur Auswahl einer Konfigurationsdatei"""
        file_path = filedialog.askopenfilename(filetypes=[("INI files", "*.ini")])
        if file_path:
            self.config_path = Path(file_path)
            self.config = Config(self.config_path)
            self.refresh_gui()

    def refresh_gui(self):
        """Aktualisiert die GUI basierend auf einer neuen Config"""
        for section in self.config.config_items:
            key = section.key
            value = getattr(self.config, key)

            if key in self.entries:
                self.entries[key].set(str(value))
            elif key in self.checkbuttons:
                self.checkbuttons[key].set(value)
            elif key in self.start_date_vars:
                day, month, year = value.strftime("%d.%m.%Y").split(".")
                self.start_date_vars[key]["day"].set(day)
                self.start_date_vars[key]["month"].set(month)
                self.start_date_vars[key]["year"].set(year)

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

    @staticmethod
    def create_folders():
        folderGen = FolderGenerator()
        folderGen.generateFolders(56)
        messagebox.showinfo("Erfolg", f"Ordner in '{folderGen.outputDir}' wurden erstellt.")

    @staticmethod
    def run_generator():
        messagebox.showinfo("Info", "Generator wird gestartet!")
        colGen = CollageGenerator()
        colGen.generateProjectFromSubFolders()


if __name__ == "__main__":
    root = tk.Tk()
    app = ConfigEditorApp(root)
    root.mainloop()
