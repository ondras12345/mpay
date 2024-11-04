import tkinter as tk
import tkinter.ttk as ttk


class DfGUI(tk.Frame):
    """Generic pandas dataframe display."""

    def __init__(self, parent, df):
        super().__init__(parent)
        self.parent = parent
        self.parent.title("Mpay results")
        self.df = df
        self.create_widgets()

    def create_widgets(self):
        columns: list[str] = list(self.df)
        self.trv = ttk.Treeview(self.parent, show="headings", columns=columns)

        self.vsb = ttk.Scrollbar(self.parent, orient="vertical", command=self.trv.yview)
        self.trv.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.trv.pack(fill=tk.BOTH, side=tk.LEFT, expand=True)

        for col in columns:
            self.trv.column(col, anchor=tk.CENTER)
            self.trv.heading(col, text=col)

        for _, row in self.df.iterrows():
            self.trv.insert("", "end", iid=row.id, values=row.tolist())


def show_df(df):
    root = tk.Tk()
    app = DfGUI(root, df)
    app.mainloop()
