import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk, filedialog, messagebox, colorchooser

from designer.CompositionDesigner import CompositionDesigner
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

        self.create_menu()
        self.create_widgets()
        self.tooltip = None

    def create_menu(self):
        menu_bar = tk.Menu(self.root)
        file_menu = tk.Menu(menu_bar, tearoff=0)
        file_menu.add_command(label="Konfiguration öffnen", command=self.open_config)
        file_menu.add_command(label="Speichern", command=self.save_config)
        file_menu.add_separator()
        file_menu.add_command(label="Beenden", command=self.root.quit)
        menu_bar.add_cascade(label="Datei", menu=file_menu)
        self.root.config(menu=menu_bar)

    def create_widgets(self):
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

            if isinstance(value, bool):  # Bool as Checkbox
                var = tk.BooleanVar(value=value)
                chk = ttk.Checkbutton(frame, variable=var)
                chk.grid(row=row, column=1, sticky="w")
                self.checkbuttons[key] = var

            elif isinstance(processedValue, datetime):  # Date select
                day, month, year = processedValue.strftime("%d.%m.%Y").split(".")
                self.start_date_vars[key] = {
                    "day": tk.StringVar(value=day),
                    "month": tk.StringVar(value=month),
                    "year": tk.StringVar(value=year),
                }
                ttk.Combobox(
                    frame, textvariable=self.start_date_vars[key]["day"], values=[str(i) for i in range(1, 32)], width=3
                ).grid(row=row, column=1)
                ttk.Combobox(
                    frame,
                    textvariable=self.start_date_vars[key]["month"],
                    values=[str(i) for i in range(1, 13)],
                    width=3,
                ).grid(row=row, column=2)
                ttk.Combobox(
                    frame,
                    textvariable=self.start_date_vars[key]["year"],
                    values=[str(i) for i in range(1900, 2100)],
                    width=5,
                ).grid(row=row, column=3)

            elif isinstance(processedValue, Path):  # Datei-Pfad mit Auswahl
                entry_var = tk.StringVar(value=str(value))
                entry = ttk.Entry(frame, textvariable=entry_var, width=30)
                entry.grid(row=row, column=1, sticky="w")
                self.entries[key] = entry_var
                ttk.Button(frame, text="...", command=lambda var=entry_var: self.select_file(var)).grid(
                    row=row, column=2, pady=5, sticky="w"
                )

            elif isinstance(processedValue, tuple):  # Farbauswahl
                entry_var = tk.StringVar(value=",".join(map(str, processedValue)))
                entry = ttk.Entry(frame, textvariable=entry_var, width=20)
                entry.grid(row=row, column=1, sticky="w")
                self.entries[key] = entry_var
                if "color" in str(key).lower():
                    ttk.Button(frame, text="Farbe", command=lambda var=entry_var: self.choose_color(var)).grid(
                        row=row, column=2, pady=5, sticky="w"
                    )
            else:  # Standard Textfeld
                entry_var = tk.StringVar(value=str(value))
                entry = ttk.Entry(frame, textvariable=entry_var, width=20)
                entry.grid(row=row, column=1, sticky="w")
                self.entries[key] = entry_var
            row += 1

        # Buttons
        ttk.Button(frame, text="Generator starten", command=self.run_generator).grid(row=row, column=0, pady=10)
        ttk.Button(frame, text="Ordner generieren", command=self.create_folders).grid(row=row, column=1, pady=10)

    def save_config(self):
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
        print(f"Config saved as: {self.config_path}")
        # messagebox.showinfo("Erfolg", "Konfiguration gespeichert.")

    def open_config(self):
        file_path = filedialog.askopenfilename(filetypes=[("INI files", "*.ini")])
        if file_path:
            self.config_path = Path(file_path)
            self.config = Config(self.config_path)
            self.refresh_gui()

    def refresh_gui_new(self):
        for key, value in self.config.config_items.items():
            if key in self.entries:
                self.entries[key].set(str(getattr(self.config, key)))
            elif key in self.checkbuttons:
                self.checkbuttons[key].set(getattr(self.config, key))

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

    @staticmethod
    def select_file(var):
        file_path = filedialog.askopenfilename()
        if file_path:
            var.set(file_path)

    @staticmethod
    def choose_color(var):
        color = colorchooser.askcolor()[0]
        if color:
            var.set(f"{int(color[0])},{int(color[1])},{int(color[2])}")

    def show_tooltip(self, event, text):
        """Zeigt ein Tooltip mit einem Kommentar an."""
        x, y, _, _ = event.widget.bbox("insert")
        x += event.widget.winfo_rootx() + 25
        y += event.widget.winfo_rooty() + 25

        self.tooltip = tk.Toplevel(self.root)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{x}+{y}")

        label = tk.Label(
            self.tooltip, text=text, background="yellow", relief="solid", borderwidth=1, font=("Arial", 10)
        )
        label.pack()

    def hide_tooltip(self, event):
        """Blendet das Tooltip aus."""
        if hasattr(self, "tooltip"):
            self.tooltip.destroy()

    def create_folders(self):
        config = Config(self.config_path)
        folderGen = FolderGenerator(config)
        folderGen.generateFolders()
        messagebox.showinfo("Erfolg", f"Ordner in '{folderGen.output_dir}' wurden erstellt.")

    def run_generator(self):
        self.save_config()
        config = Config(self.config_path)
        colGen = CompositionDesigner(config)
        colGen.generateProjectFromSubFolders()
        messagebox.showinfo("Info", "Generator ausgeführt!")


if __name__ == "__main__":
    root = tk.Tk()
    app = ConfigEditorApp(root)
    root.mainloop()
